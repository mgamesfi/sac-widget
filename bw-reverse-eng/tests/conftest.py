"""Fixtures compartilhadas — em especial um `SqlConnection` fake, sem hdbcli/HANA real."""
from __future__ import annotations

from typing import Any

import pytest


class FakeConnection:
    """Implementa o protocolo `extractor.connection.SqlConnection` em memória.

    `script` é uma lista de (substring, linhas): a primeira entrada cuja
    substring aparece no SQL executado é usada como resposta. Permite testar
    classic_layer/nextgen_layer sem depender do driver `hdbcli` nem de um HANA real.
    """

    def __init__(self, script: list[tuple[str, list[dict[str, Any]]]], user: str = "BWREVENG_TECH"):
        self.script = script
        self.calls: list[tuple[str, tuple]] = []
        self.user = user

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        self.calls.append((sql, params or ()))
        for needle, rows in self.script:
            if needle in sql:
                return rows
        raise AssertionError(f"Nenhuma resposta configurada para a consulta:\n{sql}")


@pytest.fixture
def fake_connection_factory():
    return FakeConnection
