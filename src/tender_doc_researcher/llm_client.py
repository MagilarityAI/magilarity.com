"""
llm_client.py — Уніфікований LLM клієнт для tender_doc_researcher.

Підтримує три провайдери:
  claude — Claude Opus (analysis) / Sonnet (classification) — default
  openai — GPT-5.1 (analysis) / GPT-5-mini (classification)
  gemini — Gemini 2.5 Flash для обох ролей

Провайдер задається через env:
  LLM_PROVIDER=claude|openai|gemini   (default: claude)
  ANTHROPIC_API_KEY=...
  OPENAI_API_KEY=...
  GEMINI_API_KEY=...

Ролі:
  analysis       — глибокий аналіз ТД, 16+ пунктів (Opus/gpt-5.1/gemini-2.5-flash)
  classification — класифікація, Q&A (Sonnet/gpt-5-mini/gemini-3.1-flash-lite)
"""

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

MODELS: dict[str, dict[str, str]] = {
    'claude': {
        'analysis':       'claude-opus-4-7',
        'classification': 'claude-sonnet-4-6',
    },
    'openai': {
        'analysis':       'gpt-5.1',    # base_analyzer (Call A+B) + contract_analyzer
        'classification': 'gpt-5-mini', # classifier + qa_analyzer
    },
    'gemini': {
        'analysis':       'gemini-2.5-flash',
        'classification': 'gemini-3.1-flash-lite',
    },
}

# Gemini API key routing: analysis uses GEMINI_API_KEY_2 (second account), classification uses GEMINI_API_KEY
_GEMINI_KEY_BY_ROLE: dict[str, str] = {
    'analysis':       'GEMINI_API_KEY_2',
    'classification': 'GEMINI_API_KEY',
}

_VALID_PROVIDERS = frozenset(MODELS)


def _provider() -> str:
    """Читає LLM_PROVIDER з env при кожному виклику (lazy — для сумісності з dotenv)."""
    return os.getenv('LLM_PROVIDER', 'claude').lower()


def get_model(role: str = 'analysis') -> str:
    """Назва моделі для поточного провайдера та ролі."""
    provider_models = MODELS.get(_provider(), MODELS['claude'])
    return provider_models.get(role, provider_models['analysis'])


# ── Claude ────────────────────────────────────────────────────────────────────

def _call_claude(prompt: str, role: str, max_tokens: Optional[int], max_retries: int) -> str:
    import anthropic

    _client = anthropic.Anthropic()
    model = get_model(role)
    # Claude API вимагає max_tokens — якщо None, беремо максимум моделі
    effective_max = max_tokens if max_tokens is not None else 64000

    for attempt in range(max_retries):
        try:
            if role == 'analysis':
                # Opus з adaptive thinking та streaming
                with _client.messages.stream(
                    model=model,
                    max_tokens=effective_max,
                    thinking={"type": "adaptive"},
                    messages=[{"role": "user", "content": prompt}],
                ) as stream:
                    message = stream.get_final_message()
                text = next(
                    (b.text for b in message.content if b.type == "text"),
                    None,
                )
            else:
                # Sonnet — звичайний виклик
                response = _client.messages.create(
                    model=model,
                    max_tokens=effective_max,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.content[0].text if response.content else None

            if text:
                return text
            logger.warning("llm_client[claude]: порожня відповідь (спроба %d)", attempt + 1)
            return ''

        except anthropic.APIError as exc:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            logger.warning(
                "llm_client[claude]: API error спроба %d/%d: %s — retry %ds",
                attempt + 1, max_retries, exc, wait,
            )
            time.sleep(wait)

    return ''


# ── OpenAI ────────────────────────────────────────────────────────────────────

def _call_openai(prompt: str, role: str, max_tokens: Optional[int], max_retries: int) -> str:
    from openai import OpenAI, RateLimitError, APIError as OpenAIAPIError

    _client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    model = get_model(role)

    # gpt-5-mini: no temperature (only default=1), json_object mode requires "json" in prompt
    create_kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if max_tokens is not None:
        create_kwargs["max_completion_tokens"] = max_tokens
    if 'json' in prompt.lower():
        create_kwargs["response_format"] = {"type": "json_object"}
    if 'mini' not in model:
        create_kwargs["temperature"] = 0.1

    for attempt in range(max_retries):
        try:
            response = _client.chat.completions.create(**create_kwargs)
            return response.choices[0].message.content or ''

        except RateLimitError:
            wait = (attempt + 1) * 30
            logger.warning(
                "llm_client[openai]: rate limit спроба %d/%d — retry %ds",
                attempt + 1, max_retries, wait,
            )
            time.sleep(wait)

        except OpenAIAPIError as exc:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            logger.warning(
                "llm_client[openai]: API error спроба %d/%d: %s — retry %ds",
                attempt + 1, max_retries, exc, wait,
            )
            time.sleep(wait)

    return ''


# ── Gemini ────────────────────────────────────────────────────────────────────

def _call_gemini(prompt: str, role: str, max_tokens: Optional[int], max_retries: int) -> str:
    from google import genai
    from google.genai import types

    api_key_name = _GEMINI_KEY_BY_ROLE.get(role, 'GEMINI_API_KEY')
    api_key = os.getenv(api_key_name) or os.getenv('GEMINI_API_KEY')
    _client = genai.Client(api_key=api_key)
    model = get_model(role)

    config_kwargs: dict = {
        "temperature": 0.5,
        "response_mime_type": "application/json",
    }
    if max_tokens is not None:
        config_kwargs["max_output_tokens"] = max_tokens
    config = types.GenerateContentConfig(**config_kwargs)

    for attempt in range(max_retries):
        try:
            response = _client.models.generate_content(
                model=model,
                config=config,
                contents=prompt,
            )
            return response.text or ''

        except Exception as exc:
            # ResourceExhausted (429) або ServiceUnavailable (503) — довгий backoff
            exc_str = str(exc)
            is_long_wait = (
                'ResourceExhausted' in type(exc).__name__
                or '429' in exc_str
                or 'ServiceUnavailable' in type(exc).__name__
                or '503' in exc_str
                or 'UNAVAILABLE' in exc_str.upper()
            )
            wait = (attempt + 1) * 30 if is_long_wait else 2 ** attempt
            if attempt == max_retries - 1:
                raise
            logger.warning(
                "llm_client[gemini]: error спроба %d/%d: %s — retry %ds",
                attempt + 1, max_retries, exc, wait,
            )
            time.sleep(wait)

    return ''


# ── Публічний API ─────────────────────────────────────────────────────────────

def call_llm(
    prompt: str,
    role: str = 'analysis',
    max_tokens: Optional[int] = 16000,
    max_retries: int = 13,
) -> str:
    """
    Уніфікований виклик LLM — прозоро перемикається між Claude/OpenAI/Gemini.

    Args:
        prompt:      Повний промпт (всі інструкції + дані в одному рядку).
        role:        'analysis' | 'classification'
        max_tokens:  Максимум токенів у відповіді.
        max_retries: Кількість повторів при помилці API.

    Returns:
        Текстова відповідь LLM або '' при невдачі.

    Raises:
        ValueError:  При невідомому LLM_PROVIDER.
        Exception:   Пропагується від провайдера після вичерпання спроб.
    """
    provider = _provider()

    if provider not in _VALID_PROVIDERS:
        raise ValueError(
            f"Невідомий LLM_PROVIDER='{provider}'. "
            f"Допустимі: {', '.join(sorted(_VALID_PROVIDERS))}"
        )

    model = get_model(role)
    api_key_info = _GEMINI_KEY_BY_ROLE.get(role, 'GEMINI_API_KEY') if provider == 'gemini' else ''
    logger.info(
        "llm_client: provider=%s model=%s role=%s key=%s max_tokens=%s prompt_len=%d",
        provider, model, role, api_key_info or '-',
        str(max_tokens) if max_tokens is not None else 'unlimited',
        len(prompt),
    )

    if provider == 'claude':
        return _call_claude(prompt, role, max_tokens, max_retries)
    if provider == 'openai':
        return _call_openai(prompt, role, max_tokens, max_retries)
    return _call_gemini(prompt, role, max_tokens, max_retries)
