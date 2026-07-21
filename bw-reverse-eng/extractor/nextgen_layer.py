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


def _hana_columns(
    conn: SqlConnection, hana_schema: str, table_names: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """Lista real de colunas (nome/tipo/comprimento/obrigatório) de tabelas/views HANA,
    via `SYS.TABLE_COLUMNS` — a fonte mais confiável de schema para objetos next-gen,
    já que ADSOs/CompositeProviders/Open ODS Views são fisicamente tabelas/views HANA.

    Enriquecimento opcional: tabela/view ausente do schema informado (ou schema
    incorreto) apenas resulta em `campos` vazio para aquele objeto, sem interromper
    a extração dos demais.
    """
    if not table_names:
        return {}
    placeholders = ", ".join("?" for _ in table_names)
    sql = f"""
        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE_NAME, LENGTH, IS_NULLABLE, POSITION
        FROM SYS.TABLE_COLUMNS
        WHERE SCHEMA_NAME = ? AND TABLE_NAME IN ({placeholders})
        ORDER BY TABLE_NAME, POSITION
    """
    rows = _run_optional(conn, "SYS.TABLE_COLUMNS (colunas)", sql, (hana_schema, *table_names))
    by_table: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_table.setdefault(row["TABLE_NAME"], []).append(
            {
                "nome": row["COLUMN_NAME"],
                "tipo_dado": row.get("DATA_TYPE_NAME"),
                "comprimento": row.get("LENGTH"),
                "obrigatorio": row.get("IS_NULLABLE") == "FALSE",
            }
        )
    return by_table


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


def enrich_adsos_with_hana_catalog(conn: SqlConnection, adsos: list[dict[str, Any]], hana_schema: str) -> None:
    """Tenta obter as colunas reais de cada ADSO via catálogo HANA, usando o nome
    técnico do ADSO como nome da tabela ativa.

    Aviso: este é o enriquecimento menos confiável do grupo — a tabela ativa gerada
    para um ADSO no HANA nem sempre tem exatamente o mesmo nome do ADSO (pode levar
    prefixo/sufixo interno dependendo da versão/Support Package). Se não casar, o
    ADSO simplesmente fica sem `campos` (mesmo padrão tolerante das demais consultas
    de enriquecimento) — valide o nome real da tabela ativa no sandbox do cliente.
    """
    adso_names = [a["ADSONM"] for a in adsos]
    columns_by_table = _hana_columns(conn, hana_schema, adso_names)
    for adso in adsos:
        campos = columns_by_table.get(adso["ADSONM"])
        if campos:
            adso["CAMPOS"] = campos


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
    Calculation View equivalente no catálogo HANA (seção 3.2), quando existir —
    incluindo agora a lista real de colunas (nome/tipo/comprimento), não só a
    contagem, em `HANA_VIEW["campos"]`.

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

    columns_by_name = _hana_columns(conn, hana_schema, view_names)

    for cp in composite_providers:
        name = cp["COMPPROV"]
        campos = columns_by_name.get(name, [])
        if name in view_by_name or campos:
            cp["HANA_VIEW"] = {
                "view_type": view_by_name.get(name, {}).get("VIEW_TYPE"),
                "num_columns": len(campos),
                "campos": campos,
            }


def enrich_open_ods_views_with_hana_catalog(
    conn: SqlConnection, views: list[dict[str, Any]], hana_schema: str
) -> None:
    """Complementa cada Open ODS View com as colunas reais da tabela/view HANA de
    origem (`SOURCE`), já que uma Open ODS View lê diretamente de um objeto HANA
    existente — essa é a fonte mais confiável de schema para este tipo."""
    source_names = [v["SOURCE"] for v in views if v.get("SOURCE")]
    columns_by_table = _hana_columns(conn, hana_schema, source_names)
    for view in views:
        campos = columns_by_table.get(view.get("SOURCE"))
        if campos:
            view["CAMPOS"] = campos


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

    if hana_schema:
        if "CompositeProvider" in results:
            try:
                enrich_with_hana_catalog(conn, results["CompositeProvider"], hana_schema)
            except Exception:  # noqa: BLE001
                logger.exception("Falha ao enriquecer CompositeProviders com catálogo HANA")
        if "OpenODSView" in results:
            try:
                enrich_open_ods_views_with_hana_catalog(conn, results["OpenODSView"], hana_schema)
            except Exception:  # noqa: BLE001
                logger.exception("Falha ao enriquecer Open ODS Views com catálogo HANA")
        if "ADSO" in results:
            try:
                enrich_adsos_with_hana_catalog(conn, results["ADSO"], hana_schema)
            except Exception:  # noqa: BLE001
                logger.exception("Falha ao enriquecer ADSOs com catálogo HANA")

    return results
