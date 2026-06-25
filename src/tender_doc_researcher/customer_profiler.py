import logging
import os

import psycopg2

logger = logging.getLogger(__name__)


def get_customer_profile(edrpou: str) -> dict:
    """Отримує профіль замовника за ЄДРПОУ з APPDB (часткова реалізація).

    Наразі повертає кількість рішень ООПЗ проти замовника.
    Повна реалізація — після обробки всіх рішень ООПЗ та інтеграції з Юконтрол.
    """
    oopz_count = 0
    conn = None
    try:
        conn = psycopg2.connect(
            host='localhost',
            port=5432,
            database=os.getenv('POSTGRES_DB', 'appdb'),
            user=os.getenv('POSTGRES_USER', 'user'),
            password=os.getenv('POSTGRES_PASSWORD', 'pass'),
        )
        with conn.cursor() as cur:
            cur.execute(
                'SELECT COUNT(*) FROM oopz_decisions WHERE customer_edrpou = %s',
                (edrpou,),
            )
            row = cur.fetchone()
            oopz_count = int(row[0]) if row else 0
    except Exception as exc:
        logger.error('customer_profiler: помилка отримання даних ООПЗ для %s: %s', edrpou, exc)
        oopz_count = 0
    finally:
        if conn is not None:
            conn.close()

    return {
        'edrpou': edrpou,
        'oopz_decisions_count': oopz_count,
        'oopz_analysis': 'pending_full_implementation',
        'court_decisions': 'pending_yucontrol_integration',
        'procurement_stats': 'pending_implementation',
        'reputation_score': None,
        'implementation_status': 'partial',
        'note': 'Повна реалізація після обробки всіх рішень ООПЗ та інтеграції з Юконтрол',
    }
