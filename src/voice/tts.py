"""
Text-to-Speech com Piper.

Sintetiza int16 PCM via `synthesize_stream_raw` e toca com sounddevice.
Se o modelo não estiver em disco, o TTS entra em modo "silencioso" (só loga
o que falaria), pra não quebrar o pipeline enquanto você baixa a voz.

Obs.: o Piper oficial só tem voz masculina em PT-BR (`faber`, `edresson`).
Se quiser feminina PT-BR no futuro, dá pra trocar por Edge TTS (cloud) ou
pyttsx3 + SAPI5 (local, qualidade inferior).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd

LOGGER = logging.getLogger("bolha.voice.tts")


class PiperTTS:
    """Wrapper async em torno do Piper."""

    def __init__(self, config: dict[str, Any], root_dir: Path) -> None:
        tcfg = config["voice"]["tts"]
        self._voice_name: str = tcfg.get("voice", "pt_BR-faber-medium")
        self._speaker_id = tcfg.get("speaker_id")
        self._use_cuda: bool = tcfg.get("use_cuda", False)

        model_path = (root_dir / tcfg["model_path"]).resolve()
        config_path = (root_dir / tcfg["config_path"]).resolve()

        self._voice = None
        self._sample_rate = 22050  # default Piper, sobrescrito se modelo carregar

        if not model_path.exists() or not config_path.exists():
            LOGGER.warning(
                "Modelo Piper não encontrado (%s). TTS em modo silencioso. "
                "Baixe com: huggingface-cli download rhasspy/piper-voices "
                "pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx "
                "pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json "
                "--local-dir data/models --local-dir-use-symlinks False",
                model_path,
            )
            return

        try:
            from piper import PiperVoice

            LOGGER.info("Carregando voz Piper '%s' de %s...", self._voice_name, model_path)
            self._voice = PiperVoice.load(
                str(model_path), config_path=str(config_path), use_cuda=self._use_cuda
            )
            self._sample_rate = int(self._voice.config.sample_rate)
            LOGGER.info(
                "Piper pronto (sample_rate=%d, speaker_id=%s).",
                self._sample_rate,
                self._speaker_id,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Falha ao carregar Piper: %s — TTS em modo silencioso.", exc)
            self._voice = None

    @property
    def disponivel(self) -> bool:
        return self._voice is not None

    def _sintetizar_sync(self, texto: str) -> np.ndarray:
        # piper-tts 1.4.x: voice.synthesize(text, syn_config=...) devolve AudioChunks.
        syn_config = None
        if self._speaker_id is not None:
            try:
                from piper import SynthesisConfig

                syn_config = SynthesisConfig(speaker_id=int(self._speaker_id))
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("Sem SynthesisConfig (%s), seguindo sem speaker_id.", exc)

        pedacos: list[np.ndarray] = []
        for chunk in self._voice.synthesize(texto, syn_config=syn_config):
            # AudioChunk.audio_int16_array é numpy int16 mono.
            arr = getattr(chunk, "audio_int16_array", None)
            if arr is None:
                raw = getattr(chunk, "audio_int16_bytes", b"")
                arr = np.frombuffer(raw, dtype=np.int16)
            pedacos.append(np.asarray(arr, dtype=np.int16).reshape(-1))

        if not pedacos:
            return np.zeros(0, dtype=np.int16)
        return np.concatenate(pedacos)

    def _falar_sync(self, texto: str) -> None:
        audio = self._sintetizar_sync(texto)
        if len(audio) == 0:
            return
        sd.play(audio, self._sample_rate)
        sd.wait()

    async def falar(self, texto: str) -> None:
        """Sintetiza e toca. Aguarda a reprodução terminar."""
        if not texto:
            return
        if not self.disponivel:
            LOGGER.info("[TTS silencioso] %s", texto)
            print(f"[TTS silencioso] {texto}")
            return
        try:
            await asyncio.to_thread(self._falar_sync, texto)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Falha ao sintetizar/tocar: %s", exc)
