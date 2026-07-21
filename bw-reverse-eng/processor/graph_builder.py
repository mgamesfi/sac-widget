"""Construção do grafo de lineage (RF04): nós = objetos, arestas = fonte→destino."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import networkx as nx
from networkx.readwrite import json_graph

from processor.models import UnifiedObject

logger = logging.getLogger("bw_reveng.processor.graph_builder")


class DuplicateObjectError(ValueError):
    """Levantado quando dois objetos normalizados compartilham o mesmo id."""


@dataclass
class OrphanReport:
    sem_fonte: list[str] = field(default_factory=list)
    sem_consumidor: list[str] = field(default_factory=list)
    isolados: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "sem_fonte": self.sem_fonte,
            "sem_consumidor": self.sem_consumidor,
            "isolados": self.isolados,
        }


def _node_attrs(obj: UnifiedObject) -> dict[str, Any]:
    return {
        "tipo": obj.tipo.value,
        "nome_tecnico": obj.nome_tecnico,
        "descricao": obj.descricao,
        "pacote": obj.pacote,
        "camada": obj.camada,
        "atributos_especificos": obj.atributos_especificos,
        "external": False,
    }


def build_graph(objects: list[UnifiedObject]) -> nx.DiGraph:
    """Monta o grafo direcionado de lineage.

    Garante ausência de nós duplicados (levanta `DuplicateObjectError` se dois
    objetos tiverem o mesmo id) e não descarta relações fonte→destino mesmo
    quando o objeto referenciado não foi extraído/normalizado — nesse caso é
    criado um nó "externo" (`external=True`) apenas para preservar a aresta.
    """
    graph = nx.DiGraph()

    seen_ids: set[str] = set()
    for obj in objects:
        if obj.id in seen_ids:
            raise DuplicateObjectError(f"Id duplicado ao montar o grafo: {obj.id}")
        seen_ids.add(obj.id)
        graph.add_node(obj.id, **_node_attrs(obj))

    def ensure_node(node_id: str) -> None:
        if node_id not in graph:
            graph.add_node(
                node_id,
                tipo="Desconhecido",
                nome_tecnico=node_id,
                descricao="",
                pacote="",
                camada="desconhecida",
                atributos_especificos={},
                external=True,
            )
            logger.warning("Nó externo criado para preservar aresta: %s", node_id)

    for obj in objects:
        for source_id in obj.fontes:
            ensure_node(source_id)
            graph.add_edge(source_id, obj.id, relation="fonte")
        for target_id in obj.destinos:
            ensure_node(target_id)
            graph.add_edge(obj.id, target_id, relation="destino")

    return graph


def find_orphans(graph: nx.DiGraph) -> OrphanReport:
    """Detecta objetos sem fonte e/ou sem consumidor (RF04), ignorando nós externos."""
    report = OrphanReport()
    for node_id, data in graph.nodes(data=True):
        if data.get("external"):
            continue
        has_source = graph.in_degree(node_id) > 0
        has_consumer = graph.out_degree(node_id) > 0
        if not has_source:
            report.sem_fonte.append(node_id)
        if not has_consumer:
            report.sem_consumidor.append(node_id)
        if not has_source and not has_consumer:
            report.isolados.append(node_id)
    return report


def lineage_upstream(graph: nx.DiGraph, object_id: str, max_depth: int | None = None) -> list[str]:
    """Retorna os ids de todos os objetos "de trás pra frente" (fontes, diretas e indiretas)."""
    if object_id not in graph:
        raise KeyError(f"Objeto não encontrado no grafo: {object_id}")
    if max_depth is None:
        return sorted(nx.ancestors(graph, object_id))
    lengths = nx.single_target_shortest_path_length(graph, object_id, cutoff=max_depth)
    return sorted(n for n in lengths if n != object_id)


def lineage_downstream(graph: nx.DiGraph, object_id: str, max_depth: int | None = None) -> list[str]:
    """Retorna os ids de todos os consumidores "pra frente" (diretos e indiretos)."""
    if object_id not in graph:
        raise KeyError(f"Objeto não encontrado no grafo: {object_id}")
    if max_depth is None:
        return sorted(nx.descendants(graph, object_id))
    lengths = nx.single_source_shortest_path_length(graph, object_id, cutoff=max_depth)
    return sorted(n for n in lengths if n != object_id)


def immediate_context(graph: nx.DiGraph, object_id: str) -> tuple[list[str], list[str]]:
    """Fontes e destinos diretos de um objeto — usado no diagrama de contexto imediato (RF05)."""
    if object_id not in graph:
        raise KeyError(f"Objeto não encontrado no grafo: {object_id}")
    fontes = sorted(graph.predecessors(object_id))
    destinos = sorted(graph.successors(object_id))
    return fontes, destinos


def collapse_through(graph: nx.DiGraph, keep_types: set[str]) -> nx.DiGraph:
    """Reduz o grafo aos nós cujo `tipo` está em `keep_types`, ligando por aresta direta
    pares que só se conectavam através de nós intermediários (ex: Transformação/DTP).

    Usado para a visão macro de lineage (RF05), que deve mostrar apenas os
    InfoProviders e suas dependências, sem o "ruído" dos objetos de carga.
    """
    keep = {n for n, data in graph.nodes(data=True) if data.get("tipo") in keep_types}

    collapsed = nx.DiGraph()
    for n in keep:
        collapsed.add_node(n, **graph.nodes[n])

    for n in keep:
        visited: set[str] = set()
        stack = list(graph.successors(n))
        while stack:
            succ = stack.pop()
            if succ in visited:
                continue
            visited.add(succ)
            if succ in keep:
                collapsed.add_edge(n, succ)
            else:
                stack.extend(graph.successors(succ))
    return collapsed


def to_json_dict(graph: nx.DiGraph) -> dict[str, Any]:
    return json_graph.node_link_data(graph)


def from_json_dict(data: dict[str, Any]) -> nx.DiGraph:
    return json_graph.node_link_graph(data, directed=True)
