"""
Cliente LLM do Bolha.

Interface genérica (`BaseLLMClient`) + implementação Ollama (`OllamaClient`).
Trocar de provedor é criar uma nova subclasse — ex.: `ClaudeAPIClient` — sem
mexer no resto do brain/.

Todas as chamadas pedem `format: 'json'` por padrão: o Ollama força o modelo
a responder em JSON válido, o que alivia o trabalho do intent_parser.
"""
from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger("bolha.brain.llm_client")


@dataclass
class LLMResponse:
    """Resposta normalizada — o brain consome isso, não o dict bruto."""

    text: str                        # conteúdo da resposta (esperado: JSON quando format='json')
    model: str                       # qual modelo gerou
    latency_ms: float                # tempo total da chamada
    raw: dict[str, Any] = field(default_factory=dict)  # payload completo do provedor

    def parse_json(self) -> dict[str, Any]:
        """Decodifica `text` como JSON; levanta `json.JSONDecodeError` se inválido."""
        return json.loads(self.text)


class BaseLLMClient(ABC):
    """Contrato mínimo que todo provedor de LLM precisa cumprir."""

    @abstractmethod
    async def gerar_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Gera uma resposta em modo JSON. Deve retornar texto parseável."""

    @abstractmethod
    async def fechar(self) -> None:
        """Libera recursos (conexões HTTP, etc)."""

    async def __aenter__(self) -> "BaseLLMClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.fechar()


class OllamaClient(BaseLLMClient):
    """Cliente para Ollama local via API HTTP (`/api/generate`)."""

    def __init__(self, config: dict[str, Any]) -> None:
        from ollama import AsyncClient

        bcfg = config["brain"]
        self._host: str = bcfg.get("host", "http://localhost:11434")
        self._model: str = bcfg.get("model", "phi3:mini")
        self._temperature_default: float = float(bcfg.get("temperature", 0.2))
        self._format: str = bcfg.get("format", "json")

        LOGGER.info(
            "OllamaClient pronto (host=%s, model=%s, format=%s, temp=%.2f).",
            self._host,
            self._model,
            self._format,
            self._temperature_default,
        )
        self._client = AsyncClient(host=self._host)

    async def gerar_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        opcoes: dict[str, Any] = {
            "temperature": self._temperature_default if temperature is None else temperature
        }

        inicio = asyncio.get_event_loop().time()
        resposta = await self._client.generate(
            model=self._model,
            prompt=prompt,
            system=system,
            format=self._format,
            options=opcoes,
            stream=False,
        )
        latencia_ms = (asyncio.get_event_loop().time() - inicio) * 1000.0

        # ollama-python 0.6.x devolve objeto pydantic; 0.1.x devolvia dict.
        if hasattr(resposta, "model_dump"):
            raw = resposta.model_dump()
        elif isinstance(resposta, dict):
            raw = resposta
        else:
            raw = dict(resposta)  # fallback

        texto = str(raw.get("response", "")).strip()
        LOGGER.debug("Ollama respondeu em %.0fms: %s", latencia_ms, texto[:200])

        return LLMResponse(
            text=texto,
            model=self._model,
            latency_ms=latencia_ms,
            raw=raw,
        )

    async def fechar(self) -> None:
        # ollama.AsyncClient internamente é um httpx.AsyncClient — fechamos se possível.
        cliente_http = getattr(self._client, "_client", None)
        if cliente_http is not None and hasattr(cliente_http, "aclose"):
            await cliente_http.aclose()


# Exemplo/demo standalone: `python -m src.brain.llm_client`
async def _demo() -> None:
    import sys
    from pathlib import Path

    import yaml

    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

    system = (
        "Você é o Bolha, um assistente pessoal. "
        "Responda SEMPRE com um objeto JSON válido, sem texto fora das chaves."
    )
    prompt = (
        'Devolva um JSON no formato {"saudacao": <string>, "idioma": "pt", "hora_ideal": <string>} '
        "com uma saudação curta em português pra quem acabou de ligar o PC."
    )

    client = OllamaClient(config)
    try:
        print("\n>>> prompt:\n", prompt, "\n")
        resp = await client.gerar_json(prompt, system=system)
        print(f"<<< model={resp.model}  latência={resp.latency_ms:.0f}ms")
        print(f"<<< response:\n{resp.text}\n")
        try:
            parsed = resp.parse_json()
            print(f"<<< parsed: {parsed}")
        except json.JSONDecodeError as exc:
            print(f"!!! JSON inválido: {exc}")
    finally:
        await client.fechar()


if __name__ == "__main__":
    asyncio.run(_demo())
