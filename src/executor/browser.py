"""
Browser Manager — abre URLs e faz pesquisas no Google.

Usa webbrowser.open() pra abrir no navegador padrão do sistema.
Pesquisas constroem a query string pro Google.
"""
from __future__ import annotations

import asyncio
import logging
import webbrowser
from urllib.parse import quote_plus
from typing import Any

from src.executor.router import ActionResult

LOGGER = logging.getLogger("bolha.executor.browser")

GOOGLE_SEARCH_URL = "https://www.google.com/search?q="


class BrowserManager:
    """Handler de abertura de URLs e pesquisas no navegador."""

    def __init__(self, config: dict[str, Any]) -> None:
        _ = config  # reservado pra configurações futuras
        LOGGER.info("BrowserManager pronto.")

    def handlers(self) -> dict[str, Any]:
        """Retorna mapa intent → handler pra registrar no router."""
        return {
            "browser_open": self.browser_open,
            "browser_search": self.browser_search,
        }

    async def browser_open(self, params: dict[str, Any]) -> ActionResult:
        """Abre uma URL no navegador padrão."""
        url = params.get("url", "")
        if not url:
            return ActionResult(
                False, "URL não especificada.", "browser_open", params,
            )

        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        LOGGER.info("Abrindo URL: '%s'", url)

        def _abrir() -> tuple[bool, str]:
            try:
                webbrowser.open(url)
                return True, f"Abrindo {url} no navegador."
            except webbrowser.Error as exc:
                return False, f"Erro ao abrir URL: {exc}"

        try:
            success, msg = await asyncio.to_thread(_abrir)
            return ActionResult(success=success, message=msg, intent="browser_open", params=params)
        except Exception as exc:  # noqa: BLE001
            msg = f"Erro inesperado ao abrir URL: {exc}"
            LOGGER.exception(msg)
            return ActionResult(success=False, message=msg, intent="browser_open", params=params)

    async def browser_search(self, params: dict[str, Any]) -> ActionResult:
        """Pesquisa no Google abrindo a query string no navegador."""
        query = params.get("query", "")
        if not query:
            return ActionResult(
                False, "Termo de pesquisa não especificado.", "browser_search", params,
            )

        url = GOOGLE_SEARCH_URL + quote_plus(query)
        LOGGER.info("Pesquisando: '%s' → %s", query, url)

        def _pesquisar() -> tuple[bool, str]:
            try:
                webbrowser.open(url)
                return True, f"Pesquisando '{query}' no Google."
            except webbrowser.Error as exc:
                return False, f"Erro ao pesquisar: {exc}"

        try:
            success, msg = await asyncio.to_thread(_pesquisar)
            return ActionResult(success=success, message=msg, intent="browser_search", params=params)
        except Exception as exc:  # noqa: BLE001
            msg = f"Erro inesperado ao pesquisar: {exc}"
            LOGGER.exception(msg)
            return ActionResult(success=False, message=msg, intent="browser_search", params=params)
