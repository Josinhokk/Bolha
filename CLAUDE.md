# Bolha — Contexto do Projeto

## O que é
Assistente pessoal de voz para Windows 11 com controle total do PC.

## Status atual
- Fase: **4/6 (Mãos)** — sub-etapa 3 concluída (system_cmd + permissions)
- Último trabalho:
  - `src/executor/permissions.py` — `is_admin()` via `ctypes.windll.shell32.IsUserAnAdmin()`, cacheado com `lru_cache`. Exporta `MENSAGEM_SEM_ADMIN = "Preciso de permissão de administrador para isso."`. Não auto-eleva — só detecta e reporta.
  - `src/executor/system_cmd.py` — `SystemManager` com `system_info` (psutil: CPU%, RAM GB usado/total, disco livre/total), `system_volume` (pycaw via COM: up/down/mute/unmute, passo padrão `executor.system.volume_step=10%`, desmuta ao subir/descer), `system_shutdown` (subprocess: `shutdown /s|/r /t 0` pra desligar/reiniciar, `rundll32 powrprof.dll,SetSuspendState 0,1,0` pra suspender). shutdown/restart checam `is_admin()` antes e bloqueiam com `MENSAGEM_SEM_ADMIN` se não estiver elevado; sleep funciona sem admin. Import de pycaw/psutil é try/except → ausência vira mensagem amigável sem quebrar o app.
  - `config.yaml` — nova seção `executor.system` (`volume_step: 10`, `disk_path: "C:/"`).
  - `requirements.txt` — adicionados `psutil>=5.9.0`, `pycaw>=20240210`, `comtypes>=1.2.0` (COM wrapper que pycaw usa).
  - `src/main.py` — `SystemManager` instanciado e registrado no router ao lado dos demais.
  - Sub-etapas 1 e 2 (router, file_manager, app_launcher, browser): mantidas intactas.
- Fase 3 (Cérebro): CONCLUÍDA — llm_client, intent_parser, prompts, memory.
- Próximo passo: sub-etapa 4 — screen_control.py (PyAutoGUI como último recurso, mouse/teclado/screenshot).
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
- Brain completo: Ollama + Phi-3 Mini consumindo `fila_transcricao`, output JSON validado com Pydantic, memória com sliding window + SQLite. Pipeline: wake word → STT → fila_transcricao → brain (intent parser + memória + TTS).
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
- config.yaml: valores com `:` no final (ex: `ms-settings:`) precisam de aspas no YAML, senão o parser quebra.

## Problemas conhecidos
- Sem modelo custom de "Bolha" (openWakeWord) — usando `hey_jarvis` como fallback temporário

## Próximos passos
- Baixar `pt_BR-faber-medium.onnx(.json)` pra `data/models/` (voz do TTS)
- Treinar modelo custom "bolha.onnx" (openWakeWord) e apontar em `voice.wake_word.model_path`
- Instalar deps novas: `pip install psutil pycaw comtypes` (sem elas, system_info/system_volume ficam desabilitados mas o app sobe)
- Fase 4 sub-etapa 4: screen_control.py (PyAutoGUI — mouse, teclado, screenshot)
- Fase 4 sub-etapa 5: integração com o security/guardian (rate limiter + confirm destrutivas) já listada no config mas ainda não codada
- Streaming VAD em vez de janela fixa de 5s (corta quando o usuário para de falar)

## Regras pro Claude Code
1. Sempre ler o CLAUDE.md antes de começar
2. Atualizar o CLAUDE.md no final de cada sessão
3. Um módulo por vez — não misturar voice + brain na mesma sessão
4. Testar antes de avançar — cada fase tem seu entregável
5. Commits descritivos — `feat(voice): add wake word detection`
6. Nunca hardcodar paths — tudo vem do config.yaml
