"""
oopz_fetcher.py — Отримує практику рішень ООПЗ по коду ДК з APPDB.

Використовується tender_doc_researcher для формування контексту ООПЗ
при аналізі тендерної документації.

APPDB — тільки читання. Graceful деградація якщо міграція ще не виконана.
"""

import os
import logging
import psycopg2

logger = logging.getLogger(__name__)

# Маппінг канонічних 13 категорій → префікси dk_code.
# Ключі ТОЧНО відповідають 13 ID категорій з tdr CLAUDE.md (§4 контракту oopz_researcher/schemas.md).
# Джерело префіксів (08.07.2026, узгоджено з bid_researcher): plain-list з
# agents/implementations/tender_doc_researcher/prompts/dk_category_map_canonical.md,
# ідентичний _CPV_CATEGORY_MAP у agents/implementations/bid_researcher/main.py:81.
# ⛔ Зміни — синхронно з обома джерелами вище.
CATEGORY_DK_PREFIXES = {
    # Категорія 1 — Будівельні роботи (канон: 45)
    'building_works':    ['45'],

    # Категорія 2 — Поточний ремонт (канон: 50, 51; 45453100 — ambiguous у classifier.py,
    # тут лишаємо без '45453' — ООПЗ практика по відновлювальних роботах шукається
    # через building_works '45' fallback)
    'maintenance_works': ['50', '51'],

    # Категорія 3 — Продукти харчування (канон: 15, 553, 555, 031-033 — розщеплення
    # 03 за 3-м знаком, рішення користувача 09.07.2026)
    'food_products':     ['15', '553', '555', '031', '032', '033'],

    # Категорія 4 — Фармацевтика/медикаменти (канон: 336 — 3-знак виняток Порядку №708)
    'pharmaceuticals':   ['336'],

    # Категорія 5 — Медичне обладнання (канон: 331, 33 fallback)
    'medical_equipment': ['331', '33'],

    # Категорія 6 — ЖКГ та енергоносії (канон: 65, 40, 41, 64)
    'utilities_energy':  ['65', '40', '41', '64'],

    # Категорія 7 — Паливо/ПММ (канон: увесь розділ 09, fallback без підрозділів)
    'fuel':              ['09'],

    # Категорія 8 — Товари технічно складні (канон: 44, 31, 32, 34, 35, 38, 42, 43, 16, 14, 30,
    # 034 — розщеплення 03 за 3-м знаком, рішення користувача 09.07.2026)
    'technical_goods':   ['44', '31', '32', '34', '35', '38', '42', '43', '16', '14', '30', '034'],

    # Категорія 9 — Витратні матеріали та хімічна продукція (канон: 24 — узгоджено з bid,
    # '301'/канцелярія перенесено у technical_goods разом з рештою розділу 30)
    'consumables':       ['24'],

    # Категорія 10 — IT послуги та ПЗ (канон: 48, 72)
    'it_services':       ['48', '72'],

    # Категорія 11 — Послуги загальні (канон: 79, 90, 85, 55, 60, 61, 62, 63, 75, 76, 77, 80, 92, 98)
    'general_services':  ['79', '90', '85', '55', '60', '61', '62', '63',
                          '75', '76', '77', '80', '92', '98'],

    # Категорія 12 — Консультаційні послуги (канон: 71, 73, 70, 66 — раніше 71/70/66
    # були у general_services/ambiguous, узгоджено з bid 08.07.2026)
    'consulting_services': ['71', '73', '70', '66'],

    # Категорія 13 — Товари прості (широкий пошук — не фільтруємо по префіксу;
    # канон: 18, 19, 03 (fallback поза 031-034, розщеплено 09.07.2026), 22, 37, 39, 337 —
    # але fetch_oopz_context() для simple_goods завжди повертає [] за дизайном,
    # тому список префіксів навмисно порожній)
    'simple_goods':      [],
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


def _query_for_prefix(cur, dk_prefix: str, limit: int) -> list:
    """
    Виконує запит практики ООПЗ для одного dk_prefix.

    Міграція oopz_decisions (dk_code/dk_category/key_violation/is_analyzed/
    analysis_json/importance_score) ЗАСТОСОВАНА 07.07.2026 — колонки існують
    у продакшн APPDB (перевірено 09.07.2026, information_schema.columns).
    Legacy fallback-запит без is_analyzed (до міграції) видалено — тримати
    мертву гілку без реальної потреби лише збільшувало ризик випадково
    повернути нерозібрані рішення (сирий текст) у промпт LLM.

    Повертає список dict.
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

        for prefix in prefixes:
            logger.debug(
                "Запит ООПЗ: категорія='%s', префікс='%s', ліміт=%d",
                category, prefix, limit,
            )
            results = _query_for_prefix(cur, prefix, limit)
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
