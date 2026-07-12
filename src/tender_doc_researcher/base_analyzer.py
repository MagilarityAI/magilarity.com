"""
base_analyzer.py — Головний аналізатор тендерної документації (Фаза 5).

Збирає весь контекст (текст ТД, ООПЗ практику, Q&A аналіз, профіль замовника)
та викликає Claude Opus для аналізу за 16 пунктами.

Модель: claude-opus-4-7 з adaptive thinking + streaming
Retry: 3 спроби з exponential backoff
"""

import importlib
import json
import logging
import re
import time
from datetime import datetime

# Пріоритети сортування файлів ТД для LLM (менше число = вище)
_TD_SORT_PRIORITIES: list[tuple[int, list[str]]] = [
    (0, ['тендерна документація', 'умови закупівлі', 'оголошення про закупівлю']),
    (1, ['додаток 10', 'додаток 11', 'документи учасника', 'документи переможця']),
    (2, ['додаток 2', 'проект договору', 'договір підряду', 'договір про закупівлю']),
    (3, ['додаток 3', 'додаток 4', 'додаток 5', 'технічне завдання', 'технічна специфікація']),
    (5, ['зміни до', 'зміна до', 'amendment']),
    # priority 4 = всі інші (за замовчуванням)
]


def _td_sort_key(filename: str) -> tuple:
    """Ключ сортування: (пріоритет, базова назва, номер версії)."""
    name_lower = filename.lower()
    priority = 4
    for p, keywords in _TD_SORT_PRIORITIES:
        if any(kw in name_lower for kw in keywords):
            priority = p
            break
    # Розбиваємо "Додаток 10_2.docx" → base="додаток 10", ver=2
    m = re.match(r'^(.+?)(_(\d+))?(\.\w+)?$', filename)
    base = m.group(1).lower() if m else name_lower
    ver = int(m.group(3)) if m and m.group(3) else 0
    return (priority, base, ver)

from .llm_client import call_llm, get_model
from .prompts.prompt_registry import get_category_prompt, get_base_prompt, detect_donors, get_donor_supplement, get_example_prompt

logger = logging.getLogger(__name__)

# ── Формат виводу для Виклику A (тільки чеклист документів) ──────────────────
_CHECKLIST_OUTPUT_FORMAT = """\
Поверни ТІЛЬКИ валідний JSON без тексту до або після. Без markdown блоків.
Потрібне ОДНЕ поле:

{
  "document_blocks": [
    {
      "block_id": "B01",
      "block_name": "Назва блоку документів",
      "stage": "proposal",
      "items": [
        {
          "num": 1,
          "document": "Назва документа",
          "td_reference": "Розділ X, п. X.X",
          "quote": "дослівна цитата з ТД — повне речення або абзац що вимагає цей документ, не скорочуй",
          "note": "примітка або порожній рядок",
          "is_hidden": false,
          "risk_flag": false
        }
      ]
    }
  ]
}

stage: "proposal" — подання пропозиції, "winner" — дії переможця після перемоги.
is_hidden=true — вимога прихована в тексті ТД (не в явному переліку документів).
risk_flag=true — вимога відхиляється від норм законодавства або є надмірною.
Включи ВСІ документи: і явно перелічені, і приховані в описових текстах ТД.\
"""


# ── Завантаження промптів ─────────────────────────────────────────────────────

def _load_prompt(module_name: str, attr: str, default: str = '') -> str:
    """
    Динамічно завантажує промпт з модуля prompts/{module_name}.py.

    Args:
        module_name: Назва модуля (без шляху), напр. 'base_prompt'.
        attr:        Назва атрибута в модулі, напр. 'BASE_PROMPT'.
        default:     Значення за замовчуванням якщо модуль або атрибут не знайдено.

    Returns:
        Рядок промпту або порожній рядок.
    """
    try:
        mod = importlib.import_module(
            f'agents.implementations.tender_doc_researcher.prompts.{module_name}'
        )
        return getattr(mod, attr, default)
    except (ImportError, AttributeError):
        return default


# ── Форматування Q&A для промпту ─────────────────────────────────────────────

def _format_qa_for_prompt(qa_analysis: dict) -> str:
    """
    Форматує qa_analysis dict для вставки в промпт Opus.

    Args:
        qa_analysis: Результат з qa_analyzer.analyze().

    Returns:
        Відформатований рядок або порожній рядок якщо нічого немає.
    """
    if not qa_analysis or qa_analysis.get('analysis_skipped'):
        return ''

    lines = []

    if qa_analysis.get('td_has_amendments'):
        new_deadline = qa_analysis.get('new_appeal_deadline', '—')
        lines.append(
            f"⚠️ ТД містить зміни. Новий дедлайн оскарження змін: {new_deadline}"
        )
        appealable = qa_analysis.get('appealable_after_amendments') or []
        not_appealable = qa_analysis.get('not_appealable_unchanged') or []
        if appealable:
            lines.append(f"Можна оскаржити (після змін): {', '.join(str(p) for p in appealable)}")
        if not_appealable:
            lines.append(
                f"НЕ можна оскаржити (незмінені положення): {', '.join(str(p) for p in not_appealable)}"
            )

    for c in (qa_analysis.get('key_clarifications') or []):
        topic = c.get('topic', '—')
        answer = c.get('customer_answer_summary', '—')
        lines.append(f"Уточнення [{topic}]: {answer}")

    for q in (qa_analysis.get('unanswered_questions') or []):
        title = q.get('title', '—')
        lines.append(f"⚠️ Питання без відповіді: {title}")

    return '\n'.join(lines)


# ── Об'єднання текстів ТД ────────────────────────────────────────────────────

def _latest_versions(filenames: list[str]) -> list[str]:
    """
    Для кожного унікального документа залишає тільки останню версію (_N з найбільшим N).
    'Додаток 10_1.docx' + 'Додаток 10_2.docx' → залишається 'Додаток 10_2.docx'.
    """
    latest: dict[str, tuple[int, str]] = {}  # base+ext → (ver, original_name)
    for fname in filenames:
        m = re.match(r'^(.+?)(_(\d+))?(\.\w+)$', fname)
        if m:
            base_key = (m.group(1) + (m.group(4) or '')).lower()
            ver = int(m.group(3)) if m.group(3) else 0
        else:
            base_key = fname.lower()
            ver = 0
        if base_key not in latest or ver > latest[base_key][0]:
            latest[base_key] = (ver, fname)
    return [fname for _, fname in latest.values()]


def _combine_td_texts(td_texts: dict) -> str:
    """
    Об'єднує тексти файлів ТД в єдиний рядок.
    Використовує тільки останню версію кожного документа (дедублікація amendment-копій).

    Args:
        td_texts: {filename: {'text': str, 'is_amendment': bool}}

    Returns:
        Конкатенований текст з роздільниками.
    """
    unique = _latest_versions(list(td_texts))
    parts = []
    separator = '\n\n' + '=' * 60 + '\n\n'

    for filename in sorted(unique, key=_td_sort_key):
        info = td_texts[filename]
        text = info.get('text') or ''
        if not text.strip():
            continue
        prefix = "[ЗМІНИ ДО ТД]" if info.get('is_amendment') else "[ДОКУМЕНТ ТД]"
        parts.append(f"{prefix} {filename}\n{text}")

    return separator.join(parts)


# ── Побудова промпту ──────────────────────────────────────────────────────────

def _build_prompt(
    tender_info: dict,
    td_text_combined: str,
    oopz_context: list,
    qa_analysis: dict,
    customer_profile: dict,
    legal_context: str,
    base_prompt: str,
    category_prompt: str,
    donor_supplement: str = '',
    output_format: str = '',
    example_prompt: str = '',
) -> str:
    """
    Збирає повний промпт для Opus з усіх частин.

    Args:
        tender_info:       Словник з класифікатора (public_id, dk_code, category, ...).
        td_text_combined:  Об'єднаний текст файлів ТД.
        oopz_context:      Список рішень ООПЗ з oopz_fetcher.
        qa_analysis:       Результат qa_analyzer.
        customer_profile:  Профіль замовника з customer_profiler.
        legal_context:     Текст правового контексту (ст.16/17/18, КМУ 1178).
        base_prompt:       Базовий промпт (16 пунктів).
        category_prompt:   Категорійний промпт (специфіка ДК).

    Returns:
        Повний рядок промпту.
    """
    # Імпортуємо format_for_prompt тут щоб уникнути кругових залежностей
    from .oopz_fetcher import format_for_prompt
    oopz_text = format_for_prompt(oopz_context)

    parts = []

    # 1. Правовий контекст
    if legal_context:
        parts.append(f"## ЗАКОНОДАВЧА БАЗА\n{legal_context}")

    # 2. Базовий промпт (16 пунктів)
    if base_prompt:
        parts.append(f"## ЗАВДАННЯ АНАЛІЗУ\n{base_prompt}")

    # 3. Специфіка категорії
    if category_prompt:
        parts.append(f"## СПЕЦИФІКА КАТЕГОРІЇ\n{category_prompt}")

    # 4. Еталонний приклад (few-shot) — Голосіїв
    if example_prompt:
        parts.append(f"## ЕТАЛОННИЙ ПРИКЛАД АНАЛІЗУ ТД\n{example_prompt}")

    # 5. Інформація про закупівлю
    expected_value = tender_info.get('expected_value')
    expected_value_str = (
        f"{expected_value:,.2f}".replace(',', ' ')
        if isinstance(expected_value, (int, float))
        else str(expected_value or '—')
    )
    parts.append(
        f"## ІНФОРМАЦІЯ ПРО ЗАКУПІВЛЮ\n"
        f"Публічний ID: {tender_info.get('public_id', '—')}\n"
        f"Внутрішній ID: {tender_info.get('internal_id', '—')}\n"
        f"Код ДК: {tender_info.get('dk_code', '—')}\n"
        f"Категорія: {tender_info.get('category', '—')}\n"
        f"Назва: {tender_info.get('title', '—')}\n"
        f"Замовник: {tender_info.get('customer_name', '—')} "
        f"(ЄДРПОУ: {tender_info.get('customer_edrpou', '—')})\n"
        f"Очікувана вартість: {expected_value_str} грн\n"
        f"Дедлайн подачі: {tender_info.get('submission_deadline', '—')}"
    )

    # 5а. Лот-контекст (К4 аудиту — мультилотові закупівлі, CLAUDE.md
    # «Правило щодо лотів — ФІНАЛЬНО»: кожен лот аналізується ОКРЕМО, бо
    # технічні завдання різні). Присутній лише коли main.py розгалужується
    # по активних лотах; для однолотових закупівель tender_info['lot_context']
    # відсутній і цей блок НЕ додається — промпт ідентичний старому.
    lot_context = tender_info.get('lot_context')
    if lot_context:
        lot_value = lot_context.get('value')
        lot_value_str = (
            f"{lot_value:,.2f}".replace(',', ' ')
            if isinstance(lot_value, (int, float))
            else str(lot_value or '—')
        )
        lot_items_lines = "\n".join(
            f"  - {it.get('description', '—')} "
            f"(кількість: {it.get('quantity', '—')} {it.get('unit', '')}, "
            f"код ДК: {it.get('classification_id', '—')})"
            for it in (lot_context.get('items') or [])
        ) or "  (позиції не визначені окремо для лоту)"
        parts.append(
            f"## ЛОТ {lot_context.get('index', '—')}: {lot_context.get('title', '—')}\n"
            f"Lot ID: {lot_context.get('id', '—')}\n"
            f"Вартість лоту: {lot_value_str} грн\n"
            f"Позиції цього лоту:\n{lot_items_lines}\n\n"
            f"⚠️ АНАЛІЗУЙ ВИМОГИ ТД ЩОДО ЦЬОГО КОНКРЕТНОГО ЛОТУ. Спільні (загальні) "
            f"розділи тендерної документації застосовуй до цього лоту як до всіх "
            f"інших лотів закупівлі. Технічні вимоги, специфічні документи та "
            f"кваліфікаційні критерії аналізуй лише в контексті позицій цього лоту — "
            f"не змішуй з вимогами інших лотів цієї ж закупівлі."
        )

    # 6. Повний текст ТД (без обрізки — Gemini 1M ctx, Claude Opus 200K ctx)
    parts.append(f"## ТЕКСТ ТЕНДЕРНОЇ ДОКУМЕНТАЦІЇ\n{td_text_combined}")

    # 7. Практика ООПЗ
    if oopz_text and oopz_text != "Практика ООПЗ відсутня":
        parts.append(f"## ПРАКТИКА ООПЗ\n{oopz_text}")

    # 8. Q&A та зміни до ТД
    qa_summary = _format_qa_for_prompt(qa_analysis)
    if qa_summary:
        parts.append(f"## Q&A ТА ЗМІНИ ДО ТД\n{qa_summary}")

    # 9. Профіль замовника (тільки якщо є дані)
    oopz_count = customer_profile.get('oopz_decisions_count', 0)
    if oopz_count and oopz_count > 0:
        parts.append(
            f"## ПРОФІЛЬ ЗАМОВНИКА\n"
            f"Рішень ООПЗ проти замовника (ЄДРПОУ {customer_profile.get('edrpou', '—')}): "
            f"{oopz_count}"
        )

    # 10. Донорські програми — після тексту ТД, перед форматом (щоб не губилось в довгому контексті)
    if donor_supplement:
        parts.append(f"## ДОНОРСЬКІ ПРОГРАМИ ТА ВИМОГИ\n{donor_supplement}")

    # 11. Формат виводу JSON (завжди останнім — інструкція для LLM)
    if output_format:
        parts.append(f"## ФОРМАТ ВИВОДУ\n{output_format}")
    else:
        parts.append(
            "## ФОРМАТ ВИВОДУ\n"
            "Поверни ТІЛЬКИ валідний JSON без тексту до або після. "
            "Поля: verdict (recommended|risky|not_recommended), "
            "risk_level (low|medium|high|critical), participate (bool), "
            "short_summary (str), law_violations (list), hidden_requirements (list), "
            "appeal_grounds (list), document_blocks (list), deadlines (dict), "
            "guarantee_requirements (dict)."
        )

    return "\n\n---\n\n".join(parts)


# _call_opus_with_retry видалено — використовується call_llm з llm_client.py


# ── Парсинг JSON з відповіді ──────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """
    Витягує перший JSON-об'єкт з тексту відповіді Opus.

    Алгоритм: знаходить перший { і останній }, парсить.
    Якщо не вдається — повертає порожній dict.

    Args:
        text: Текстова відповідь Opus.

    Returns:
        Розпарсений dict або {}.
    """
    start = text.find('{')
    end = text.rfind('}')

    if start == -1 or end == -1 or end <= start:
        logger.error(
            "base_analyzer: JSON-об'єкт не знайдено у відповіді LLM. "
            "Перші 300 символів: %s",
            text[:300],
        )
        return {}

    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        logger.warning(
            "base_analyzer: JSON невалідний (%s) — спроба auto-repair без нового виклику LLM",
            exc,
        )
        try:
            from json_repair import repair_json
            repaired = repair_json(text[start:end + 1], return_objects=True)
            if isinstance(repaired, dict) and repaired:
                logger.info("base_analyzer: json_repair успішно виправив JSON")
                return repaired
        except Exception as repair_exc:
            logger.error("base_analyzer: json_repair не допоміг: %s", repair_exc)
        return {}


# ── Побудова результату при помилці ──────────────────────────────────────────

def _build_error_result(tender_info: dict, error_msg: str, start_time: float) -> dict:
    """
    Повертає мінімальний словник з позначкою помилки.
    Не пропагує виключення.
    """
    _lot_context = tender_info.get('lot_context') or {}
    return {
        'public_id': tender_info.get('public_id'),
        'internal_id': tender_info.get('internal_id'),
        'dk_code': tender_info.get('dk_code'),
        'category': tender_info.get('category'),
        'customer_name': tender_info.get('customer_name'),
        'customer_edrpou': tender_info.get('customer_edrpou'),
        'expected_value': tender_info.get('expected_value'),
        'submission_deadline': tender_info.get('submission_deadline'),
        'lot_id': _lot_context.get('id'),
        'lot_title': _lot_context.get('title'),
        'lot_value': _lot_context.get('value'),
        'verdict': None,
        'risk_level': None,
        'participate': None,
        'appeal_possible': None,
        'appeal_deadline': None,
        'appeal_deadline_source': None,
        'short_summary': None,
        'law_violations': [],
        'hidden_requirements': [],
        'appeal_grounds': [],
        'document_blocks': [],
        'deadlines': {},
        'guarantee_requirements': {},
        'oopz_context_used': [],
        'qa_analysis': {},
        'customer_profile': {},
        'metadata': {
            'model_analysis': get_model('analysis'),
            'model_classification': get_model('classification'),
            'analysis_duration_sec': round(time.time() - start_time, 2),
            'prompts_loaded': False,
        },
        'analysis_error': error_msg,
    }


# ── Головна функція ───────────────────────────────────────────────────────────

def analyze(
    tender_info: dict,
    td_texts: dict,
    oopz_context: list,
    qa_analysis: dict,
    customer_profile: dict,
) -> dict:
    """
    Головний аналізатор тендерної документації. Фаза 5.

    Збирає весь контекст та викликає Claude Opus для аналізу за 16 пунктами.
    При помилці повертає dict з analysis_error, не пропагує виключення.

    Args:
        tender_info:     Словник з classifier.py:
                           public_id, internal_id, dk_code, category,
                           title, customer_name, customer_edrpou,
                           expected_value, submission_deadline, ...
        td_texts:        Словник з file_extractor:
                           {filename: {'text': str, 'is_amendment': bool}}
        oopz_context:    Список рішень ООПЗ з oopz_fetcher.fetch_oopz_context().
        qa_analysis:     Результат qa_analyzer.analyze().
        customer_profile: Профіль замовника з customer_profiler.get_customer_profile().

    Returns:
        Структурований dict з результатами аналізу (або з analysis_error при помилці).
    """
    start_time = time.time()

    logger.info(
        "base_analyzer: старт аналізу. public_id=%s, category=%s, "
        "td_files=%d, oopz_decisions=%d",
        tender_info.get('public_id'),
        tender_info.get('category'),
        len(td_texts),
        len(oopz_context),
    )

    # ── Завантаження промптів ─────────────────────────────────────────────────
    legal_context = _load_prompt('legal_context', 'LEGAL_CONTEXT')
    base_prompt = get_base_prompt()
    output_format_full = _load_prompt('base_prompt', 'OUTPUT_FORMAT')
    category = tender_info.get('category', 'simple_goods')
    category_prompt = get_category_prompt(category)

    prompts_loaded = bool(legal_context or base_prompt or category_prompt)
    logger.debug(
        "base_analyzer: промпти завантажено: legal_context=%s, base_prompt=%s, "
        "category_prompt=%s",
        bool(legal_context), bool(base_prompt), bool(category_prompt),
    )

    # ── Об'єднання текстів ТД ────────────────────────────────────────────────
    td_text_combined = _combine_td_texts(td_texts)
    donor_ids = detect_donors(td_text_combined)
    if donor_ids:
        logger.info(
            "base_analyzer: виявлено донорське фінансування: %s",
            donor_ids,
        )
    donor_supplement = get_donor_supplement(donor_ids)
    if not td_text_combined.strip():
        logger.warning(
            "base_analyzer: тексти ТД порожні для public_id=%s",
            tender_info.get('public_id'),
        )

    # Спільні аргументи для _build_prompt (однакові для обох викликів)
    _common_kwargs = dict(
        tender_info=tender_info,
        td_text_combined=td_text_combined,
        oopz_context=oopz_context,
        qa_analysis=qa_analysis,
        customer_profile=customer_profile,
        legal_context=legal_context,
        base_prompt=base_prompt,
        category_prompt=category_prompt,
        donor_supplement=donor_supplement,
    )

    model_analysis = get_model('analysis')

    # ── Виклик A: чеклист документів ─────────────────────────────────────────
    try:
        prompt_a = _build_prompt(
            **_common_kwargs,
            output_format=_CHECKLIST_OUTPUT_FORMAT,
            example_prompt=get_example_prompt(fields=['document_blocks']),
        )
    except Exception as exc:
        error_msg = f"Помилка побудови промпту A: {exc}"
        logger.error("base_analyzer: %s", error_msg)
        return _build_error_result(tender_info, error_msg, start_time)

    logger.info(
        "base_analyzer: Виклик A — чеклист (model=%s, розмір=%d символів).",
        model_analysis, len(prompt_a),
    )

    try:
        raw_a = call_llm(prompt_a, role='analysis', max_tokens=30000)
    except Exception as exc:
        error_msg = f"LLM API недоступний (виклик A): {exc}"
        logger.error("base_analyzer: %s", error_msg, exc_info=True)
        return _build_error_result(tender_info, error_msg, start_time)

    if not raw_a:
        error_msg = "LLM повернув порожню відповідь (виклик A)"
        logger.error("base_analyzer: %s", error_msg)
        return _build_error_result(tender_info, error_msg, start_time)

    data_a = _extract_json(raw_a)
    if not data_a:
        logger.warning(
            "base_analyzer: виклик A не дав JSON — document_blocks буде порожній. "
            "Відповідь (перші 300): %s", raw_a[:300],
        )
        data_a = {'document_blocks': []}

    logger.info(
        "base_analyzer: Виклик A завершено. document_blocks=%d блоків.",
        len(data_a.get('document_blocks') or []),
    )

    # ── Виклик B: глибокий аналіз ────────────────────────────────────────────
    output_format_b = (
        (output_format_full or '') +
        '\n\nВАЖЛИВО: поле "document_blocks" залиши як [] — '
        'чеклист документів вже сформований окремим викликом.'
    )

    try:
        prompt_b = _build_prompt(
            **_common_kwargs,
            output_format=output_format_b,
            example_prompt=get_example_prompt(fields=['law_violations', 'hidden_requirements', 'appeal_grounds']),
        )
    except Exception as exc:
        error_msg = f"Помилка побудови промпту B: {exc}"
        logger.error("base_analyzer: %s", error_msg)
        return _build_error_result(tender_info, error_msg, start_time)

    logger.info(
        "base_analyzer: Виклик B — аналіз (model=%s, розмір=%d символів).",
        model_analysis, len(prompt_b),
    )

    try:
        raw_b = call_llm(prompt_b, role='analysis', max_tokens=65000)
    except Exception as exc:
        error_msg = f"LLM API недоступний (виклик B): {exc}"
        logger.error("base_analyzer: %s", error_msg, exc_info=True)
        return _build_error_result(tender_info, error_msg, start_time)

    if not raw_b:
        error_msg = "LLM повернув порожню відповідь (виклик B)"
        logger.error("base_analyzer: %s", error_msg)
        return _build_error_result(tender_info, error_msg, start_time)

    data_b = _extract_json(raw_b)
    if not data_b:
        error_msg = "Не вдалось витягти JSON з відповіді LLM (виклик B)"
        logger.error("base_analyzer: %s. Відповідь (перші 500): %s",
                     error_msg, raw_b[:500])
        return _build_error_result(tender_info, error_msg, start_time)

    # ── Злиття результатів A + B ──────────────────────────────────────────────
    analysis_data = {**data_b, 'document_blocks': data_a.get('document_blocks') or []}

    # ── Розрахунок appeal_deadline ────────────────────────────────────────────
    # КМУ 1178-2022-п:
    #   - є зміни ТД (td_has_amendments) і порахований новий дедлайн (п.59 абз.5,
    #     5 днів з публікації змін, але ≥3 дні до нового дедлайну подання) →
    #     він пріоритетний, бо це дедлайн для ОСТАННЬОЇ хвилі оскарження
    #   - інакше — первинний дедлайн з qa_analyzer (п.59: дедлайн подання − 3 дні)
    #   - якщо qa_analysis порожній/без даних (qa_analyzer впав чи пропущений
    #     крок 7) — fallback: рахуємо первинний дедлайн напряму із
    #     submission_deadline, щоб appeal_deadline НІКОЛИ не губився мовчки
    _qa = qa_analysis or {}
    new_deadline = _qa.get('new_appeal_deadline')
    original_deadline = _qa.get('appeal_deadline_original')

    if _qa.get('td_has_amendments') and new_deadline:
        appeal_deadline = new_deadline
        appeal_deadline_source = 'п.59 абз.5 КМУ 1178 (після змін ТД)'
    elif original_deadline:
        appeal_deadline = original_deadline
        appeal_deadline_source = 'п.59 КМУ 1178 (первинний)'
    else:
        # Fallback: qa_analysis порожній/помилковий — рахуємо напряму,
        # щоб не втратити юридично критичний дедлайн (аудит К3, середнє).
        from .qa_analyzer import calculate_appeal_deadline as _calc_fallback_deadline
        fallback_deadline = _calc_fallback_deadline(tender_info.get('submission_deadline', ''))
        appeal_deadline = fallback_deadline
        appeal_deadline_source = (
            'п.59 КМУ 1178 (первинний, fallback — qa_analysis недоступний)'
            if fallback_deadline else None
        )

    # ── oopz_context_used ─────────────────────────────────────────────────────
    oopz_context_used = [
        d['decision_number']
        for d in oopz_context
        if d.get('decision_number')
    ]

    # ── Збираємо фінальний результат ──────────────────────────────────────────
    duration_sec = round(time.time() - start_time, 2)

    # OUTPUT_FORMAT: verdict/risk_level/participate знаходяться в risk_summary
    risk_summary = analysis_data.get('risk_summary') or {}

    _lot_context = tender_info.get('lot_context') or {}

    result: dict = {
        # Ідентифікаційні поля з tender_info
        'public_id': tender_info.get('public_id'),
        'internal_id': tender_info.get('internal_id'),
        'dk_code': tender_info.get('dk_code'),
        'category': category,
        'customer_name': tender_info.get('customer_name'),
        'customer_edrpou': tender_info.get('customer_edrpou'),
        'expected_value': tender_info.get('expected_value'),
        'submission_deadline': tender_info.get('submission_deadline'),
        # Лот-метадані (К4 аудиту) — присутні лише для мультилотового аналізу,
        # None для однолотових закупівель (сумісність зі старим форматом).
        'lot_id': _lot_context.get('id'),
        'lot_title': _lot_context.get('title'),
        'lot_value': _lot_context.get('value'),

        # Поля з відповіді LLM — verdict/risk в risk_summary, інше на верхньому рівні
        'verdict': risk_summary.get('verdict'),
        'risk_level': risk_summary.get('overall_risk'),  # OUTPUT_FORMAT: overall_risk
        'participate': risk_summary.get('participate'),
        'appeal_possible': bool(analysis_data.get('appeal_grounds')),
        'appeal_deadline': appeal_deadline,
        'appeal_deadline_source': appeal_deadline_source,
        'short_summary': analysis_data.get('short_summary'),
        'law_violations': analysis_data.get('law_violations') or [],
        'hidden_requirements': analysis_data.get('hidden_requirements') or [],
        'appeal_grounds': analysis_data.get('appeal_grounds') or [],
        'document_blocks': analysis_data.get('document_blocks') or [],
        'deadlines': analysis_data.get('deadlines') or {},
        'guarantee_requirements': analysis_data.get('guarantee_requirements') or {},

        # Контекст
        'oopz_context_used': oopz_context_used,
        'donor_ids': donor_ids,
        'qa_analysis': qa_analysis or {},
        'customer_profile': customer_profile or {},

        # Метадані
        'metadata': {
            'model_analysis': get_model('analysis'),
            'model_classification': get_model('classification'),
            'analysis_duration_sec': duration_sec,
            'prompts_loaded': prompts_loaded,
        },
        'analysis_error': None,
    }

    logger.info(
        "base_analyzer: завершено за %.1f сек. "
        "public_id=%s, verdict=%s, risk_level=%s, appeal_grounds=%d",
        duration_sec,
        result['public_id'],
        result['verdict'],
        result['risk_level'],
        len(result['appeal_grounds']),
    )

    return result
