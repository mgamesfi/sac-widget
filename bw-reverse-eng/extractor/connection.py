"""Camada de conexão ao HANA (RF01).

Implementa um wrapper fino sobre `hdbcli` que expõe apenas o necessário para a
extração de metadados: `execute()` (leitura em lote) e `test_connection()`.

O `hdbcli` é importado de forma preguiçosa (lazy) dentro dos métodos, para que
o restante da aplicação (processor/docgen, e os testes unitários deste módulo)
não dependam da instalação do driver SAP nem de uma conexão real — os testes
injetam um objeto que segue o protocolo `SqlConnection` definido abaixo.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("bw_reveng.extractor.connection")


class ConnectionError_(Exception):
    """Erro ao conectar ou autenticar no HANA."""


class QueryError(Exception):
    """Erro ao executar uma consulta de metadados."""


@runtime_checkable
class SqlConnection(Protocol):
    """Contrato mínimo exigido pelas camadas de extração.

    `HanaConnection` implementa este protocolo usando `hdbcli`; os testes usam
    um "fake" em memória — ambos são intercambiáveis para `classic_layer` e
    `nextgen_layer`.
    """

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        ...


class HanaConnection:
    """Conexão HANA via `hdbcli`, usada como fonte SQL preferencial (seção 3.3)."""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str | None = None,
        client_cert: str | None = None,
        client_key: str | None = None,
        encrypt: bool = True,
        validate_cert: bool = True,
        connect_timeout_s: int = 30,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self._password = password
        self._client_cert = client_cert
        self._client_key = client_key
        self.encrypt = encrypt
        self.validate_cert = validate_cert
        self.connect_timeout_s = connect_timeout_s
        self._conn = None

    def connect(self) -> "HanaConnection":
        try:
            from hdbcli import dbapi
        except ImportError as exc:  # pragma: no cover - depende de ambiente do cliente
            raise ConnectionError_(
                "Pacote 'hdbcli' não instalado. Instale com `pip install hdbcli`."
            ) from exc

        try:
            self._conn = dbapi.connect(
                address=self.host,
                port=self.port,
                user=self.user,
                password=self._password,
                encrypt=self.encrypt,
                sslValidateCertificate=self.validate_cert,
                sslCryptoProvider="openssl" if self.encrypt else None,
                communicationTimeout=self.connect_timeout_s * 1000,
            )
        except Exception as exc:  # noqa: BLE001 - normaliza qualquer erro do driver
            raise ConnectionError_(f"Falha ao conectar em {self.host}:{self.port}: {exc}") from exc

        logger.info("Conectado ao HANA %s:%s como %s", self.host, self.port, self.user)
        return self

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None

    def __enter__(self) -> "HanaConnection":
        return self.connect()

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        if self._conn is None:
            raise ConnectionError_("Conexão não estabelecida — chame connect() antes de execute().")
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, params or ())
            columns = [c[0] for c in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            cursor.close()
        except Exception as exc:  # noqa: BLE001
            raise QueryError(f"Falha ao executar consulta: {exc}\nSQL: {sql}") from exc
        return [dict(zip(columns, row)) for row in rows]

    def test_connection(self) -> dict[str, Any]:
        """Valida conectividade e permissões mínimas antes da extração completa.

        Corresponde ao modo `--test-connection` do RF01: verifica que o usuário
        técnico consegue autenticar e ler as tabelas de metadados essenciais.
        """
        info: dict[str, Any] = {"host": self.host, "port": self.port, "user": self.user}
        try:
            if self._conn is None:
                self.connect()
            version_row = self.execute("SELECT VERSION FROM SYS.M_DATABASE")
            info["hana_version"] = version_row[0]["VERSION"] if version_row else "desconhecida"

            checks = {
                "RSDIOBJ": "SELECT COUNT(*) AS CNT FROM RSDIOBJ",
                "RSDCUBE": "SELECT COUNT(*) AS CNT FROM RSDCUBE",
                "SYS.VIEWS": "SELECT COUNT(*) AS CNT FROM SYS.VIEWS",
            }
            permissions: dict[str, bool] = {}
            for label, sql in checks.items():
                try:
                    self.execute(sql)
                    permissions[label] = True
                except QueryError:
                    permissions[label] = False
            info["permissions"] = permissions
            info["ok"] = all(permissions.values())
        except ConnectionError_ as exc:
            info["ok"] = False
            info["error"] = str(exc)
        return info
