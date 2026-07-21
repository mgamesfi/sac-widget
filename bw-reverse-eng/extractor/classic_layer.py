"""Extração da camada BW clássica (RF02, seção 3.1).

Cada função consulta as tabelas de dicionário documentadas na especificação
(RSD*/RSTRAN*/RSBKDTP*/RSPC*/RSDHIE*), faz o JOIN com a respectiva tabela de
textos (`*T`) para obter a descrição no idioma configurado, e devolve uma
lista de dicionários "crus" (ainda não normalizados — isso é responsabilidade
de `processor.normalizer`).

Nota de implementação: os nomes de tabela/coluna abaixo seguem o dicionário de
dados padrão do SAP BW 7.5. Como o próprio item 9 da especificação aponta,
Support Packages específicos podem alterar detalhes de schema — valide as
queries num sandbox do cliente antes de rodar a extração completa em produção.
"""
from __future__ import annotations

import logging
from typing import Any

from extractor.connection import SqlConnection
from extractor.filters import ExtractionFilters

logger = logging.getLogger("bw_reveng.extractor.classic")

_ACTIVE_VERSION = "A"  # OBJVERS = 'A' (ativo) na maioria das tabelas RSD*/RSTRAN*/RSPC*


def _run(conn: SqlConnection, label: str, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(sql, params)
        logger.info("Extraídos %d registros de %s", len(rows), label)
        return rows
    except Exception:  # noqa: BLE001
        logger.exception("Falha extraindo %s", label)
        raise


def _run_optional(conn: SqlConnection, label: str, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    """Como `_run`, mas para consultas de enriquecimento (ex: contagem de regras,
    partes de MultiProvider). Se a tabela não existir ou faltar permissão — comum
    quando a fonte é um export parcial em CSV —, registra um aviso e segue sem os
    dados extras em vez de descartar todo o tipo de objeto principal."""
    try:
        return conn.execute(sql, params)
    except Exception:  # noqa: BLE001
        logger.warning("Enriquecimento opcional indisponível (%s) — seguindo sem esses dados", label, exc_info=True)
        return []


def _infoobject_datatypes(conn: SqlConnection) -> dict[str, dict[str, Any]]:
    """Tipo de dado/comprimento por InfoObject, via as tabelas de atributos
    específicos por tipo (RSDCHA para características, RSDKYF para key figures).

    Aviso: ao contrário de RSDIOBJ/RSDCUBE/RSTRAN (citadas explicitamente na seção
    3.1 da especificação), RSDCHA/RSDKYF são menos universalmente documentadas —
    valide contra o sandbox do cliente. Como toda consulta de enriquecimento aqui,
    se a tabela não existir a extração principal segue normalmente, só sem o
    schema de campos.
    """
    cha_sql = "SELECT IOBJNM, DATATYPE, LENGTH FROM RSDCHA WHERE OBJVERS = ?"
    kyf_sql = "SELECT IOBJNM, DATATYPE, LENGTH, CURRENCY, UNIT FROM RSDKYF WHERE OBJVERS = ?"
    cha_rows = _run_optional(conn, "RSDCHA (tipo de dado de características)", cha_sql, (_ACTIVE_VERSION,))
    kyf_rows = _run_optional(conn, "RSDKYF (tipo de dado de key figures)", kyf_sql, (_ACTIVE_VERSION,))

    by_iobjnm: dict[str, dict[str, Any]] = {}
    for row in cha_rows:
        by_iobjnm[row["IOBJNM"]] = {"tipo_dado": row.get("DATATYPE"), "comprimento": row.get("LENGTH")}
    for row in kyf_rows:
        by_iobjnm[row["IOBJNM"]] = {
            "tipo_dado": row.get("DATATYPE"),
            "comprimento": row.get("LENGTH"),
            "moeda": row.get("CURRENCY"),
            "unidade": row.get("UNIT"),
        }
    return by_iobjnm


def extract_infoobjects(
    conn: SqlConnection, filters: ExtractionFilters, language: str = "EN"
) -> list[dict[str, Any]]:
    pkg_clause, pkg_params = filters.package_clause("o.DEVCLASS")
    since_clause, since_params = filters.changed_since_clause("o.TIMESTMP")
    sql = f"""
        SELECT o.IOBJNM, o.IOBJTP, o.DEVCLASS, o.TIMESTMP, o.LASTUSER, t.TXTLG
        FROM RSDIOBJ o
        LEFT JOIN RSDIOBJT t
          ON t.IOBJNM = o.IOBJNM AND t.LANGU = ?
        WHERE o.OBJVERS = ?{pkg_clause}{since_clause}
    """
    rows = _run(conn, "InfoObjects", sql, (language, _ACTIVE_VERSION) + pkg_params + since_params)

    datatypes = _infoobject_datatypes(conn)
    for row in rows:
        row.update(datatypes.get(row["IOBJNM"], {}))
    return rows


def _infoprovider_fields(conn: SqlConnection) -> dict[str, list[dict[str, Any]]]:
    """Campos (características + key figures) atribuídos a cada InfoCube/MultiProvider,
    via RSDCUBEIOBJ — usada tanto para InfoCubes quanto MultiProviders, já que ambos
    são linhas de RSDCUBE (CUBETYPE '0'/'1') e a atribuição de campos é keyed por
    INFOCUBE independente do tipo.

    Aviso: mesma ressalva de `_infoobject_datatypes` — valide o nome exato desta
    tabela contra o sandbox do cliente; se divergir, a extração principal do
    InfoCube/MultiProvider segue normalmente, só sem a lista de campos.
    """
    sql = "SELECT INFOCUBE, IOBJNM FROM RSDCUBEIOBJ WHERE OBJVERS = ?"
    rows = _run_optional(conn, "RSDCUBEIOBJ (campos do InfoProvider)", sql, (_ACTIVE_VERSION,))
    by_provider: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_provider.setdefault(row["INFOCUBE"], []).append({"nome": row["IOBJNM"]})
    return by_provider


def _enrich_fields_with_datatype(
    fields: list[dict[str, Any]], datatypes: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    for field_ in fields:
        field_.update(datatypes.get(field_["nome"], {}))
    return fields


def extract_infocubes(
    conn: SqlConnection, filters: ExtractionFilters, language: str = "EN"
) -> list[dict[str, Any]]:
    pkg_clause, pkg_params = filters.package_clause("c.DEVCLASS")
    since_clause, since_params = filters.changed_since_clause("c.TIMESTMP")
    sql = f"""
        SELECT c.INFOCUBE, c.CUBETYPE, c.DEVCLASS, c.TIMESTMP, c.LASTUSER, t.TXTLG
        FROM RSDCUBE c
        LEFT JOIN RSDCUBET t
          ON t.INFOCUBE = c.INFOCUBE AND t.LANGU = ?
        WHERE c.OBJVERS = ? AND c.CUBETYPE = '0'{pkg_clause}{since_clause}
    """
    rows = _run(conn, "InfoCubes", sql, (language, _ACTIVE_VERSION) + pkg_params + since_params)

    fields_by_provider = _infoprovider_fields(conn)
    datatypes = _infoobject_datatypes(conn)
    for row in rows:
        row["CAMPOS"] = _enrich_fields_with_datatype(fields_by_provider.get(row["INFOCUBE"], []), datatypes)
    return rows


def _dso_fields(conn: SqlConnection) -> dict[str, list[dict[str, Any]]]:
    """Campos de cada DSO standard, via RSDODSOIOBJ (marca FIELDTYPE = 'KEY' para os
    campos de chave). Mesma ressalva de nome de tabela das demais funções `_*_fields`."""
    sql = "SELECT ODSOBJECT, IOBJNM, FIELDTYPE FROM RSDODSOIOBJ WHERE OBJVERS = ?"
    rows = _run_optional(conn, "RSDODSOIOBJ (campos do DSO)", sql, (_ACTIVE_VERSION,))
    by_dso: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_dso.setdefault(row["ODSOBJECT"], []).append(
            {"nome": row["IOBJNM"], "chave": row.get("FIELDTYPE") == "KEY"}
        )
    return by_dso


def extract_dsos(
    conn: SqlConnection, filters: ExtractionFilters, language: str = "EN"
) -> list[dict[str, Any]]:
    pkg_clause, pkg_params = filters.package_clause("d.DEVCLASS")
    since_clause, since_params = filters.changed_since_clause("d.TIMESTMP")
    sql = f"""
        SELECT d.ODSOBJECT, d.DEVCLASS, d.TIMESTMP, d.LASTUSER, t.TXTLG
        FROM RSDODSO d
        LEFT JOIN RSDODSOT t
          ON t.ODSOBJECT = d.ODSOBJECT AND t.LANGU = ?
        WHERE d.OBJVERS = ?{pkg_clause}{since_clause}
    """
    rows = _run(conn, "DSOs standard", sql, (language, _ACTIVE_VERSION) + pkg_params + since_params)

    fields_by_dso = _dso_fields(conn)
    datatypes = _infoobject_datatypes(conn)
    for row in rows:
        row["CAMPOS"] = _enrich_fields_with_datatype(fields_by_dso.get(row["ODSOBJECT"], []), datatypes)
    return rows


def extract_multiproviders(
    conn: SqlConnection, filters: ExtractionFilters, language: str = "EN"
) -> list[dict[str, Any]]:
    """MultiProviders são InfoCubes com CUBETYPE = '1'; RSDMPRO traz o mapeamento
    das partes (InfoProviders que compõem a união)."""
    pkg_clause, pkg_params = filters.package_clause("c.DEVCLASS")
    since_clause, since_params = filters.changed_since_clause("c.TIMESTMP")
    sql = f"""
        SELECT c.INFOCUBE, c.DEVCLASS, c.TIMESTMP, c.LASTUSER, t.TXTLG
        FROM RSDCUBE c
        LEFT JOIN RSDCUBET t
          ON t.INFOCUBE = c.INFOCUBE AND t.LANGU = ?
        WHERE c.OBJVERS = ? AND c.CUBETYPE = '1'{pkg_clause}{since_clause}
    """
    multiproviders = _run(conn, "MultiProviders", sql, (language, _ACTIVE_VERSION) + pkg_params + since_params)

    parts_sql = "SELECT INFOCUBE, PARTCUBE FROM RSDMPRO WHERE OBJVERS = ?"
    parts = _run_optional(conn, "RSDMPRO (partes de MultiProvider)", parts_sql, (_ACTIVE_VERSION,))
    parts_by_mp: dict[str, list[str]] = {}
    for row in parts:
        parts_by_mp.setdefault(row["INFOCUBE"], []).append(row["PARTCUBE"])

    fields_by_provider = _infoprovider_fields(conn)
    datatypes = _infoobject_datatypes(conn)
    for mp in multiproviders:
        mp["PART_PROVIDERS"] = parts_by_mp.get(mp["INFOCUBE"], [])
        mp["CAMPOS"] = _enrich_fields_with_datatype(fields_by_provider.get(mp["INFOCUBE"], []), datatypes)
    return multiproviders


def extract_transformations(
    conn: SqlConnection, filters: ExtractionFilters
) -> list[dict[str, Any]]:
    pkg_clause, pkg_params = filters.package_clause("DEVCLASS")
    since_clause, since_params = filters.changed_since_clause("TIMESTMP")
    sql = f"""
        SELECT TRANID, SOURCE, SOURCETYPE, TARGET, TARGETTYPE, DEVCLASS, TIMESTMP
        FROM RSTRAN
        WHERE OBJVERS = ?{pkg_clause}{since_clause}
    """
    transformations = _run(conn, "Transformações", sql, (_ACTIVE_VERSION,) + pkg_params + since_params)

    steps_sql = "SELECT TRANID, COUNT(*) AS NUM_REGRAS FROM RSTRANSTEPS WHERE OBJVERS = ? GROUP BY TRANID"
    steps = _run_optional(conn, "RSTRANSTEPS (regras)", steps_sql, (_ACTIVE_VERSION,))
    rule_counts = {row["TRANID"]: row["NUM_REGRAS"] for row in steps}

    for tr in transformations:
        tr["NUM_REGRAS"] = rule_counts.get(tr["TRANID"], 0)
    return transformations


def extract_dtps(conn: SqlConnection, filters: ExtractionFilters) -> list[dict[str, Any]]:
    pkg_clause, pkg_params = filters.package_clause("DEVCLASS")
    since_clause, since_params = filters.changed_since_clause("TIMESTMP")
    sql = f"""
        SELECT DTP, SOURCE, SOURCETYPE, TARGET, TARGETTYPE, DTPTYPE, DEVCLASS, TIMESTMP
        FROM RSBKDTP
        WHERE OBJVERS = ?{pkg_clause}{since_clause}
    """
    return _run(conn, "DTPs", sql, (_ACTIVE_VERSION,) + pkg_params + since_params)


def extract_process_chains(conn: SqlConnection, filters: ExtractionFilters) -> list[dict[str, Any]]:
    pkg_clause, pkg_params = filters.package_clause("DEVCLASS")
    since_clause, since_params = filters.changed_since_clause("TIMESTMP")
    sql = f"""
        SELECT CHAIN_ID, DEVCLASS, TIMESTMP
        FROM RSPCCHAIN
        WHERE OBJVERS = ?{pkg_clause}{since_clause}
    """
    chains = _run(conn, "Process Chains", sql, (_ACTIVE_VERSION,) + pkg_params + since_params)

    nested_sql = "SELECT CHAIN_ID, CALLED_CHAIN_ID FROM RSPCLOGCHAIN"
    nested = _run_optional(conn, "RSPCLOGCHAIN (encadeamento)", nested_sql, ())
    called_by: dict[str, list[str]] = {}
    for row in nested:
        called_by.setdefault(row["CHAIN_ID"], []).append(row["CALLED_CHAIN_ID"])

    for chain in chains:
        chain["CALLED_CHAINS"] = called_by.get(chain["CHAIN_ID"], [])
    return chains


def extract_hierarchies(
    conn: SqlConnection, filters: ExtractionFilters, language: str = "EN"
) -> list[dict[str, Any]]:
    pkg_clause, pkg_params = filters.package_clause("h.DEVCLASS")
    since_clause, since_params = filters.changed_since_clause("h.TIMESTMP")
    sql = f"""
        SELECT h.IOBJNM, h.HIENM, h.DEVCLASS, h.TIMESTMP, t.TXTSH
        FROM RSDHIE h
        LEFT JOIN RSDHIET t
          ON t.HIENM = h.HIENM AND t.LANGU = ?
        WHERE h.OBJVERS = ?{pkg_clause}{since_clause}
    """
    return _run(conn, "Hierarquias", sql, (language, _ACTIVE_VERSION) + pkg_params + since_params)


#: Mapa "tipo lógico" -> função de extração, usado pelo CLI e por extract_all().
EXTRACTORS = {
    "InfoObject": extract_infoobjects,
    "InfoCube": extract_infocubes,
    "DSO": extract_dsos,
    "MultiProvider": extract_multiproviders,
    "Transformacao": extract_transformations,
    "DTP": extract_dtps,
    "ProcessChain": extract_process_chains,
    "Hierarquia": extract_hierarchies,
}


def extract_all(
    conn: SqlConnection, filters: ExtractionFilters, language: str = "EN"
) -> dict[str, list[dict[str, Any]]]:
    """Roda todos os extratores clássicos habilitados pelos filtros, tolerando falhas
    isoladas por tipo (uma falha não aborta a extração completa — RF02/log de erros)."""
    results: dict[str, list[dict[str, Any]]] = {}
    for object_type, fn in EXTRACTORS.items():
        if not filters.wants(object_type):
            continue
        try:
            if fn in (extract_transformations, extract_dtps, extract_process_chains):
                results[object_type] = fn(conn, filters)
            else:
                results[object_type] = fn(conn, filters, language)
        except Exception:  # noqa: BLE001
            logger.exception("Extração de %s falhou — objeto será reportado como erro", object_type)
            results[object_type] = []
    return results
