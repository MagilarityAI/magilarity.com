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
            'amendments_date': None,
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

    # ── Крок 8: Базовий аналіз (Opus) ────────────────────────────────────────────
    logger.info("Step 8/11: Running base analysis (Opus)...")
    step8_start = time.time()
    try:
        analysis = base_analyzer.analyze(
            tender_info=tender_info,
            td_texts=td_texts,
            oopz_context=oopz_context,
            qa_analysis=qa_analysis,
            customer_profile=customer_profile,
        )
        logger.info(
            "Base analysis done in %.1fs: verdict=%s  risk=%s  donors=%s",
            time.time() - step8_start,
            analysis.get('verdict'),
            analysis.get('risk_level'),
            analysis.get('donor_ids', []),
        )
    except Exception as e:
        logger.error("Step 8 FAILED (base_analyzer): %s", e, exc_info=True)
        return {
            'status': 'error',
            'public_id': public_id,
            'internal_id': internal_id,
            'error': f"Base analyzer failed: {e}",
            'duration_sec': round(time.time() - start_time, 1),
            'errors': errors + [f"base_analyzer: {e}"],
        }

    # ── Крок 9: Аналіз договору (Opus) ───────────────────────────────────────────
    logger.info("Step 9/11: Analyzing contract...")
    step9_start = time.time()
    try:
        contract_analysis = contract_analyzer.analyze(
            docs_dir=docs_dir,
            tender_info=tender_info,
            qa_analysis=qa_analysis,
        )
        if contract_analysis:
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

    # ── Крок 10: Форматування звітів ─────────────────────────────────────────────
    logger.info("Step 10/11: Generating reports...")
    output_dir = tender_dir / 'analysis'
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        format_result = report_formatter.format_reports(
            analysis=analysis,
            contract_analysis=contract_analysis,
            output_dir=output_dir,
        )
        # format_reports повертає ключі: analysis_json, analysis_report, тощо
        _skip = {'success', 'errors'}
        _files = {k: str(v) for k, v in format_result.items() if k not in _skip and v is not None}
        format_result['files'] = _files
        logger.info("Reports generated: %s", list(_files.keys()))
        if format_result.get('errors'):
            for fmt_err in format_result['errors']:
                logger.warning("Report formatter warning: %s", fmt_err)
            errors.extend(format_result['errors'])
    except Exception as e:
        logger.error("Step 10 FAILED (report_formatter): %s", e, exc_info=True)
        errors.append(f"report_formatter: {e}")
        format_result = {'files': {}, 'errors': [str(e)]}

    # ── Крок 11: Збереження в реєстр ─────────────────────────────────────────────
    logger.info("Step 11/12: Registering result...")
    try:
        registry.register_tender(
            public_id=public_id,
            internal_id=internal_id,
            customer=tender_info.get('customer_name', ''),
            dk_code=tender_info.get('dk_code', ''),
            subject=tender_info.get('title', ''),
            expected_value=tender_info.get('expected_value', 0.0),
            category=tender_info.get('category', ''),
            folder_path=str(tender_dir),
            verdict=analysis.get('verdict', ''),
            short_summary=analysis.get('short_summary', ''),
        )
        logger.info("Registered: %s", public_id)
    except Exception as e:
        logger.warning("Step 11 WARNING (registry): %s — result not saved to registry", e)
        errors.append(f"registry_register: {e}")

    # ── Крок 12: Handoff до bid_researcher ───────────────────────────────────────
    logger.info("Step 12/12: Sending handoff to bid_researcher...")
    try:
        handoff_id = handoff_sender.send_handoff(
            internal_id=internal_id,
            public_id=public_id,
            analysis=analysis,
            td_documents_path=str(docs_dir),
            cpv_code=tender_info.get('dk_code', ''),
        )
        if handoff_id:
            logger.info("Handoff sent: handoff_id=%s, td_path=%s", handoff_id, docs_dir)
        else:
            logger.warning("Handoff creation failed — bid_researcher не матиме чеклиста")
            errors.append("handoff_sender: failed to create handoff")
    except Exception as e:
        logger.warning("Step 12 WARNING (handoff_sender): %s", e)
        errors.append(f"handoff_sender: {e}")

    # ── Результат ─────────────────────────────────────────────────────────────────
    duration = round(time.time() - start_time, 1)

    return {
        'status': 'completed',
        'public_id': public_id,
        'internal_id': internal_id,
        'category': tender_info.get('category'),
        'verdict': analysis.get('verdict'),
        'risk_level': analysis.get('risk_level'),
        'participate': analysis.get('participate'),
        'appeal_deadline': analysis.get('appeal_deadline'),
        'short_summary': analysis.get('short_summary'),
        'output_dir': str(output_dir),
        'reports': format_result.get('files', {}),
        'duration_sec': duration,
        'errors': errors,
    }


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
