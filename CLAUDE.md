# Bolha — Contexto do Projeto

## O que é
Assistente pessoal de voz para Windows 11 com controle total do PC.

## Status atual
- Fase: **3/6 (Cérebro)** — sub-etapa 2 concluída (intent_parser + prompts)
- Último trabalho:
  - `src/brain/intent_parser.py` — `IntentResponse` (Pydantic BaseModel com `intent`, `params`, `confidence` [0.0–1.0], `destructive`). `IntentParser` recebe `BaseLLMClient`, método `interpretar(texto)` manda pro LLM com system prompt de intents, valida JSON com Pydantic, retry até 3x se inválido, fallback `_not_understood()` se todas falharem. Loga tentativa, latência, intent e confidence.
  - `src/brain/prompts.py` — `SYSTEM_INTENT` com 14 intents conhecidas (open_app, close_app, browser_open, browser_search, file_create, file_delete, file_move, file_list, system_info, system_volume, system_shutdown, conversation, not_understood) + regras de confiança/destructive. `INTENT_USER_TEMPLATE` formata o texto do usuário.
  - Sub-etapa 1 (llm_client) já concluída: `BaseLLMClient` ABC + `OllamaClient` + `LLMResponse` dataclass.
- Próximo passo: sub-etapa 3 — `memory.py` (sliding window + SQLite para histórico de conversas), depois integrar brain no main.py como task consumindo `fila_transcricao`.
- Entrega da Fase 2: pipeline de voz end-to-end funcionando
- Entregável validado: "hey jarvis, que horas são" → bip → gravação → VAD → Whisper → print `[STT] (pt) que horas são` → faber responde "Entendi: que horas são" por voz.
- Pipeline em `main.py` + `wake_word.py`:
  1. `MicrofoneListener` abre `sd.InputStream` 16kHz/int16/1280 samples, callback → `fila_audio` via `call_soon_threadsafe`
  2. `WakeWordDetector` consome `fila_audio`, roda openWakeWord (onnx) a cada chunk
  3. Score ≥ threshold + fora cooldown → `tocar_bip()` → `_capturar_comando()` (5s)
  4. `SileroVAD.filtrar_voz()` (thread) → se None, descarta
  5. Se tem voz → `tocar_processando()` → `WhisperSTT.transcrever()` (thread, language=pt)
  6. `print("[STT] (pt) ...")` + `fila_transcricao.put(texto)` (pra Fase 3)
  7. `PiperTTS.falar(f"Entendi: {texto}")` — placeholder até o brain existir
- Último trabalho (sub-etapa 3+4):
  - `src/voice/tts.py` — `PiperTTS` com piper-tts 1.4.x (nova API `voice.synthesize()` → `AudioChunk`s com `audio_int16_array`). Modo silencioso se modelo não está em disco.
  - Edge TTS foi tentado (voz Yara feminina) e revertido — NoAudioReceived + problema na instalação. Ficou só o Piper (voz masculina faber).
  - Modelo Piper `pt_BR-faber-medium.onnx(.json)` baixado em `data/models/` (~60MB).
- Brain em construção: Ollama + Phi-3 Mini consumindo `fila_transcricao`, output JSON validado com Pydantic, memória com sliding window + SQLite. llm_client, intent_parser e prompts prontos; faltam memory e a task consumidora em main.py.
- Pendências técnicas:
  - Modelo custom "bolha.onnx" não treinado; rodando com `hey_jarvis` como wake word.
  - Whisper `base` erra palavras PT-BR ocasionalmente ("feijão" → "fejão"). Considerar subir pra `small`/`medium` se for incomodar.
  - Só tem voz masculina no TTS (limitação do Piper oficial PT-BR).

## Decisões tomadas
- Linguagem: Python 3.11+
- Arquitetura: asyncio desde o dia 1 (asyncio.Queue entre módulos)
- STT: Whisper (faster-whisper)
- TTS: Piper (voz `pt_BR-faber-medium`, masculina — Piper oficial não tem feminina PT-BR). Edge TTS foi testado e rejeitado (erro `NoAudioReceived` + problema na instalação).
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
- Baixar `pt_BR-faber-medium.onnx(.json)` pra `data/models/` (voz do TTS)
- Treinar modelo custom "bolha.onnx" (openWakeWord) e apontar em `voice.wake_word.model_path`
- Fase 3: Ollama + Phi-3 Mini consumindo `fila_transcricao`, Pydantic no output, SQLite de memória
- Substituir a resposta hardcoded "Entendi: X" por resposta real do brain
- Streaming VAD em vez de janela fixa de 5s (corta quando o usuário para de falar)

## Regras pro Claude Code
1. Sempre ler o CLAUDE.md antes de começar
2. Atualizar o CLAUDE.md no final de cada sessão
3. Um módulo por vez — não misturar voice + brain na mesma sessão
4. Testar antes de avançar — cada fase tem seu entregável
5. Commits descritivos — `feat(voice): add wake word detection`
6. Nunca hardcodar paths — tudo vem do config.yaml
