import json
import os
import re
import logging
import requests
from pathlib import Path
from .llm_client import call_llm
from typing import Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://public-api.prozorro.gov.ua/api/2.5"
TIMEOUT = 30
MAX_RETRIES = 5

# Папка з локально збереженими тендерами (відносно цього файлу)
_TENDERS_DIR = Path(__file__).parent / 'закупівлі'

# Однозначні префікси — визначаємо без LLM
# ПОРЯДОК КРИТИЧНИЙ: специфічні перед загальними
DK_REGEX_MAP = [
    # Кат.7 ПАЛИВО — перед загальним ^09
    (r'^09134', 'fuel'),           # дизельне паливо
    (r'^0911', 'fuel'),            # тверде паливо
    (r'^0912', 'fuel'),            # газоподібне паливо
    (r'^0913[^4]', 'fuel'),        # нафта та дистиляти (не дизель)
    (r'^0914', 'fuel'),            # мазут
    (r'^0921', 'fuel'),            # мастила

    # Кат.6 ЖКГ та ЕНЕРГОНОСІЇ
    (r'^0930', 'utilities_energy'),
    (r'^0931', 'utilities_energy'),
    (r'^0932', 'utilities_energy'),
    (r'^0933', 'utilities_energy'),
    (r'^651', 'utilities_energy'),
    (r'^652', 'utilities_energy'),
    (r'^653', 'utilities_energy'),
    (r'^904', 'utilities_energy'),
    (r'^905', 'utilities_energy'),
    (r'^906', 'utilities_energy'),

    # Кат.4 МЕДИКАМЕНТИ — 3-знак 336! перед медобладнанням
    (r'^336', 'pharmaceuticals'),

    # Кат.5 МЕДИЧНЕ ОБЛАДНАННЯ — 4-знак 331-335
    (r'^331', 'medical_equipment'),
    (r'^332', 'medical_equipment'),
    (r'^333', 'medical_equipment'),
    (r'^334', 'medical_equipment'),
    (r'^335', 'medical_equipment'),

    # Кат.3 ПРОДУКТИ ХАРЧУВАННЯ
    (r'^03', 'food_products'),
    (r'^15', 'food_products'),
    (r'^553', 'food_products'),    # ресторани
    (r'^555', 'food_products'),    # їдальні, кейтеринг

    # Кат.2 ПОТОЧНИЙ РЕМОНТ та ТО
    (r'^50', 'maintenance_works'),

    # Кат.10 IT ПОСЛУГИ та ПЗ
    (r'^48', 'it_services'),
    (r'^302', 'it_services'),      # комп'ютерне обладнання
    (r'^303', 'it_services'),
    (r'^724', 'it_services'),      # IT послуги (72400000+)
    (r'^725', 'it_services'),
    (r'^726', 'it_services'),
    (r'^727', 'it_services'),
    (r'^728', 'it_services'),
    (r'^729', 'it_services'),

    # Кат.8 ТЕХНІЧНО СКЛАДНІ ТОВАРИ
    (r'^311', 'technical_goods'),  # електродвигуни, генератори
    (r'^312', 'technical_goods'),  # розподіл електроенергії
    (r'^313', 'technical_goods'),  # кабелі
    (r'^314', 'technical_goods'),  # акумулятори
    (r'^315', 'technical_goods'),  # освітлення
    (r'^316', 'technical_goods'),  # електрообладнання
    (r'^317', 'technical_goods'),  # електронне обладнання
    (r'^322', 'technical_goods'),  # апаратура передачі даних
    (r'^323', 'technical_goods'),  # телевізори, радіо
    (r'^324', 'technical_goods'),  # мережі
    (r'^325', 'technical_goods'),  # телекомунікаційне обладнання
    (r'^38', 'technical_goods'),   # лабораторне обладнання
    (r'^42', 'technical_goods'),   # промислова техніка
    (r'^43', 'technical_goods'),   # гірничо-будівельне обладнання

    # Кат.9 ВИТРАТНІ МАТЕРІАЛИ та КАНЦЕЛЯРІЯ
    (r'^30190', 'consumables'),    # офісне приладдя
    (r'^30192', 'consumables'),    # канцелярія
    (r'^30197', 'consumables'),    # дрібна канцелярія
    (r'^30199', 'consumables'),    # канцелярське приладдя
    (r'^301', 'consumables'),      # інше офісне (картриджі тощо)
    (r'^24', 'consumables'),       # хімічні продукти
    (r'^398', 'consumables'),      # засоби для прибирання

    # Кат.13 ТОВАРИ ПРОСТІ
    (r'^18', 'simple_goods'),      # одяг, взуття
    (r'^19', 'simple_goods'),      # текстиль
    (r'^22', 'simple_goods'),      # книги, друкована продукція
    (r'^34', 'simple_goods'),      # транспортні засоби (товари)
    (r'^37', 'simple_goods'),      # спортивний інвентар, іграшки
    (r'^391', 'simple_goods'),     # меблі
    (r'^392', 'simple_goods'),     # приладдя
    (r'^393', 'simple_goods'),
    (r'^395', 'simple_goods'),     # текстильні вироби
    (r'^397', 'simple_goods'),     # побутові прилади

    # Кат.11 ПОСЛУГИ ЗАГАЛЬНІ — однозначні
    (r'^551', 'general_services'),
    (r'^60', 'general_services'),
    (r'^63', 'general_services'),
    (r'^64', 'general_services'),
    (r'^66', 'general_services'),
    (r'^70', 'general_services'),
    (r'^75', 'general_services'),
    (r'^77', 'general_services'),
    (r'^791', 'general_services'),  # юридичні
    (r'^792', 'general_services'),  # бухгалтерські
    (r'^795', 'general_services'),
    (r'^796', 'general_services'),
    (r'^797', 'general_services'),  # охорона
    (r'^798', 'general_services'),  # видання
    (r'^80', 'general_services'),   # освіта
    (r'^85', 'general_services'),   # охорона здоров'я
    (r'^907', 'general_services'),
    (r'^92', 'general_services'),
    (r'^98', 'general_services'),
]

# Неоднозначні префікси — потрібен Sonnet
AMBIGUOUS_PREFIXES = [
    r'^45',    # building_works vs maintenance_works (45453100 = відновлювальні — залежить від контексту)
    r'^44',    # technical_goods vs building_works (будматеріали)
    r'^71',    # general_services (архітект.) vs building_works (для будівн.)
    r'^722',   # it_services vs consulting_services (72200000-72262000)
    r'^723',   # it_services vs consulting_services
    r'^73',    # general_services vs consulting_services
    r'^793',   # ринкові дослідження — consulting
    r'^7941',  # 79411000=consulting_services vs загальний 79400000=general
    r'^7942',  # 79421000=consulting_services vs загальний 79420000=general
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

CLASSIFICATION_PROMPT = """Визнач категорію закупівлі за кодом ДК 021:2015 та назвою предмету.

Код ДК: {dk_code}
Назва закупівлі: {title}
Опис предмету: {description}

Категорії та правила:
- building_works: будівельні роботи (нове будівництво, капітальний ремонт, реконструкція, ДК 45xxxxxx з цими словами)
- maintenance_works: поточний ремонт, технічне обслуговування (ДК 45xxxxxx або 44xxxxxx або 50xxxxxx з "поточний", "технічне обслуговування")
- food_products: продукти харчування та напої (ДК 03xxxxxx, 15xxxxxx, 553xxxxx, 555xxxxx)
- pharmaceuticals: медикаменти, ліки, фармацевтика (ДК 336xxxxx: таблетки, капсули, ін'єкції, вакцини, препарати)
- medical_equipment: медичне обладнання та прилади (ДК 331-335xxxxx: апарат, прилад, обладнання, пристрій)
- utilities_energy: ЖКГ, електроенергія, теплопостачання, водопостачання, газ (ДК 093x, 651-653, 904-906)
- fuel: паливо (бензин, дизель, мазут, тверде паливо — ДК 0911-0914, 0921)
- technical_goods: технічно складні товари, обладнання (ДК 311-317, 322-325, 38xxxxxx, 42-43xxxxxx)
- consumables: витратні матеріали, канцелярія, хімічні продукти (ДК 301xxxxx, 24xxxxxx, 398xxxxx)
- it_services: IT послуги, програмне забезпечення, комп'ютерне обладнання (ДК 48xxxxxx, 302-303, 724-729)
- general_services: послуги загального характеру (охорона, прибирання, транспорт, освіта — ДК 60, 63-64, 66, 70, 75, 77, 791-792, 795-798, 80, 85, 92, 98)
- consulting_services: консультаційні, юридичні, аудиторські, маркетингові послуги (ДК 722-723, 73xxxxxx, 793xxxxx, 7941-7942)
- simple_goods: прості товари — одяг, взуття, текстиль, книги, меблі, побутові вироби (ДК 18-19, 22, 34, 37, 391-393, 395, 397)

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
            logger.warning(f"Fetch attempt {attempt + 1} failed for {internal_id}: {e}")
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
