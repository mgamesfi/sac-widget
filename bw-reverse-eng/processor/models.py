"""Modelo de dados unificado (RF03) — schema comum entre objetos clássicos e next-gen."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ObjectType(str, Enum):
    INFO_OBJECT = "InfoObject"
    INFO_CUBE = "InfoCube"
    ADSO = "ADSO"
    COMPOSITE_PROVIDER = "CompositeProvider"
    DSO = "DSO"
    MULTI_PROVIDER = "MultiProvider"
    OPEN_ODS_VIEW = "OpenODSView"
    TRANSFORMACAO = "Transformacao"
    DTP = "DTP"
    PROCESS_CHAIN = "ProcessChain"
    HIERARQUIA = "Hierarquia"


Camada = Literal["classico", "next-gen"]

_NEXTGEN_TYPES = {
    ObjectType.ADSO,
    ObjectType.COMPOSITE_PROVIDER,
    ObjectType.OPEN_ODS_VIEW,
}


class UnifiedObject(BaseModel):
    """Schema unificado exigido pela RF03.

    `fontes`/`destinos` guardam **ids** de outros `UnifiedObject` (upstream/
    downstream, respectivamente), formando as arestas do grafo de lineage
    montado por `processor.graph_builder`.
    """

    id: str
    tipo: ObjectType
    nome_tecnico: str
    descricao: str = ""
    pacote: str = ""
    camada: Camada
    fontes: list[str] = Field(default_factory=list)
    destinos: list[str] = Field(default_factory=list)
    atributos_especificos: dict[str, Any] = Field(default_factory=dict)

    @staticmethod
    def camada_for(tipo: ObjectType) -> Camada:
        return "next-gen" if tipo in _NEXTGEN_TYPES else "classico"

    @staticmethod
    def make_id(tipo: ObjectType, nome_tecnico: str) -> str:
        return f"{tipo.value}:{nome_tecnico}"
