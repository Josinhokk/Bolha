# 🫧 Bolha

Assistente pessoal de voz para Windows 11 com controle total do PC. **Async-first**, modular, seguro por padrão.

## Características
- 🎙️ Ativação por wake word (custom "Bolha" — fallback `hey_jarvis` enquanto não treinar)
- 👂 STT com faster-whisper (PT-BR travado, evita alucinação em áudios curtos)
- 🎚️ Silero VAD corta silêncio antes de mandar pro Whisper
- 🔊 TTS com Piper (`pt_BR-faber-medium`)
- 🧠 LLM local (Ollama + Phi-3 Mini) com `format: 'json'` e Pydantic
- 🔐 Guardian de segurança — confirmação obrigatória pra ações destrutivas (planejado)
- ⚡ asyncio desde o dia 1 — `asyncio.Queue` entre módulos, graceful shutdown

## Stack
Python 3.11+ (testado em 3.14), sounddevice, faster-whisper, Silero VAD, openWakeWord, Piper, Ollama, Pydantic, SQLite.

## Status
**Fase 3/6 — Cérebro: CONCLUÍDA** ✅

Pipeline completo: microfone → wake word → bip → VAD → Whisper → LLM (Phi-3 Mini) → intent parser (Pydantic) → memória (SQLite) → TTS responde.

**Em andamento:** Fase 4 (Mãos — executor de ações no PC).

## Setup rápido

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**Baixar a voz do Piper** (~60MB) uma única vez:
```bash
curl -L -o data/models/pt_BR-faber-medium.onnx      https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx
curl -L -o data/models/pt_BR-faber-medium.onnx.json https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json
```

**Ollama** (Fase 3): https://ollama.com/download — depois `ollama pull phi3:mini`.

```bash
python src/main.py     # roda o assistente
```

Ctrl+C encerra limpo (cancela tasks, libera microfone).

## Estrutura

```
src/
├── main.py           # orquestra tudo; asyncio.Queue entre módulos
├── voice/            # Fase 2 ✅
│   ├── listener.py     # captura do microfone (thread → fila async)
│   ├── wake_word.py    # openWakeWord + fluxo pós-detecção
│   ├── vad.py          # Silero VAD (filtra silêncio)
│   ├── stt.py          # faster-whisper (PT-BR)
│   ├── tts.py          # Piper
│   └── earcons.py      # bip + som de processando
├── brain/            # Fase 3 ✅
│   ├── llm_client.py   # BaseLLMClient + OllamaClient (JSON mode)
│   ├── intent_parser.py # Pydantic valida intent; retry automático
│   ├── memory.py       # sliding window (deque) + SQLite persistência
│   └── prompts.py      # system prompts com exemplos por intent
├── executor/         # Fase 4 (planejado)
├── security/         # Fase 5 (planejado)
└── integrations/     # Fase 6 (planejado)
```

## Testar módulos individualmente

```bash
python -m src.brain.llm_client   # demo: manda um prompt JSON pro Ollama local
```

## Configuração

Tudo em `config.yaml`. Principais seções: `voice.{wake_word, stt, vad, tts}`, `brain.{model, host, temperature}`, `security.{protected_paths, blocked_commands}`, `executor.timeouts`.

Nunca hardcodar paths — tudo passa pelo config.

## Fases

1. ✅ **Fundação** — estrutura, config, main async com graceful shutdown
2. ✅ **Ouvido** — wake word + VAD + STT + TTS; pipeline de voz end-to-end
3. ✅ **Cérebro** — Ollama + Phi-3 Mini, output JSON validado, memória com SQLite
4. 🚧 **Mãos** — executor (file, app, browser, system) com timeouts
5. ⏳ **Escudo** — guardian + rate limiter + confirmação por voz
6. ⏳ **Evolução** — email, GUI, barge-in, switch pra API Claude

## Pendências conhecidas

- Modelo custom "bolha.onnx" (openWakeWord) não treinado — usando `hey_jarvis` como wake word temporário
- Whisper `base` erra ocasionalmente palavras PT-BR — subir pra `small`/`medium` se incomodar
- Piper oficial PT-BR só tem voz masculina (Edge TTS foi testado e revertido por `NoAudioReceived`)
