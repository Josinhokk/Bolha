"""
Listener do microfone.

Abre um InputStream do sounddevice numa thread dedicada (callback) e
empurra chunks int16 pro asyncio.Queue via loop.call_soon_threadsafe.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np
import sounddevice as sd

LOGGER = logging.getLogger("bolha.voice.listener")


class MicrofoneListener:
    """Captura áudio do microfone e publica chunks int16 numa fila async."""

    def __init__(
        self,
        audio_queue: asyncio.Queue[np.ndarray],
        config: dict[str, Any],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        vcfg = config["voice"]
        self._queue = audio_queue
        self._loop = loop
        self._sample_rate: int = vcfg["sample_rate"]
        self._channels: int = vcfg["channels"]
        self._chunk_samples: int = vcfg["audio"]["chunk_samples"]
        self._input_device = vcfg["audio"].get("input_device")

        self._stream: sd.InputStream | None = None
        self._stop_event = asyncio.Event()
        self._dropped_frames = 0

    def _enfileirar(self, chunk: np.ndarray) -> None:
        """Roda no event loop; descarta se a fila estiver cheia."""
        try:
            self._queue.put_nowait(chunk)
        except asyncio.QueueFull:
            self._dropped_frames += 1
            if self._dropped_frames % 50 == 1:
                LOGGER.warning(
                    "Fila de áudio cheia — %d frames descartados até agora.",
                    self._dropped_frames,
                )

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,  # noqa: ARG002
        time_info: Any,  # noqa: ARG002
        status: sd.CallbackFlags,
    ) -> None:
        """Callback chamado pela thread de áudio do sounddevice."""
        if status:
            LOGGER.debug("Status do stream: %s", status)
        # indata: shape (frames, channels) int16 — pegamos o canal 0 e copiamos.
        chunk = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
        self._loop.call_soon_threadsafe(self._enfileirar, chunk)

    async def run(self) -> None:
        """Abre o stream e mantém até receber stop()."""
        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype="int16",
            blocksize=self._chunk_samples,
            device=self._input_device,
            callback=self._callback,
        )
        self._stream.start()
        LOGGER.info(
            "Microfone aberto (%d Hz, %d canal, blocos de %d amostras).",
            self._sample_rate,
            self._channels,
            self._chunk_samples,
        )
        try:
            await self._stop_event.wait()
        except asyncio.CancelledError:
            LOGGER.debug("Listener cancelado.")
            raise
        finally:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            LOGGER.info("Microfone liberado (%d frames descartados no total).", self._dropped_frames)

    def stop(self) -> None:
        """Sinaliza o fim do listener. Seguro chamar de qualquer thread."""
        self._loop.call_soon_threadsafe(self._stop_event.set)
