# executor/

Executa as ações decididas pelo cérebro. Sempre com timeout.

Arquivos (Fase 4):
- `router.py` — roteia ação para o handler certo
- `file_manager.py` — CRUD de arquivos e pastas
- `app_launcher.py` — abrir programas
- `browser.py` — URLs e pesquisas
- `system_cmd.py` — volume, brilho, shutdown
- `screen_control.py` — PyAutoGUI (último recurso)
- `permissions.py` — checa UAC/admin antes de executar
