"""
Intent Parser — transforma texto do usuário em ação estruturada.

Manda o texto pro LLM com o system prompt de intents, valida a resposta
com Pydantic e faz retry automático se o JSON vier inválido.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from src.brain.llm_client import BaseLLMClient
from src.brain.prompts import INTENT_USER_TEMPLATE, SYSTEM_INTENT

LOGGER = logging.getLogger("bolha.brain.intent_parser")

MAX_RETRIES = 3


class IntentResponse(BaseModel):
    """Modelo Pydantic que valida a saída JSON do LLM."""

    intent: str = Field(description="Nome da ação identificada.")
    params: dict[str, Any] = Field(default_factory=dict, description="Parâmetros da ação.")
    confidence: float = Field(ge=0.0, le=1.0, description="Confiança de 0.0 a 1.0.")
    destructive: bool = Field(default=False, description="Se a ação é destrutiva.")


def _not_understood(motivo: str) -> IntentResponse:
    return IntentResponse(
        intent="not_understood",
        params={"reason": motivo},
        confidence=0.0,
        destructive=False,
    )


class IntentParser:
    """Envia texto pro LLM, valida com Pydantic, retenta até MAX_RETRIES."""

    def __init__(self, llm_client: BaseLLMClient) -> None:
        self._llm = llm_client

    async def interpretar(self, texto: str) -> IntentResponse:
        """Recebe texto do usuário e devolve IntentResponse validado."""
        if not texto or not texto.strip():
            return _not_understood("texto vazio")

        prompt = INTENT_USER_TEMPLATE.format(texto=texto)
        ultimo_erro: str = ""

        for tentativa in range(1, MAX_RETRIES + 1):
            try:
                resp = await self._llm.gerar_json(prompt, system=SYSTEM_INTENT)
                parsed = resp.parse_json()
                intent = IntentResponse.model_validate(parsed)
                LOGGER.info(
                    "Intent parsed (tentativa %d/%d, %.0fms): intent=%s confidence=%.2f destructive=%s",
                    tentativa,
                    MAX_RETRIES,
                    resp.latency_ms,
                    intent.intent,
                    intent.confidence,
                    intent.destructive,
                )
                return intent

            except (ValidationError, ValueError, KeyError) as exc:
                ultimo_erro = str(exc)
                LOGGER.warning(
                    "Tentativa %d/%d — JSON inválido ou validação falhou: %s",
                    tentativa,
                    MAX_RETRIES,
                    ultimo_erro,
                )

            except Exception as exc:  # noqa: BLE001
                ultimo_erro = str(exc)
                LOGGER.exception(
                    "Tentativa %d/%d — erro inesperado na chamada ao LLM: %s",
                    tentativa,
                    MAX_RETRIES,
                    ultimo_erro,
                )

        LOGGER.error(
            "Todas as %d tentativas falharam. Último erro: %s",
            MAX_RETRIES,
            ultimo_erro,
        )
        return _not_understood(f"falha após {MAX_RETRIES} tentativas: {ultimo_erro}")
