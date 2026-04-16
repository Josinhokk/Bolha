"""
Router de ações — direciona IntentResponse pro handler correto.

Recebe a intent do brain, busca o handler registrado e executa com
asyncio.wait_for(timeout) conforme config.yaml.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

LOGGER = logging.getLogger("bolha.executor.router")


@dataclass
class ActionResult:
    """Resultado padronizado de qualquer ação executada."""

    success: bool
    message: str
    intent: str
    params: dict[str, Any]


ActionHandler = Callable[[dict[str, Any]], Awaitable[ActionResult]]


class ActionRouter:
    """Mapeia intents → handlers e executa com timeout."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._handlers: dict[str, ActionHandler] = {}

        timeouts = config.get("executor", {}).get("timeouts", {})
        self._timeout_default: float = float(timeouts.get("default", 10))
        self._timeouts: dict[str, float] = {
            "file_create": float(timeouts.get("file_operation", 15)),
            "file_delete": float(timeouts.get("file_operation", 15)),
            "file_move": float(timeouts.get("file_operation", 15)),
            "file_copy": float(timeouts.get("file_operation", 15)),
            "file_list": float(timeouts.get("file_operation", 15)),
            "folder_create": float(timeouts.get("file_operation", 15)),
            "folder_delete": float(timeouts.get("file_operation", 15)),
            "open_app": float(timeouts.get("app_launch", 20)),
            "close_app": float(timeouts.get("app_launch", 20)),
            "browser_open": float(timeouts.get("browser", 15)),
            "browser_search": float(timeouts.get("browser", 15)),
            "system_info": float(timeouts.get("system_cmd", 10)),
            "system_volume": float(timeouts.get("system_cmd", 10)),
            "system_shutdown": float(timeouts.get("system_cmd", 10)),
        }

        LOGGER.info(
            "ActionRouter pronto (timeout_default=%.0fs, %d timeouts específicos).",
            self._timeout_default,
            len(self._timeouts),
        )

    def registrar(self, intent: str, handler: ActionHandler) -> None:
        """Registra um handler pra uma intent."""
        self._handlers[intent] = handler
        LOGGER.debug("Handler registrado: %s", intent)

    def registrar_varios(self, mapa: dict[str, ActionHandler]) -> None:
        """Registra vários handlers de uma vez."""
        for intent, handler in mapa.items():
            self.registrar(intent, handler)

    async def executar(self, intent: str, params: dict[str, Any]) -> ActionResult:
        """Busca o handler da intent e executa com timeout."""
        if intent in ("conversation", "not_understood"):
            return ActionResult(
                success=True,
                message="",
                intent=intent,
                params=params,
            )

        handler = self._handlers.get(intent)
        if handler is None:
            LOGGER.warning("Nenhum handler registrado para intent '%s'.", intent)
            return ActionResult(
                success=False,
                message=f"Ação '{intent}' ainda não implementada.",
                intent=intent,
                params=params,
            )

        timeout = self._timeouts.get(intent, self._timeout_default)
        LOGGER.info("Executando '%s' (timeout=%.0fs) params=%s", intent, timeout, params)

        try:
            result = await asyncio.wait_for(handler(params), timeout=timeout)
            LOGGER.info("'%s' concluído: success=%s msg='%s'", intent, result.success, result.message)
            return result
        except asyncio.TimeoutError:
            msg = f"Ação '{intent}' excedeu o timeout de {timeout:.0f}s."
            LOGGER.error(msg)
            return ActionResult(success=False, message=msg, intent=intent, params=params)
        except Exception as exc:  # noqa: BLE001
            msg = f"Erro ao executar '{intent}': {exc}"
            LOGGER.exception(msg)
            return ActionResult(success=False, message=msg, intent=intent, params=params)
