"""
Voice Activity Detection (Silero VAD).

Recebe áudio int16 16kHz mono e devolve só os trechos com voz concatenados,
em float32 normalizado. Serve pra evitar alucinações do Whisper em silêncio/ruído.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np

LOGGER = logging.getLogger("bolha.voice.vad")


class SileroVAD:
    """Wrapper async em torno do Silero VAD."""

    def __init__(self, config: dict[str, Any]) -> None:
        from silero_vad import get_speech_timestamps, load_silero_vad

        vcfg = config["voice"]
        vad_cfg = vcfg["vad"]
        self._sample_rate: int = vcfg["sample_rate"]
        self._threshold: float = vad_cfg.get("threshold", 0.5)
        self._min_silence_ms: int = vad_cfg.get("min_silence_ms", 500)
        self._min_speech_ms: int = vad_cfg.get("min_speech_ms", 250)

        LOGGER.info("Carregando Silero VAD (onnx)...")
        self._model = load_silero_vad(onnx=True)
        self._get_speech_timestamps = get_speech_timestamps

    def _filtrar_sync(self, audio_int16: np.ndarray) -> np.ndarray | None:
        import torch

        audio_float = (audio_int16.astype(np.float32) / 32768.0).clip(-1.0, 1.0)
        tensor = torch.from_numpy(audio_float)

        timestamps = self._get_speech_timestamps(
            tensor,
            self._model,
            sampling_rate=self._sample_rate,
            threshold=self._threshold,
            min_silence_duration_ms=self._min_silence_ms,
            min_speech_duration_ms=self._min_speech_ms,
            return_seconds=False,
        )

        if not timestamps:
            return None

        segmentos = [audio_float[ts["start"] : ts["end"]] for ts in timestamps]
        voz = np.concatenate(segmentos)
        LOGGER.debug(
            "VAD: %d segmento(s), %.2fs de voz em %.2fs de áudio.",
            len(timestamps),
            len(voz) / self._sample_rate,
            len(audio_float) / self._sample_rate,
        )
        return voz

    async def filtrar_voz(self, audio_int16: np.ndarray) -> np.ndarray | None:
        """Devolve áudio float32 só com trechos de voz, ou None se não tem voz."""
        return await asyncio.to_thread(self._filtrar_sync, audio_int16)
