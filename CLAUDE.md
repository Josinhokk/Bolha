# Bolha — Contexto do Projeto

## O que é
Assistente pessoal de voz para Windows 11 com controle total do PC.

## Status atual
- Fase: 2/6 (Ouvido) — sub-etapas 1 e 2 concluídas
- Último trabalho:
  - `src/voice/vad.py` — `SileroVAD` (onnx), roda em thread via `asyncio.to_thread`, converte int16→float32, concatena só segmentos com voz (threshold + min_silence_ms + min_speech_ms)
  - `src/voice/stt.py` — `WhisperSTT` com faster-whisper; detecta idioma automático (PT/EN) se `language: auto`; fallback CUDA→CPU se cuBLAS falhar
  - `src/voice/earcons.py` — adicionou `tocar_processando()` (440Hz grave enquanto Whisper roda)
  - `src/voice/wake_word.py` — pós-captura agora roda VAD → (se tem voz) earcon processando → Whisper → print `[STT] (idioma) texto` + `put` em `fila_transcricao`
  - `main.py` — injeta `fila_transcricao` no detector
  - `config.yaml` — adicionou `voice.stt.compute_type/beam_size/language=auto`, `voice.vad.min_speech_ms`, earcons de processando
  - Sub-etapa 1 anterior: listener, wake_word base, bip, fix `sys.path`, `inference_framework: onnx` (tflite-runtime não existe no Windows)
- Próximo passo: Fase 2 sub-etapa 3 — Piper TTS para responder por voz (consumir fila do brain quando houver)
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
- Piper TTS consumindo respostas do brain (fila a criar)
- Streaming VAD em vez de janela fixa de 5s (corta quando o usuário termina de falar)
- Fase 3: Ollama + Phi-3 Mini consumindo `fila_transcricao` e publicando `fila_acoes`

## Regras pro Claude Code
1. Sempre ler o CLAUDE.md antes de começar
2. Atualizar o CLAUDE.md no final de cada sessão
3. Um módulo por vez — não misturar voice + brain na mesma sessão
4. Testar antes de avançar — cada fase tem seu entregável
5. Commits descritivos — `feat(voice): add wake word detection`
6. Nunca hardcodar paths — tudo vem do config.yaml
