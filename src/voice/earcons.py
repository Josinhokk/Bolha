"""
Earcons — feedback sonoro curto.

Na Fase 2 usamos um bip sintetizado (numpy + sounddevice). Nas próximas
iterações podemos trocar por .wav pré-gerados em data/sounds/.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import sounddevice as sd

LOGGER = logging.getLogger("bolha.voice.earcons")

_EARCON_SAMPLE_RATE = 44100


def _gerar_tom(
    freq_hz: float,
    duration_ms: int,
    amplitude: float = 0.2,
    sample_rate: int = _EARCON_SAMPLE_RATE,
) -> np.ndarray:
    """Gera uma onda senoidal float32 com fade-in/out curto pra evitar clique."""
    n = int(sample_rate * duration_ms / 1000)
    t = np.linspace(0, duration_ms / 1000, n, endpoint=False, dtype=np.float32)
    wave = amplitude * np.sin(2 * np.pi * freq_hz * t, dtype=np.float32)

    fade_n = max(1, int(sample_rate * 0.005))  # 5ms
    envelope = np.ones(n, dtype=np.float32)
    envelope[:fade_n] = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
    envelope[-fade_n:] = np.linspace(1.0, 0.0, fade_n, dtype=np.float32)
    return wave * envelope


def _tocar(freq: float, dur_ms: int, amp: float) -> None:
    try:
        tom = _gerar_tom(freq, dur_ms, amp)
        sd.play(tom, _EARCON_SAMPLE_RATE)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Falha ao tocar earcon: %s", exc)


def tocar_bip(config: dict[str, Any]) -> None:
    """Bip de wake word — tom agudo curto."""
    ecfg = config.get("voice", {}).get("earcons", {})
    _tocar(
        ecfg.get("wake_freq_hz", 880),
        ecfg.get("wake_duration_ms", 120),
        ecfg.get("wake_amplitude", 0.2),
    )


def tocar_processando(config: dict[str, Any]) -> None:
    """Earcon de 'processando' — tom mais grave enquanto Whisper/LLM rodam."""
    ecfg = config.get("voice", {}).get("earcons", {})
    _tocar(
        ecfg.get("processing_freq_hz", 440),
        ecfg.get("processing_duration_ms", 90),
        ecfg.get("processing_amplitude", 0.18),
    )
