"""Extração da camada next-gen / HANA nativa (RF02, seção 3.2).

Cobre ADSOs, CompositeProviders (incluindo suas fontes) e Open ODS Views via
tabelas de dicionário BW, e complementa a definição técnica de
CompositeProviders com metadados do catálogo HANA (`SYS.VIEWS`,
`_SYS_BI.BIMC_*`, `SYS.TABLE_COLUMNS`) quando a Calculation View gerada estiver
disponível no schema (seção 3.2, "Definição técnica final").
"""
from __future__ import annotations

import logging
from typing import Any

from extractor.connection import SqlConnection
from extractor.filters import ExtractionFilters

logger = logging.getLogger("bw_reveng.extractor.nextgen")

_ACTIVE_VERSION = "A"


def _run(conn: SqlConnection, label: str, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(sql, params)
        logger.info("Extraídos %d registros de %s", len(rows), label)
        return rows
    except Exception:  # noqa: BLE001
        logger.exception("Falha extraindo %s", label)
        raise


def _run_optional(conn: SqlConnection, label: str, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    """Como `_run`, mas para consultas de enriquecimento (fontes/elementos de
    CompositeProvider, catálogo HANA). Tabela ausente ou sem permissão não deve
    descartar o objeto principal — apenas segue sem o enriquecimento."""
    try:
        return conn.execute(sql, params)
    except Exception:  # noqa: BLE001
        logger.warning("Enriquecimento opcional indisponível (%s) — seguindo sem esses dados", label, exc_info=True)
        return []


def extract_adsos(
    conn: SqlConnection, filters: ExtractionFilters, language: str = "EN"
) -> list[dict[str, Any]]:
    pkg_clause, pkg_params = filters.package_clause("a.DEVCLASS")
    since_clause, since_params = filters.changed_since_clause("a.TIMESTMP")
    sql = f"""
        SELECT a.ADSONM, a.DEVCLASS, a.TIMESTMP, a.LASTUSER, t.TXTLG
        FROM RSOADSO a
        LEFT JOIN RSOADSOT t
          ON t.ADSONM = a.ADSONM AND t.LANGU = ?
        WHERE a.OBJVERS = ?{pkg_clause}{since_clause}
    """
    return _run(conn, "ADSOs", sql, (language, _ACTIVE_VERSION) + pkg_params + since_params)


def extract_composite_providers(
    conn: SqlConnection, filters: ExtractionFilters, language: str = "EN"
) -> list[dict[str, Any]]:
    pkg_clause, pkg_params = filters.package_clause("c.DEVCLASS")
    since_clause, since_params = filters.changed_since_clause("c.TIMESTMP")
    sql = f"""
        SELECT c.COMPPROV, c.DEVCLASS, c.TIMESTMP, c.LASTUSER, t.TXTLG
        FROM RSOHCPR c
        LEFT JOIN RSOHCPRT t
          ON t.COMPPROV = c.COMPPROV AND t.LANGU = ?
        WHERE c.OBJVERS = ?{pkg_clause}{since_clause}
    """
    providers = _run(conn, "CompositeProviders", sql, (language, _ACTIVE_VERSION) + pkg_params + since_params)

    sources_sql = "SELECT COMPPROV, SOURCE, SOURCETYPE FROM RSOHCPRSRC WHERE OBJVERS = ?"
    sources = _run_optional(conn, "RSOHCPRSRC (fontes)", sources_sql, (_ACTIVE_VERSION,))
    sources_by_cp: dict[str, list[dict[str, str]]] = {}
    for row in sources:
        sources_by_cp.setdefault(row["COMPPROV"], []).append(
            {"source": row["SOURCE"], "source_type": row["SOURCETYPE"]}
        )

    elements_sql = "SELECT COMPPROV, COUNT(*) AS NUM_ELEMENTS FROM RSOHCPRELEMENT WHERE OBJVERS = ? GROUP BY COMPPROV"
    elements = _run_optional(conn, "RSOHCPRELEMENT (elementos/joins-unions)", elements_sql, (_ACTIVE_VERSION,))
    element_counts = {row["COMPPROV"]: row["NUM_ELEMENTS"] for row in elements}

    for cp in providers:
        cp["SOURCES"] = sources_by_cp.get(cp["COMPPROV"], [])
        cp["NUM_ELEMENTS"] = element_counts.get(cp["COMPPROV"], 0)
    return providers


def extract_open_ods_views(
    conn: SqlConnection, filters: ExtractionFilters, language: str = "EN"
) -> list[dict[str, Any]]:
    pkg_clause, pkg_params = filters.package_clause("v.DEVCLASS")
    since_clause, since_params = filters.changed_since_clause("v.TIMESTMP")
    sql = f"""
        SELECT v.VIEWNAME, v.SOURCE, v.SOURCETYPE, v.DEVCLASS, v.TIMESTMP, t.TXTLG
        FROM RSOOSVIEW v
        LEFT JOIN RSOOSVIEWT t
          ON t.VIEWNAME = v.VIEWNAME AND t.LANGU = ?
        WHERE v.OBJVERS = ?{pkg_clause}{since_clause}
    """
    return _run(conn, "Open ODS Views", sql, (language, _ACTIVE_VERSION) + pkg_params + since_params)


def enrich_with_hana_catalog(
    conn: SqlConnection, composite_providers: list[dict[str, Any]], hana_schema: str
) -> None:
    """Complementa cada CompositeProvider com a definição técnica final da
    Calculation View equivalente no catálogo HANA (seção 3.2), quando existir.

    Modifica `composite_providers` in place, adicionando a chave `HANA_VIEW`.
    """
    view_names = [cp["COMPPROV"] for cp in composite_providers]
    if not view_names:
        return

    placeholders = ", ".join("?" for _ in view_names)
    views_sql = f"""
        SELECT VIEW_NAME, VIEW_TYPE
        FROM SYS.VIEWS
        WHERE SCHEMA_NAME = ? AND VIEW_NAME IN ({placeholders})
    """
    view_rows = _run_optional(conn, "SYS.VIEWS (catálogo HANA)", views_sql, (hana_schema, *view_names))
    view_by_name = {row["VIEW_NAME"]: row for row in view_rows}

    columns_sql = f"""
        SELECT TABLE_NAME, COUNT(*) AS NUM_COLUNAS
        FROM SYS.TABLE_COLUMNS
        WHERE SCHEMA_NAME = ? AND TABLE_NAME IN ({placeholders})
        GROUP BY TABLE_NAME
    """
    column_rows = _run_optional(conn, "SYS.TABLE_COLUMNS (catálogo HANA)", columns_sql, (hana_schema, *view_names))
    columns_by_name = {row["TABLE_NAME"]: row["NUM_COLUNAS"] for row in column_rows}

    for cp in composite_providers:
        name = cp["COMPPROV"]
        if name in view_by_name:
            cp["HANA_VIEW"] = {
                "view_type": view_by_name[name].get("VIEW_TYPE"),
                "num_columns": columns_by_name.get(name),
            }


EXTRACTORS = {
    "ADSO": extract_adsos,
    "CompositeProvider": extract_composite_providers,
    "OpenODSView": extract_open_ods_views,
}


def extract_all(
    conn: SqlConnection,
    filters: ExtractionFilters,
    language: str = "EN",
    hana_schema: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Roda todos os extratores next-gen habilitados pelos filtros."""
    results: dict[str, list[dict[str, Any]]] = {}
    for object_type, fn in EXTRACTORS.items():
        if not filters.wants(object_type):
            continue
        try:
            results[object_type] = fn(conn, filters, language)
        except Exception:  # noqa: BLE001
            logger.exception("Extração de %s falhou — objeto será reportado como erro", object_type)
            results[object_type] = []

    if hana_schema and "CompositeProvider" in results:
        try:
            enrich_with_hana_catalog(conn, results["CompositeProvider"], hana_schema)
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao enriquecer CompositeProviders com catálogo HANA")

    return results
