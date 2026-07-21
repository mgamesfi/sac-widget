"""Inventário e relatórios (RF06)."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from processor.models import ObjectType, UnifiedObject


@dataclass
class SummaryReport:
    total: int
    por_tipo: dict[str, int]
    por_pacote: dict[str, int]
    por_camada: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "por_tipo": self.por_tipo,
            "por_pacote": self.por_pacote,
            "por_camada": self.por_camada,
        }


@dataclass
class ComplexityFinding:
    id: str
    nome_tecnico: str
    tipo: str
    metric: str
    value: int
    threshold: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "nome_tecnico": self.nome_tecnico,
            "tipo": self.tipo,
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
        }


def summary_report(objects: list[UnifiedObject]) -> SummaryReport:
    por_tipo = Counter(obj.tipo.value for obj in objects)
    por_pacote = Counter(obj.pacote or "(sem pacote)" for obj in objects)
    por_camada = Counter(obj.camada for obj in objects)
    return SummaryReport(
        total=len(objects),
        por_tipo=dict(sorted(por_tipo.items())),
        por_pacote=dict(sorted(por_pacote.items())),
        por_camada=dict(sorted(por_camada.items())),
    )


def missing_docs_report(objects: list[UnifiedObject]) -> list[UnifiedObject]:
    """Objetos sem descrição preenchida no BW (RF06)."""
    return [obj for obj in objects if not obj.descricao.strip()]


def complexity_report(
    objects: list[UnifiedObject],
    composite_provider_source_threshold: int = 5,
    transformation_rule_threshold: int = 10,
) -> list[ComplexityFinding]:
    """CompositeProviders com muitas fontes e Transformações com muitas regras (RF06)."""
    findings: list[ComplexityFinding] = []
    for obj in objects:
        if obj.tipo == ObjectType.COMPOSITE_PROVIDER:
            num_sources = len(obj.fontes)
            if num_sources > composite_provider_source_threshold:
                findings.append(
                    ComplexityFinding(
                        obj.id, obj.nome_tecnico, obj.tipo.value, "num_fontes",
                        num_sources, composite_provider_source_threshold,
                    )
                )
        elif obj.tipo == ObjectType.TRANSFORMACAO:
            num_regras = int(obj.atributos_especificos.get("num_regras", 0) or 0)
            if num_regras > transformation_rule_threshold:
                findings.append(
                    ComplexityFinding(
                        obj.id, obj.nome_tecnico, obj.tipo.value, "num_regras",
                        num_regras, transformation_rule_threshold,
                    )
                )
    return sorted(findings, key=lambda f: f.value, reverse=True)
