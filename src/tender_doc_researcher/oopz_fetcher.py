"""
oopz_fetcher.py — Отримує практику рішень ООПЗ по коду ДК з APPDB.

Використовується tender_doc_researcher для формування контексту ООПЗ
при аналізі тендерної документації.

APPDB — тільки читання. Graceful деградація якщо міграція ще не виконана.
"""

import os
import logging
import psycopg2
import psycopg2.errors

logger = logging.getLogger(__name__)

# Маппінг категорій → префікси dk_code (перший префікс у списку має пріоритет)
CATEGORY_DK_PREFIXES = {
    'building_works':    ['45'],
    'current_repair':    ['45', '44'],
    'pharmaceuticals':   ['33'],
    'medical_equipment': ['33'],
    'food_products':     ['15'],
    'utilities':         ['09', '65'],
    'fuel':              ['09134', '09'],
    'it_services':       ['48', '72'],
    'technical_goods':   ['44', '34', '38'],
    'lubricants':        ['09'],
    'general_services':  ['85', '98', '55', '60', '90'],
    'consulting':        ['79', '71', '73'],
    'simple_goods':      [],   # широкий пошук — не фільтруємо по префіксу
}


def _get_connection():
    """Підключення до APPDB (тільки читання)."""
    return psycopg2.connect(
        host='localhost',
        port=5432,
        database=os.getenv('POSTGRES_DB', 'appdb'),
        user=os.getenv('POSTGRES_USER', 'user'),
        password=os.getenv('POSTGRES_PASSWORD', 'pass'),
    )


def _query_with_new_columns(cur, dk_prefix: str, limit: int) -> list:
    """
    Запит після міграції: з новими колонками key_violation, is_analyzed,
    analysis_json, importance_score.

    Повертає список dict або кидає ProgrammingError якщо колонки не існують.
    """
    like_pattern = f"{dk_prefix}%"
    cur.execute(
        """
        SELECT decision_number, dk_code, complaint_type,
               key_violation, is_analyzed, analysis_json
        FROM oopz_decisions
        WHERE dk_code LIKE %s
          AND is_analyzed = true
        ORDER BY importance_score DESC
        LIMIT %s
        """,
        (like_pattern, limit),
    )
    rows = cur.fetchall()
    results = []
    for row in rows:
        results.append({
            'decision_number': row[0],
            'dk_code': row[1],
            'complaint_type': row[2],
            'key_violation': row[3],
            'is_analyzed': row[4],
            'analysis_json': row[5],
            'source': 'oopz_decisions',
        })
    return results


def _query_fallback(cur, dk_prefix: str, limit: int) -> list:
    """
    Fallback запит до міграції: тільки гарантовано існуючі поля.

    Повертає список dict з позначкою migration_pending=True.
    """
    like_pattern = f"{dk_prefix}%"
    cur.execute(
        """
        SELECT decision_number, complaint_type
        FROM oopz_decisions
        WHERE dk_code LIKE %s
        LIMIT %s
        """,
        (like_pattern, limit),
    )
    rows = cur.fetchall()
    results = []
    for row in rows:
        results.append({
            'decision_number': row[0],
            'complaint_type': row[1],
            'source': 'oopz_decisions_fallback',
            'migration_pending': True,
        })
    return results


def _query_for_prefix(cur, dk_prefix: str, limit: int, use_new_columns: bool) -> list:
    """
    Виконує запит для одного префіксу.
    Автоматично перемикається на fallback при ProgrammingError.

    Повертає (results, use_new_columns) — оновлений прапорець.
    """
    if use_new_columns:
        try:
            results = _query_with_new_columns(cur, dk_prefix, limit)
            return results, True
        except (psycopg2.errors.UndefinedColumn, psycopg2.ProgrammingError) as e:
            logger.warning(
                "Нові колонки oopz_decisions ще не існують (міграція не виконана): %s. "
                "Переключаємось на fallback.",
                e,
            )
            # Після ProgrammingError транзакція зламана — треба rollback
            cur.connection.rollback()
            # Більше не пробуємо нові колонки в цьому виклику
            results = _query_fallback(cur, dk_prefix, limit)
            return results, False
    else:
        results = _query_fallback(cur, dk_prefix, limit)
        return results, False


def fetch_oopz_context(category: str, dk_code: str, limit: int = 5) -> list:
    """
    Отримує релевантну практику рішень ООПЗ для категорії та коду ДК.

    Алгоритм:
    1. Визначає dk_prefix(и) по категорії (або по dk_code напряму).
    2. Для кожного префіксу пробує запит з новими колонками → fallback.
    3. Повертає перший непорожній результат.
    4. Якщо нічого немає — повертає [].

    При будь-якій критичній помилці — повертає [] (не пропагує виключення).

    Args:
        category: Одна з 13 категорій (напр. 'building_works').
        dk_code:  Код ДК закупівлі (напр. '45453000-7'). Може бути порожнім.
        limit:    Максимальна кількість рішень (default 5).

    Returns:
        Список dict з практикою ООПЗ або [] якщо нічого не знайдено.
    """
    conn = None
    try:
        conn = _get_connection()
        cur = conn.cursor()

        # Визначаємо список префіксів для пошуку
        prefixes = _resolve_prefixes(category, dk_code)

        if not prefixes:
            # Для simple_goods або якщо префікс не визначено — широкий пошук без фільтру по dk_code
            logger.debug(
                "Категорія '%s' без префіксів — повертаємо порожній список.", category
            )
            return []

        use_new_columns = True  # Спочатку пробуємо нові колонки

        for prefix in prefixes:
            logger.debug(
                "Запит ООПЗ: категорія='%s', префікс='%s', ліміт=%d",
                category, prefix, limit,
            )
            results, use_new_columns = _query_for_prefix(
                cur, prefix, limit, use_new_columns
            )
            if results:
                logger.info(
                    "Знайдено %d рішень ООПЗ для категорії '%s' (префікс '%s%%).",
                    len(results), category, prefix,
                )
                return results

        # Жоден префікс не дав результатів
        logger.info(
            "Практика ООПЗ не знайдена для категорії '%s', dk_code='%s'.",
            category, dk_code,
        )
        return []

    except Exception as e:
        logger.error(
            "Критична помилка при отриманні практики ООПЗ (категорія='%s', dk_code='%s'): %s",
            category, dk_code, e,
        )
        return []
    finally:
        if conn is not None:
            conn.close()


def _resolve_prefixes(category: str, dk_code: str) -> list:
    """
    Визначає список dk_prefix для пошуку.

    Пріоритет:
    1. Якщо dk_code переданий — береться його перші N цифр (збіг з префіксами категорії).
    2. Якщо категорія відома — повертає її префікси.
    3. Якщо категорія simple_goods або невідома — повертає [].

    Args:
        category: Категорія закупівлі.
        dk_code:  Код ДК (напр. '45453000-7').

    Returns:
        Список префіксів для LIKE-запитів.
    """
    category_prefixes = CATEGORY_DK_PREFIXES.get(category, [])

    # Якщо є dk_code і категорія має префікси — перевіряємо збіг
    # щоб відфільтрувати нерелевантні префікси (напр. current_repair: '45' або '44')
    if dk_code and category_prefixes:
        # Нормалізуємо: прибираємо дефіси, беремо цифрову частину
        dk_digits = dk_code.replace('-', '').strip()
        matched = [p for p in category_prefixes if dk_digits.startswith(p)]
        if matched:
            # Повертаємо тільки співпадаючі (більш специфічні — першими)
            matched_sorted = sorted(matched, key=len, reverse=True)
            return matched_sorted

    # Якщо збігів немає або dk_code не переданий — використовуємо всі префікси категорії
    return category_prefixes


def format_for_prompt(decisions: list) -> str:
    """
    Форматує список рішень ООПЗ для вставки в промпт аналізатора.

    Args:
        decisions: Список dict повернутих fetch_oopz_context().

    Returns:
        Відформатований рядок для промпту.
    """
    if not decisions:
        return "Практика ООПЗ відсутня"

    lines = ["Практика ООПЗ по даному коду ДК:"]
    for idx, d in enumerate(decisions, start=1):
        number = d.get('decision_number', 'б/н')
        complaint_type = d.get('complaint_type') or '—'
        key_violation = d.get('key_violation')

        if key_violation:
            line = f"{idx}. Рішення {number}: [{complaint_type}] — {key_violation}"
        else:
            # Fallback формат (до міграції)
            migration_note = " [дані неповні — міграція не виконана]" \
                if d.get('migration_pending') else ""
            line = f"{idx}. Рішення {number}: [{complaint_type}]{migration_note}"

        lines.append(line)

    return "\n".join(lines)
