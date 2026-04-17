"""
Verificação de privilégios (UAC) no Windows.

Usa ctypes.windll.shell32.IsUserAnAdmin() pra detectar se o processo atual
está elevado. O resultado é cacheado — o privilégio não muda durante a
execução do processo.
"""
from __future__ import annotations

import ctypes
import logging
from functools import lru_cache

LOGGER = logging.getLogger("bolha.executor.permissions")

MENSAGEM_SEM_ADMIN = "Preciso de permissão de administrador para isso."


@lru_cache(maxsize=1)
def is_admin() -> bool:
    """Retorna True se o processo atual tem privilégio de administrador."""
    try:
        resultado = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError) as exc:
        LOGGER.warning("Não foi possível verificar privilégio admin: %s", exc)
        return False

    LOGGER.debug("Privilégio admin: %s", resultado)
    return resultado
