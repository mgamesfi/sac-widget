"""Conexão RFC complementar (seção 3.3 da especificação): usada apenas para dados que
não são totalmente recuperáveis via SQL puro — no caso deste app, a lógica de negócio
das regras de transformação (mapeamentos, rotinas ABAP, fórmulas), que no BW ficam
armazenadas de forma serializada/binária e não aparecem em `RSTRANSTEPS` além da
contagem de regras (ver `extractor.classic_layer.extract_transformations`).

Aviso importante: `pyrfc` exige o **SAP NW RFC SDK**, uma biblioteca C proprietária
distribuída pela SAP via SAP Support Portal (não instalável via pip, exige
licença/conta SAP). Este módulo foi implementado e testado com uma conexão RFC
"fake" injetada (ver `tests/conftest.py` / `tests/test_rfc_connection.py`), mas nunca
foi executado contra um sistema SAP real — valide cuidadosamente antes de usar em
produção.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("bw_reveng.extractor.rfc_connection")


class RfcConnectionError(Exception):
    """Erro ao conectar/autenticar via RFC."""


class RfcCallError(Exception):
    """Erro ao chamar uma função RFC (função inexistente, sem autorização, etc.)."""


@runtime_checkable
class RfcCaller(Protocol):
    """Contrato mínimo exigido por `extractor.transformation_rules`.

    `RfcConnection` implementa isto usando `pyrfc`; os testes usam um "fake" em
    memória — ambos são intercambiáveis.
    """

    def call(self, function_name: str, **params: Any) -> dict[str, Any]:
        ...


class RfcConnection:
    """Conexão RFC via `pyrfc`, usada apenas para complementar a extração SQL/CSV
    principal com a lógica de negócio das regras de transformação.
    """

    def __init__(
        self,
        ashost: str,
        sysnr: str,
        client: str,
        user: str,
        password: str,
        lang: str = "EN",
        router: str | None = None,
    ) -> None:
        self.ashost = ashost
        self.sysnr = sysnr
        self.client = client
        self.user = user
        self._password = password
        self.lang = lang
        self.router = router
        self._conn = None

    def connect(self) -> "RfcConnection":
        try:
            from pyrfc import Connection
        except ImportError as exc:  # pragma: no cover - depende do NW RFC SDK do ambiente
            raise RfcConnectionError(
                "Pacote 'pyrfc' não instalado (ou SAP NW RFC SDK ausente do sistema). "
                "Instale com `pip install pyrfc` e o SDK correspondente do SAP Support Portal."
            ) from exc

        try:
            kwargs: dict[str, Any] = dict(
                ashost=self.ashost,
                sysnr=self.sysnr,
                client=self.client,
                user=self.user,
                passwd=self._password,
                lang=self.lang,
            )
            if self.router:
                kwargs["saprouter"] = self.router
            self._conn = Connection(**kwargs)
        except Exception as exc:  # noqa: BLE001 - normaliza qualquer erro do driver
            raise RfcConnectionError(f"Falha ao conectar via RFC em {self.ashost}: {exc}") from exc

        logger.info("Conectado via RFC a %s (client %s) como %s", self.ashost, self.client, self.user)
        return self

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None

    def __enter__(self) -> "RfcConnection":
        return self.connect()

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def call(self, function_name: str, **params: Any) -> dict[str, Any]:
        if self._conn is None:
            raise RfcConnectionError("Conexão RFC não estabelecida — chame connect() antes de call().")
        try:
            return self._conn.call(function_name, **params)
        except Exception as exc:  # noqa: BLE001
            raise RfcCallError(f"Falha ao chamar função RFC '{function_name}': {exc}") from exc

    def test_connection(self) -> dict[str, Any]:
        """Valida conectividade RFC chamando `RFC_PING` (função padrão presente em
        qualquer sistema SAP), antes de tentar a extração de regras de transformação.
        """
        info: dict[str, Any] = {"host": self.ashost, "client": self.client, "user": self.user}
        try:
            if self._conn is None:
                self.connect()
            self.call("RFC_PING")
            info["ok"] = True
        except (RfcConnectionError, RfcCallError) as exc:
            info["ok"] = False
            info["error"] = str(exc)
        return info
