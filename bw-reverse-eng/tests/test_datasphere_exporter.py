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


def test_build_scaffold_flow_uses_rfc_extracted_rules_when_present():
    dso = _obj(ObjectType.DSO, "ZDSO1")
    transf = _obj(
        ObjectType.TRANSFORMACAO, "T1",
        fontes=["DSO:ZDSO1"], destinos=["InfoCube:ZSALES"],
        atributos={
            "num_regras": 1,
            "regras": [{"campo_origem": "MATNR", "campo_destino": "0MATERIAL", "tipo_regra": "MOVE", "rotina": None}],
        },
    )
    cube = _obj(ObjectType.INFO_CUBE, "ZSALES")
    graph = build_graph([dso, transf, cube])
    scaffold = build_scaffold([dso, transf, cube], graph)

    flow = scaffold["fluxos"][0]
    assert flow["regras_bw"] == [
        {"campo_origem": "MATNR", "campo_destino": "0MATERIAL", "tipo_regra": "MOVE", "rotina": None}
    ]
    assert "extraída via RFC" in flow["pendencias"][0]


def test_global_warnings_reflect_rule_extraction_coverage():
    dso = _obj(ObjectType.DSO, "ZDSO1")
    with_rules = _obj(
        ObjectType.TRANSFORMACAO, "T1", fontes=["DSO:ZDSO1"],
        atributos={"regras": [{"campo_origem": "A", "campo_destino": "B", "tipo_regra": "MOVE", "rotina": None}]},
    )
    graph = build_graph([dso, with_rules])
    scaffold = build_scaffold([dso, with_rules], graph)

    warnings_text = " ".join(scaffold["avisos"])
    assert "extraída via RFC para todos os fluxos" in warnings_text


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


def test_build_scaffold_populates_elements_from_campos():
    dso = _obj(
        ObjectType.DSO, "ZDSO1",
        atributos={"campos": [
            {"nome": "0MATERIAL", "tipo_dado": "CHAR", "comprimento": 18, "chave": True},
            {"nome": "0AMOUNT", "tipo_dado": "CURR", "comprimento": 15, "chave": False},
        ]},
    )
    graph = build_graph([dso])
    scaffold = build_scaffold([dso], graph)

    entity = scaffold["entidades"][0]
    assert entity["csn_stub"]["elements"]["0MATERIAL"] == {
        "tipo_dado_origem": "CHAR", "comprimento": 18, "key": True,
    }
    assert entity["csn_stub"]["elements"]["0AMOUNT"] == {
        "tipo_dado_origem": "CURR", "comprimento": 15,
    }
    assert "tipos CDS do Datasphere" in entity["pendencias"][0]


def test_build_scaffold_populates_single_element_for_infoobject_own_datatype():
    iobj = _obj(
        ObjectType.INFO_OBJECT, "0MATERIAL",
        atributos={"tipo_dado": "CHAR", "comprimento": 18},
    )
    graph = build_graph([iobj])
    scaffold = build_scaffold([iobj], graph)

    entity = scaffold["entidades"][0]
    assert entity["csn_stub"]["elements"] == {"0MATERIAL": {"tipo_dado_origem": "CHAR", "comprimento": 18}}


def test_global_warnings_reflect_partial_schema_coverage():
    with_schema = _obj(ObjectType.DSO, "ZDSO1", atributos={"campos": [{"nome": "X", "tipo_dado": "CHAR"}]})
    without_schema = _obj(ObjectType.INFO_CUBE, "ZSALES")
    graph = build_graph([with_schema, without_schema])
    scaffold = build_scaffold([with_schema, without_schema], graph)

    warnings_text = " ".join(scaffold["avisos"])
    assert "1 de 2 entidades" in warnings_text


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
