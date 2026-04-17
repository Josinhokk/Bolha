"""
Entry point do Bolha.

Orquestra os módulos via asyncio.Queue e implementa graceful shutdown
(Ctrl+C cancela as tasks, fecha SQLite e libera o microfone).
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config.yaml"

# Permite rodar tanto com `python src/main.py` quanto `python -m src.main`.
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.brain.intent_parser import IntentParser  # noqa: E402
from src.brain.llm_client import OllamaClient  # noqa: E402
from src.brain.memory import MemoriaManager  # noqa: E402
from src.executor.app_launcher import AppLauncher  # noqa: E402
from src.executor.browser import BrowserManager  # noqa: E402
from src.executor.file_manager import FileManager  # noqa: E402
from src.executor.router import ActionRouter  # noqa: E402
from src.executor.system_cmd import SystemManager  # noqa: E402
from src.voice.listener import MicrofoneListener  # noqa: E402
from src.voice.tts import PiperTTS  # noqa: E402

LOGGER = logging.getLogger("bolha")


def carregar_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Carrega o config.yaml e devolve um dict."""
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def configurar_logging(config: dict[str, Any]) -> None:
    """Configura o logger raiz com base no config.yaml."""
    log_cfg = config.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
    fmt = log_cfg.get("format", "%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    log_file = ROOT_DIR / log_cfg.get("file", "data/logs/bolha.log")
    log_file.parent.mkdir(parents=True, exist_ok=True)

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
    logging.basicConfig(level=level, format=fmt, handlers=handlers, force=True)


class Bolha:
    """Orquestrador principal. Mantém as filas e o ciclo de vida das tasks."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.debug = config.get("app", {}).get("debug_mode", False)
        self.shutdown_timeout = config.get("shutdown", {}).get("timeout_seconds", 5)

        # Filas que ligam os módulos.
        queue_max = config["voice"]["audio"].get("queue_maxsize", 200)
        self.fila_audio: asyncio.Queue[Any] = asyncio.Queue(maxsize=queue_max)
        self.fila_transcricao: asyncio.Queue[str] = asyncio.Queue()
        self.fila_acoes: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        self._shutdown_event = asyncio.Event()
        self._tasks: list[asyncio.Task[Any]] = []
        self._listener: MicrofoneListener | None = None
        self._llm_client: OllamaClient | None = None
        self._memoria: MemoriaManager | None = None

    async def iniciar(self) -> None:
        """Sobe todas as tasks e aguarda o sinal de shutdown."""
        LOGGER.info("Bolha iniciando (debug=%s)", self.debug)
        loop = asyncio.get_running_loop()

        # TTS compartilhado entre wake_word e brain.
        tts = PiperTTS(self.config, ROOT_DIR)

        # Listener: captura do microfone alimentando fila_audio.
        self._listener = MicrofoneListener(self.fila_audio, self.config, loop)
        self._tasks.append(asyncio.create_task(self._listener.run(), name="listener"))

        # Wake word: consome fila_audio e detecta "Bolha".
        from src.voice.wake_word import WakeWordDetector

        detector = WakeWordDetector(
            self.fila_audio,
            self.config,
            transcricao_queue=self.fila_transcricao,
            tts=None,
        )
        self._tasks.append(asyncio.create_task(detector.run(), name="wake_word"))

        # Brain: consome fila_transcricao, interpreta intent, registra na memória.
        self._llm_client = OllamaClient(self.config)
        self._memoria = MemoriaManager(self.config, ROOT_DIR)
        parser = IntentParser(self._llm_client)

        # Executor: router + handlers.
        router = ActionRouter(self.config)
        file_mgr = FileManager(self.config)
        app_launcher = AppLauncher(self.config)
        browser_mgr = BrowserManager(self.config)
        system_mgr = SystemManager(self.config)
        router.registrar_varios(file_mgr.handlers())
        router.registrar_varios(app_launcher.handlers())
        router.registrar_varios(browser_mgr.handlers())
        router.registrar_varios(system_mgr.handlers())

        self._tasks.append(
            asyncio.create_task(
                self._task_brain(parser, tts, router), name="brain",
            )
        )

        LOGGER.info("Bolha pronto. Aguardando wake word (Ctrl+C para sair).")
        await self._shutdown_event.wait()

    async def _task_brain(
        self, parser: IntentParser, tts: PiperTTS, router: ActionRouter,
    ) -> None:
        """Consome fila_transcricao, interpreta via LLM, executa e responde."""
        LOGGER.info("Task brain iniciada — aguardando transcrições.")
        while True:
            texto = await self.fila_transcricao.get()
            LOGGER.info("[Brain] Recebido: '%s'", texto)

            try:
                intent = await parser.interpretar(texto)
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Erro no intent parser: %s", exc)
                await tts.falar("Desculpa, tive um problema ao processar seu pedido.")
                continue

            print(
                f"[Brain] intent={intent.intent}  params={intent.params}  "
                f"confidence={intent.confidence:.2f}  destructive={intent.destructive}"
            )

            # Executar a ação via router.
            result = await router.executar(intent.intent, intent.params)

            if self._memoria is not None:
                self._memoria.registrar(
                    user_input=texto,
                    intent=intent.intent,
                    params=intent.params,
                    confidence=intent.confidence,
                    destructive=intent.destructive,
                    resultado=result.message,
                )

            # Resposta por voz.
            if intent.intent == "conversation":
                resposta = intent.params.get("reply", "Não sei o que dizer.")
            elif intent.intent == "not_understood":
                resposta = "Desculpa, não entendi o que você disse."
            elif result.success and result.message:
                resposta = result.message
            elif not result.success and result.message:
                resposta = result.message
            else:
                resposta = f"Entendido: {intent.intent}."

            print(f"[Executor] {resposta}")
            await tts.falar(resposta)

    def solicitar_shutdown(self) -> None:
        """Sinaliza shutdown. Chamado pelos signal handlers."""
        if not self._shutdown_event.is_set():
            LOGGER.info("Shutdown solicitado — encerrando com calma...")
            self._shutdown_event.set()

    async def encerrar(self) -> None:
        """Cancela tasks, libera recursos, fecha SQLite."""
        if self._listener is not None:
            self._listener.stop()

        LOGGER.info("Cancelando %d task(s)...", len(self._tasks))
        for task in self._tasks:
            task.cancel()

        if self._tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._tasks, return_exceptions=True),
                    timeout=self.shutdown_timeout,
                )
            except asyncio.TimeoutError:
                LOGGER.warning(
                    "Timeout de %ss ao encerrar tasks — forçando saída.",
                    self.shutdown_timeout,
                )

        if self._llm_client is not None:
            await self._llm_client.fechar()
        if self._memoria is not None:
            self._memoria.fechar()

        LOGGER.info("Bolha encerrado.")


def _instalar_signal_handlers(loop: asyncio.AbstractEventLoop, bolha: Bolha) -> None:
    """Instala handlers de SIGINT/SIGTERM quando possível.

    No Windows, loop.add_signal_handler não existe, então fazemos fallback
    para signal.signal passando o callback thread-safe.
    """
    def _handler(*_: Any) -> None:
        loop.call_soon_threadsafe(bolha.solicitar_shutdown)

    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, bolha.solicitar_shutdown)
        except NotImplementedError:
            signal.signal(sig, _handler)


async def _main_async() -> int:
    config = carregar_config()
    configurar_logging(config)

    bolha = Bolha(config)
    loop = asyncio.get_running_loop()
    _instalar_signal_handlers(loop, bolha)

    try:
        await bolha.iniciar()
    except asyncio.CancelledError:
        pass
    finally:
        await bolha.encerrar()
    return 0


def main() -> int:
    try:
        return asyncio.run(_main_async())
    except KeyboardInterrupt:
        # Fallback caso o signal handler não pegue a tempo.
        LOGGER.info("Interrompido pelo usuário.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
