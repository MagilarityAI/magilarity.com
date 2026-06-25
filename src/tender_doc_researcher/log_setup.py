"""
log_setup.py — Налаштування логування для tender_doc_researcher.

Два рівні:
  1. Per-run лог: logs/{public_id}_{YYYYMMDD_HHMMSS}.log — всі INFO+ повідомлення
  2. errors.log:  logs/errors.log — тільки ERROR+ (rotating, 5MB x 3 файли)

Використання в main.py:
    run_ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_handler = setup_run_logger(public_id, run_ts)
    try:
        ...pipeline...
    finally:
        teardown_run_logger(run_handler)
"""

import logging
import logging.handlers
from pathlib import Path

LOGS_DIR = Path(__file__).parent / 'logs'
AGENT_LOGGER = 'agents.implementations.tender_doc_researcher'

_FMT = '%(asctime)s.%(msecs)03d %(levelname)-8s [%(module)s] %(message)s'
_DATE_FMT = '%Y-%m-%d %H:%M:%S'

_errors_handler: logging.Handler | None = None


def _ensure_errors_handler() -> None:
    """Ініціалізує errors.log handler один раз за процес."""
    global _errors_handler
    if _errors_handler is not None:
        return

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(
        LOGS_DIR / 'errors.log',
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8',
    )
    h.setLevel(logging.ERROR)
    h.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))
    _errors_handler = h

    parent = logging.getLogger(AGENT_LOGGER)
    parent.addHandler(h)
    if parent.level == logging.NOTSET:
        parent.setLevel(logging.DEBUG)


def setup_run_logger(public_id: str, run_ts: str) -> logging.FileHandler:
    """
    Додає FileHandler для конкретного прогону аналізу.

    Файл: logs/{public_id}_{YYYYMMDD_HHMMSS}.log
    Повертає handler — передати в teardown_run_logger після завершення.
    """
    _ensure_errors_handler()

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f'{public_id}_{run_ts}.log'

    h = logging.FileHandler(log_file, encoding='utf-8')
    h.setLevel(logging.DEBUG)
    h.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))

    parent = logging.getLogger(AGENT_LOGGER)
    parent.addHandler(h)
    if parent.level == logging.NOTSET:
        parent.setLevel(logging.DEBUG)

    return h


def teardown_run_logger(handler: logging.FileHandler) -> None:
    """Видаляє per-run handler і закриває файл."""
    parent = logging.getLogger(AGENT_LOGGER)
    parent.removeHandler(handler)
    handler.close()


def log_run_summary(
    logger: logging.Logger,
    public_id: str,
    internal_id: str,
    category: str,
    verdict: str,
    risk_level: str,
    duration_sec: float,
    errors: list[str],
    reports: dict,
) -> None:
    """Записує підсумковий блок в кінці лог-файлу."""
    sep = '═' * 60
    report_names = ', '.join(reports.keys()) if reports else '—'
    err_summary = f'{len(errors)} помилок' if errors else 'без помилок'
    lines = [
        sep,
        f'  РЕЗУЛЬТАТ: {public_id}',
        f'  internal:  {internal_id}',
        f'  Категорія: {category}',
        f'  Вердикт:   {verdict} ({risk_level})',
        f'  Тривалість:{duration_sec}s  |  {err_summary}',
        f'  Звіти:     {report_names}',
    ]
    if errors:
        lines.append('  Деталі помилок:')
        for e in errors:
            lines.append(f'    • {e}')
    lines.append(sep)

    for line in lines:
        logger.info(line)
