"""Orquestra normalização + construção do grafo, e persiste a saída processada."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

from extractor.export import load_snapshot
from processor.graph_builder import build_graph, find_orphans, to_json_dict
from processor.models import UnifiedObject
from processor.normalizer import normalize

logger = logging.getLogger("bw_reveng.processor.pipeline")


@dataclass
class ProcessResult:
    objects: list[UnifiedObject]
    graph: nx.DiGraph
    warnings: list[str]
    orphan_counts: dict[str, int]


def run_process(input_dir: Path, output_dir: Path) -> ProcessResult:
    """Lê um snapshot extraído (`input_dir`), normaliza e monta o grafo de lineage,
    então grava `objects.json`, `graph.json`, `orphans.json` e `processing.log.json`
    em `output_dir` (RF03/RF04, NFR Auditabilidade)."""
    started_at = datetime.now(timezone.utc)
    raw_objects_by_type = load_snapshot(input_dir)

    normalization = normalize(raw_objects_by_type)
    for warning in normalization.warnings:
        logger.warning(warning)

    graph = build_graph(normalization.objects)
    orphans = find_orphans(graph)

    output_dir.mkdir(parents=True, exist_ok=True)

    with (output_dir / "objects.json").open("w", encoding="utf-8") as fh:
        json.dump([o.model_dump() for o in normalization.objects], fh, ensure_ascii=False, indent=2)

    with (output_dir / "graph.json").open("w", encoding="utf-8") as fh:
        json.dump(to_json_dict(graph), fh, ensure_ascii=False, indent=2)

    with (output_dir / "orphans.json").open("w", encoding="utf-8") as fh:
        json.dump(orphans.to_dict(), fh, ensure_ascii=False, indent=2)

    finished_at = datetime.now(timezone.utc)
    processing_log = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "input_dir": str(input_dir),
        "total_objects": len(normalization.objects),
        "total_edges": graph.number_of_edges(),
        "warnings": normalization.warnings,
        "orphan_counts": {
            "sem_fonte": len(orphans.sem_fonte),
            "sem_consumidor": len(orphans.sem_consumidor),
            "isolados": len(orphans.isolados),
        },
    }
    with (output_dir / "processing.log.json").open("w", encoding="utf-8") as fh:
        json.dump(processing_log, fh, ensure_ascii=False, indent=2)

    logger.info(
        "Processamento concluído: %d objetos, %d arestas, %d warnings",
        len(normalization.objects),
        graph.number_of_edges(),
        len(normalization.warnings),
    )

    return ProcessResult(
        objects=normalization.objects,
        graph=graph,
        warnings=normalization.warnings,
        orphan_counts=processing_log["orphan_counts"],
    )


def load_processed(processed_dir: Path) -> tuple[list[UnifiedObject], nx.DiGraph]:
    """Recarrega a saída de `run_process()` (usado por generate-docs e summary)."""
    from processor.graph_builder import from_json_dict

    with (processed_dir / "objects.json").open("r", encoding="utf-8") as fh:
        objects = [UnifiedObject.model_validate(o) for o in json.load(fh)]

    with (processed_dir / "graph.json").open("r", encoding="utf-8") as fh:
        graph = from_json_dict(json.load(fh))

    return objects, graph
