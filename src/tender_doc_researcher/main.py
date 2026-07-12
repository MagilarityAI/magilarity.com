"""
main.py — Оркестратор pipeline tender_doc_researcher.

Приймає internal_id (системний UUID Prozorro), запускає всі модулі по черзі
і повертає готовий структурований результат.

Використання:
    from agents.implementations.tender_doc_researcher import analyze_tender
    result = analyze_tender("abc123-uuid")

CLI:
    python -m agents.implementations.tender_doc_researcher.main <internal_id> [--force]
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import classifier
from . import downloader
from . import file_extractor
from . import registry
from . import oopz_fetcher
from . import customer_profiler
from . import qa_analyzer
from . import base_analyzer
from . import contract_analyzer
from . import report_formatter
from . import handoff_sender
from .log_setup import setup_run_logger, teardown_run_logger, log_run_summary

logger = logging.getLogger(__name__)


def analyze_tender(
    internal_id: str,
    force_reanalyze: bool = False,
) -> dict:
    """
    Головна функція оркестратора. Виконує повний pipeline аналізу ТД.

    Args:
        internal_id:      Системний UUID закупівлі Prozorro (не публічний номер!)
        force_reanalyze:  Якщо True — ігнорувати кеш реєстру, аналізувати повторно

    Returns:
        dict з полями:
            status        — 'completed' | 'cached' | 'error'
            public_id     — публічний номер закупівлі (UA-XXXX-...)
            internal_id   — вхідний UUID
            category      — категорія ДК (building_works, food_products тощо)
            verdict       — recommended | risky | not_recommended
            risk_level    — low | medium | high | critical
            participate   — bool: чи рекомендується участь
            appeal_deadline — дата дедлайну оскарження (str або None)
            short_summary — коротке резюме 2-3 речення
            output_dir    — шлях до папки з результатами
            reports       — dict з іменами файлів: analysis.json, *.docx
            duration_sec  — тривалість в секундах
            errors        — список некритичних помилок (порожній якщо все ОК)
    """
    start_time = time.time()
    run_ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    errors: list[str] = []
    run_handler: Optional[logging.FileHandler] = None

    logger.info("Starting analysis: %s", internal_id)

    # ── Крок 1: Класифікація ────────────────────────────────────────────────────
    # Критичний крок — без public_id не можна продовжувати.
    # Лог-файл відкривається ПІСЛЯ цього кроку (потрібен public_id для назви файлу).
    logger.info("Step 1/11: Classifying tender...")
    try:
        tender_info = classifier.classify(internal_id)
    except Exception as e:
        logger.error("Step 1 FAILED (classifier): %s", e, exc_info=True)
        return {
            'status': 'error',
            'public_id': None,
            'internal_id': internal_id,
            'error': f"Classifier failed: {e}",
            'duration_sec': round(time.time() - start_time, 1),
            'errors': [f"classifier: {e}"],
        }

    public_id = tender_info['public_id']
    run_handler = setup_run_logger(public_id, run_ts)
    logger.info(
        "=== START: %s | internal_id=%s | force=%s ===",
        public_id, internal_id, force_reanalyze,
    )
    logger.info(
        "Classified: dk_code=%s  category=%s  customer=%s",
        tender_info.get('dk_code'),
        tender_info.get('category'),
        tender_info.get('customer_name', '—'),
    )

    # Решта pipeline — у try/finally щоб гарантовано закрити лог-файл
    try:
        result = _run_pipeline(
            internal_id=internal_id,
            public_id=public_id,
            tender_info=tender_info,
            force_reanalyze=force_reanalyze,
            start_time=start_time,
            errors=errors,
        )
        # Записуємо підсумок лише для completed (при error/cached він короткий)
        if result.get('status') == 'completed':
            log_run_summary(
                logger=logger,
                public_id=public_id,
                internal_id=internal_id,
                category=result.get('category', ''),
                verdict=result.get('verdict', ''),
                risk_level=result.get('risk_level', ''),
                duration_sec=result.get('duration_sec', 0),
                errors=result.get('errors', []),
                reports=result.get('reports', {}),
            )
        else:
            logger.info(
                "=== END: %s | status=%s | %.1fs ===",
                public_id, result.get('status'), time.time() - start_time,
            )
        return result

    finally:
        if run_handler is not None:
            teardown_run_logger(run_handler)


def _run_pipeline(
    internal_id: str,
    public_id: str,
    tender_info: dict,
    force_reanalyze: bool,
    start_time: float,
    errors: list[str],
) -> dict:
    """Виконує кроки 2–11 pipeline. Викликається з analyze_tender."""

    # ── Крок 2: Перевірка дублів ─────────────────────────────────────────────────
    if not force_reanalyze:
        logger.info("Step 2/11: Checking registry for duplicates...")
        try:
            cached = registry.is_tender_analyzed(public_id)
            if cached:
                logger.info("Already analyzed: %s — returning cached result", public_id)
                return {
                    'status': 'cached',
                    'public_id': public_id,
                    'internal_id': internal_id,
                    'data': cached,
                    'duration_sec': round(time.time() - start_time, 1),
                    'errors': [],
                }
        except Exception as e:
            logger.warning("Step 2 WARNING (registry check): %s — continuing", e)
            errors.append(f"registry_check: {e}")
    else:
        logger.info("Step 2/11: Skipping registry check (force_reanalyze=True)")

    # ── Крок 3: Завантаження файлів ──────────────────────────────────────────────
    logger.info("Step 3/11: Downloading tender documents...")
    try:
        download_result = downloader.download_tender(internal_id)
        docs_dir = Path(download_result['docs_dir'])
        tender_dir = Path(download_result['tender_dir'])
        logger.info(
            "Downloaded: %d docs to %s",
            download_result.get('docs_count', 0), tender_dir,
        )
    except Exception as e:
        logger.error("Step 3 FAILED (downloader): %s", e, exc_info=True)
        return {
            'status': 'error',
            'public_id': public_id,
            'internal_id': internal_id,
            'error': f"Downloader failed: {e}",
            'duration_sec': round(time.time() - start_time, 1),
            'errors': [f"downloader: {e}"],
        }

    # ── Крок 4: Витяг тексту ─────────────────────────────────────────────────────
    logger.info("Step 4/11: Extracting text from documents...")
    try:
        td_texts = file_extractor.extract_all_documents(docs_dir)
        logger.info("Extracted text from %d documents", len(td_texts))
    except Exception as e:
        logger.error("Step 4 FAILED (file_extractor): %s", e, exc_info=True)
        return {
            'status': 'error',
            'public_id': public_id,
            'internal_id': internal_id,
            'error': f"File extractor failed: {e}",
            'duration_sec': round(time.time() - start_time, 1),
            'errors': [f"file_extractor: {e}"],
        }

    # ── Крок 5: ООПЗ практика ────────────────────────────────────────────────────
    logger.info("Step 5/11: Fetching OOPZ context...")
    try:
        oopz_context = oopz_fetcher.fetch_oopz_context(
            tender_info['category'],
            tender_info['dk_code'],
        )
        logger.info("OOPZ context: %d decisions loaded", len(oopz_context))
    except Exception as e:
        logger.warning("Step 5 WARNING (oopz_fetcher): %s — using empty context", e)
        errors.append(f"oopz_fetcher: {e}")
        oopz_context = []

    # ── Крок 6: Профіль замовника ─────────────────────────────────────────────────
    logger.info("Step 6/11: Building customer profile...")
    try:
        customer_edrpou = tender_info.get('customer_edrpou', '')
        if customer_edrpou:
            customer_profile = customer_profiler.get_customer_profile(customer_edrpou)
            logger.info(
                "Customer profile: edrpou=%s oopz_count=%s",
                customer_edrpou,
                customer_profile.get('oopz_decisions_count', '?'),
            )
        else:
            logger.warning("Step 6: customer_edrpou not provided — skipping customer profile")
            customer_profile = {'edrpou': '', 'implementation_status': 'skipped'}
    except Exception as e:
        logger.warning("Step 6 WARNING (customer_profiler): %s — using default profile", e)
        errors.append(f"customer_profiler: {e}")
        customer_profile = {
            'edrpou': tender_info.get('customer_edrpou', ''),
            'implementation_status': 'error',
        }

    # ── Крок 7: Q&A аналіз ───────────────────────────────────────────────────────
    logger.info("Step 7/11: Analyzing Q&A and amendments...")
    try:
        amendments_text: Optional[str] = None
        amendments_file: Optional[str] = None
        for fname, info in td_texts.items():
            if info.get('is_amendment') and info.get('text'):
                amendments_text = info['text']
                amendments_file = fname
                break

        qa_input = {
            **download_result,
            'amendments_text': amendments_text,
            'amendments_file': amendments_file,
            'amendments_date': download_result.get('amendments_date'),
        }
        qa_analysis = qa_analyzer.analyze(qa_input)
        logger.info(
            "Q&A: has_amendments=%s  questions=%d  unanswered=%d",
            qa_analysis.get('td_has_amendments'),
            qa_analysis.get('questions_total', 0),
            len(qa_analysis.get('unanswered_questions', [])),
        )
        if amendments_file:
            logger.info("Amendments file: %s", amendments_file)
    except Exception as e:
        logger.warning("Step 7 WARNING (qa_analyzer): %s — using empty qa_analysis", e)
        errors.append(f"qa_analyzer: {e}")
        qa_analysis = {
            'td_has_amendments': False,
            'questions_total': 0,
            'questions_answered': 0,
            'key_clarifications': [],
        }

    # ── Кроки 8-12: базовий аналіз → договір → звіти → реєстр → handoff ─────────
    # Мультилотові закупівлі (К4 аудиту, CLAUDE.md «Правило щодо лотів —
    # ФІНАЛЬНО»): кожен лот аналізується ОКРЕМО (ТЗ різні), окремий запис
    # реєстру, окрема підпапка analysis/lot_N/. Однолотові закупівлі (переважний
    # випадок) — потік НЕ ЗМІНЮЄТЬСЯ: та сама analysis/ без підпапок, той самий
    # формат реєстру (виклик _analyze_one_lot нижче з lot_meta=None відтворює
    # СТАРИЙ код 1:1, лише винесений у функцію).
    lots_raw = download_result.get('lots') or []
    items_raw = download_result.get('items') or []
    active_lots = [lot for lot in lots_raw if lot.get('status', 'active') == 'active']
    cancelled_lots = [lot for lot in lots_raw if lot.get('status', 'active') != 'active']

    for lot in cancelled_lots:
        logger.info(
            "Лот %s (%s) статус=%s — пропущено (не активний)",
            lot.get('id'), lot.get('title', '—'), lot.get('status'),
        )

    is_multilot = tender_info.get('has_lots') and len(active_lots) > 1

    # Аналіз договору (contract_analyzer) — ОДИН раз на закупівлю незалежно від
    # кількості лотів (договір зазвичай спільний або по-лотовий буде окремим
    # backlog-завданням — див. звіт субагента). Результат передається в кожен
    # lot-аналіз з позначкою scope='procurement'.
    logger.info("Step 9/11: Analyzing contract (once per procurement)...")
    step9_start = time.time()
    try:
        contract_analysis = contract_analyzer.analyze(
            docs_dir=docs_dir,
            tender_info=tender_info,
            qa_analysis=qa_analysis,
        )
        if contract_analysis:
            contract_analysis['scope'] = 'procurement'
            logger.info(
                "Contract analysis done in %.1fs: balance=%s  risk=%s",
                time.time() - step9_start,
                contract_analysis.get('overall_balance'),
                contract_analysis.get('risk_level'),
            )
        else:
            logger.info("Contract analysis: no contract file found — skipped")
    except Exception as e:
        logger.warning("Step 9 WARNING (contract_analyzer): %s — skipped", e)
        errors.append(f"contract_analyzer: {e}")
        contract_analysis = None

    base_analysis_dir = tender_dir / 'analysis'

    if not is_multilot:
        # ── Однолотова закупівля (або без лотів) — старий потік без змін ───────
        try:
            lot_result = _analyze_one_lot(
                internal_id=internal_id,
                public_id=public_id,
                tender_info=tender_info,
                td_texts=td_texts,
                oopz_context=oopz_context,
                customer_profile=customer_profile,
                qa_analysis=qa_analysis,
                contract_analysis=contract_analysis,
                docs_dir=docs_dir,
                tender_dir=tender_dir,
                output_dir=base_analysis_dir,
                lot_meta=None,
                errors=errors,
            )
        except Exception as e:
            # base_analyzer — критичний крок (як і в старому коді): при падінні
            # pipeline зупиняється з status=error, а не продовжує з порожнім
            # аналізом (поведінка ідентична дореструктуризаційній).
            logger.error("Step 8 FAILED (base_analyzer): %s", e, exc_info=True)
            return {
                'status': 'error',
                'public_id': public_id,
                'internal_id': internal_id,
                'error': f"Base analyzer failed: {e}",
                'duration_sec': round(time.time() - start_time, 1),
                'errors': errors + [f"base_analyzer: {e}"],
            }
        duration = round(time.time() - start_time, 1)
        return {
            'status': 'completed',
            'public_id': public_id,
            'internal_id': internal_id,
            'category': tender_info.get('category'),
            'verdict': lot_result['analysis'].get('verdict'),
            'risk_level': lot_result['analysis'].get('risk_level'),
            'participate': lot_result['analysis'].get('participate'),
            'appeal_deadline': lot_result['analysis'].get('appeal_deadline'),
            'short_summary': lot_result['analysis'].get('short_summary'),
            'output_dir': str(base_analysis_dir),
            'reports': lot_result['files'],
            'duration_sec': duration,
            'errors': errors,
        }

    # ── Мультилотова закупівля — цикл по активних лотах ─────────────────────────
    logger.warning(
        "Мультилотова закупівля: %d активних лотів (%d скасовано) — "
        "буде виконано ПРИБЛИЗНО %d окремих викликів base_analyzer "
        "(бюджет LLM зростає лінійно з кількістю лотів)",
        len(active_lots), len(cancelled_lots), len(active_lots),
    )

    lot_reports_by_lot: dict[str, dict] = {}

    for idx, lot in enumerate(active_lots, start=1):
        lot_id = lot.get('id', '')
        lot_title = lot.get('title', f'Лот {idx}')
        lot_suffix = f'lot{idx}'          # суфікс реєстру: 'UA-...:lot1'
        lot_dirname = f'lot_{idx}'        # підпапка виводу: analysis/lot_1/ (CLAUDE.md)
        logger.info(
            "=== Лот %d/%d: %s (id=%s) ===",
            idx, len(active_lots), lot_title, lot_id,
        )

        lot_context = _build_lot_context(lot, idx, items_raw)
        lot_tender_info = {**tender_info, 'lot_context': lot_context}
        lot_td_texts = _filter_td_texts_for_lot(td_texts, download_result, lot_id)
        lot_output_dir = base_analysis_dir / lot_dirname

        try:
            lot_result = _analyze_one_lot(
                internal_id=internal_id,
                public_id=public_id,
                tender_info=lot_tender_info,
                td_texts=lot_td_texts,
                oopz_context=oopz_context,
                customer_profile=customer_profile,
                qa_analysis=qa_analysis,
                contract_analysis=contract_analysis,
                docs_dir=docs_dir,
                tender_dir=tender_dir,
                output_dir=lot_output_dir,
                lot_meta={'suffix': lot_suffix, 'id': lot_id, 'title': lot_title},
                errors=errors,
            )
            lot_reports_by_lot[lot_suffix] = {
                'lot_id': lot_id,
                'lot_title': lot_title,
                'verdict': lot_result['analysis'].get('verdict'),
                'risk_level': lot_result['analysis'].get('risk_level'),
                'output_dir': str(lot_output_dir),
                'reports': lot_result['files'],
            }
        except Exception as e:
            logger.error("Лот %s FAILED: %s", lot_suffix, e, exc_info=True)
            errors.append(f"lot_{lot_suffix}: {e}")
            lot_reports_by_lot[lot_suffix] = {
                'lot_id': lot_id,
                'lot_title': lot_title,
                'error': str(e),
            }

    duration = round(time.time() - start_time, 1)
    return {
        'status': 'completed',
        'public_id': public_id,
        'internal_id': internal_id,
        'category': tender_info.get('category'),
        'is_multilot': True,
        'lots_total': len(lots_raw),
        'lots_analyzed': len(active_lots),
        'lots_skipped_cancelled': len(cancelled_lots),
        'lots': lot_reports_by_lot,
        'output_dir': str(base_analysis_dir),
        'duration_sec': duration,
        'errors': errors,
    }


def _build_lot_context(lot: dict, index: int, items_raw: list[dict]) -> dict:
    """
    Будує lot_context для промпту base_analyzer з сирого lots[]/items[] Prozorro.

    Args:
        lot:       Один запис з lots[] (id, title, value, status тощо).
        index:     Порядковий номер лоту (для нумерації в промпті/шляхах, з 1).
        items_raw: Повний items[] закупівлі — фільтрується по relatedLot == lot.id.

    Returns:
        dict: id, title, value, index, items (список тільки для цього лоту).
    """
    lot_id = lot.get('id', '')
    lot_items = [it for it in items_raw if it.get('relatedLot') == lot_id]
    return {
        'id': lot_id,
        'title': lot.get('title', f'Лот {index}'),
        'value': (lot.get('value') or {}).get('amount'),
        'index': index,
        'items': [
            {
                'description': it.get('description', ''),
                'quantity': it.get('quantity'),
                'unit': (it.get('unit') or {}).get('name', ''),
                'classification_id': (it.get('classification') or {}).get('id', ''),
            }
            for it in lot_items
        ],
    }


def _filter_td_texts_for_lot(
    td_texts: dict,
    download_result: dict,
    lot_id: str,
) -> dict:
    """
    Фільтрує td_texts для конкретного лоту: документи цього лоту (relatedLot ==
    lot_id) + СПІЛЬНІ документи закупівлі (relatedLot відсутній/None — типово
    основна ТД). Документи ІНШИХ лотів виключаються.

    Args:
        td_texts:        Повний результат file_extractor.extract_all_documents()
                          — {filename: {'text': str, 'is_amendment': bool, ...}}.
        download_result: Результат downloader.download_tender() — містить
                          downloaded_files[] з полем related_lot per файл.
        lot_id:           id лоту з lots[].

    Returns:
        Підмножина td_texts: спільні документи + документи цього лоту.
    """
    downloaded_files = download_result.get('downloaded_files') or []
    # local_path → related_lot (з downloader.py)
    related_lot_by_path: dict[str, object] = {
        Path(f['local_path']).name: f.get('related_lot')
        for f in downloaded_files
        if f.get('local_path')
    }

    filtered = {}
    for fname, info in td_texts.items():
        related_lot = related_lot_by_path.get(fname)
        if related_lot is None or related_lot == lot_id:
            filtered[fname] = info
    return filtered


def _analyze_one_lot(
    internal_id: str,
    public_id: str,
    tender_info: dict,
    td_texts: dict,
    oopz_context: list,
    customer_profile: dict,
    qa_analysis: dict,
    contract_analysis: Optional[dict],
    docs_dir: Path,
    tender_dir: Path,
    output_dir: Path,
    lot_meta: Optional[dict],
    errors: list[str],
) -> dict:
    """
    Виконує кроки 8, 10, 11, 12 pipeline (базовий аналіз → звіти → реєстр →
    handoff) для ОДНІЄЇ закупівлі АБО одного лоту мультилотової закупівлі.

    Крок 9 (contract_analyzer) виконується у виклика ОДИН раз на закупівлю —
    сюди передається вже готовий contract_analysis.

    Args:
        tender_info: Для однолотової закупівлі — оригінальний tender_info.
                     Для лоту — tender_info + ключ 'lot_context' (див.
                     _build_lot_context) що інжектиться у промпт base_analyzer.
        td_texts:    Для лоту — вже відфільтровані _filter_td_texts_for_lot.
        output_dir:  analysis/ (однолотова) або analysis/lot_N/ (лот).
        lot_meta:    None для однолотової закупівлі; {'suffix','id','title'}
                     для лоту — використовується для реєстру.

    Returns:
        {'analysis': dict, 'files': dict} — результат base_analyzer.analyze()
        та шляхи до згенерованих звітів.

    Raises:
        Exception: якщо base_analyzer.analyze() падає критично — пропагується
                   до виклика (для лота — щоб інші лоти могли продовжити;
                   для однолотової — щоб _run_pipeline повернув status=error
                   як раніше, обробка на рівні виклика).
    """
    label = f"лот {lot_meta['suffix']}" if lot_meta else "закупівля"

    # ── Крок 8: Базовий аналіз (Opus) ────────────────────────────────────────────
    logger.info("Step 8/11: Running base analysis (Opus) [%s]...", label)
    step8_start = time.time()
    analysis = base_analyzer.analyze(
        tender_info=tender_info,
        td_texts=td_texts,
        oopz_context=oopz_context,
        qa_analysis=qa_analysis,
        customer_profile=customer_profile,
    )
    logger.info(
        "Base analysis done in %.1fs [%s]: verdict=%s  risk=%s  donors=%s",
        time.time() - step8_start, label,
        analysis.get('verdict'),
        analysis.get('risk_level'),
        analysis.get('donor_ids', []),
    )

    # contract_analysis прикріплюється до кожного lot-аналізу (scope='procurement')
    lot_contract_analysis = contract_analysis

    # ── Крок 10: Форматування звітів ─────────────────────────────────────────────
    logger.info("Step 10/11: Generating reports [%s]...", label)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        format_result = report_formatter.format_reports(
            analysis=analysis,
            contract_analysis=lot_contract_analysis,
            output_dir=output_dir,
        )
        _skip = {'success', 'errors'}
        _files = {k: str(v) for k, v in format_result.items() if k not in _skip and v is not None}
        format_result['files'] = _files
        logger.info("Reports generated [%s]: %s", label, list(_files.keys()))
        if format_result.get('errors'):
            for fmt_err in format_result['errors']:
                logger.warning("Report formatter warning [%s]: %s", label, fmt_err)
            errors.extend(format_result['errors'])
    except Exception as e:
        logger.error("Step 10 FAILED (report_formatter) [%s]: %s", label, e, exc_info=True)
        errors.append(f"report_formatter[{label}]: {e}")
        format_result = {'files': {}, 'errors': [str(e)]}

    # ── Крок 11: Збереження в реєстр ─────────────────────────────────────────────
    logger.info("Step 11/12: Registering result [%s]...", label)
    try:
        registry.register_tender(
            public_id=public_id,
            internal_id=internal_id,
            customer=tender_info.get('customer_name', ''),
            dk_code=tender_info.get('dk_code', ''),
            subject=tender_info.get('title', ''),
            expected_value=tender_info.get('expected_value', 0.0),
            category=tender_info.get('category', ''),
            folder_path=str(output_dir.parent if lot_meta else tender_dir),
            verdict=analysis.get('verdict', ''),
            short_summary=analysis.get('short_summary', ''),
            lot_suffix=lot_meta['suffix'] if lot_meta else None,
            lot_id=lot_meta['id'] if lot_meta else None,
            lot_title=lot_meta['title'] if lot_meta else None,
        )
        logger.info("Registered [%s]: %s", label, public_id)
    except Exception as e:
        logger.warning("Step 11 WARNING (registry) [%s]: %s — result not saved to registry", label, e)
        errors.append(f"registry_register[{label}]: {e}")

    # ── Крок 12: Handoff до bid_researcher ───────────────────────────────────────
    # ПРИМІТКА (backlog): handoff_sender.py наразі НЕ лот-обізнаний (файл
    # заблокований паралельним субагентом) — надсилає той самий cpv_code для
    # кожного лоту без розрізнення lot_id. Для однолотових закупівель це не
    # проблема (поведінка ідентична старій). Справжній лот-обізнаний handoff —
    # окреме завдання, див. звіт.
    logger.info("Step 12/12: Sending handoff to bid_researcher [%s]...", label)
    try:
        handoff_id = handoff_sender.send_handoff(
            internal_id=internal_id,
            public_id=public_id,
            analysis=analysis,
            td_documents_path=str(docs_dir),
            cpv_code=tender_info.get('dk_code', ''),
        )
        if handoff_id:
            logger.info("Handoff sent [%s]: handoff_id=%s, td_path=%s", label, handoff_id, docs_dir)
        else:
            logger.warning("Handoff creation failed [%s] — bid_researcher не матиме чеклиста", label)
            errors.append(f"handoff_sender[{label}]: failed to create handoff")
    except Exception as e:
        logger.warning("Step 12 WARNING (handoff_sender) [%s]: %s", label, e)
        errors.append(f"handoff_sender[{label}]: {e}")

    return {'analysis': analysis, 'files': format_result.get('files', {})}


if __name__ == '__main__':
    import json
    import sys
    from dotenv import load_dotenv

    load_dotenv()

    if len(sys.argv) < 2:
        print("Usage: python main.py <internal_id> [--force]")
        sys.exit(1)

    internal_id_arg = sys.argv[1]
    force = '--force' in sys.argv

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )

    result = analyze_tender(internal_id_arg, force_reanalyze=force)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
