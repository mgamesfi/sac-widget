"""Fonte alternativa de metadados: tabelas exportadas para arquivos CSV, para quando
não há acesso SQL direto ao HANA (ex: o cliente só consegue exportar os dumps das
tabelas de dicionário para arquivo).

`CsvConnection` implementa o mesmo protocolo `SqlConnection` que `HanaConnection`
(`extractor.connection.SqlConnection`): carrega cada CSV reconhecido para uma tabela
homônima num SQLite em memória e executa as consultas com `?` como placeholder —
exatamente o que `classic_layer`/`nextgen_layer` já geram. Ou seja, nenhuma dessas
duas camadas precisa saber se está lendo do HANA ou de CSV.
"""
from __future__ import annotations

import csv
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger("bw_reveng.extractor.csv_source")

#: Tabelas que classic_layer/nextgen_layer sabem consultar (seção 3 da especificação).
#: O nome de arquivo esperado é `<TABELA>.csv` (case-insensitive) dentro do diretório
#: informado — inclusive para as tabelas do catálogo HANA com "." no nome
#: (ex: `SYS.VIEWS.csv`).
KNOWN_TABLES = [
    "RSDIOBJ", "RSDIOBJT",
    "RSDCHA", "RSDKYF",  # tipo de dado por InfoObject (características/key figures)
    "RSDCUBE", "RSDCUBET",
    "RSDCUBEIOBJ",  # campos (características + key figures) de InfoCube/MultiProvider
    "RSDODSO", "RSDODSOT",
    "RSDODSOIOBJ",  # campos de DSO standard
    "RSDMPRO",
    "RSTRAN", "RSTRANSTEPS",
    "RSBKDTP",
    "RSPCCHAIN", "RSPCLOGCHAIN",
    "RSDHIE", "RSDHIET",
    "RSOADSO", "RSOADSOT",
    "RSOHCPR", "RSOHCPRT", "RSOHCPRSRC", "RSOHCPRELEMENT",
    "RSOOSVIEW", "RSOOSVIEWT",
    "SYS.VIEWS", "SYS.TABLE_COLUMNS", "SYS.M_DATABASE",
]

#: Tabelas cuja presença já viabiliza uma extração mínima (usado por test_connection()).
_CORE_TABLES = ("RSDIOBJ", "RSDCUBE", "RSDODSO")

#: Tabelas de texto (`*T`) usadas em LEFT JOIN pelas consultas de classic_layer/
#: nextgen_layer. Ao contrário das tabelas de enriquecimento (RSDMPRO, RSTRANSTEPS
#: etc., já toleradas via `_run_optional`), um JOIN referencia a tabela diretamente
#: na consulta principal — se ela não existir, o SQLite recusa a consulta inteira.
#: Por isso, se o export em CSV não trouxer a tabela de texto (comum quando a
#: descrição não é necessária), criamos uma tabela vazia com o schema mínimo em vez
#: de deixar a extração inteira do tipo de objeto falhar.
_TEXT_TABLE_STUBS: dict[str, list[str]] = {
    "RSDIOBJT": ["IOBJNM", "LANGU", "TXTLG"],
    "RSDCUBET": ["INFOCUBE", "LANGU", "TXTLG"],
    "RSDODSOT": ["ODSOBJECT", "LANGU", "TXTLG"],
    "RSDHIET": ["HIENM", "LANGU", "TXTSH"],
    "RSOADSOT": ["ADSONM", "LANGU", "TXTLG"],
    "RSOHCPRT": ["COMPPROV", "LANGU", "TXTLG"],
    "RSOOSVIEWT": ["VIEWNAME", "LANGU", "TXTLG"],
}


class CsvSourceError(Exception):
    """Erro ao localizar/ler o diretório ou os arquivos CSV."""


class CsvConnection:
    """Carrega tabelas de dicionário a partir de CSVs para um SQLite em memória e
    expõe `execute()`/`test_connection()` com a mesma assinatura de `HanaConnection`.
    """

    def __init__(self, directory: Path, delimiter: str | None = None):
        self.directory = Path(directory)
        self.delimiter = delimiter
        self.user = f"csv:{self.directory.name}"
        self._conn: sqlite3.Connection | None = None
        self.loaded_tables: dict[str, int] = {}

    def connect(self) -> "CsvConnection":
        if not self.directory.is_dir():
            raise CsvSourceError(f"Diretório de CSVs não encontrado: {self.directory}")

        self._conn = sqlite3.connect(":memory:")
        self._conn.execute("ATTACH DATABASE ':memory:' AS SYS")

        for table_name in KNOWN_TABLES:
            csv_path = self._find_csv(table_name)
            if csv_path is None:
                continue
            try:
                self._load_csv(table_name, csv_path)
            except Exception:  # noqa: BLE001
                logger.exception("Falha ao carregar %s de %s — tabela ficará indisponível", table_name, csv_path)

        for table_name, columns in _TEXT_TABLE_STUBS.items():
            if table_name not in self.loaded_tables:
                self._create_empty_stub(table_name, columns)

        if not self.loaded_tables:
            logger.warning(
                "Nenhuma tabela reconhecida (%s) encontrada em %s",
                ", ".join(KNOWN_TABLES),
                self.directory,
            )
        return self

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "CsvConnection":
        return self.connect()

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _find_csv(self, table_name: str) -> Path | None:
        for candidate in sorted(self.directory.iterdir()):
            if candidate.is_file() and candidate.stem.upper() == table_name.upper():
                return candidate
        return None

    def _detect_delimiter(self, sample: str) -> str:
        if self.delimiter:
            return self.delimiter
        try:
            return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            return ","

    def _load_csv(self, table_name: str, csv_path: Path) -> None:
        assert self._conn is not None
        with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
            sample = fh.read(4096)
            fh.seek(0)
            delimiter = self._detect_delimiter(sample)
            reader = csv.DictReader(fh, delimiter=delimiter)
            columns = [c.strip() for c in (reader.fieldnames or [])]
            if not columns:
                logger.warning("%s está vazio — tabela %s não carregada", csv_path, table_name)
                return

            schema, bare_name = table_name.split(".", 1) if "." in table_name else ("main", table_name)

            columns_ddl = ", ".join(f'"{c}" TEXT' for c in columns)
            self._conn.execute(f'CREATE TABLE {schema}."{bare_name}" ({columns_ddl})')

            placeholders = ", ".join("?" for _ in columns)
            insert_sql = f'INSERT INTO {schema}."{bare_name}" VALUES ({placeholders})'
            rows = [tuple(row.get(c) for c in columns) for row in reader]
            if rows:
                self._conn.executemany(insert_sql, rows)
            self._conn.commit()

            self.loaded_tables[table_name] = len(rows)
            logger.info("Carregado %s de %s (%d linhas)", table_name, csv_path.name, len(rows))

    def _create_empty_stub(self, table_name: str, columns: list[str]) -> None:
        assert self._conn is not None
        columns_ddl = ", ".join(f'"{c}" TEXT' for c in columns)
        self._conn.execute(f'CREATE TABLE main."{table_name}" ({columns_ddl})')
        self._conn.commit()
        logger.info(
            "%s não encontrada — criada vazia para não quebrar o JOIN (descrições ficarão em branco)",
            table_name,
        )

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        if self._conn is None:
            raise CsvSourceError("Conexão não estabelecida — chame connect() antes de execute().")
        try:
            cursor = self._conn.execute(sql, params or ())
        except sqlite3.Error as exc:
            raise CsvSourceError(f"Falha ao executar consulta sobre os CSVs: {exc}\nSQL: {sql}") from exc
        columns = [c[0] for c in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    def test_connection(self) -> dict[str, Any]:
        """Equivalente CSV do `HanaConnection.test_connection()`: reporta quais tabelas
        reconhecidas foram encontradas no diretório em vez de testar conectividade de rede.
        """
        info: dict[str, Any] = {"host": f"csv:{self.directory}", "port": None, "user": self.user}
        try:
            if self._conn is None:
                self.connect()
            info["hana_version"] = "n/a (fonte: arquivos CSV)"
            info["permissions"] = {t: t in self.loaded_tables for t in KNOWN_TABLES}
            info["loaded_tables"] = dict(self.loaded_tables)
            info["ok"] = any(t in self.loaded_tables for t in _CORE_TABLES)
        except CsvSourceError as exc:
            info["ok"] = False
            info["error"] = str(exc)
        return info
