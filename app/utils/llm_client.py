"""LLM client wrapper for OpenAI / Azure OpenAI."""

import json
import logging

from openai import OpenAI, AzureOpenAI

from app.config.settings import settings

logger = logging.getLogger(__name__)


def get_llm_client():
    """Get the appropriate OpenAI client based on configuration."""
    if settings.use_azure:
        return AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version="2024-08-01-preview",
        )
    return OpenAI(api_key=settings.openai_api_key)


def get_model_name() -> str:
    """Get the model name to use."""
    if settings.use_azure:
        return settings.azure_openai_deployment
    return "gpt-4o"


def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    """Call the LLM and return the response text."""
    client = get_llm_client()
    model = get_model_name()

    logger.info(f"Calling LLM ({model}) with {len(user_prompt)} char prompt")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=4096,
    )

    return response.choices[0].message.content


def call_llm_json(system_prompt: str, user_prompt: str, temperature: float = 0.1) -> dict | list:
    """Call the LLM expecting a JSON response. Parses and returns the JSON."""
    client = get_llm_client()
    model = get_model_name()

    logger.info(f"Calling LLM JSON ({model}) with {len(user_prompt)} char prompt")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    return json.loads(content)
