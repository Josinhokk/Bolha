# executor/

Executa as ações decididas pelo cérebro. Sempre com timeout.

Arquivos (Fase 4):
- `router.py` ✅ — roteia ação para o handler certo, com `asyncio.wait_for` por intent
- `file_manager.py` ✅ — CRUD de arquivos e pastas
- `app_launcher.py` ✅ — abrir e fechar programas (aliases PT-BR no config.yaml)
- `browser.py` ✅ — URLs e pesquisas no Google
- `system_cmd.py` ✅ — volume (pycaw), info (psutil), shutdown/restart/sleep
- `permissions.py` ✅ — checa UAC/admin antes de ações que exigem elevação
- `screen_control.py` ✅ — PyAutoGUI (último recurso: click, type, screenshot)

## screen_control — quando usar
É o fallback quando o usuário pede algo que nenhum outro handler resolve. Três intents:
- `screen_click` (x, y, button, clicks) — fail-safe aborta se o mouse for pro canto da tela.
- `screen_type` (text, interval) — digita na janela em foco.
- `screen_screenshot` (path opcional) — salva PNG em `data/screenshots/` por padrão.

PyAutoGUI é opcional: sem ele, os handlers sobem em modo degradado e devolvem mensagem amigável.

## Como o system_cmd lida com admin
- `system_info`: não precisa admin.
- `system_volume`: não precisa admin (pycaw fala com a sessão de áudio do user).
- `system_shutdown` action=`shutdown|restart`: **precisa admin**. Se `is_admin()` for False, retorna `MENSAGEM_SEM_ADMIN` sem tentar executar.
- `system_shutdown` action=`sleep`: não precisa admin.

Dependências opcionais (`psutil`, `pycaw`, `comtypes`): se não estiverem instaladas, o módulo sobe em modo degradado e devolve mensagem amigável.
