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


class FakeRfcConnection:
    """Implementa o protocolo `extractor.rfc_connection.RfcCaller` em memória.

    `responses` mapeia nome de função RFC -> resultado (dict) ou uma Exception a
    ser levantada. Permite testar `extractor.transformation_rules` sem depender
    de `pyrfc`/SAP NW RFC SDK nem de um sistema SAP real.
    """

    def __init__(self, responses: dict[str, Any]):
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, function_name: str, **params: Any) -> dict[str, Any]:
        self.calls.append((function_name, params))
        if function_name not in self.responses:
            raise AssertionError(f"Nenhuma resposta configurada para a função RFC: {function_name}")
        outcome = self.responses[function_name]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def fake_rfc_connection_factory():
    return FakeRfcConnection
