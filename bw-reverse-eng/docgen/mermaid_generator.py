"""Geração de diagramas de lineage em Mermaid (RF05) — texto puro, sem dependência
de renderização própria; compatível com a renderização nativa do GitHub/Markdown.
"""
from __future__ import annotations

import hashlib
import re

import networkx as nx

from processor.graph_builder import collapse_through

#: Tipos considerados "InfoProvider" para a visão macro (RF05).
INFO_PROVIDER_TYPES = {
    "InfoCube",
    "ADSO",
    "CompositeProvider",
    "DSO",
    "MultiProvider",
    "OpenODSView",
}

_UNSAFE_ID = re.compile(r"[^A-Za-z0-9_]")


def _safe_node_id(object_id: str) -> str:
    """Mermaid exige ids de nó alfanuméricos; ids do domínio contêm ':' e outros
    caracteres, então geramos um id estável e legível a partir deles."""
    slug = _UNSAFE_ID.sub("_", object_id)
    if slug and slug[0].isdigit():
        slug = f"n_{slug}"
    # sufixo curto para evitar colisão entre ids que colapsem para o mesmo slug
    suffix = hashlib.sha1(object_id.encode("utf-8")).hexdigest()[:6]
    return f"{slug}_{suffix}"


def _escape_label(label: str) -> str:
    return label.replace('"', "'").replace("\n", " ")


def _node_label(data: dict) -> str:
    tipo = data.get("tipo", "?")
    nome = data.get("nome_tecnico", "?")
    return _escape_label(f"{tipo}: {nome}")


def _class_for(data: dict) -> str:
    if data.get("external"):
        return "externo"
    return "classico" if data.get("camada") == "classico" else "nextgen"


_CLASS_DEFS = (
    "    classDef classico fill:#dbe4f0,stroke:#33629e,color:#1a2b3c;\n"
    "    classDef nextgen fill:#dcecdc,stroke:#3a8b3a,color:#1a2b1a;\n"
    "    classDef externo fill:#f0f0f0,stroke:#999,color:#555,stroke-dasharray: 3 3;\n"
)


def _render_flowchart(graph: nx.DiGraph, direction: str = "LR") -> str:
    if graph.number_of_nodes() == 0:
        return f"flowchart {direction}\n    empty[\"(sem objetos)\"]\n"

    lines = [f"flowchart {direction}"]
    id_map = {n: _safe_node_id(n) for n in graph.nodes}

    for node_id, data in graph.nodes(data=True):
        lines.append(f'    {id_map[node_id]}["{_node_label(data)}"]')

    for source, target in graph.edges:
        lines.append(f"    {id_map[source]} --> {id_map[target]}")

    lines.append(_CLASS_DEFS.rstrip())
    for node_id, data in graph.nodes(data=True):
        lines.append(f"    class {id_map[node_id]} {_class_for(data)}")

    return "\n".join(lines) + "\n"


def generate_macro_diagram(graph: nx.DiGraph) -> str:
    """Visão macro: todos os InfoProviders e suas dependências (RF05)."""
    provider_graph = collapse_through(graph, INFO_PROVIDER_TYPES)
    return _render_flowchart(provider_graph, direction="LR")


def generate_object_diagram(graph: nx.DiGraph, object_id: str) -> str:
    """Diagrama de contexto imediato de um objeto: fontes e destinos diretos (RF05)."""
    if object_id not in graph:
        raise KeyError(f"Objeto não encontrado no grafo: {object_id}")

    nodes = {object_id} | set(graph.predecessors(object_id)) | set(graph.successors(object_id))
    subgraph = graph.subgraph(nodes).copy()
    return _render_flowchart(subgraph, direction="LR")
