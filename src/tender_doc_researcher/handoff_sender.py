#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Передача handoff від tender_doc_researcher до bid_researcher.

Записує в agent_memory.agent_handoffs:
  - чеклист документів (document_blocks → плоский список items)
  - шлях до папки з файлами ТД (td_documents_path)
  - метадані тендера (tender_internal_id, tender_public_id, cpv_code)
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras


logger = logging.getLogger(__name__)


def send_handoff(
    internal_id: str,
    public_id: str,
    analysis: dict,
    td_documents_path: str,
    cpv_code: str = "",
) -> Optional[str]:
    """
    Створює або оновлює handoff для bid_researcher в agent_memory.

    Args:
        internal_id:        UUID закупівлі Prozorro
        public_id:          Публічний номер (UA-2026-...)
        analysis:           Результат аналізу ТД (з document_blocks)
        td_documents_path:  Абсолютний шлях до папки з файлами ТД
        cpv_code:           ДК код закупівлі (для category routing в bid_researcher)

    Returns:
        handoff_id (UUID рядок) або None при помилці
    """
    checklist = _build_checklist(analysis.get("document_blocks", []))

    winner_checklist = _build_winner_checklist(analysis.get("document_blocks", []))

    context_data = {
        "tender_internal_id": internal_id,
        "tender_public_id": public_id,
        "cpv_code": cpv_code,
        "checklist": checklist,
        "winner_checklist": winner_checklist,
        "td_documents_path": td_documents_path,
    }

    conn = _get_memory_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SET search_path TO agent_memory")

            # Якщо вже є pending → оновлюємо context_data
            cur.execute(
                """
                SELECT handoff_id::text
                FROM agent_handoffs
                WHERE from_agent_id = 'tender_doc_researcher'
                  AND to_agent_id   = 'bid_researcher'
                  AND status        = 'pending'
                  AND context_data->>'tender_internal_id' = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (internal_id,),
            )
            row = cur.fetchone()

            if row:
                handoff_id = row[0]
                cur.execute(
                    """
                    UPDATE agent_handoffs
                    SET context_data = %s::jsonb,
                        updated_at   = NOW()
                    WHERE handoff_id = %s::uuid
                    """,
                    (json.dumps(context_data, ensure_ascii=False), handoff_id),
                )
                logger.info(
                    "handoff оновлено: handoff_id=%s, checklist=%d, td_path=%s",
                    handoff_id, len(checklist), td_documents_path,
                )
            else:
                cur.execute(
                    """
                    INSERT INTO agent_handoffs
                        (from_agent_id, to_agent_id, status, handoff_reason,
                         context_data, created_at)
                    VALUES
                        ('tender_doc_researcher', 'bid_researcher', 'pending',
                         %s, %s::jsonb, NOW())
                    RETURNING handoff_id::text
                    """,
                    (
                        "Передача чеклиста документів пропозиції від "
                        "tender_doc_researcher до bid_researcher",
                        json.dumps(context_data, ensure_ascii=False),
                    ),
                )
                handoff_id = cur.fetchone()[0]
                logger.info(
                    "handoff створено: handoff_id=%s, checklist=%d пунктів, td_path=%s",
                    handoff_id, len(checklist), td_documents_path,
                )

        conn.commit()
        return handoff_id

    except Exception as exc:
        logger.error("Помилка при збереженні handoff: %s", exc, exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        return None
    finally:
        conn.close()


def _build_checklist(document_blocks: list) -> list:
    """
    Конвертує document_blocks (з analysis.json) у плоский список для bid_researcher.

    Кожен елемент:
      item_key    — "B01_item1" (унікальний ідентифікатор)
      block_id    — "B01"
      block_name  — "Технічна пропозиція"
      item_num    — 1
      item_name   — назва документу (поле 'document')
      td_quote    — цитата з ТД
      td_reference — посилання на пункт ТД
      note        — примітка
      is_hidden   — bool
      risk_flag   — bool
      requires_content_verification — bool: bid_researcher має глибоко звірити вміст
                    файлу з вимогою ТД сильною моделлю (ст.16/БГ/техспека — обов'язково)
      verification_focus — що саме звіряти (поля/пороги з ТД) або None

    Включає тільки stage = 'proposal' (документи пропозиції).
    Документи переможця (winner_4days, winner_signing) — не входять.
    """
    checklist: list = []
    global_num = 0

    for block in document_blocks:
        if not isinstance(block, dict):
            continue

        # Пропускаємо документи переможця — bid_researcher їх не перевіряє
        stage = block.get("stage", "proposal")
        if stage not in ("proposal", ""):
            continue

        block_id = block.get("block_id", "")
        block_name = block.get("block_name", "")
        items = block.get("items", [])

        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue

            global_num += 1
            item_num = item.get("num", global_num)
            item_key = f"{block_id}_item{item_num}"

            checklist.append({
                "item_key":     item_key,
                "block_id":     block_id,
                "block_name":   block_name,
                "item_num":     item_num,
                "item_name":    item.get("document", ""),
                "td_quote":     item.get("quote", ""),
                "td_reference": item.get("td_reference", ""),
                "note":         item.get("note", ""),
                "is_hidden":    bool(item.get("is_hidden", False)),
                "risk_flag":    bool(item.get("risk_flag", False)),
                # Прапорець глибокої звірки вмісту для bid_researcher (ст.16/БГ/техспека)
                "requires_content_verification": bool(item.get("requires_content_verification", False)),
                "verification_focus": item.get("verification_focus") or None,
            })

    return checklist


def _build_winner_checklist(document_blocks: list) -> list:
    """
    Аналогічно _build_checklist але для stage winner/winner_4days/winner_signing.
    Повертає чеклист вимог до документів переможця.
    block_id отримує префікс "BW" щоб не конфліктувати з proposal "B0X".
    """
    checklist: list = []
    global_num = 0
    winner_stages = {"winner", "winner_4days", "winner_signing"}

    for block in document_blocks:
        if not isinstance(block, dict):
            continue
        stage = block.get("stage", "proposal")
        if stage not in winner_stages:
            continue

        raw_block_id = block.get("block_id", "")
        # Додаємо префікс "W" якщо block_id не починається з "BW"
        block_id = raw_block_id if raw_block_id.startswith("BW") else f"BW{raw_block_id.lstrip('B')}"
        block_name = block.get("block_name", "")
        items = block.get("items", [])

        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue
            global_num += 1
            item_num = item.get("num", global_num)
            item_key = f"{block_id}_item{item_num}"
            checklist.append({
                "item_key":     item_key,
                "block_id":     block_id,
                "block_name":   block_name,
                "item_num":     item_num,
                "item_name":    item.get("document", ""),
                "td_quote":     item.get("quote", ""),
                "td_reference": item.get("td_reference", ""),
                "note":         item.get("note", ""),
                "is_hidden":    bool(item.get("is_hidden", False)),
                "risk_flag":    bool(item.get("risk_flag", False)),
                "stage":        stage,
            })

    return checklist


def _get_memory_conn():
    """Підключення до magilarity_agent_memory."""
    return psycopg2.connect(
        dbname=os.getenv("MEMORY_DB_NAME", "magilarity_agent_memory"),
        host=os.getenv("MEMORY_DB_HOST", "localhost"),
        port=int(os.getenv("MEMORY_DB_PORT", 5432)),
        user=os.getenv("MEMORY_DB_USER", os.getenv("POSTGRES_USER", "user")),
        password=os.getenv("MEMORY_DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", "pass")),
    )
