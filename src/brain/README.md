# brain/

Interpreta o que o usuário disse e decide a ação.

Arquivos (Fase 3):
- `llm_client.py` — interface genérica (Ollama, futuramente Anthropic)
- `intent_parser.py` — valida saída JSON com Pydantic, retry automático
- `memory.py` — sliding window + SQLite
- `prompts.py` — system prompts e templates
