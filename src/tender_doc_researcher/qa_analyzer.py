"""
qa_analyzer.py — Аналіз питань-відповідей та змін до тендерної документації

Читає questions[] з JSON Prozorro + текст файлу змін до ТД (якщо є).
Виявляє ключові уточнення, нові дедлайни оскарження, які пункти
можна/не можна оскаржити після змін.

Правова база: КМУ 1178-2022-п п.59-60 (воєнний стан, пріоритет над ЗУ 922-VIII)
"""

import json
import logging
import os
from datetime import datetime, timedelta

from .llm_client import call_llm

logger = logging.getLogger(__name__)



# ── Розрахунок дедлайнів ──────────────────────────────────────────────────────

def calculate_appeal_deadline(submission_deadline: str) -> str | None:
    """
    Розраховує первинний дедлайн оскарження умов ТД.

    КМУ 1178-2022-п п.59: не пізніше ніж за 3 дні до кінцевого строку
    подання пропозицій (воєнний стан, пріоритет над ЗУ 922 ст.18 ч.8 — 4 дні).

    Повертає дату у форматі 'YYYY-MM-DD' або None при помилці парсингу.
    """
    if not submission_deadline:
        return None
    try:
        dt = datetime.fromisoformat(submission_deadline.replace('Z', '+00:00'))
        deadline = dt - timedelta(days=3)
        return deadline.date().isoformat()
    except (ValueError, TypeError) as exc:
        logger.warning(
            "Не вдалось розрахувати дедлайн оскарження з '%s': %s",
            submission_deadline, exc,
        )
        return None


def calculate_amendments_deadline(
    amendments_date: str,
    new_submission_deadline: str,
) -> str | None:
    """
    Розраховує новий дедлайн оскарження після внесення змін до ТД.

    КМУ 1178-2022-п п.59 абз.5:
      5 днів з дати оприлюднення змін,
      але не пізніше ніж за 3 дні до нового дедлайну подання пропозицій.

    Повертає дату у форматі 'YYYY-MM-DD' або None при помилці парсингу.
    """
    try:
        amend_dt = datetime.fromisoformat(amendments_date.replace('Z', '+00:00'))
        five_days_later = (amend_dt + timedelta(days=5)).date()

        sub_dt = datetime.fromisoformat(new_submission_deadline.replace('Z', '+00:00'))
        three_before_sub = (sub_dt - timedelta(days=3)).date()

        return min(five_days_later, three_before_sub).isoformat()
    except (ValueError, TypeError) as exc:
        logger.warning(
            "Не вдалось розрахувати дедлайн після змін (amendments_date='%s', "
            "new_submission_deadline='%s'): %s",
            amendments_date, new_submission_deadline, exc,
        )
        return None


# ── Форматування Q&A для промпту ──────────────────────────────────────────────

def _format_questions(questions: list) -> str:
    """Форматує список питань для вставки в промпт LLM."""
    if not questions:
        return "Питань немає"

    parts = []
    for q in questions:
        status = "ВІДПОВІДЬ Є" if q.get('has_answer') else "БЕЗ ВІДПОВІДІ ⚠️"
        parts.append(
            f"[{q.get('id', '?')}] {q.get('title', '(без назви)')} ({status})\n"
            f"  Питання: {(q.get('description') or '—')[:500]}\n"
            f"  Відповідь: {(q.get('answer') or '—')[:500]}"
        )
    return '\n\n'.join(parts)


# ── Виклик LLM ────────────────────────────────────────────────────────────────

def _call_sonnet(tender_info: dict) -> dict:
    """
    Формує промпт та викликає Sonnet для аналізу Q&A і змін до ТД.

    Повертає розпарсений JSON-словник з відповіді моделі.
    При будь-якій помилці API або парсингу повертає порожній dict.
    """
    questions = tender_info.get('questions') or []
    amendments_text = tender_info.get('amendments_text') or 'відсутній'
    submission_deadline = tender_info.get('submission_deadline', '')
    td_has_amendments = tender_info.get('td_has_amendments', False)
    questions_total = tender_info.get('questions_total', len(questions))
    questions_answered = tender_info.get('questions_answered', 0)

    formatted_questions = _format_questions(questions)

    prompt = (
        f"Проаналізуй питання-відповіді тендерної документації та/або зміни до ТД.\n\n"
        f"ДЕДЛАЙН ПОДАЧІ ПРОПОЗИЦІЙ: {submission_deadline}\n"
        f"ЧИ ВНОСИЛИСЬ ЗМІНИ ДО ТД: {td_has_amendments}\n\n"
        f"ПИТАННЯ-ВІДПОВІДІ ({questions_total} питань, {questions_answered} відповідей):\n"
        f"{formatted_questions}\n\n"
        f"ТЕКСТ ЗМІН ДО ТД (якщо є):\n"
        f"{amendments_text}\n\n"
        "Визнач:\n"
        "1. Ключові уточнення що змінюють вимоги ТД "
        "(навіть якщо зміни не вносились офіційно)\n"
        "2. Питання без відповіді що можуть бути проблемою для учасника\n"
        "3. Якщо є зміни до ТД — які положення змінились, а які залишились без змін\n"
        "4. Чи є питання про спірні вимоги (ISO, БГ, аналогічний договір тощо)\n\n"
        "Відповідь у форматі JSON:\n"
        '{\n'
        '  "key_clarifications": [\n'
        '    {"question_id": "...", "topic": "...", "customer_answer_summary": "...", '
        '"changes_requirement": bool, "note": "..."}\n'
        '  ],\n'
        '  "unanswered_important": [\n'
        '    {"question_id": "...", "title": "...", "description": "..."}\n'
        '  ],\n'
        '  "changed_provisions": ["опис зміненого пункту 1", ...],\n'
        '  "unchanged_provisions": ["опис незміненого пункту 1", ...],\n'
        '  "has_meaningful_qa": bool\n'
        '}'
    )

    try:
        raw_text = call_llm(prompt, role='classification', max_tokens=8000)
    except Exception as exc:
        logger.error("qa_analyzer: LLM API помилка: %s", exc)
        return {}

    if not raw_text:
        logger.warning("qa_analyzer: LLM повернув порожню відповідь")
        return {}

    try:
        start = raw_text.find('{')
        end = raw_text.rfind('}')
        if start == -1 or end == -1 or end <= start:
            logger.warning(
                "qa_analyzer: не знайдено JSON у відповіді LLM. Перші 200: %s",
                raw_text[:200],
            )
            return {}
        return json.loads(raw_text[start:end + 1])
    except json.JSONDecodeError as exc:
        logger.warning("qa_analyzer: не вдалось розпарсити JSON: %s", exc)
        return {}


# ── Основна функція ───────────────────────────────────────────────────────────

def analyze(tender_info: dict) -> dict:
    """
    Аналізує питання-відповіді та зміни до тендерної документації.

    Вхідний параметр tender_info — dict зі структурою:
        questions           list[dict]  — питання учасників і відповіді замовника
        questions_total     int
        questions_answered  int
        submission_deadline str         — ISO datetime дедлайну подачі пропозицій
        td_has_amendments   bool
        amendments_text     str|None    — текст файлу змін до ТД
        amendments_file     str|None    — назва файлу змін
        amendments_date     str|None    — дата публікації змін (ISO)

    Повертає dict qa_analysis для включення в analysis.json.
    """
    questions: list = tender_info.get('questions') or []
    td_has_amendments: bool = bool(tender_info.get('td_has_amendments'))
    amendments_text: str | None = tender_info.get('amendments_text')
    amendments_file: str | None = tender_info.get('amendments_file')
    amendments_date: str | None = tender_info.get('amendments_date')
    submission_deadline: str = tender_info.get('submission_deadline', '')
    questions_total: int = tender_info.get('questions_total', len(questions))
    questions_answered: int = tender_info.get('questions_answered', 0)

    # Базова структура результату з дефолтними значеннями
    result: dict = {
        'td_has_amendments': td_has_amendments,
        'amendments_file': amendments_file,
        'amendments_date': amendments_date,
        'appeal_deadline_original': None,
        'new_appeal_deadline': None,
        'appealable_after_amendments': [],
        'not_appealable_unchanged': [],
        'questions_total': questions_total,
        'questions_answered': questions_answered,
        'key_clarifications': [],
        'unanswered_questions': [],
        'has_meaningful_qa': False,
        'analysis_skipped': False,
    }

    # ── Розрахунок первинного дедлайну оскарження ──────────────────────────
    if submission_deadline:
        result['appeal_deadline_original'] = calculate_appeal_deadline(
            submission_deadline
        )
    else:
        logger.warning("qa_analyzer: submission_deadline не передано, дедлайн не розраховано")

    # ── Розрахунок нового дедлайну (якщо є зміни до ТД) ───────────────────
    if td_has_amendments and amendments_date and submission_deadline:
        result['new_appeal_deadline'] = calculate_amendments_deadline(
            amendments_date, submission_deadline
        )

    # ── Перевірка: чи є що аналізувати ────────────────────────────────────
    has_questions = bool(questions)
    has_amendments_text = bool(amendments_text and amendments_text.strip())

    if not has_questions and not has_amendments_text:
        logger.info(
            "qa_analyzer: Q&A порожній та текст змін відсутній — аналіз пропущено"
        )
        result['analysis_skipped'] = True
        return result

    # ── Виклик LLM ────────────────────────────────────────────────────────
    logger.info(
        "qa_analyzer: запит до Sonnet (питань=%d, є_зміни=%s)",
        len(questions), td_has_amendments,
    )

    try:
        llm_data = _call_sonnet(tender_info)
    except Exception as exc:
        # Непередбачена помилка — повертаємо безпечний результат
        logger.error("qa_analyzer: непередбачена помилка при виклику LLM: %s", exc)
        result['analysis_skipped'] = True
        return result

    if not llm_data:
        # LLM не відповів або відповідь не розпарсена
        result['analysis_skipped'] = True
        return result

    # ── Формуємо key_clarifications ───────────────────────────────────────
    raw_clarifications = llm_data.get('key_clarifications') or []
    key_clarifications = []
    for item in raw_clarifications:
        if not isinstance(item, dict):
            continue
        key_clarifications.append({
            'question_id': str(item.get('question_id', '')),
            'topic': str(item.get('topic', '')),
            'customer_answer_summary': str(item.get('customer_answer_summary', '')),
            'changes_requirement': bool(item.get('changes_requirement', False)),
            'note': str(item.get('note', '')),
        })
    result['key_clarifications'] = key_clarifications

    # ── Формуємо unanswered_questions ─────────────────────────────────────
    raw_unanswered = llm_data.get('unanswered_important') or []
    unanswered_questions = []
    for item in raw_unanswered:
        if not isinstance(item, dict):
            continue
        unanswered_questions.append({
            'question_id': str(item.get('question_id', '')),
            'title': str(item.get('title', '')),
            'description': str(item.get('description', '')),
        })
    result['unanswered_questions'] = unanswered_questions

    # ── Appealable / not appealable після змін ────────────────────────────
    if td_has_amendments:
        changed_provisions = llm_data.get('changed_provisions') or []
        unchanged_provisions = llm_data.get('unchanged_provisions') or []
        result['appealable_after_amendments'] = [
            str(p) for p in changed_provisions if p
        ]
        result['not_appealable_unchanged'] = [
            str(p) for p in unchanged_provisions if p
        ]

    # ── has_meaningful_qa ─────────────────────────────────────────────────
    result['has_meaningful_qa'] = bool(llm_data.get('has_meaningful_qa', False))

    logger.info(
        "qa_analyzer: завершено. key_clarifications=%d, unanswered=%d, "
        "appeal_original=%s, appeal_new=%s",
        len(result['key_clarifications']),
        len(result['unanswered_questions']),
        result['appeal_deadline_original'],
        result['new_appeal_deadline'],
    )

    return result
