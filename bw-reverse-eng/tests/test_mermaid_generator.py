from docgen.mermaid_generator import generate_macro_diagram, generate_object_diagram
from processor.graph_builder import build_graph
from processor.models import ObjectType, UnifiedObject


def _obj(tipo, nome, fontes=None, destinos=None):
    return UnifiedObject(
        id=UnifiedObject.make_id(tipo, nome),
        tipo=tipo,
        nome_tecnico=nome,
        camada=UnifiedObject.camada_for(tipo),
        fontes=fontes or [],
        destinos=destinos or [],
    )


def _sample_graph():
    dso = _obj(ObjectType.DSO, "ZDSO1")
    transf = _obj(ObjectType.TRANSFORMACAO, "T1", fontes=["DSO:ZDSO1"], destinos=["InfoCube:ZSALES"])
    cube = _obj(ObjectType.INFO_CUBE, "ZSALES")
    return build_graph([dso, transf, cube])


def test_generate_macro_diagram_collapses_transformation_and_is_valid_mermaid():
    diagram = generate_macro_diagram(_sample_graph())
    assert diagram.startswith("flowchart LR")
    assert "ZDSO1" in diagram
    assert "ZSALES" in diagram
    assert "T1" not in diagram  # nó de transformação foi colapsado na visão macro


def test_generate_object_diagram_shows_immediate_context_only():
    diagram = generate_object_diagram(_sample_graph(), "Transformacao:T1")
    assert "flowchart LR" in diagram
    assert "ZDSO1" in diagram
    assert "T1" in diagram
    assert "ZSALES" in diagram


def test_generate_object_diagram_raises_for_unknown_object():
    import pytest

    with pytest.raises(KeyError):
        generate_object_diagram(_sample_graph(), "InfoCube:INEXISTENTE")


def test_node_ids_are_mermaid_safe_despite_colons_in_domain_ids():
    diagram = generate_macro_diagram(_sample_graph())
    node_lines = [line for line in diagram.splitlines() if '["' in line]
    assert node_lines, "esperava ao menos uma linha de definição de nó"
    for line in node_lines:
        node_id = line.strip().split("[", 1)[0]
        assert ":" not in node_id
