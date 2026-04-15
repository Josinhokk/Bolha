# voice/

Captura áudio, detecta wake word, filtra com VAD, transcreve com Whisper e sintetiza com Piper.

Arquivos (Fase 2):
- `listener.py` — captura áudio do microfone (async)
- `wake_word.py` — detecta "Bolha" com openWakeWord
- `vad.py` — Silero VAD
- `stt.py` — Whisper (faster-whisper)
- `tts.py` — Piper TTS
- `earcons.py` — feedback sonoro
