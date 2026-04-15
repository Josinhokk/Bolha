"""
Speech-to-Text com faster-whisper.

Recebe áudio float32 16kHz mono (já filtrado pelo VAD) e devolve (texto, idioma).
Roda em thread pra não bloquear o event loop.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np

LOGGER = logging.getLogger("bolha.voice.stt")


class WhisperSTT:
    """Wrapper async em torno do faster-whisper."""

    def __init__(self, config: dict[str, Any]) -> None:
        from faster_whisper import WhisperModel

        scfg = config["voice"]["stt"]
        self._model_size: str = scfg.get("model", "base")
        self._device: str = scfg.get("device", "cpu")
        self._beam_size: int = scfg.get("beam_size", 5)

        compute_type = scfg.get("compute_type", "auto")
        if compute_type == "auto":
            compute_type = "float16" if self._device == "cuda" else "int8"

        language = scfg.get("language", "auto")
        self._language = None if language in (None, "auto", "") else language

        LOGGER.info(
            "Carregando faster-whisper (model=%s, device=%s, compute_type=%s, language=%s)...",
            self._model_size,
            self._device,
            compute_type,
            self._language or "auto",
        )
        try:
            self._model = WhisperModel(
                self._model_size, device=self._device, compute_type=compute_type
            )
        except Exception as exc:
            if self._device == "cuda":
                LOGGER.warning(
                    "Falha ao inicializar Whisper em CUDA (%s). Caindo pra CPU/int8.",
                    exc,
                )
                self._device = "cpu"
                self._model = WhisperModel(
                    self._model_size, device="cpu", compute_type="int8"
                )
            else:
                raise

    def _transcrever_sync(self, audio_float32: np.ndarray) -> tuple[str, str]:
        segments, info = self._model.transcribe(
            audio_float32,
            language=self._language,
            beam_size=self._beam_size,
            vad_filter=False,  # já filtrado pelo Silero antes
        )
        texto = " ".join(seg.text.strip() for seg in segments).strip()
        idioma = info.language if info and info.language else "?"
        return texto, idioma

    async def transcrever(self, audio_float32: np.ndarray) -> tuple[str, str]:
        return await asyncio.to_thread(self._transcrever_sync, audio_float32)
