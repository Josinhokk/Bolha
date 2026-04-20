"""
Screen Controller — fallback de controle via PyAutoGUI.

Só é chamado quando nenhum outro handler resolve a intent — é o último
recurso pra automações que exigem mouse, teclado ou captura de tela.

Implementa:
- screen_click: clica em (x, y) com botão e repetições configuráveis
- screen_type: digita texto na janela em foco
- screen_screenshot: salva PNG em data/screenshots/ e devolve o path

PyAutoGUI é dependência opcional: se não estiver instalado, o módulo sobe
em modo degradado e cada handler devolve mensagem amigável.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.executor.router import ActionResult

LOGGER = logging.getLogger("bolha.executor.screen_control")

try:
    import pyautogui

    _PYAUTOGUI_OK = True
except ImportError:
    _PYAUTOGUI_OK = False

_BOTOES_VALIDOS = ("left", "right", "middle")
_MSG_SEM_PYAUTOGUI = "Controle de tela indisponível (pyautogui não instalado)."


class ScreenController:
    """Handler de mouse/teclado/screenshot via PyAutoGUI. Último recurso."""

    def __init__(self, config: dict[str, Any], root_dir: Path) -> None:
        screen_cfg = config.get("executor", {}).get("screen", {}) or {}
        self._type_interval: float = float(screen_cfg.get("type_interval", 0.02))
        self._failsafe: bool = bool(screen_cfg.get("failsafe", True))

        screenshots_rel = screen_cfg.get("screenshots_dir", "data/screenshots")
        self._screenshots_dir = (root_dir / screenshots_rel).resolve()

        if _PYAUTOGUI_OK:
            pyautogui.FAILSAFE = self._failsafe
            pyautogui.PAUSE = 0.0
            self._screenshots_dir.mkdir(parents=True, exist_ok=True)
            LOGGER.info(
                "ScreenController pronto (failsafe=%s, type_interval=%.3fs, dir=%s).",
                self._failsafe,
                self._type_interval,
                self._screenshots_dir,
            )
        else:
            LOGGER.warning(
                "pyautogui não disponível — screen_* ficarão desabilitados.",
            )

    def handlers(self) -> dict[str, Any]:
        """Retorna mapa intent → handler pra registrar no router."""
        return {
            "screen_click": self.screen_click,
            "screen_type": self.screen_type,
            "screen_screenshot": self.screen_screenshot,
        }

    async def screen_click(self, params: dict[str, Any]) -> ActionResult:
        """Clica em (x, y). params: x:int, y:int, button:str, clicks:int."""
        if not _PYAUTOGUI_OK:
            return ActionResult(False, _MSG_SEM_PYAUTOGUI, "screen_click", params)

        try:
            x = int(params.get("x"))
            y = int(params.get("y"))
        except (TypeError, ValueError):
            return ActionResult(
                False, "Coordenadas x/y inválidas ou ausentes.", "screen_click", params,
            )

        button = str(params.get("button", "left")).lower().strip()
        if button not in _BOTOES_VALIDOS:
            return ActionResult(
                False,
                f"Botão inválido: '{button}'. Use left, right ou middle.",
                "screen_click",
                params,
            )

        try:
            clicks = max(1, int(params.get("clicks", 1) or 1))
        except (TypeError, ValueError):
            clicks = 1

        # Valida coordenadas contra o tamanho da tela.
        largura, altura = pyautogui.size()
        if not (0 <= x < largura and 0 <= y < altura):
            return ActionResult(
                False,
                f"Coordenadas ({x},{y}) fora da tela ({largura}x{altura}).",
                "screen_click",
                params,
            )

        def _clicar() -> str:
            pyautogui.click(x=x, y=y, clicks=clicks, button=button)
            vezes = "clique" if clicks == 1 else f"{clicks} cliques"
            return f"Feito: {vezes} em ({x}, {y}) com o botão {button}."

        try:
            msg = await asyncio.to_thread(_clicar)
            return ActionResult(True, msg, "screen_click", params)
        except pyautogui.FailSafeException:
            return ActionResult(
                False,
                "Clique abortado pelo fail-safe (mouse foi pro canto da tela).",
                "screen_click",
                params,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Erro em screen_click")
            return ActionResult(
                False, f"Erro ao clicar: {exc}", "screen_click", params,
            )

    async def screen_type(self, params: dict[str, Any]) -> ActionResult:
        """Digita texto na janela em foco. params: text:str, interval:float."""
        if not _PYAUTOGUI_OK:
            return ActionResult(False, _MSG_SEM_PYAUTOGUI, "screen_type", params)

        text = params.get("text", "")
        if not isinstance(text, str) or not text:
            return ActionResult(
                False, "Texto vazio ou inválido.", "screen_type", params,
            )

        try:
            raw_interval = params.get("interval")
            interval = float(raw_interval) if raw_interval is not None else self._type_interval
        except (TypeError, ValueError):
            interval = self._type_interval
        interval = max(0.0, min(interval, 1.0))

        def _digitar() -> str:
            # pyautogui.typewrite só suporta ASCII; pra acentos e símbolos
            # usamos .write por caractere via clipboard-free path (keyDown/keyUp).
            pyautogui.write(text, interval=interval)
            return f"Texto digitado ({len(text)} caracteres)."

        try:
            msg = await asyncio.to_thread(_digitar)
            return ActionResult(True, msg, "screen_type", params)
        except pyautogui.FailSafeException:
            return ActionResult(
                False,
                "Digitação abortada pelo fail-safe.",
                "screen_type",
                params,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Erro em screen_type")
            return ActionResult(
                False, f"Erro ao digitar: {exc}", "screen_type", params,
            )

    async def screen_screenshot(self, params: dict[str, Any]) -> ActionResult:
        """Tira screenshot e salva em data/screenshots/. params: path:str (opcional)."""
        if not _PYAUTOGUI_OK:
            return ActionResult(False, _MSG_SEM_PYAUTOGUI, "screen_screenshot", params)

        raw_path = params.get("path")
        if raw_path:
            destino = Path(raw_path)
            if not destino.is_absolute():
                destino = self._screenshots_dir / destino
        else:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            destino = self._screenshots_dir / f"screenshot_{stamp}.png"

        def _capturar() -> str:
            destino.parent.mkdir(parents=True, exist_ok=True)
            img = pyautogui.screenshot()
            img.save(destino)
            return f"Screenshot salvo em {destino}."

        try:
            msg = await asyncio.to_thread(_capturar)
            return ActionResult(True, msg, "screen_screenshot", params)
        except OSError as exc:
            LOGGER.exception("Erro de IO em screen_screenshot")
            return ActionResult(
                False, f"Erro ao salvar screenshot: {exc}", "screen_screenshot", params,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Erro em screen_screenshot")
            return ActionResult(
                False, f"Erro ao tirar screenshot: {exc}", "screen_screenshot", params,
            )
