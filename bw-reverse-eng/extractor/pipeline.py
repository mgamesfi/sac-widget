"""Orquestra a extração completa (clássica + next-gen) e a exportação em JSON."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from extractor import classic_layer, nextgen_layer
from extractor.connection import HanaConnection
from extractor.export import ExecutionLog, export_objects, make_snapshot_dir
from extractor.filters import ExtractionFilters
from extractor.rfc_connection import RfcCaller

logger = logging.getLogger("bw_reveng.extractor.pipeline")


def run_extraction(
    conn: HanaConnection,
    filters: ExtractionFilters,
    output_base_dir: Path,
    language: str = "EN",
    hana_schema: str | None = None,
    rfc: RfcCaller | None = None,
    rfc_function_module: str | None = None,
    rfc_fetch_routine_source: bool = False,
) -> Path:
    """Extrai todos os tipos habilitados por `filters` (RF02) e grava o snapshot
    versionado em `output_base_dir` (NFR Idempotência/Auditabilidade).

    Se `rfc` for informado (conexão RFC complementar — seção 3.3), tenta enriquecer
    as Transformações com a lógica de negócio real das regras (ver
    `extractor.transformation_rules`); falha nessa etapa não afeta a extração
    principal, só deixa as Transformações sem o detalhe de regras.

    Retorna o diretório de snapshot efetivamente usado.
    """
    started_at = datetime.now(timezone.utc)
    execution_log = ExecutionLog(started_at=started_at, technical_user=conn.user)

    objects_by_type: dict[str, list] = {}
    try:
        objects_by_type.update(classic_layer.extract_all(conn, filters, language))
    except Exception as exc:  # noqa: BLE001
        execution_log.errors.append(f"Camada clássica: {exc}")
        logger.exception("Falha geral na extração da camada clássica")

    try:
        objects_by_type.update(nextgen_layer.extract_all(conn, filters, language, hana_schema))
    except Exception as exc:  # noqa: BLE001
        execution_log.errors.append(f"Camada next-gen: {exc}")
        logger.exception("Falha geral na extração da camada next-gen")

    if rfc is not None and "Transformacao" in objects_by_type:
        from extractor.transformation_rules import enrich_transformations_with_rules

        try:
            enrich_transformations_with_rules(
                rfc,
                objects_by_type["Transformacao"],
                rfc_function_module or "Z_BWREVENG_GET_TRFN_RULES",
                fetch_routine_source=rfc_fetch_routine_source,
            )
        except Exception as exc:  # noqa: BLE001
            execution_log.errors.append(f"Regras de transformação via RFC: {exc}")
            logger.exception("Falha geral ao enriquecer transformações via RFC")

    snapshot_dir = make_snapshot_dir(output_base_dir, started_at)
    export_objects(objects_by_type, snapshot_dir, execution_log)
    return snapshot_dir
