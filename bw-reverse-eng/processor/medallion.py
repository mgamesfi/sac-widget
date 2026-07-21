"""Classificação heurística dos objetos observados no BW em camadas de arquitetura
medalhão (Bronze/Prata/Ouro), como ponto de partida para um redesenho em SAP Datasphere.

Importante (ler antes de usar em produção): esta classificação é estrutural — baseada
no *tipo* do objeto e na sua *posição no grafo de lineage* — não em uma análise de
conteúdo/negócio. Ela não reproduz sozinha o resultado do BW: falta o schema de campos
de cada objeto (não extraído) e a lógica de negócio das regras de transformação (não
extraída — ver seção 3.3 da especificação: regras complexas ficam serializadas no BW e
só seriam recuperáveis via RFC/BAPI, camada não implementada nesta versão). Trate a
saída como um mapa de arquitetura-alvo para revisão manual, não como migração automática.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import networkx as nx

from processor.models import ObjectType, UnifiedObject


class MedallionLayer(str, Enum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PIPELINE = "pipeline"  # Transformação/DTP/Process Chain: orquestração, não é uma camada de dados


#: Tipos sempre tratados como orquestração/ETL, não como dado em repouso.
_PIPELINE_TYPES = {ObjectType.TRANSFORMACAO, ObjectType.DTP, ObjectType.PROCESS_CHAIN}

#: Dado de referência/conformado (master data e hierarquias) — Prata por padrão,
#: pois tipicamente alimenta múltiplos consumidores já num formato conformado.
_REFERENCE_TYPES = {ObjectType.INFO_OBJECT, ObjectType.HIERARQUIA}

#: Camada de consumo/reporting — sempre Ouro nesta heurística.
_GOLD_TYPES = {
    ObjectType.INFO_CUBE,
    ObjectType.MULTI_PROVIDER,
    ObjectType.COMPOSITE_PROVIDER,
    ObjectType.OPEN_ODS_VIEW,
}

#: Camada de armazenamento granular (DSO/ADSO) — Bronze ou Prata depende da posição
#: no grafo (ver classify_object).
_STORAGE_TYPES = {ObjectType.DSO, ObjectType.ADSO}


def classify_object(obj: UnifiedObject, graph: nx.DiGraph) -> MedallionLayer:
    """Classifica um objeto numa camada medalhão.

    Heurística:
    - Transformação/DTP/Process Chain -> pipeline (não é dado, é orquestração).
    - InfoObject/Hierarquia -> silver (dado de referência conformado).
    - InfoCube/MultiProvider/CompositeProvider/OpenODSView -> gold (consumo).
    - DSO/ADSO sem nenhuma fonte no grafo observado -> bronze (primeiro ponto de
      pouso visível; sem PSA/DataSource extraído, é o mais próximo de "bruto" que
      conseguimos enxergar).
    - DSO/ADSO com fonte no grafo observado -> silver (já recebeu alguma
      transformação/harmonização a partir de outro objeto).
    """
    if obj.tipo in _PIPELINE_TYPES:
        return MedallionLayer.PIPELINE
    if obj.tipo in _REFERENCE_TYPES:
        return MedallionLayer.SILVER
    if obj.tipo in _GOLD_TYPES:
        return MedallionLayer.GOLD
    if obj.tipo in _STORAGE_TYPES:
        has_source = obj.id in graph and graph.in_degree(obj.id) > 0
        return MedallionLayer.SILVER if has_source else MedallionLayer.BRONZE
    raise ValueError(f"Tipo sem regra de classificação medalhão: {obj.tipo}")


@dataclass
class MedallionClassification:
    layer_by_id: dict[str, MedallionLayer] = field(default_factory=dict)

    def objects_in(self, objects: list[UnifiedObject], layer: MedallionLayer) -> list[UnifiedObject]:
        return [o for o in objects if self.layer_by_id.get(o.id) == layer]

    def counts(self) -> dict[str, int]:
        counts = {layer.value: 0 for layer in MedallionLayer}
        for layer in self.layer_by_id.values():
            counts[layer.value] += 1
        return counts


def classify_all(objects: list[UnifiedObject], graph: nx.DiGraph) -> MedallionClassification:
    return MedallionClassification({obj.id: classify_object(obj, graph) for obj in objects})
