"""Gera um scaffold JSON de arquitetura-alvo (Bronze/Prata/Ouro) para SAP Datasphere
a partir do lineage observado no BW.

Leia isto antes de usar o resultado: o JSON gerado **não é um CSN oficial pronto para
importar** — é um rascunho estruturado (entidades classificadas por camada + fluxos de
transformação) para acelerar o redesenho manual no Data Builder. Ele não reproduz o
resultado do BW sozinho porque faltam duas informações que este app não extrai hoje:

1. Schema de campos de cada objeto (nome/tipo/chave) — por isso todo `csn_stub.elements`
   sai vazio.
2. Lógica de negócio das regras de transformação (mapeamentos, rotinas, fórmulas) — por
   isso cada fluxo lista apenas contagem de regras e origem/destino, não a lógica em si.

Ver `processor.medallion` para a heurística de classificação e as mesmas ressalvas.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import networkx as nx

from processor.medallion import MedallionClassification, MedallionLayer, classify_all
from processor.models import ObjectType, UnifiedObject

_SUGGESTED_SPACES = {
    MedallionLayer.BRONZE: "BW_BRONZE",
    MedallionLayer.SILVER: "BW_SILVER",
    MedallionLayer.GOLD: "BW_GOLD",
}

_NAME_PREFIXES = {
    MedallionLayer.BRONZE: "BRZ_",
    MedallionLayer.SILVER: "SLV_",
    MedallionLayer.GOLD: "GLD_",
    MedallionLayer.PIPELINE: "FLW_",
}

_UNSAFE_IDENTIFIER = re.compile(r"[^A-Za-z0-9_]")

_PIPELINE_TYPE_LABELS = {
    ObjectType.TRANSFORMACAO: "Transformação",
    ObjectType.DTP: "DTP",
    ObjectType.PROCESS_CHAIN: "Process Chain",
}


def _suggested_name(layer: MedallionLayer, nome_tecnico: str) -> str:
    slug = _UNSAFE_IDENTIFIER.sub("_", nome_tecnico.upper()).strip("_")
    return f"{_NAME_PREFIXES[layer]}{slug}"[:60]


def _entity_entry(
    obj: UnifiedObject, layer: MedallionLayer, name_by_id: dict[str, str]
) -> dict[str, Any]:
    return {
        "id": obj.id,
        "camada_medalhao": layer.value,
        "espaco_sugerido": _SUGGESTED_SPACES[layer],
        "tipo_origem_bw": obj.tipo.value,
        "nome_tecnico_bw": obj.nome_tecnico,
        "nome_sugerido_datasphere": name_by_id[obj.id],
        "descricao": obj.descricao,
        "pacote_bw": obj.pacote,
        "fontes_bw": [name_by_id.get(f, f) for f in obj.fontes],
        "destinos_bw": [name_by_id.get(d, d) for d in obj.destinos],
        "csn_stub": {
            "kind": "entity",
            "elements": {},
        },
        "pendencias": [
            "Adicionar os campos reais (nome, tipo de dado, chave) antes de importar no Data Builder — "
            "'elements' está vazio porque o schema de campos não foi extraído do BW."
        ],
    }


def _flow_entry(obj: UnifiedObject, name_by_id: dict[str, str]) -> dict[str, Any]:
    num_regras = obj.atributos_especificos.get("num_regras")
    entry: dict[str, Any] = {
        "id": obj.id,
        "tipo_origem_bw": _PIPELINE_TYPE_LABELS.get(obj.tipo, obj.tipo.value),
        "nome_tecnico_bw": obj.nome_tecnico,
        "de": [name_by_id.get(f, f) for f in obj.fontes],
        "para": [name_by_id.get(d, d) for d in obj.destinos],
        "pendencias": [
            "Lógica de negócio das regras de transformação não foi extraída (requer camada RFC/BAPI, "
            "não implementada nesta versão) — recrie manualmente como View/Data Flow no Datasphere."
        ],
    }
    if num_regras is not None:
        entry["num_regras_bw"] = num_regras
    return entry


def _global_warnings(classification: MedallionClassification, objects: list[UnifiedObject]) -> list[str]:
    warnings = [
        "Classificação Bronze/Prata/Ouro é heurística (tipo de objeto + posição no grafo de lineage "
        "observado) — valide com o time de negócio antes de tratar como arquitetura final.",
        "Nenhum schema de campos foi extraído do BW — todo 'csn_stub.elements' está vazio; complete "
        "cada entidade manualmente (ou via SYS.TABLE_COLUMNS/characteristics do BW) antes de importar.",
        "A lógica de negócio das regras de transformação não foi extraída — reveja cada item em "
        "'fluxos' e recrie a lógica manualmente no Datasphere.",
        "Este arquivo é um rascunho de arquitetura-alvo, não um CSN oficial pronto para carregar — "
        "não é garantido que produza o mesmo resultado do BW sem revisão manual.",
    ]
    counts = classification.counts()
    if counts["bronze"] == 0:
        warnings.append(
            "Nenhum objeto foi classificado como Bronze — sem PSA/DataSource extraído, a camada mais "
            "bruta observável são DSOs/ADSOs sem fonte no grafo; se não há nenhum, revise se o "
            "snapshot extraído cobre a cadeia completa de lineage."
        )
    return warnings


def build_scaffold(objects: list[UnifiedObject], graph: nx.DiGraph) -> dict[str, Any]:
    """Monta o dicionário do scaffold (antes de serializar) — usado pelos testes e por
    `export_scaffold()`."""
    classification = classify_all(objects, graph)
    name_by_id = {
        obj.id: _suggested_name(classification.layer_by_id[obj.id], obj.nome_tecnico) for obj in objects
    }

    entidades = [
        _entity_entry(obj, classification.layer_by_id[obj.id], name_by_id)
        for obj in objects
        if classification.layer_by_id[obj.id] != MedallionLayer.PIPELINE
    ]
    fluxos = [
        _flow_entry(obj, name_by_id)
        for obj in objects
        if classification.layer_by_id[obj.id] == MedallionLayer.PIPELINE
    ]

    return {
        "schema_version": "1.0",
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "origem": "SAP BW 7.5 on HANA (bw-reveng)",
        "alvo": "SAP Datasphere — arquitetura medalhão (Bronze/Prata/Ouro)",
        "resumo": classification.counts(),
        "espacos_sugeridos": {k.value: v for k, v in _SUGGESTED_SPACES.items()},
        "entidades": sorted(entidades, key=lambda e: (e["camada_medalhao"], e["nome_tecnico_bw"])),
        "fluxos": sorted(fluxos, key=lambda f: f["nome_tecnico_bw"]),
        "avisos": _global_warnings(classification, objects),
    }


def export_scaffold(objects: list[UnifiedObject], graph: nx.DiGraph, output_path: Path) -> Path:
    """Gera o scaffold e grava em `output_path` (JSON)."""
    scaffold = build_scaffold(objects, graph)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(scaffold, fh, ensure_ascii=False, indent=2)
    return output_path
