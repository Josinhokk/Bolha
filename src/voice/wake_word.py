"""
Wake word — detecta "Bolha" (ou modelo fallback) em cima do stream do listener.

Fluxo:
    1. Consome chunks int16 (1280 amostras) da fila do listener.
    2. Passa cada chunk pro openWakeWord.
    3. Quando o score passa do threshold: toca bip + grava o comando.
    4. Imprime um resumo do áudio capturado (STT entra na sub-etapa 2).
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import numpy as np

from src.voice.earcons import tocar_bip

LOGGER = logging.getLogger("bolha.voice.wake_word")


class WakeWordDetector:
    """Detecta wake word e captura o comando subsequente em janela fixa."""

    def __init__(
        self,
        audio_queue: asyncio.Queue[np.ndarray],
        config: dict[str, Any],
    ) -> None:
        # Import tardio: openwakeword é pesado e pode não estar instalado em dev.
        from openwakeword.model import Model

        self._config = config
        vcfg = config["voice"]
        ww = vcfg["wake_word"]

        self._queue = audio_queue
        self._sample_rate: int = vcfg["sample_rate"]
        self._chunk_samples: int = vcfg["audio"]["chunk_samples"]
        self._threshold: float = ww.get("threshold", 0.5)
        self._cooldown: float = ww.get("cooldown_seconds", 2.0)
        self._command_duration: float = vcfg["command"]["duration_seconds"]
        self._wake_name: str = ww.get("name", "bolha")

        model_path = ww.get("model_path")
        fallback = ww.get("fallback_model", "hey_jarvis")

        # ONNX é o runtime padrão no Windows — tflite-runtime não tem wheel oficial.
        inference_framework = ww.get("inference_framework", "onnx")

        if model_path and Path(model_path).exists():
            LOGGER.info("Carregando modelo custom de wake word: %s", model_path)
            self._model = Model(
                wakeword_models=[model_path],
                inference_framework=inference_framework,
            )
            self._model_key = Path(model_path).stem
        else:
            if model_path:
                LOGGER.warning(
                    "model_path '%s' não encontrado — caindo pro fallback '%s'.",
                    model_path,
                    fallback,
                )
            else:
                LOGGER.warning(
                    "Sem modelo custom de '%s' — usando fallback '%s'. "
                    "Treine o modelo e aponte voice.wake_word.model_path no config.yaml.",
                    self._wake_name,
                    fallback,
                )
            self._model = Model(
                wakeword_models=[fallback],
                inference_framework=inference_framework,
            )
            self._model_key = fallback

        self._last_detection_ts = 0.0

    def _score(self, chunk: np.ndarray) -> float:
        """Roda openWakeWord num chunk e devolve o score do modelo carregado."""
        scores = self._model.predict(chunk)
        if self._model_key in scores:
            return float(scores[self._model_key])
        return float(max(scores.values())) if scores else 0.0

    async def _capturar_comando(self) -> np.ndarray:
        """Coleta `command_duration` segundos de áudio da fila."""
        total_amostras_alvo = int(self._sample_rate * self._command_duration)
        blocos: list[np.ndarray] = []
        acumulado = 0
        LOGGER.info(
            "Gravando comando por ~%.1fs (%d amostras)...",
            self._command_duration,
            total_amostras_alvo,
        )
        while acumulado < total_amostras_alvo:
            chunk = await self._queue.get()
            blocos.append(chunk)
            acumulado += len(chunk)
        return np.concatenate(blocos)

    async def run(self) -> None:
        """Loop principal: ouve o stream até ser cancelado."""
        LOGGER.info(
            "Detector pronto (wake='%s', modelo='%s', threshold=%.2f).",
            self._wake_name,
            self._model_key,
            self._threshold,
        )
        while True:
            chunk = await self._queue.get()

            if len(chunk) != self._chunk_samples:
                LOGGER.debug(
                    "Chunk com tamanho inesperado (%d != %d), ignorando.",
                    len(chunk),
                    self._chunk_samples,
                )
                continue

            score = self._score(chunk)

            agora = time.monotonic()
            em_cooldown = (agora - self._last_detection_ts) < self._cooldown
            if score >= self._threshold and not em_cooldown:
                self._last_detection_ts = agora
                LOGGER.info("Wake word detectada (score=%.3f).", score)
                tocar_bip(self._config)

                audio = await self._capturar_comando()
                rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
                duracao_s = len(audio) / self._sample_rate
                print(
                    f"[wake+cmd] amostras={len(audio)} duração={duracao_s:.2f}s "
                    f"dtype={audio.dtype} rms={rms:.1f}"
                )
                LOGGER.info(
                    "Comando capturado: %d amostras, %.2fs, rms=%.1f. "
                    "(STT entra na sub-etapa 2.)",
                    len(audio),
                    duracao_s,
                    rms,
                )
                # Reseta o buffer interno do openWakeWord pra evitar eco da detecção.
                if hasattr(self._model, "reset"):
                    self._model.reset()
