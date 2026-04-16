"""
File Manager — operações de arquivo e pasta.

Todas as operações rodam em thread (asyncio.to_thread) pra não bloquear
o event loop. PermissionError e FileNotFoundError viram mensagens amigáveis.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any

from src.executor.router import ActionResult

LOGGER = logging.getLogger("bolha.executor.file_manager")


def _resolver_path(raw: str, base: Path) -> Path:
    """Resolve path relativo ao home do usuário."""
    p = Path(raw)
    if p.is_absolute():
        return p
    return (base / p).resolve()


class FileManager:
    """Handler de operações de arquivo: create, delete, move, copy, list, folder_create, folder_delete."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._base = Path.home()
        self._dry_run: bool = config.get("executor", {}).get("dry_run", False)
        LOGGER.info("FileManager pronto (base=%s, dry_run=%s).", self._base, self._dry_run)

    def handlers(self) -> dict[str, Any]:
        """Retorna mapa intent → handler pra registrar no router."""
        return {
            "file_create": self.file_create,
            "file_delete": self.file_delete,
            "file_move": self.file_move,
            "file_copy": self.file_copy,
            "file_list": self.file_list,
            "folder_create": self.folder_create,
            "folder_delete": self.folder_delete,
        }

    async def file_create(self, params: dict[str, Any]) -> ActionResult:
        raw_path = params.get("path", "")
        content = params.get("content", "")
        if not raw_path:
            return ActionResult(False, "Caminho do arquivo não especificado.", "file_create", params)

        path = _resolver_path(raw_path, self._base)

        if self._dry_run:
            return ActionResult(True, f"[DRY RUN] Criaria: {path}", "file_create", params)

        def _criar() -> str:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"Arquivo criado: {path}"

        return await self._executar_sync(_criar, "file_create", params)

    async def file_delete(self, params: dict[str, Any]) -> ActionResult:
        raw_path = params.get("path", "")
        if not raw_path:
            return ActionResult(False, "Caminho do arquivo não especificado.", "file_delete", params)

        path = _resolver_path(raw_path, self._base)

        if self._dry_run:
            return ActionResult(True, f"[DRY RUN] Deletaria: {path}", "file_delete", params)

        def _deletar() -> str:
            if not path.exists():
                return f"Arquivo não encontrado: {path}"
            path.unlink()
            return f"Arquivo deletado: {path}"

        return await self._executar_sync(_deletar, "file_delete", params)

    async def file_move(self, params: dict[str, Any]) -> ActionResult:
        source = params.get("source", "")
        dest = params.get("destination", "")
        if not source or not dest:
            return ActionResult(False, "Origem ou destino não especificado.", "file_move", params)

        src_path = _resolver_path(source, self._base)
        dst_path = _resolver_path(dest, self._base)

        if self._dry_run:
            return ActionResult(True, f"[DRY RUN] Moveria: {src_path} → {dst_path}", "file_move", params)

        def _mover() -> str:
            if not src_path.exists():
                return f"Arquivo não encontrado: {src_path}"
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_path), str(dst_path))
            return f"Movido: {src_path} → {dst_path}"

        return await self._executar_sync(_mover, "file_move", params)

    async def file_copy(self, params: dict[str, Any]) -> ActionResult:
        source = params.get("source", "")
        dest = params.get("destination", "")
        if not source or not dest:
            return ActionResult(False, "Origem ou destino não especificado.", "file_copy", params)

        src_path = _resolver_path(source, self._base)
        dst_path = _resolver_path(dest, self._base)

        if self._dry_run:
            return ActionResult(True, f"[DRY RUN] Copiaria: {src_path} → {dst_path}", "file_copy", params)

        def _copiar() -> str:
            if not src_path.exists():
                return f"Arquivo não encontrado: {src_path}"
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src_path), str(dst_path))
            return f"Copiado: {src_path} → {dst_path}"

        return await self._executar_sync(_copiar, "file_copy", params)

    async def file_list(self, params: dict[str, Any]) -> ActionResult:
        raw_path = params.get("path", "")
        path = _resolver_path(raw_path, self._base) if raw_path else self._base

        def _listar() -> str:
            if not path.exists():
                return f"Pasta não encontrada: {path}"
            if not path.is_dir():
                return f"Não é uma pasta: {path}"
            itens = sorted(path.iterdir())
            if not itens:
                return f"Pasta vazia: {path}"
            linhas = []
            for item in itens[:50]:
                tipo = "📁" if item.is_dir() else "📄"
                linhas.append(f"  {tipo} {item.name}")
            header = f"Conteúdo de {path} ({len(itens)} itens):"
            if len(itens) > 50:
                header += f" (mostrando 50 de {len(itens)})"
            return header + "\n" + "\n".join(linhas)

        return await self._executar_sync(_listar, "file_list", params)

    async def folder_create(self, params: dict[str, Any]) -> ActionResult:
        raw_path = params.get("path", "")
        if not raw_path:
            return ActionResult(False, "Caminho da pasta não especificado.", "folder_create", params)

        path = _resolver_path(raw_path, self._base)

        if self._dry_run:
            return ActionResult(True, f"[DRY RUN] Criaria pasta: {path}", "folder_create", params)

        def _criar() -> str:
            path.mkdir(parents=True, exist_ok=True)
            return f"Pasta criada: {path}"

        return await self._executar_sync(_criar, "folder_create", params)

    async def folder_delete(self, params: dict[str, Any]) -> ActionResult:
        raw_path = params.get("path", "")
        if not raw_path:
            return ActionResult(False, "Caminho da pasta não especificado.", "folder_delete", params)

        path = _resolver_path(raw_path, self._base)

        if self._dry_run:
            return ActionResult(True, f"[DRY RUN] Deletaria pasta: {path}", "folder_delete", params)

        def _deletar() -> str:
            if not path.exists():
                return f"Pasta não encontrada: {path}"
            if not path.is_dir():
                return f"Não é uma pasta: {path}"
            shutil.rmtree(str(path))
            return f"Pasta deletada: {path}"

        return await self._executar_sync(_deletar, "folder_delete", params)

    async def _executar_sync(
        self,
        func: Any,
        intent: str,
        params: dict[str, Any],
    ) -> ActionResult:
        """Roda função sync em thread, captura erros comuns."""
        try:
            msg = await asyncio.to_thread(func)
            success = not msg.startswith("Arquivo não encontrado") and not msg.startswith("Pasta não encontrada") and not msg.startswith("Não é uma pasta")
            return ActionResult(success=success, message=msg, intent=intent, params=params)
        except PermissionError:
            msg = "Sem permissão pra essa operação. Tente rodar como administrador."
            LOGGER.warning("%s: PermissionError em %s", intent, params)
            return ActionResult(success=False, message=msg, intent=intent, params=params)
        except FileNotFoundError as exc:
            msg = f"Arquivo ou pasta não encontrado: {exc.filename or exc}"
            LOGGER.warning("%s: FileNotFoundError — %s", intent, msg)
            return ActionResult(success=False, message=msg, intent=intent, params=params)
        except OSError as exc:
            msg = f"Erro do sistema: {exc}"
            LOGGER.exception("%s: OSError", intent)
            return ActionResult(success=False, message=msg, intent=intent, params=params)
