"""
contract_analyzer.py — Аналіз проекту договору в тендерній документації.

Знаходить файл договору в папці ТД, витягує текст і передає Opus для
юридичного аналізу: договір приєднання (ст.634 ЦКУ), односторонність умов
(ст.849 ЦКУ, КМУ №668), відповідність ст.41 ЗУ 922-VIII, приховані ризики.

Правова база: ЦКУ ст.634, 841, 849; ЗУ 922-VIII ст.41; КМУ №668; КМУ №1178.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .file_extractor import find_contract_file, extract_text
from .llm_client import call_llm, get_model

logger = logging.getLogger(__name__)

CONTRACT_LEGAL_FRAMEWORK = """
ЗАКОНОДАВЧА БАЗА ДЛЯ АНАЛІЗУ ДОГОВОРУ:

1. ст.634 ЦКУ — Договір приєднання: якщо умови є явно невигідними для іншої сторони — вона має право вимагати зміни або визнання недійсним.

2. ст.849 ЦКУ — Відмова замовника від договору підряду: замовник зобов'язаний відшкодувати збитки підряднику. Якщо договір це виключає — порушення ЦКУ.

3. ст.841 ЦКУ — Ризики: якщо предмет договору знищений не з вини підрядника — замовник несе ризик.

4. ст.41 ЗУ 922-VIII — Обов'язкові умови договору про закупівлю: предмет, кількість, ціна, строки, умови зміни ціни, умови розірвання.

5. КМУ №668 від 01.08.2005 — Загальні умови підряду в будівництві: розподіл ризиків, порядок прийомки, оплати, гарантійні строки.

6. КМУ №1178-2022-п — Особливості закупівель в умовах воєнного стану: особливості оплати, строків.

ШКАЛА ОЦІНКИ БАЛАНСУ (поле overall_balance):
- "balanced" — умовно рівні права та обов'язки
- "slightly_skewed_to_customer" — незначний перекіс
- "skewed_to_customer" — помітний перекіс
- "heavily_skewed_to_customer" — значний перекіс, явно невигідний для переможця
"""


# ── Допоміжні функції ─────────────────────────────────────────────────────────

def _calculate_appeal_deadline(submission_deadline: str) -> str:
    """
    Розраховує дедлайн оскарження як fallback, якщо qa_analysis порожній.

    КМУ 1178-2022-п п.59: не пізніше ніж за 3 дні до кінцевого строку
    подання пропозицій (воєнний стан, пріоритет над ЗУ 922 ст.18 — 4 дні).

    Повертає дату у форматі 'YYYY-MM-DD' або 'невідомо' при помилці.
    """
    if not submission_deadline:
        return 'невідомо'
    try:
        dt = datetime.fromisoformat(submission_deadline.replace('Z', '+00:00'))
        return (dt - timedelta(days=3)).date().isoformat()
    except Exception:
        return 'невідомо'


CONTRACT_TEXT_LIMIT = 80000


def _build_contract_prompt(
    contract_text: str,
    contract_filename: str,
    appeal_deadline: str,
    tender_info: dict,
) -> str:
    """Формує промпт для аналізу проекту договору."""
    return f"""Проаналізуй проект договору тендерної документації на юридичні ризики.

{CONTRACT_LEGAL_FRAMEWORK}

КРИТИЧНИЙ ДЕДЛАЙН: зміни до умов договору можна ініціювати ТІЛЬКИ шляхом оскарження до ООПЗ до {appeal_deadline} (КМУ 1178 п.59, воєнний стан: 3 дні до дедлайну подачі).

ІНФОРМАЦІЯ ПРО ЗАКУПІВЛЮ:
- Назва: {tender_info.get('title')}
- Замовник: {tender_info.get('customer_name')}
- Очікувана вартість: {tender_info.get('expected_value')} грн
- Категорія: {tender_info.get('category')}

ФАЙЛ ДОГОВОРУ: {contract_filename}

ТЕКСТ ДОГОВОРУ:
{contract_text[:CONTRACT_TEXT_LIMIT]}

ВАЖЛИВО щодо one_sided_conditions: Перевір КОЖНИЙ пункт договору методично. У великих будівельних договорах (50+ млн грн) типово 10-20 односторонніх умов на шкоду підряднику:
- Права замовника на одностороннє розірвання/зміну обсягів без симетричних прав підрядника
- Штрафні санкції лише для підрядника, відсутні або мінімальні для замовника
- Умови оплати залежать від надходження бюджетних коштів (ризик неотримання)
- Вимоги забезпечення виконання без еквівалентних гарантій замовника
- Умови щодо матеріалів, субпідряду, звітності що обмежують підрядника
Внеси в список ВСІ знайдені умови без обмеження кількості.

ВАЖЛИВО щодо hidden_risks — прихованих фінансових зобов'язань: Уважно перевір чи є в тексті договору ЗОБОВ'ЯЗАННЯ підрядника надати або оплатити документ/послугу, яка відсутня у переліку документів учасника (Додатки 10/11 або аналоги). Типові приклади:
- Страховий поліс БМР (страхування будівельно-монтажних ризиків) — підрядник оплачує страховку об'єкта
- Фінансування проходження експертизи ПКД — порушення ст.837 ЦКУ (витрати несе замовник)
- Щотижнева фото/відеофіксація робіт — прихований операційний обов'язок
- Надання машинозчитувальних форматів при кожному КБ-2в — прихована вимога
Кожне таке зобов'язання вноси до hidden_risks з полем financial_impact (оцінка вартості або "невизначений").

Проаналізуй та поверни JSON:
{{
  "adhesion_contract": bool,
  "adhesion_note": "коментар про договір приєднання та ступінь невигідності",
  "overall_balance": "balanced|slightly_skewed_to_customer|skewed_to_customer|heavily_skewed_to_customer",
  "risk_level": "low|medium|high|critical",
  "law_violations": [
    {{"article": "ст.849 ЦКУ", "description": "...", "contract_clause": "п.X.X", "severity": "high"}}
  ],
  "one_sided_conditions": [
    {{"condition": "...", "impact": "...", "contract_clause": "п.X.X"}}
  ],
  "hidden_risks": [
    {{"risk": "...", "contract_clause": "п.X.X", "financial_impact": "..."}}
  ],
  "appeal_grounds": [
    {{"ground": "...", "legal_basis": "ст.634 ЦКУ", "contract_clause": "п.X.X", "suggested_claim": "..."}}
  ],
  "summary": "загальний висновок 2-3 речення"
}}"""


# _call_opus_with_retry видалено — використовується call_llm з llm_client.py


def _extract_json(text: str) -> dict:
    """
    Витягує JSON з тексту відповіді LLM.

    Шукає перший { та останній } у тексті, парсить вміст між ними.
    При помилці парсингу повертає порожній dict.
    """
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        logger.error(
            "contract_analyzer: JSON не знайдено у відповіді. "
            "Перші 200 символів: %s", text[:200]
        )
        return {}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        # "Extra data" — модель повернула кілька JSON об'єктів підряд; беремо перший
        if 'Extra data' in str(exc):
            try:
                obj, _ = json.JSONDecoder().raw_decode(text, start)
                return obj
            except json.JSONDecodeError:
                pass
        logger.error("contract_analyzer: не вдалось розпарсити JSON: %s", exc)
        return {}


# ── Основна функція ───────────────────────────────────────────────────────────

def analyze(
    docs_dir: Path,
    tender_info: dict,
    qa_analysis: dict,
) -> Optional[dict]:
    """
    Аналізує проект договору в папці тендерних документів.

    Args:
        docs_dir:    Шлях до папки tender_documents з файлами ТД.
        tender_info: Словник з інформацією про закупівлю (з classifier):
                     title, customer_name, expected_value, category,
                     submission_deadline тощо.
        qa_analysis: Результат qa_analyzer.analyze() — використовується для
                     отримання appeal_deadline_original.

    Returns:
        Словник з результатами аналізу договору або None, якщо:
          - файл договору не знайдено (не помилка, просто відсутній)
          - текст не вдалось витягти
          - Opus повернув помилку або невалідний JSON

    Структура результату відповідає секції contract_analysis в analysis.json.
    """
    # ── 1. Знайти файл договору ───────────────────────────────────────────────
    contract_path = find_contract_file(docs_dir)
    if not contract_path:
        logger.info("contract_analyzer: файл договору не знайдено в %s", docs_dir)
        return None

    # ── 2. Витягти текст ──────────────────────────────────────────────────────
    contract_text = extract_text(contract_path)
    if not contract_text or not contract_text.strip():
        logger.warning(
            "contract_analyzer: не вдалось витягти текст з '%s'",
            contract_path.name,
        )
        return None

    logger.info(
        "contract_analyzer: знайдено договір '%s' (%d символів)",
        contract_path.name, len(contract_text),
    )

    is_truncated = len(contract_text) > CONTRACT_TEXT_LIMIT
    if is_truncated:
        logger.warning(
            "contract_analyzer: текст договору '%s' обрізано з %d до %d символів "
            "(CONTRACT_TEXT_LIMIT) — можлива втрата умов у хвості договору",
            contract_path.name, len(contract_text), CONTRACT_TEXT_LIMIT,
        )

    # ── 3. Отримати дедлайн оскарження ───────────────────────────────────────
    # Пріоритет: qa_analysis → розрахунок з submission_deadline
    appeal_deadline: str = (
        qa_analysis.get('appeal_deadline_original')
        or _calculate_appeal_deadline(
            tender_info.get('submission_deadline', '')
        )
    )

    # ── 4. Побудувати промпт і викликати Opus ─────────────────────────────────
    prompt = _build_contract_prompt(
        contract_text=contract_text,
        contract_filename=contract_path.name,
        appeal_deadline=appeal_deadline,
        tender_info=tender_info,
    )

    start_time = time.time()
    try:
        raw_response = call_llm(prompt, role='analysis', max_tokens=None)
    except Exception as e:
        logger.error(
            "contract_analyzer: LLM API помилка після всіх спроб (model=%s): %s",
            get_model('analysis'), e,
        )
        return None

    duration = time.time() - start_time

    if not raw_response:
        logger.error("contract_analyzer: Opus повернув порожню відповідь")
        return None

    # ── 5. Розпарсити JSON ────────────────────────────────────────────────────
    result = _extract_json(raw_response)
    if not result:
        return None

    # ── 6. Додати метаінформацію ──────────────────────────────────────────────
    result['contract_file'] = contract_path.name
    result['appeal_deadline_note'] = (
        f"Зміни до умов договору — через ООПЗ до {appeal_deadline}"
    )
    result['analysis_duration_sec'] = round(duration, 1)
    result['truncated'] = is_truncated

    logger.info(
        "contract_analyzer: завершено. balance=%s, risk=%s, "
        "violations=%d, appeal_grounds=%d, duration=%.1fs",
        result.get('overall_balance', '?'),
        result.get('risk_level', '?'),
        len(result.get('law_violations', [])),
        len(result.get('appeal_grounds', [])),
        duration,
    )

    return result
