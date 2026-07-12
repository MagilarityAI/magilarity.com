"""
downloader.py — Завантаження тендеру з Prozorro API

Завантажує повний JSON закупівлі та всі файли тендерної документації.
Детектує зміни до ТД (amendment files), читає Q&A (questions[]).
"""

import logging
import re
import time
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ── Конфігурація ──────────────────────────────────────────────────────────────

BASE_URL = "https://public-api.prozorro.gov.ua/api/2.5"
TIMEOUT = 30
MAX_RETRIES = 5
RETRY_DELAY = 2          # секунд між спробами
CHUNK_SIZE = 8192
MAX_FILENAME_LEN = 200

BASE_DIR = Path(__file__).parent / "закупівлі"

# Ключові слова для визначення файлу "змін до ТД"
AMENDMENT_KEYWORDS = [
    "зміни",
    "зміна тд",
    "зміни до тендерної",
    "amendment",
    "зміна до тендерної",
]
AMENDMENT_DOCUMENT_TYPE = "tendernotice"


# ── Утиліти ───────────────────────────────────────────────────────────────────

def _safe_filename(name: str) -> str:
    """Видаляє заборонені символи та обрізає назву файлу до MAX_FILENAME_LEN."""
    sanitized = re.sub(r'[<>:"/\\|?*]', "", name)
    sanitized = sanitized.strip()
    if len(sanitized) > MAX_FILENAME_LEN:
        # Зберігаємо розширення якщо є
        stem, _, ext = sanitized.rpartition(".")
        if ext and len(ext) <= 10:
            max_stem = MAX_FILENAME_LEN - len(ext) - 1
            sanitized = stem[:max_stem] + "." + ext
        else:
            sanitized = sanitized[:MAX_FILENAME_LEN]
    return sanitized or "document"


def _is_amendment(doc: dict) -> bool:
    """Визначає чи є документ змінами до тендерної документації."""
    title_lower = doc.get("title", "").lower()
    doc_type_lower = doc.get("documentType", "").lower()

    if doc_type_lower == AMENDMENT_DOCUMENT_TYPE:
        return True

    return any(kw in title_lower for kw in AMENDMENT_KEYWORDS)


is_amendment_file = _is_amendment


def _doc_published_date(doc: dict) -> str:
    """
    Дата оприлюднення документа. Prozorro для кожного документа віддає
    'datePublished' (дата першої публікації версії) та 'dateModified'
    (дата останньої зміни цього конкретного запису).
    Для дедлайну оскарження після змін (п.59 абз.5 КМУ 1178) важлива саме
    дата ОПРИЛЮДНЕННЯ змін → пріоритет datePublished, fallback dateModified.
    """
    return doc.get("datePublished") or doc.get("dateModified") or ""


def _group_latest_document_versions(raw_docs: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Групує documents[] Prozorro по document id та лишає тільки ОСТАННЮ версію
    кожного документа (найпізніший dateModified).

    Механіка версій у Prozorro API v2.5 (див. скіл prozorro-api): при заміні
    файлу замовником у documents[] з'являється НОВИЙ запис із тим самим `id`,
    але іншим `url`/`dateModified` — попередні версії залишаються в масиві
    (Prozorro documents є append-only history, не in-place перезаписом).
    Тобто "остання версія" == запис з max(dateModified) для даного id.

    Якщо документ взагалі не має `id` (не повинно траплятись за специфікацією,
    але захищаємось) — трактуємо кожен такий запис як унікальний (без групування).

    Returns:
        (latest_docs, superseded_docs) — латест-версії (у вихідному порядку
        першої появи id) та відкинуті старіші версії (з позначкою superseded_by).
    """
    by_id: dict[str, list[dict]] = {}
    order: list[str] = []
    no_id_docs: list[dict] = []

    for doc in raw_docs:
        doc_id = doc.get("id")
        if not doc_id:
            no_id_docs.append(doc)
            continue
        if doc_id not in by_id:
            by_id[doc_id] = []
            order.append(doc_id)
        by_id[doc_id].append(doc)

    latest_docs: list[dict] = []
    superseded_docs: list[dict] = []

    for doc_id in order:
        versions = by_id[doc_id]
        if len(versions) == 1:
            latest_docs.append(versions[0])
            continue
        # Сортуємо за dateModified (fallback datePublished) — найновіша останньою
        versions_sorted = sorted(
            versions,
            key=lambda d: d.get("dateModified") or d.get("datePublished") or "",
        )
        newest = versions_sorted[-1]
        older = versions_sorted[:-1]
        latest_docs.append(newest)
        for old in older:
            superseded_docs.append(
                {
                    "id": old.get("id", ""),
                    "title": old.get("title", ""),
                    "dateModified": old.get("dateModified") or old.get("datePublished") or "",
                    "superseded_by": newest.get("dateModified") or newest.get("datePublished") or "",
                }
            )
        if len(older) > 0:
            logger.info(
                "Документ id=%s: знайдено %d версій, беремо останню "
                "(dateModified=%s), відкинуто %d старіших",
                doc_id, len(versions), newest.get("dateModified"), len(older),
            )

    # Документи без id — пропускаємо через дедуп за (title, url), бо групувати
    # по id неможливо; regex-дедуп суфіксу _N у base_analyzer лишається другим
    # рубежем захисту від дублів імені файлу.
    latest_docs.extend(no_id_docs)

    return latest_docs, superseded_docs


def _fetch_with_retry(url: str, description: str = "") -> requests.Response:
    """GET-запит з повтором при помилках. Піднімає останній виняток якщо всі спроби вичерпані."""
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "Спроба %d/%d невдала для %s: %s",
                attempt, MAX_RETRIES, description or url, exc,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
    raise last_exc  # type: ignore[misc]


def _download_file(url: str, file_path: Path, description: str = "") -> bool:
    """
    Завантажує файл по URL у file_path з потоковою передачею.
    Повертає True при успіху, False при помилці (після MAX_RETRIES спроб).
    """
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=TIMEOUT, stream=True)
            resp.raise_for_status()
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                    fh.write(chunk)
            logger.debug("Завантажено: %s → %s", description or url, file_path.name)
            return True
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Спроба %d/%d завантаження '%s' невдала: %s",
                attempt, MAX_RETRIES, description or url, exc,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
    logger.error(
        "Не вдалось завантажити '%s' після %d спроб: %s",
        description or url, MAX_RETRIES, last_exc,
    )
    return False


# ── Основна функція ───────────────────────────────────────────────────────────

def download_tender(internal_id: str) -> dict[str, Any]:
    """
    Завантажує повний JSON тендеру та всі файли тендерної документації.

    Args:
        internal_id: Внутрішній UUID закупівлі в Prozorro.

    Returns:
        Словник з результатами завантаження (структура описана в CLAUDE.md).

    Raises:
        requests.RequestException: Якщо не вдалось отримати JSON тендеру.
        ValueError: Якщо відповідь API не містить очікуваних полів.
    """
    # ── 1. Отримуємо JSON тендеру ────────────────────────────────────────────
    logger.info("Завантажую тендер: %s", internal_id)
    url = f"{BASE_URL}/tenders/{internal_id}"
    resp = _fetch_with_retry(url, description=f"тендер {internal_id}")
    payload = resp.json()

    data = payload.get("data")
    if not data:
        raise ValueError(f"API не повернув 'data' для тендера {internal_id}")

    public_id: str = data.get("tenderID", internal_id)
    logger.info("Публічний ID: %s", public_id)

    # ── 2. Створюємо структуру папок ─────────────────────────────────────────
    tender_dir = BASE_DIR / public_id
    docs_dir = tender_dir / "tender_documents"
    tender_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    # ── 3. Зберігаємо повний JSON ─────────────────────────────────────────────
    import json

    json_path = tender_dir / f"{public_id}.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    logger.info("JSON збережено: %s", json_path)

    # ── 4. Обробляємо документи ───────────────────────────────────────────────
    raw_docs: list[dict] = data.get("documents", [])
    logger.info("Знайдено документів у JSON: %d", len(raw_docs))

    # Prozorro documents[] — append-only історія версій: заміна файлу додає
    # НОВИЙ запис з тим самим id, старий запис лишається в масиві. Групуємо
    # по id і завантажуємо ТІЛЬКИ останню версію кожного документа (CRITICAL
    # RULE з CLAUDE.md — аналізувати останню редакцію ТД). Regex-дедуп
    # суфіксу _N імені файлу в base_analyzer._combine_td_texts лишається
    # другим рубежем (для рідкісного випадку документів без id).
    docs_to_download, superseded_documents = _group_latest_document_versions(raw_docs)
    if superseded_documents:
        logger.info(
            "Відкинуто %d застарілих версій документів (замінені новішими)",
            len(superseded_documents),
        )

    downloaded_files: list[dict] = []
    failed_files: list[str] = []
    amendment_files: list[dict] = []

    # Відстежуємо вже використані назви файлів (уникаємо перезапису)
    used_names: set[str] = set()

    for doc in docs_to_download:
        doc_id = doc.get("id", "")
        title = doc.get("title", f"document_{doc_id}")
        url_dl = doc.get("url", "")
        doc_type = doc.get("documentType", "")
        doc_format = doc.get("format", "")
        date_published = _doc_published_date(doc)

        if not url_dl:
            logger.warning("Документ '%s' не має URL, пропускаємо", title)
            failed_files.append(title)
            continue

        is_amend = _is_amendment(doc)

        # Формуємо безпечну назву файлу
        safe_name = _safe_filename(title)

        # Додаємо префікс для amendment файлів
        if is_amend:
            safe_name = "[ЗМІНИ] " + safe_name

        # Вирішуємо конфлікти назв
        final_name = safe_name
        counter = 1
        while final_name in used_names:
            stem, _, ext = safe_name.rpartition(".")
            if ext and len(ext) <= 10:
                final_name = f"{stem}_{counter}.{ext}"
            else:
                final_name = f"{safe_name}_{counter}"
            counter += 1
        used_names.add(final_name)

        file_path = docs_dir / final_name
        success = _download_file(url_dl, file_path, description=title)

        if success:
            file_info = {
                "id": doc_id,
                "title": title,
                "local_path": str(file_path),
                "is_amendment": is_amend,
                "document_type": doc_type,
                "format": doc_format,
                "date_published": date_published,
                # Лот-метадані (К4 аудиту): Prozorro documents[] може мати
                # relatedLot (id лоту) для документів специфічних одному лоту;
                # None/відсутнє = спільний документ закупівлі (типово ТД).
                "related_lot": doc.get("relatedLot"),
            }
            downloaded_files.append(file_info)
            if is_amend:
                amendment_files.append(file_info)
        else:
            failed_files.append(title)

    td_has_amendments = len(amendment_files) > 0

    # ── Дата змін ТД: найпізніша серед усіх файлів змін ────────────────────
    # (кілька файлів змін можливі — кожні наступні зміни публікуються окремим
    # документом; юридично релевантна дата для п.59 абз.5 — дата ОСТАННІХ змін)
    amendments_date: str | None = None
    if amendment_files:
        dated = [f["date_published"] for f in amendment_files if f.get("date_published")]
        if dated:
            amendments_date = max(dated)
        logger.info(
            "Виявлено %d файл(ів) змін до ТД: %s (amendments_date=%s)",
            len(amendment_files),
            [f["title"] for f in amendment_files],
            amendments_date,
        )
        if not amendments_date:
            logger.warning(
                "td_has_amendments=True, але жоден amendment-файл не має "
                "datePublished/dateModified — amendments_date залишається None"
            )

    # ── 5. Обробляємо Q&A ─────────────────────────────────────────────────────
    raw_questions: list[dict] = data.get("questions", [])
    questions: list[dict] = []
    questions_answered = 0

    for q in raw_questions:
        answer = q.get("answer") or ""
        has_answer = bool(answer.strip())
        if has_answer:
            questions_answered += 1

        questions.append(
            {
                "id": q.get("id", ""),
                "title": q.get("title", ""),
                "description": q.get("description", ""),
                "answer": answer,
                "date": q.get("date", ""),
                "date_answered": q.get("dateAnswered", ""),
                "has_answer": has_answer,
            }
        )

    logger.info(
        "Q&A: всього %d, з відповідями %d",
        len(questions), questions_answered,
    )

    # ── 6. Читаємо терміни ────────────────────────────────────────────────────
    tender_period = data.get("tenderPeriod", {})
    enquiry_period = data.get("enquiryPeriod", {})
    submission_deadline: str = tender_period.get("endDate", "")
    enquiry_deadline: str = enquiry_period.get("endDate", "")
    status: str = data.get("status", "")

    # ── 8. Лоти та позиції (К4 аудиту — мультилотові закупівлі) ────────────────
    # Сирі lots[]/items[] з Prozorro без трансформації — розгалуження та побудова
    # lot_context виконується у main.py (одна закупівля = один код ДК, але кожен
    # лот аналізується окремо — CLAUDE.md «Правило щодо лотів — ФІНАЛЬНО»).
    lots: list[dict] = data.get("lots", [])
    items: list[dict] = data.get("items", [])

    # ── 7. Формуємо результат ─────────────────────────────────────────────────
    result: dict[str, Any] = {
        "internal_id": internal_id,
        "public_id": public_id,
        "tender_dir": str(tender_dir),
        "docs_dir": str(docs_dir),
        "json_path": str(json_path),
        "downloaded_files": downloaded_files,
        "failed_files": failed_files,
        "td_has_amendments": td_has_amendments,
        "amendment_files": amendment_files,
        "amendments_date": amendments_date,
        "superseded_documents": superseded_documents,
        "questions": questions,
        "questions_total": len(questions),
        "questions_answered": questions_answered,
        "submission_deadline": submission_deadline,
        "enquiry_deadline": enquiry_deadline,
        "status": status,
        "lots": lots,
        "items": items,
    }

    logger.info(
        "Завантаження завершено: %d файлів, %d помилок, amendments=%s "
        "(amendments_date=%s), superseded_versions=%d",
        len(downloaded_files), len(failed_files), td_has_amendments,
        amendments_date, len(superseded_documents),
    )
    return result
