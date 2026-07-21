import json

from exporters.datasphere import build_scaffold, export_scaffold
from processor.graph_builder import build_graph
from processor.models import ObjectType, UnifiedObject


def _obj(tipo, nome, descricao="", fontes=None, destinos=None, atributos=None):
    return UnifiedObject(
        id=UnifiedObject.make_id(tipo, nome),
        tipo=tipo,
        nome_tecnico=nome,
        descricao=descricao,
        camada=UnifiedObject.camada_for(tipo),
        fontes=fontes or [],
        destinos=destinos or [],
        atributos_especificos=atributos or {},
    )


def _sample_objects():
    dso = _obj(ObjectType.DSO, "ZDSO1", descricao="DSO de vendas")
    transf = _obj(
        ObjectType.TRANSFORMACAO, "T1",
        fontes=["DSO:ZDSO1"], destinos=["InfoCube:ZSALES"],
        atributos={"num_regras": 7},
    )
    cube = _obj(ObjectType.INFO_CUBE, "ZSALES", descricao="Cubo de vendas")
    return [dso, transf, cube]


def test_build_scaffold_classifies_entities_and_flows_separately():
    objects = _sample_objects()
    graph = build_graph(objects)
    scaffold = build_scaffold(objects, graph)

    entity_ids = {e["id"] for e in scaffold["entidades"]}
    assert entity_ids == {"DSO:ZDSO1", "InfoCube:ZSALES"}
    flow_ids = {f["id"] for f in scaffold["fluxos"]}
    assert flow_ids == {"Transformacao:T1"}


def test_build_scaffold_suggests_layer_prefixed_names():
    objects = _sample_objects()
    graph = build_graph(objects)
    scaffold = build_scaffold(objects, graph)

    dso_entry = next(e for e in scaffold["entidades"] if e["id"] == "DSO:ZDSO1")
    cube_entry = next(e for e in scaffold["entidades"] if e["id"] == "InfoCube:ZSALES")
    assert dso_entry["nome_sugerido_datasphere"] == "BRZ_ZDSO1"
    assert dso_entry["camada_medalhao"] == "bronze"
    assert cube_entry["nome_sugerido_datasphere"] == "GLD_ZSALES"
    assert cube_entry["camada_medalhao"] == "gold"


def test_build_scaffold_flow_carries_rule_count_and_resolved_endpoints():
    objects = _sample_objects()
    graph = build_graph(objects)
    scaffold = build_scaffold(objects, graph)

    flow = scaffold["fluxos"][0]
    assert flow["num_regras_bw"] == 7
    assert flow["de"] == ["BRZ_ZDSO1"]
    assert flow["para"] == ["GLD_ZSALES"]


def test_build_scaffold_entities_have_empty_elements_and_pendencia():
    objects = _sample_objects()
    graph = build_graph(objects)
    scaffold = build_scaffold(objects, graph)

    for entity in scaffold["entidades"]:
        assert entity["csn_stub"]["elements"] == {}
        assert entity["pendencias"]


def test_build_scaffold_includes_honest_warnings():
    objects = _sample_objects()
    graph = build_graph(objects)
    scaffold = build_scaffold(objects, graph)

    warnings_text = " ".join(scaffold["avisos"])
    assert "schema de campos" in warnings_text
    assert "lógica de negócio" in warnings_text or "regras de transformação" in warnings_text
    assert "não é um CSN oficial" in warnings_text or "rascunho" in warnings_text


def test_export_scaffold_writes_valid_json(tmp_path):
    objects = _sample_objects()
    graph = build_graph(objects)
    output_path = tmp_path / "datasphere" / "scaffold.json"

    result_path = export_scaffold(objects, graph, output_path)

    assert result_path == output_path
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert data["resumo"]["bronze"] == 1
    assert data["resumo"]["gold"] == 1
    assert data["resumo"]["pipeline"] == 1
