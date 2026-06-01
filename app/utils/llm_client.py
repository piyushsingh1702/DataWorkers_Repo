"""LLM client wrapper for Compass API (Core42)."""

import json
import logging

from openai import OpenAI

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Model constants
MODEL_GPT4 = "gpt-4.1"  # Use for most tasks
MODEL_GPT5 = "gpt-5.1"  # Use only for complex reasoning steps


def get_llm_client():
    """Get the Compass API client."""
    return OpenAI(
        api_key=settings.compass_api_key,
        base_url=settings.base_url,
    )


def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.2, use_complex_model: bool = False) -> str:
    """Call the LLM and return the response text.
    
    Args:
        system_prompt: System prompt for the LLM.
        user_prompt: User prompt for the LLM.
        temperature: Sampling temperature.
        use_complex_model: If True, uses GPT-5.1 for complex reasoning. Otherwise uses GPT-4.1.
    """
    client = get_llm_client()
    model = MODEL_GPT5 if use_complex_model else MODEL_GPT4

    logger.info(f"Calling LLM ({model}) with {len(user_prompt)} char prompt")

    token_kwarg = {"max_completion_tokens": 4096} if use_complex_model else {"max_tokens": 4096}
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        **token_kwarg,
    )

    return response.choices[0].message.content or ""


def call_llm_json(system_prompt: str, user_prompt: str, temperature: float = 0.1, use_complex_model: bool = False) -> dict | list:
    """Call the LLM expecting a JSON response. Parses and returns the JSON.
    
    Args:
        system_prompt: System prompt for the LLM.
        user_prompt: User prompt for the LLM.
        temperature: Sampling temperature.
        use_complex_model: If True, uses GPT-5.1 for complex reasoning. Otherwise uses GPT-4.1.
    """
    client = get_llm_client()
    model = MODEL_GPT5 if use_complex_model else MODEL_GPT4

    logger.info(f"Calling LLM JSON ({model}) with {len(user_prompt)} char prompt")

    token_kwarg = {"max_completion_tokens": 4096} if use_complex_model else {"max_tokens": 4096}
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
        **token_kwarg,
    )

    content = response.choices[0].message.content or ""
    return json.loads(content)
