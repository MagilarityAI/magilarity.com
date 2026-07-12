"""
registry.py — Реєстр проаналізованих тендерів для tender_doc_researcher.

Зберігає облік та забезпечує перевірку дублів.
Файли реєстру:
    output/tender_analysis/registry.json  — машинний формат
    output/tender_analysis/registry.xlsx  — Excel для користувача
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import openpyxl

logger = logging.getLogger(__name__)

REGISTRY_DIR = Path(__file__).parent.parent.parent.parent / 'output' / 'tender_analysis'
REGISTRY_JSON = REGISTRY_DIR / 'registry.json'
REGISTRY_XLSX = REGISTRY_DIR / 'registry.xlsx'

XLSX_HEADERS = [
    'public_id', 'internal_id', 'customer', 'dk_code', 'subject',
    'expected_value', 'analyzed_at', 'category', 'verdict', 'short_summary', 'folder_path',
    'lot_id', 'lot_title',
]


def _load_registry() -> dict:
    """Завантажує registry.json. Якщо файл не існує — повертає порожній dict."""
    if not REGISTRY_JSON.exists():
        return {}
    try:
        with open(REGISTRY_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Помилка читання registry.json: {e}")
        return {}


def _save_registry(registry: dict) -> None:
    """Зберігає registry.json та синхронізує registry.xlsx."""
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_JSON, 'w', encoding='utf-8') as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
    _sync_xlsx(registry)


def _sync_xlsx(registry: dict) -> None:
    """Синхронізує registry.xlsx з поточним станом реєстру."""
    try:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Реєстр'
        ws.append(XLSX_HEADERS)
        for entry in registry.values():
            row = [entry.get(col, '') for col in XLSX_HEADERS]
            ws.append(row)
        wb.save(str(REGISTRY_XLSX))
    except Exception as e:
        logger.error(f"Помилка синхронізації registry.xlsx: {e}")


def _registry_key(public_id: str, lot_suffix: Optional[str] = None) -> str:
    """
    Ключ запису реєстру. Однолотові закупівлі (lot_suffix=None) — ключ БЕЗ змін
    (public_id), для повної сумісності зі старим форматом реєстру. Мультилотові —
    'UA-...:lot1' тощо (К4 аудиту, CLAUDE.md «Правило щодо лотів — ФІНАЛЬНО»:
    окремий запис реєстру на кожен лот).
    """
    return f"{public_id}:{lot_suffix}" if lot_suffix else public_id


def is_tender_analyzed(public_id: str, lot_suffix: Optional[str] = None) -> Optional[dict]:
    """
    Перевіряє чи тендер (або конкретний лот) вже проаналізований.

    Args:
        public_id:  Публічний ідентифікатор тендера (наприклад, UA-2024-01-01-000001-a).
        lot_suffix: Опціонально — суфікс лоту (наприклад 'lot1'). Якщо None —
                    перевіряється однолотовий/без-лотовий запис (як раніше).

    Returns:
        Запис реєстру якщо тендер вже аналізувався, або None.
    """
    registry = _load_registry()
    return registry.get(_registry_key(public_id, lot_suffix))


def register_tender(
    public_id: str,
    internal_id: str,
    customer: str,
    dk_code: str,
    subject: str,
    expected_value,
    category: str,
    folder_path: str,
    verdict: str = '',
    short_summary: str = '',
    lot_suffix: Optional[str] = None,
    lot_id: Optional[str] = None,
    lot_title: Optional[str] = None,
) -> dict:
    """
    Додає або оновлює запис тендера (або одного лоту) у реєстрі.

    Args:
        public_id:      Публічний ідентифікатор тендера.
        internal_id:    Внутрішній ідентифікатор.
        customer:       Замовник.
        dk_code:        Код ДК 021:2015.
        subject:        Предмет закупівлі.
        expected_value: Очікувана вартість.
        category:       Категорія (одна з 13 категорій ДК).
        folder_path:    Шлях до папки з документами тендера (або лоту).
        verdict:        Висновок аналізу (опціонально).
        short_summary:  Короткий підсумок аналізу (опціонально).
        lot_suffix:     Опціонально — суфікс лоту для ключа реєстру ('lot1').
                        None (за замовчуванням) → однолотова поведінка без змін.
        lot_id:         Опціонально — id лоту з Prozorro (для довідки в записі).
        lot_title:      Опціонально — назва лоту.

    Returns:
        Створений або оновлений запис реєстру.
    """
    registry = _load_registry()
    key = _registry_key(public_id, lot_suffix)
    entry = {
        'public_id': public_id,
        'internal_id': internal_id,
        'customer': customer,
        'dk_code': dk_code,
        'subject': subject,
        'expected_value': expected_value,
        'analyzed_at': datetime.now().isoformat(),
        'category': category,
        'verdict': verdict,
        'short_summary': short_summary,
        'folder_path': folder_path,
        'lot_id': lot_id or '',
        'lot_title': lot_title or '',
    }
    registry[key] = entry
    _save_registry(registry)
    logger.info(f"Тендер зареєстровано: {key}")
    return entry


def update_verdict(public_id: str, verdict: str, short_summary: str) -> None:
    """
    Оновлює verdict та short_summary існуючого запису після завершення аналізу.

    Args:
        public_id:     Публічний ідентифікатор тендера.
        verdict:       Висновок аналізу.
        short_summary: Короткий підсумок аналізу.

    Raises:
        KeyError: Якщо тендер з таким public_id не знайдено у реєстрі.
    """
    registry = _load_registry()
    if public_id not in registry:
        raise KeyError(f"Тендер {public_id!r} не знайдено у реєстрі")
    registry[public_id]['verdict'] = verdict
    registry[public_id]['short_summary'] = short_summary
    _save_registry(registry)
    logger.info(f"Вердикт оновлено для тендера: {public_id}")


def list_analyzed() -> list:
    """
    Повертає список всіх записів реєстру.

    Returns:
        Список словників з даними по кожному проаналізованому тендеру.
    """
    registry = _load_registry()
    return list(registry.values())
