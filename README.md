# 🫧 Bolha

Assistente pessoal de voz para Windows 11 com controle total do PC.

## Características
- 🎙️ Ativação por voz (wake word "Bolha")
- 🧠 LLM local (Ollama + Phi-3 Mini)
- 🔐 Guardian de segurança — confirmação obrigatória para ações destrutivas
- ⚡ Async-first (asyncio desde o dia 1)
- 🧩 Modular — cada componente é substituível

## Stack
Python 3.11+, Whisper, Piper TTS, Ollama, openWakeWord, Silero VAD, Pydantic, SQLite.

## Status
**Fase 1/6** — Fundação. Estrutura do projeto e main.py async com graceful shutdown.

## Setup
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python src/main.py
```

Ctrl+C encerra limpo (cancela tasks, fecha SQLite, libera microfone).

## Estrutura
```
src/
├── voice/        # captura e transcreve voz
├── brain/        # interpreta intenção via LLM
├── executor/     # executa ação no PC
├── security/     # valida e loga toda ação
└── integrations/ # integrações externas (email, etc)
```

## Configuração
Tudo em `config.yaml`. Nunca hardcodar paths.

## Fases
1. ✅ Fundação — estrutura, config, main async
2. ⏳ Ouvido — wake word + STT + TTS + VAD
3. ⏳ Cérebro — LLM + intent parser + memória
4. ⏳ Mãos — executor (file, app, browser, system)
5. ⏳ Escudo — guardian + rate limiter + confirmação
6. ⏳ Evolução — email, GUI, barge-in, API Claude
