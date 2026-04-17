"""
System Manager — comandos de sistema do Windows.

Implementa:
- system_info: CPU, RAM, disco (via psutil)
- system_volume: up / down / mute / unmute (via pycaw)
- system_shutdown: shutdown / restart / sleep (via shutdown.exe + rundll32)

Ações que exigem UAC (shutdown, restart) checam is_admin() antes de tentar —
se não estiver elevado, retorna mensagem amigável em vez de falhar no meio.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from datetime import datetime
from typing import Any

from src.executor.permissions import MENSAGEM_SEM_ADMIN, is_admin
from src.executor.router import ActionResult

_DIAS_SEMANA = (
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
)
_MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)
_KINDS_VALIDOS = ("time", "date", "battery", "hardware", "all")

LOGGER = logging.getLogger("bolha.executor.system_cmd")

try:
    from ctypes import POINTER, cast

    import comtypes
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    _PYCAW_OK = True
except ImportError:
    _PYCAW_OK = False

try:
    import psutil

    _PSUTIL_OK = True
except ImportError:
    _PSUTIL_OK = False


class SystemManager:
    """Handler de comandos de sistema: info, volume, shutdown/restart/sleep."""

    def __init__(self, config: dict[str, Any]) -> None:
        system_cfg = config.get("executor", {}).get("system", {}) or {}
        self._volume_step: int = int(system_cfg.get("volume_step", 10))
        self._disk_path: str = str(system_cfg.get("disk_path", "C:/"))

        if not _PYCAW_OK:
            LOGGER.warning(
                "pycaw não disponível — system_volume ficará desabilitado.",
            )
        if not _PSUTIL_OK:
            LOGGER.warning(
                "psutil não disponível — system_info ficará limitado.",
            )

        LOGGER.info(
            "SystemManager pronto (volume_step=%d%%, disk=%s, admin=%s).",
            self._volume_step,
            self._disk_path,
            is_admin(),
        )

    def handlers(self) -> dict[str, Any]:
        """Retorna mapa intent → handler pra registrar no router."""
        return {
            "system_info": self.system_info,
            "system_volume": self.system_volume,
            "system_shutdown": self.system_shutdown,
        }

    async def system_info(self, params: dict[str, Any]) -> ActionResult:
        """Retorna info do sistema. kind: time | date | battery | hardware | all."""
        kind_raw = str(params.get("kind", "")).lower().strip()
        kind = kind_raw if kind_raw in _KINDS_VALIDOS else "all"
        if kind_raw and kind_raw != kind:
            LOGGER.warning(
                "system_info kind desconhecido '%s' — caindo pra 'all'.", kind_raw,
            )

        def _coletar() -> str:
            if kind == "time":
                return self._format_hora()
            if kind == "date":
                return self._format_data()
            if kind == "battery":
                return self._format_bateria()
            if kind == "hardware":
                return self._format_hardware()
            # "all": hora + hardware + bateria (se existir)
            partes = [self._format_hora(), self._format_hardware()]
            bat = self._format_bateria()
            if bat and "sem bateria" not in bat.lower() and "indisponível" not in bat.lower():
                partes.append(bat)
            return " ".join(partes)

        try:
            msg = await asyncio.to_thread(_coletar)
            return ActionResult(True, msg, "system_info", params)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Erro em system_info")
            return ActionResult(
                False, f"Erro ao consultar o sistema: {exc}", "system_info", params,
            )

    @staticmethod
    def _format_hora() -> str:
        agora = datetime.now()
        return f"Agora são {agora.hour} horas e {agora.minute:02d} minutos."

    @staticmethod
    def _format_data() -> str:
        hoje = datetime.now()
        return (
            f"Hoje é {_DIAS_SEMANA[hoje.weekday()]}, "
            f"{hoje.day} de {_MESES[hoje.month - 1]} de {hoje.year}."
        )

    def _format_hardware(self) -> str:
        if not _PSUTIL_OK:
            return "Informações de hardware indisponíveis (psutil não instalado)."
        mem = psutil.virtual_memory()
        cpu_pct = psutil.cpu_percent(interval=0.5)
        disco = psutil.disk_usage(self._disk_path)

        ram_usado = mem.used / (1024 ** 3)
        ram_total = mem.total / (1024 ** 3)
        disco_livre = disco.free / (1024 ** 3)
        disco_total = disco.total / (1024 ** 3)
        return (
            f"CPU em {cpu_pct:.0f}%. "
            f"RAM: {ram_usado:.1f} de {ram_total:.1f} GB em uso. "
            f"Disco {self._disk_path}: {disco_livre:.0f} GB livres "
            f"de {disco_total:.0f} GB."
        )

    @staticmethod
    def _format_bateria() -> str:
        if not _PSUTIL_OK:
            return "Informação de bateria indisponível (psutil não instalado)."
        bat = psutil.sensors_battery()
        if bat is None:
            return "Sem bateria detectada — provavelmente um desktop."
        status = "carregando" if bat.power_plugged else "descarregando"
        return f"Bateria em {bat.percent:.0f}%, {status}."

    async def system_volume(self, params: dict[str, Any]) -> ActionResult:
        """Controla volume: up | down | mute | unmute."""
        action = str(params.get("action", "")).lower().strip()

        if not _PYCAW_OK:
            return ActionResult(
                False,
                "Controle de volume indisponível (pycaw não instalado).",
                "system_volume",
                params,
            )

        if action not in ("up", "down", "mute", "unmute"):
            return ActionResult(
                False,
                f"Ação de volume inválida: '{action}'. Use up, down, mute ou unmute.",
                "system_volume",
                params,
            )

        valor_raw = params.get("value")
        try:
            passo_pct = int(valor_raw) if valor_raw not in (None, "", 0) else self._volume_step
        except (TypeError, ValueError):
            passo_pct = self._volume_step
        passo = max(1, min(100, passo_pct)) / 100.0

        def _ajustar() -> str:
            # asyncio.to_thread roda num worker sem COM inicializado —
            # pycaw precisa de CoInitialize no thread atual.
            comtypes.CoInitialize()
            try:
                speakers = AudioUtilities.GetSpeakers()
                # pycaw novo (>=20240210) envolve o IMMDevice num wrapper
                # AudioDevice com o ponteiro real em `._dev`. Versões antigas
                # retornavam o ponteiro direto.
                imm_device = getattr(speakers, "_dev", speakers)
                interface = imm_device.Activate(
                    IAudioEndpointVolume._iid_, CLSCTX_ALL, None,
                )
                volume = cast(interface, POINTER(IAudioEndpointVolume))

                if action == "mute":
                    volume.SetMute(1, None)
                    return "Som mutado."
                if action == "unmute":
                    volume.SetMute(0, None)
                    return "Som reativado."

                atual = volume.GetMasterVolumeLevelScalar()
                if action == "up":
                    novo = min(1.0, atual + passo)
                else:  # down
                    novo = max(0.0, atual - passo)

                volume.SetMasterVolumeLevelScalar(novo, None)
                if volume.GetMute():
                    volume.SetMute(0, None)
                return f"Volume em {novo * 100:.0f}%."
            finally:
                comtypes.CoUninitialize()

        try:
            msg = await asyncio.to_thread(_ajustar)
            return ActionResult(True, msg, "system_volume", params)
        except OSError as exc:
            LOGGER.exception("Erro de sistema em system_volume")
            return ActionResult(
                False, f"Erro ao ajustar volume: {exc}", "system_volume", params,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Erro inesperado em system_volume")
            return ActionResult(
                False, f"Erro ao ajustar volume: {exc}", "system_volume", params,
            )

    async def system_shutdown(self, params: dict[str, Any]) -> ActionResult:
        """Desliga, reinicia ou suspende o PC. shutdown/restart exigem admin."""
        action = str(params.get("action", "shutdown")).lower().strip()

        if action not in ("shutdown", "restart", "sleep"):
            return ActionResult(
                False,
                f"Ação inválida: '{action}'. Use shutdown, restart ou sleep.",
                "system_shutdown",
                params,
            )

        if action in ("shutdown", "restart") and not is_admin():
            LOGGER.warning(
                "system_shutdown '%s' bloqueado — sem privilégio admin.", action,
            )
            return ActionResult(
                False, MENSAGEM_SEM_ADMIN, "system_shutdown", params,
            )

        if action == "shutdown":
            cmd = ["shutdown", "/s", "/t", "0"]
            msg_ok = "Desligando o computador."
        elif action == "restart":
            cmd = ["shutdown", "/r", "/t", "0"]
            msg_ok = "Reiniciando o computador."
        else:  # sleep
            cmd = ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]
            msg_ok = "Suspendendo o computador."

        LOGGER.info("Executando system_shutdown '%s': %s", action, cmd)

        def _executar() -> tuple[bool, str]:
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=8,
                )
                if result.returncode == 0:
                    return True, msg_ok
                err = (result.stderr or result.stdout or "").strip()
                return False, f"Falha no {action}: {err or 'retorno não-zero'}."
            except subprocess.TimeoutExpired:
                return False, f"Timeout ao executar {action}."
            except OSError as exc:
                return False, f"Erro ao executar {action}: {exc}"

        try:
            success, msg = await asyncio.to_thread(_executar)
            return ActionResult(success, msg, "system_shutdown", params)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Erro inesperado em system_shutdown")
            return ActionResult(
                False, f"Erro inesperado: {exc}", "system_shutdown", params,
            )
