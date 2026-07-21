import pytest

from processor.graph_builder import (
    DuplicateObjectError,
    build_graph,
    collapse_through,
    find_orphans,
    from_json_dict,
    immediate_context,
    lineage_downstream,
    lineage_upstream,
    to_json_dict,
)
from processor.models import ObjectType, UnifiedObject


def _obj(tipo, nome, fontes=None, destinos=None, camada=None):
    return UnifiedObject(
        id=UnifiedObject.make_id(tipo, nome),
        tipo=tipo,
        nome_tecnico=nome,
        camada=camada or UnifiedObject.camada_for(tipo),
        fontes=fontes or [],
        destinos=destinos or [],
    )


def _sample_objects():
    dso = _obj(ObjectType.DSO, "ZDSO1")
    transf = _obj(ObjectType.TRANSFORMACAO, "T1", fontes=["DSO:ZDSO1"], destinos=["InfoCube:ZSALES"])
    cube = _obj(ObjectType.INFO_CUBE, "ZSALES")
    orphan_cube = _obj(ObjectType.INFO_CUBE, "ZORPHAN")
    return [dso, transf, cube, orphan_cube]


def test_build_graph_creates_nodes_and_edges():
    graph = build_graph(_sample_objects())
    assert graph.number_of_nodes() == 4
    assert graph.has_edge("DSO:ZDSO1", "Transformacao:T1")
    assert graph.has_edge("Transformacao:T1", "InfoCube:ZSALES")


def test_build_graph_raises_on_duplicate_id():
    objects = _sample_objects() + [_obj(ObjectType.DSO, "ZDSO1")]
    with pytest.raises(DuplicateObjectError):
        build_graph(objects)


def test_build_graph_preserves_edges_to_unresolved_external_nodes():
    obj = _obj(ObjectType.INFO_CUBE, "ZSALES", fontes=["DSO:ZNAO_EXTRAIDO"])
    graph = build_graph([obj])
    assert graph.has_edge("DSO:ZNAO_EXTRAIDO", "InfoCube:ZSALES")
    assert graph.nodes["DSO:ZNAO_EXTRAIDO"]["external"] is True


def test_find_orphans_detects_no_source_and_no_consumer():
    graph = build_graph(_sample_objects())
    orphans = find_orphans(graph)
    assert "DSO:ZDSO1" in orphans.sem_fonte
    assert "InfoCube:ZSALES" in orphans.sem_consumidor
    assert "InfoCube:ZORPHAN" in orphans.isolados


def test_lineage_upstream_and_downstream():
    graph = build_graph(_sample_objects())
    assert lineage_upstream(graph, "InfoCube:ZSALES") == ["DSO:ZDSO1", "Transformacao:T1"]
    assert lineage_downstream(graph, "DSO:ZDSO1") == ["InfoCube:ZSALES", "Transformacao:T1"]


def test_immediate_context():
    graph = build_graph(_sample_objects())
    fontes, destinos = immediate_context(graph, "Transformacao:T1")
    assert fontes == ["DSO:ZDSO1"]
    assert destinos == ["InfoCube:ZSALES"]


def test_collapse_through_hides_transformation_nodes():
    graph = build_graph(_sample_objects())
    collapsed = collapse_through(graph, keep_types={"DSO", "InfoCube"})
    assert collapsed.has_edge("DSO:ZDSO1", "InfoCube:ZSALES")
    assert "Transformacao:T1" not in collapsed.nodes


def test_json_round_trip_preserves_nodes_and_edges():
    graph = build_graph(_sample_objects())
    data = to_json_dict(graph)
    restored = from_json_dict(data)
    assert set(restored.nodes) == set(graph.nodes)
    assert set(restored.edges) == set(graph.edges)
