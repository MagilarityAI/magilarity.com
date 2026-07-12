import json
import os
import re
import time
import logging
import requests
from pathlib import Path
from .llm_client import call_llm
from typing import Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://public-api.prozorro.gov.ua/api/2.5"
TIMEOUT = 30
MAX_RETRIES = 5
RETRY_DELAY = 2  # секунд; фактична затримка = RETRY_DELAY * номер_спроби (як у downloader.py)

# Папка з локально збереженими тендерами (відносно цього файлу)
_TENDERS_DIR = Path(__file__).parent / 'закупівлі'

# ─────────────────────────────────────────────────────────────────────────
# КАНОНІЧНИЙ МАПІНГ — узгоджено з bid_researcher (main.py:81 _CPV_CATEGORY_MAP)
# Джерело істини: prompts/dk_category_map_canonical.md (08.07.2026)
# ⛔ Зміни — СИНХРОННО в bid_researcher/main.py та цьому файлі.
#
# Однозначні префікси — визначаємо без LLM.
# ПОРЯДОК КРИТИЧНИЙ: специфічні префікси ПЕРЕД загальними (dict/list перебирається по порядку).
# Порядок секцій ІДЕНТИЧНИЙ _CPV_CATEGORY_MAP bid_researcher.
# ─────────────────────────────────────────────────────────────────────────
DK_REGEX_MAP = [
    # ===== БУДІВНИЦТВО (роботи) =====
    # 45453100 (відновлювальні роботи) винесено в AMBIGUOUS_PREFIXES — залежить від контексту
    # "поточний ремонт" у тексті ТД. Негативний lookahead виключає його з детермінованого '^45'.
    (r'^45(?!453100)', 'building_works'),

    # ===== БУДІВЕЛЬНІ МАТЕРІАЛИ ТА КОНСТРУКЦІЇ (товари) =====
    (r'^44', 'technical_goods'),

    # ===== РЕМОНТ ТА ТЕХНІЧНЕ ОБСЛУГОВУВАННЯ =====
    (r'^50', 'maintenance_works'),
    (r'^51', 'maintenance_works'),

    # ===== ПРОДУКТИ ХАРЧУВАННЯ =====
    (r'^553', 'food_products'),    # ресторани (специфічніше за загальний 55)
    (r'^555', 'food_products'),    # їдальні, кейтеринг
    (r'^15', 'food_products'),

    # ===== МЕДИЧНЕ ОБЛАДНАННЯ ТА ФАРМА =====
    # УВАГА: специфічніші 3-значні префікси ОБОВ'ЯЗКОВО перед "33" (fallback)
    (r'^337', 'simple_goods'),         # засоби особистої гігієни (НЕ медобладнання)
    (r'^336', 'pharmaceuticals'),      # фармацевтична хімія (Порядок №708 — 3-й знак, виняток)
    (r'^331', 'medical_equipment'),    # медичні вироби та пристрої
    (r'^33', 'medical_equipment'),     # медичне обладнання та фарма (fallback: 330,332-335)

    # ===== ТЕХНІЧНІ ТОВАРИ ТА ОБЛАДНАННЯ =====
    (r'^31', 'technical_goods'),   # електричне обладнання, освітлення
    (r'^32', 'technical_goods'),   # радіо, телеком, мережеве обладнання
    (r'^34', 'technical_goods'),   # транспортне обладнання та запчастини
    (r'^35', 'technical_goods'),   # обладнання безпеки, пожежне, поліцейське
    (r'^38', 'technical_goods'),   # вимірювальне та лабораторне обладнання
    (r'^42', 'technical_goods'),   # промислове обладнання
    (r'^43', 'technical_goods'),   # гірничодобувне та будівельне обладнання
    (r'^16', 'technical_goods'),   # сільськогосподарська техніка
    (r'^14', 'technical_goods'),   # гірнича сировина, метали, мінерали
    (r'^30', 'technical_goods'),   # офісна та комп'ютерна техніка (hardware)

    # ===== ПАЛИВО ТА ПММ =====
    (r'^09', 'fuel'),               # паливо, ПММ, газ, вугілля, енергоносії (fallback увесь розділ 09)

    # ===== IT =====
    (r'^48', 'it_services'),        # пакети програмного забезпечення
    (r'^72', 'it_services'),        # IT послуги, розробка ПЗ

    # ===== ХІМІЧНА ПРОДУКЦІЯ ТА ВИТРАТНІ МАТЕРІАЛИ =====
    (r'^24', 'consumables'),        # хімічна продукція, фарби, клеї, добрива

    # ===== ПРОСТІ ТОВАРИ =====
    (r'^18', 'simple_goods'),       # одяг та взуття
    (r'^19', 'simple_goods'),       # шкіра, текстиль, гума, пластмаси
    # 03 розщеплено за 3-м знаком, рішення користувача 09.07.2026:
    # 031-033 — реальні харчові закупівлі шкіл/лікарень (профіль ХАССП), 034 — деревина/лісоматеріали
    # (профіль як будматеріали 44). Специфічні префікси ПЕРЕД fallback '^03'.
    (r'^031', 'food_products'),     # продукція рослинництва, харчова сировина
    (r'^032', 'food_products'),     # продукція тваринництва, харчова сировина
    (r'^033', 'food_products'),     # продукція рибальства, харчова сировина
    (r'^034', 'technical_goods'),   # деревина, лісоматеріали (профіль будматеріалів)
    (r'^03', 'simple_goods'),       # сільськогосподарська та фермерська продукція (fallback, хвости розділу)
    (r'^22', 'simple_goods'),       # друкована продукція, книги, канцтовари
    (r'^37', 'simple_goods'),       # спортивний інвентар, іграшки, музінструменти
    (r'^39', 'simple_goods'),       # меблі, побутові прилади, приладдя для прибирання

    # ===== КОМУНАЛЬНІ ПОСЛУГИ ТА ЕНЕРГІЯ =====
    (r'^65', 'utilities_energy'),   # газо-, водопостачання
    (r'^40', 'utilities_energy'),   # електро/газо/теплопостачання
    (r'^41', 'utilities_energy'),   # питна та очищена вода
    (r'^64', 'utilities_energy'),   # поштові та телекомунікаційні послуги

    # ===== КОНСУЛЬТАЦІЙНІ ПОСЛУГИ =====
    (r'^71', 'consulting_services'),  # архітектурні, інженерні, інспекційні послуги
    (r'^73', 'consulting_services'),  # наукові дослідження та розробки
    (r'^70', 'consulting_services'),  # послуги у сфері нерухомості
    (r'^66', 'consulting_services'),  # фінансові та страхові послуги

    # ===== ЗАГАЛЬНІ ПОСЛУГИ =====
    (r'^79', 'general_services'),   # ділові послуги (юр., бухг., маркетинг, охорона, консалтинг)
    (r'^90', 'general_services'),   # санітарія, поводження з відходами, довкілля
    (r'^85', 'general_services'),   # охорона здоров'я та соціальні послуги
    (r'^55', 'general_services'),   # готельні, ресторанні послуги (fallback, крім 553/555 вище)
    (r'^60', 'general_services'),   # транспортні послуги (дорожній, залізничний)
    (r'^61', 'general_services'),   # морський та прибережний транспорт
    (r'^62', 'general_services'),   # авіаційні послуги та ТО авіатехніки
    (r'^63', 'general_services'),   # допоміжні транспортні послуги, складування
    (r'^75', 'general_services'),   # послуги органів державної влади
    (r'^76', 'general_services'),   # нафтогазові послуги
    (r'^77', 'general_services'),   # сільськогосподарські, лісові, рибальські послуги
    (r'^80', 'general_services'),   # освіта та навчання
    (r'^92', 'general_services'),   # відпочинок, культура, спорт
    (r'^98', 'general_services'),   # інші послуги
]

# Неоднозначні префікси — потрібен LLM (справді залежать від контексту тексту ТД,
# НЕ покриваються детермінованою таблицею вище).
AMBIGUOUS_PREFIXES = [
    r'^45453100',  # building_works (капітальний об'єкт) vs maintenance_works (контекст "поточний ремонт")
]

ALL_CATEGORIES = [
    'building_works',       # Кат.1
    'maintenance_works',    # Кат.2
    'food_products',        # Кат.3
    'pharmaceuticals',      # Кат.4
    'medical_equipment',    # Кат.5
    'utilities_energy',     # Кат.6
    'fuel',                 # Кат.7
    'technical_goods',      # Кат.8
    'consumables',          # Кат.9
    'it_services',          # Кат.10
    'general_services',     # Кат.11
    'consulting_services',  # Кат.12
    'simple_goods',         # Кат.13
]

# ─────────────────────────────────────────────────────────────────────────
# Канонічна таблиця для CLASSIFICATION_PROMPT — читається з
# prompts/dk_category_map_canonical.md (узгоджено з bid_researcher 08.07.2026).
# LLM-виклик рідкісний (лише для AMBIGUOUS_PREFIXES) — розмір промпту не критичний.
# Кешується в модульну константу при першому імпорті; якщо файл відсутній —
# fallback на вбудовану коротку виписку (щоб pipeline не падав).
# ─────────────────────────────────────────────────────────────────────────
_CANONICAL_MAP_PATH = Path(__file__).parent / 'prompts' / 'dk_category_map_canonical.md'

_FALLBACK_CATEGORY_TABLE = """- building_works: будівельні роботи (нове будівництво, капітальний ремонт, реконструкція, ДК 45xxxxxx з цими словами)
- maintenance_works: поточний ремонт, технічне обслуговування (ДК 45453100 з контекстом "поточний ремонт", або 50xxxxxx, 51xxxxxx)
- food_products: продукти харчування та напої (ДК 15xxxxxx, 553xxxxx, 555xxxxx, 031xxxxx-033xxxxx: рослинництво/тваринництво/рибальство як харчова сировина)
- pharmaceuticals: медикаменти, ліки, фармацевтика (ДК 336xxxxx: таблетки, капсули, ін'єкції, вакцини, препарати)
- medical_equipment: медичне обладнання та прилади (ДК 33xxxxxx, 331xxxxx: апарат, прилад, обладнання, пристрій)
- utilities_energy: ЖКГ, електроенергія, теплопостачання, водопостачання, газ, пошта/телеком (ДК 65xxxxxx, 40xxxxxx, 41xxxxxx, 64xxxxxx)
- fuel: паливо (бензин, дизель, мазут, тверде паливо, енергоносії — ДК 09xxxxxx)
- technical_goods: технічно складні товари, обладнання, будматеріали (ДК 14, 16, 30-32, 34-35, 38, 42-44xxxxxx, 034xxxxx: деревина/лісоматеріали)
- consumables: витратні матеріали, хімічна продукція (ДК 24xxxxxx)
- it_services: IT послуги, програмне забезпечення (ДК 48xxxxxx, 72xxxxxx)
- general_services: послуги загального характеру (охорона, прибирання, транспорт, освіта, ділові послуги — ДК 55, 60-63, 75-77, 79, 80, 85, 90, 92, 98)
- consulting_services: консультаційні, фінансові, архітектурно-інженерні, наукові послуги (ДК 66xxxxxx, 70xxxxxx, 71xxxxxx, 73xxxxxx)
- simple_goods: прості товари — одяг, взуття, текстиль, книги, меблі, сільгосппродукція (ДК 03xxxxxx fallback поза 031-034, 18-19, 22, 37, 39xxxxxx, 337xxxxx)"""


def _load_canonical_category_table() -> str:
    """
    Завантажує канонічну таблицю префіксів ДК → категорія з .md файла
    (єдине джерело істини, узгоджене з bid_researcher).

    Fallback на вбудовану коротку виписку якщо файл відсутній/недоступний —
    щоб класифікація не падала.
    """
    try:
        text = _CANONICAL_MAP_PATH.read_text(encoding='utf-8')
        # Витягуємо тільки розділ "ПОВНИЙ СПИСОК ПРЕФІКСІВ" (компактний, машинний) —
        # весь файл занадто великий (конфлікти, пояснення) для вставки у кожен LLM виклик.
        marker = '## ПОВНИЙ СПИСОК ПРЕФІКСІВ'
        idx = text.find(marker)
        if idx == -1:
            logger.warning(
                "classifier: маркер '%s' не знайдено у %s — використовую fallback таблицю",
                marker, _CANONICAL_MAP_PATH,
            )
            return _FALLBACK_CATEGORY_TABLE
        section = text[idx:]
        # Обрізаємо до наступного "---" (кінець розділу) або кінця файлу
        end_idx = section.find('\n---', 1)
        if end_idx != -1:
            section = section[:end_idx]
        return section.strip()
    except OSError as e:
        logger.warning(
            "classifier: не вдалося прочитати канонічну таблицю %s (%s) — використовую fallback",
            _CANONICAL_MAP_PATH, e,
        )
        return _FALLBACK_CATEGORY_TABLE


# Кешується один раз при імпорті модуля.
CANONICAL_CATEGORY_TABLE = _load_canonical_category_table()

CLASSIFICATION_PROMPT = """Визнач категорію закупівлі за кодом ДК 021:2015 та назвою предмету.

Код ДК: {dk_code}
Назва закупівлі: {title}
Опис предмету: {description}

Канонічна таблиця відповідності префіксів ДК 021:2015 → категорія
(узгоджено з bid_researcher, перевіряй префікси зверху вниз, специфічні — першими):

""" + CANONICAL_CATEGORY_TABLE + """

Категорії (ідентифікатори для відповіді): building_works, maintenance_works, food_products,
pharmaceuticals, medical_equipment, utilities_energy, fuel, technical_goods, consumables,
it_services, general_services, consulting_services, simple_goods.

Особливе правило для ДК 45453100 (Відновлювальні роботи): якщо контекст вказує на
капітальний ремонт/реконструкцію об'єкта будівництва → building_works;
якщо контекст явно вказує на поточний ремонт конкретного об'єкта → maintenance_works.

Відповідь: тільки одне слово — ідентифікатор категорії з наведеного списку."""


def _find_local_tender_json(internal_id: str) -> Optional[dict]:
    """Шукає локально збережений JSON тендера за internal_id."""
    if not _TENDERS_DIR.exists():
        return None
    for json_file in _TENDERS_DIR.glob('*/*.json'):
        try:
            data = json.loads(json_file.read_text(encoding='utf-8'))
            if data.get('id') == internal_id:
                logger.info("classifier: знайдено локальний JSON %s", json_file)
                return data
        except Exception:
            continue
    return None


def _fetch_tender_json(internal_id: str) -> dict:
    # Спочатку перевіряємо локальний кеш (якщо Prozorro API недоступний)
    local = _find_local_tender_json(internal_id)
    if local:
        return local

    url = f"{BASE_URL}/tenders/{internal_id}"
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.json()['data']
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise RuntimeError(f"Cannot fetch tender {internal_id} after {MAX_RETRIES} attempts: {e}")
            wait = RETRY_DELAY * (attempt + 1)
            logger.warning(
                f"Fetch attempt {attempt + 1} failed for {internal_id}: {e} — retry in {wait}s"
            )
            time.sleep(wait)
    return {}


def _extract_category_from_response(raw: str) -> str:
    """Витягує category_id з відповіді LLM (plain text, JSON об'єкт, або рядок з категорією)."""
    import json as _json
    text = raw.strip()

    # 1. Спроба розпарсити як JSON об'єкт {"category": "..."}
    try:
        data = _json.loads(text)
        if isinstance(data, dict):
            val = str(data.get('category', '')).strip().strip('"\'').lower()
            if val in ALL_CATEGORIES:
                return val
    except (_json.JSONDecodeError, ValueError):
        pass

    # 2. Regex: шукаємо будь-яку відому категорію в тексті відповіді
    for cat in ALL_CATEGORIES:
        if re.search(r'\b' + re.escape(cat) + r'\b', text):
            return cat

    # 3. Prefix-match: Gemini іноді повертає усічений рядок ("building_" замість "building_works")
    text_clean = text.strip('"\'').strip().lower()
    for cat in ALL_CATEGORIES:
        if cat.startswith(text_clean) and len(text_clean) >= 4:
            return cat

    # 4. Plain text: прибираємо лапки та пробіли
    return text_clean


def _classify_with_llm(dk_code: str, title: str, description: str) -> str:
    prompt = CLASSIFICATION_PROMPT.format(
        dk_code=dk_code,
        title=title,
        description=description or 'не вказано',
    )
    try:
        raw = call_llm(prompt, role='classification', max_tokens=500)
        category = _extract_category_from_response(raw)
    except Exception as exc:
        logger.warning("classifier: LLM помилка при класифікації: %s — defaulting to simple_goods", exc)
        return 'simple_goods'
    if category not in ALL_CATEGORIES:
        logger.warning(
            "classifier: LLM повернув невідому категорію '%s' для dk=%s — defaulting to simple_goods",
            category, dk_code,
        )
        return 'simple_goods'
    return category


def classify_dk(dk_code: str, title: str, description: str = '') -> str:
    dk_clean = re.sub(r'[-\s]', '', dk_code).strip()

    for pattern, category in DK_REGEX_MAP:
        if re.match(pattern, dk_clean):
            logger.debug(f"Regex match: dk={dk_code} → {category}")
            return category

    for pattern in AMBIGUOUS_PREFIXES:
        if re.match(pattern, dk_clean):
            logger.debug(f"Ambiguous dk={dk_code}, calling Sonnet")
            return _classify_with_llm(dk_code, title, description)

    logger.debug(f"No regex match for dk={dk_code}, calling Sonnet")
    return _classify_with_llm(dk_code, title, description)


def classify(internal_id: str) -> dict:
    """Fetch tender from Prozorro and classify by DK code.

    Returns:
        dict with keys: internal_id, public_id, title, dk_code, category,
        customer_name, customer_edrpou, expected_value, submission_deadline,
        questions_deadline, status, has_lots, lots_count
    """
    tender = _fetch_tender_json(internal_id)

    public_id = tender.get('tenderID', '')
    title = tender.get('title', '')
    description = tender.get('description', '')

    dk_code = ''
    items = tender.get('items', [])
    if items:
        classification = items[0].get('classification', {})
        dk_code = classification.get('id', '')

    customer = tender.get('procuringEntity', {})
    customer_name = customer.get('name', '')
    customer_edrpou = customer.get('identifier', {}).get('id', '')

    expected_value = 0.0
    value = tender.get('value', {})
    if value:
        try:
            expected_value = float(value.get('amount', 0))
        except (TypeError, ValueError):
            pass

    tender_period = tender.get('tenderPeriod', {})
    enquiry_period = tender.get('enquiryPeriod', {})

    lots = tender.get('lots', [])

    category = classify_dk(dk_code, title, description)

    logger.info(f"Classified {public_id}: dk_code={dk_code}, category={category}, customer={customer_edrpou}")

    return {
        'internal_id': internal_id,
        'public_id': public_id,
        'title': title,
        'description': description,
        'dk_code': dk_code,
        'category': category,
        'customer_name': customer_name,
        'customer_edrpou': customer_edrpou,
        'expected_value': expected_value,
        'submission_deadline': tender_period.get('endDate', ''),
        'questions_deadline': enquiry_period.get('endDate', ''),
        'status': tender.get('status', ''),
        'has_lots': len(lots) > 1,
        'lots_count': len(lots),
    }
