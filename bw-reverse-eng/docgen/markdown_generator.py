"""Geração de documentação em Markdown (RF05): uma página por objeto + índice geral
+ relatórios (RF06), com diagramas Mermaid embutidos.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
from jinja2 import Environment, FileSystemLoader, select_autoescape

from docgen.mermaid_generator import generate_macro_diagram, generate_object_diagram
from processor.models import UnifiedObject
from processor.reports import complexity_report, missing_docs_report, summary_report
from processor.graph_builder import find_orphans

logger = logging.getLogger("bw_reveng.docgen.markdown")

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_SLUG_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(disabled_extensions=("j2",), default=False),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def object_slug(object_id: str) -> str:
    """Nome de arquivo estável e legível para a página de um objeto."""
    return _SLUG_UNSAFE.sub("_", object_id) + ".md"


def _link_list(ids: list[str], objects_by_id: dict[str, UnifiedObject]) -> list[tuple[str, str | None]]:
    result = []
    for object_id in ids:
        obj = objects_by_id.get(object_id)
        if obj is None:
            result.append((object_id, None))
        else:
            result.append((obj.nome_tecnico, object_slug(object_id)))
    return result


def render_object_page(obj: UnifiedObject, graph: nx.DiGraph, objects_by_id: dict[str, UnifiedObject]) -> str:
    """Renderiza a página Markdown de um objeto.

    Fontes/destinos exibidos vêm dos predecessores/sucessores diretos no grafo
    (não do campo `obj.fontes`/`obj.destinos` isolado), pois para InfoProviders a
    relação real passa por um nó intermediário (Transformação/DTP) — usar o grafo
    garante que a página reflita a linhagem efetiva em vez de só a aresta declarada.
    """
    template = _env().get_template("object.md.j2")
    if obj.id in graph:
        fontes_ids = sorted(graph.predecessors(obj.id))
        destinos_ids = sorted(graph.successors(obj.id))
        mermaid = generate_object_diagram(graph, obj.id)
    else:
        fontes_ids, destinos_ids = obj.fontes, obj.destinos
        mermaid = "flowchart LR\n"

    obj_dump = obj.model_dump(mode="json")
    atributos = dict(obj_dump["atributos_especificos"])
    campos = atributos.pop("campos", None)
    atributos.pop("hana_view", None)  # já refletido em 'campos'; dict aninhado renderiza mal na tabela
    obj_dump["atributos_especificos"] = atributos

    return template.render(
        obj=obj_dump,
        campos=campos,
        fontes=_link_list(fontes_ids, objects_by_id),
        destinos=_link_list(destinos_ids, objects_by_id),
        mermaid=mermaid,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def render_index_page(objects: list[UnifiedObject], graph: nx.DiGraph) -> str:
    template = _env().get_template("index.md.j2")
    summary = summary_report(objects)

    grouped: dict[str, dict[str, list[tuple[str, str]]]] = {}
    for obj in sorted(objects, key=lambda o: (o.camada, o.tipo.value, o.nome_tecnico)):
        camada_group = grouped.setdefault(obj.camada, {})
        tipo_group = camada_group.setdefault(obj.tipo.value, [])
        tipo_group.append((obj.nome_tecnico, f"objects/{object_slug(obj.id)}"))

    macro_mermaid = generate_macro_diagram(graph)
    return template.render(
        generated_at=datetime.now(timezone.utc).isoformat(),
        summary=summary.to_dict(),
        grouped=grouped,
        macro_mermaid=macro_mermaid,
    )


def render_reports_page(
    objects: list[UnifiedObject],
    graph: nx.DiGraph,
    composite_provider_source_threshold: int,
    transformation_rule_threshold: int,
) -> str:
    template = _env().get_template("reports.md.j2")
    summary = summary_report(objects)
    missing = missing_docs_report(objects)
    complexity = complexity_report(
        objects, composite_provider_source_threshold, transformation_rule_threshold
    )
    orphans = find_orphans(graph)
    return template.render(
        generated_at=datetime.now(timezone.utc).isoformat(),
        summary=summary.to_dict(),
        missing_docs=[o.model_dump(mode="json") for o in missing],
        complexity=[f.to_dict() for f in complexity],
        orphans=orphans.to_dict(),
    )


def generate_documentation(
    objects: list[UnifiedObject],
    graph: nx.DiGraph,
    output_dir: Path,
    composite_provider_source_threshold: int = 5,
    transformation_rule_threshold: int = 10,
) -> None:
    """Gera toda a documentação (RF05/RF06) em `output_dir`:

    - `index.md` — índice geral + visão macro de lineage
    - `objects/<id>.md` — uma página por objeto, com diagrama de contexto imediato
    - `reports.md` — sumário, objetos sem documentação e relatório de complexidade
    """
    objects_by_id = {obj.id: obj for obj in objects}
    objects_dir = output_dir / "objects"
    objects_dir.mkdir(parents=True, exist_ok=True)

    for obj in objects:
        page = render_object_page(obj, graph, objects_by_id)
        (objects_dir / object_slug(obj.id)).write_text(page, encoding="utf-8")
    logger.info("Geradas %d páginas de objeto em %s", len(objects), objects_dir)

    (output_dir / "index.md").write_text(render_index_page(objects, graph), encoding="utf-8")
    (output_dir / "reports.md").write_text(
        render_reports_page(
            objects, graph, composite_provider_source_threshold, transformation_rule_threshold
        ),
        encoding="utf-8",
    )
    logger.info("Documentação gerada em %s", output_dir)
