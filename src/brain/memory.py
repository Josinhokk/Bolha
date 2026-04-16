"""
Memória do Bolha — sliding window + SQLite.

Mantém as últimas N interações no contexto do LLM (rápido) e persiste
tudo no SQLite pra consulta futura e analytics.

Cada interação guarda: timestamp, user_input, intent_response completa
e resultado da execução (quando houver).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("bolha.brain.memory")


@dataclass
class Interacao:
    """Uma interação completa (pergunta + resposta + resultado)."""

    timestamp: str
    user_input: str
    intent: str
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    destructive: bool = False
    resultado: str = ""

    def to_context_str(self) -> str:
        """Formata pra incluir no contexto do LLM."""
        return (
            f"[{self.timestamp}] Usuário: \"{self.user_input}\" "
            f"→ intent={self.intent} params={json.dumps(self.params, ensure_ascii=False)}"
        )


class MemoriaManager:
    """Sliding window em memória + persistência SQLite."""

    def __init__(self, config: dict[str, Any], root_dir: Path) -> None:
        bcfg = config.get("brain", {})
        self._max_history: int = bcfg.get("max_history", 10)

        db_path = (root_dir / config.get("paths", {}).get("db_path", "data/logs/bolha.db")).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._window: deque[Interacao] = deque(maxlen=self._max_history)

        self._conn = sqlite3.connect(str(db_path))
        self._criar_tabela()

        LOGGER.info(
            "MemoriaManager pronto (max_history=%d, db=%s).",
            self._max_history,
            db_path,
        )

    def _criar_tabela(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS interacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_input TEXT NOT NULL,
                intent TEXT NOT NULL,
                params TEXT NOT NULL DEFAULT '{}',
                confidence REAL NOT NULL DEFAULT 0.0,
                destructive INTEGER NOT NULL DEFAULT 0,
                resultado TEXT NOT NULL DEFAULT ''
            )
        """)
        self._conn.commit()

    def registrar(
        self,
        user_input: str,
        intent: str,
        params: dict[str, Any] | None = None,
        confidence: float = 0.0,
        destructive: bool = False,
        resultado: str = "",
    ) -> Interacao:
        """Registra uma interação na window e no SQLite."""
        agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        interacao = Interacao(
            timestamp=agora,
            user_input=user_input,
            intent=intent,
            params=params or {},
            confidence=confidence,
            destructive=destructive,
            resultado=resultado,
        )

        self._window.append(interacao)

        self._conn.execute(
            """INSERT INTO interacoes (timestamp, user_input, intent, params, confidence, destructive, resultado)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                interacao.timestamp,
                interacao.user_input,
                interacao.intent,
                json.dumps(interacao.params, ensure_ascii=False),
                interacao.confidence,
                int(interacao.destructive),
                interacao.resultado,
            ),
        )
        self._conn.commit()

        LOGGER.debug(
            "Interação registrada: '%s' → %s (window=%d/%d)",
            user_input,
            intent,
            len(self._window),
            self._max_history,
        )
        return interacao

    def contexto_para_prompt(self) -> str:
        """Retorna o histórico recente formatado pra injetar no prompt do LLM."""
        if not self._window:
            return ""
        linhas = [i.to_context_str() for i in self._window]
        return "Histórico recente:\n" + "\n".join(linhas)

    def ultimas(self, n: int | None = None) -> list[Interacao]:
        """Retorna as últimas N interações da window."""
        items = list(self._window)
        if n is not None:
            return items[-n:]
        return items

    def buscar_no_sqlite(self, limite: int = 50) -> list[dict[str, Any]]:
        """Busca interações antigas no SQLite (além da window)."""
        cursor = self._conn.execute(
            "SELECT timestamp, user_input, intent, params, confidence, destructive, resultado "
            "FROM interacoes ORDER BY id DESC LIMIT ?",
            (limite,),
        )
        resultados = []
        for row in cursor.fetchall():
            resultados.append({
                "timestamp": row[0],
                "user_input": row[1],
                "intent": row[2],
                "params": json.loads(row[3]),
                "confidence": row[4],
                "destructive": bool(row[5]),
                "resultado": row[6],
            })
        return resultados

    def fechar(self) -> None:
        """Fecha a conexão SQLite."""
        self._conn.close()
        LOGGER.info("MemoriaManager fechado.")
