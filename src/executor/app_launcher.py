"""
App Launcher — abre e fecha programas pelo nome.

Usa subprocess.Popen pra abrir apps e taskkill pra fechar.
Mapeamento de aliases PT-BR → executável vem do config.yaml.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Any

from src.executor.router import ActionResult

LOGGER = logging.getLogger("bolha.executor.app_launcher")


class AppLauncher:
    """Handler de abertura/fechamento de apps via subprocess."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._aliases: dict[str, str] = (
            config.get("executor", {}).get("app_aliases", {})
        )
        LOGGER.info(
            "AppLauncher pronto (%d aliases carregados).", len(self._aliases),
        )

    def handlers(self) -> dict[str, Any]:
        """Retorna mapa intent → handler pra registrar no router."""
        return {
            "open_app": self.open_app,
            "close_app": self.close_app,
        }

    def _resolver_app(self, nome: str) -> str:
        """Resolve alias PT-BR pro nome real do executável."""
        chave = nome.strip().lower()
        return self._aliases.get(chave, chave)

    async def open_app(self, params: dict[str, Any]) -> ActionResult:
        """Abre um programa pelo nome usando subprocess.Popen."""
        app_name = params.get("app_name", "")
        if not app_name:
            return ActionResult(
                False, "Nome do programa não especificado.", "open_app", params,
            )

        executavel = self._resolver_app(app_name)
        LOGGER.info("Abrindo app: '%s' (executável: '%s')", app_name, executavel)

        def _abrir() -> tuple[bool, str]:
            try:
                subprocess.Popen(
                    [executavel],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.DETACHED_PROCESS,
                )
                return True, f"Programa '{app_name}' aberto."
            except FileNotFoundError:
                return False, f"Programa '{app_name}' não encontrado. Verifique se está instalado."
            except OSError as exc:
                return False, f"Erro ao abrir '{app_name}': {exc}"

        try:
            success, msg = await asyncio.to_thread(_abrir)
            return ActionResult(success=success, message=msg, intent="open_app", params=params)
        except Exception as exc:  # noqa: BLE001
            msg = f"Erro inesperado ao abrir '{app_name}': {exc}"
            LOGGER.exception(msg)
            return ActionResult(success=False, message=msg, intent="open_app", params=params)

    async def close_app(self, params: dict[str, Any]) -> ActionResult:
        """Fecha um programa pelo nome usando taskkill."""
        app_name = params.get("app_name", "")
        if not app_name:
            return ActionResult(
                False, "Nome do programa não especificado.", "close_app", params,
            )

        executavel = self._resolver_app(app_name)
        processo = executavel if executavel.endswith(".exe") else f"{executavel}.exe"
        LOGGER.info("Fechando app: '%s' (processo: '%s')", app_name, processo)

        def _fechar() -> tuple[bool, str]:
            try:
                result = subprocess.run(
                    ["taskkill", "/IM", processo, "/F"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return True, f"Programa '{app_name}' fechado."
                return False, f"Programa '{app_name}' não está aberto."
            except subprocess.TimeoutExpired:
                return False, f"Timeout ao tentar fechar '{app_name}'."
            except OSError as exc:
                return False, f"Erro ao fechar '{app_name}': {exc}"

        try:
            success, msg = await asyncio.to_thread(_fechar)
            return ActionResult(success=success, message=msg, intent="close_app", params=params)
        except Exception as exc:  # noqa: BLE001
            msg = f"Erro inesperado ao fechar '{app_name}': {exc}"
            LOGGER.exception(msg)
            return ActionResult(success=False, message=msg, intent="close_app", params=params)
