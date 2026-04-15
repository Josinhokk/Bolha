# Bolha — Contexto do Projeto

## O que é
Assistente pessoal de voz para Windows 11 com controle total do PC.

## Status atual
- Fase: 2/6 (Ouvido) — sub-etapa 1 concluída
- Último trabalho:
  - `src/voice/listener.py` — captura do microfone em thread de áudio, empurra chunks int16 na `fila_audio` via `loop.call_soon_threadsafe`
  - `src/voice/wake_word.py` — openWakeWord consome a fila; no hit toca bip e grava ~5s de comando
  - `src/voice/earcons.py` — bip senoidal 880Hz/120ms não-bloqueante
  - `main.py` — substituiu heartbeat por tasks listener + wake_word; shutdown chama `listener.stop()`
  - `config.yaml` — reestruturou `voice.wake_word` como dict (model_path, fallback_model, threshold, cooldown), adicionou `voice.audio` (chunk_samples, queue_maxsize, input_device), `voice.command.duration_seconds` e `voice.earcons`
- Próximo passo: Fase 2 sub-etapa 2 — Silero VAD + Whisper STT + Piper TTS
- Pendência conhecida: modelo custom de "Bolha" pro openWakeWord ainda não foi treinado; rodando com fallback `hey_jarvis` até o treino

## Decisões tomadas
- Linguagem: Python 3.11+
- Arquitetura: asyncio desde o dia 1 (asyncio.Queue entre módulos)
- STT: Whisper (faster-whisper)
- TTS: Piper
- LLM: Ollama + Phi-3 Mini (futuro: API Claude) com format: 'json'
- Validação: Pydantic nos outputs do LLM
- Wake word: openWakeWord (treinado com "Bolha")
- Segurança: Guardian intercepta toda ação + rate limiter
- Controle: CLI first, PyAutoGUI como fallback
- UX: Earcons (bip no wake word, som de processando)
- VAD: Silero VAD filtra silêncio antes do Whisper (evita alucinações)
- Memória: sliding window (últimas N interações no prompt, resto no SQLite)
- Executor: timeout por ação + checagem de UAC antes de executar
- Não auto-elevar pra admin (avisa o user, nunca tenta sozinho)
- Graceful shutdown: Ctrl+C e "Bolha, encerrar" fazem cleanup completo

## Convenções de código
- Type hints em tudo
- Docstrings em português
- Cada módulo tem seu README.md
- Imports absolutos (from src.voice.stt import ...)
- Logging padrão do Python (não print)
- Async por padrão (async def em vez de def)
- Debug mode via config.yaml (loga cada etapa no terminal)
- Toda ação do executor tem timeout (asyncio.wait_for)

## Arquitetura
- voice/ → captura e transcreve voz
- brain/ → interpreta intenção via LLM
- executor/ → executa ação no PC
- security/ → valida e loga toda ação

## Erros conhecidos e soluções
(Atualizar a cada sessão com bugs encontrados e como foram resolvidos)

## Problemas conhecidos
- Sem modelo custom de "Bolha" (openWakeWord) — usando `hey_jarvis` como fallback temporário

## Próximos passos
- Treinar modelo custom "bolha.onnx" e apontar em `voice.wake_word.model_path`
- Silero VAD após wake word: corta silêncio antes de mandar pro Whisper
- Whisper (faster-whisper) consumindo `fila_audio` pós-VAD e publicando em `fila_transcricao`
- Piper TTS consumindo respostas do brain
- Som de "processando" enquanto o LLM roda (earcons.py)

## Regras pro Claude Code
1. Sempre ler o CLAUDE.md antes de começar
2. Atualizar o CLAUDE.md no final de cada sessão
3. Um módulo por vez — não misturar voice + brain na mesma sessão
4. Testar antes de avançar — cada fase tem seu entregável
5. Commits descritivos — `feat(voice): add wake word detection`
6. Nunca hardcodar paths — tudo vem do config.yaml
