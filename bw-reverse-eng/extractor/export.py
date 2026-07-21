"""Serialização da extração em JSON (RF02) com versionamento e auditoria (NFR)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("bw_reveng.extractor.export")


@dataclass
class ExecutionLog:
    """Registro auditável de uma execução de extração (NFR Auditabilidade)."""

    started_at: datetime
    technical_user: str
    finished_at: datetime | None = None
    counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "technical_user": self.technical_user,
            "counts": self.counts,
            "total_objects": sum(self.counts.values()),
            "errors": self.errors,
        }


def make_snapshot_dir(base_output_dir: Path, timestamp: datetime | None = None) -> Path:
    """Cria (se necessário) um diretório de snapshot versionado por timestamp de execução.

    Se `base_output_dir` já existir e não estiver vazio, um sufixo de timestamp é
    acrescentado para não sobrescrever/corromper uma extração anterior (NFR
    Idempotência) — a menos que o diretório já pareça ser, ele próprio, um
    snapshot dedicado (nesse caso é usado como está).
    """
    timestamp = timestamp or datetime.now(timezone.utc)
    stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")

    if not base_output_dir.exists() or not any(base_output_dir.iterdir()):
        base_output_dir.mkdir(parents=True, exist_ok=True)
        return base_output_dir

    snapshot_dir = base_output_dir / f"snapshot_{stamp}"
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    logger.warning(
        "%s já existe e não está vazio; gravando em %s para preservar a extração anterior",
        base_output_dir,
        snapshot_dir,
    )
    return snapshot_dir


def export_objects(
    objects_by_type: dict[str, list[dict[str, Any]]],
    output_dir: Path,
    execution_log: ExecutionLog,
) -> Path:
    """Grava um arquivo JSON por tipo de objeto, mais um manifest.json e o log de execução.

    Retorna o diretório de snapshot efetivamente usado.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    for object_type, objects in objects_by_type.items():
        execution_log.counts[object_type] = len(objects)
        file_path = output_dir / f"{object_type}.json"
        with file_path.open("w", encoding="utf-8") as fh:
            json.dump(objects, fh, ensure_ascii=False, indent=2, default=str)
        logger.info("Gravado %s (%d objetos)", file_path, len(objects))

    execution_log.finished_at = datetime.now(timezone.utc)
    manifest = {
        "schema_version": "1.0",
        "object_types": sorted(objects_by_type.keys()),
        "execution": execution_log.to_dict(),
    }
    manifest_path = output_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    log_path = output_dir / "extraction.log.json"
    with log_path.open("w", encoding="utf-8") as fh:
        json.dump(execution_log.to_dict(), fh, ensure_ascii=False, indent=2)

    return output_dir


def load_snapshot(snapshot_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Carrega todos os arquivos `<tipo>.json` de um diretório de snapshot."""
    objects_by_type: dict[str, list[dict[str, Any]]] = {}
    for file_path in sorted(snapshot_dir.glob("*.json")):
        if file_path.name in {"manifest.json", "extraction.log.json"}:
            continue
        object_type = file_path.stem
        with file_path.open("r", encoding="utf-8") as fh:
            objects_by_type[object_type] = json.load(fh)
    return objects_by_type
