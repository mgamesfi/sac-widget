from processor.graph_builder import build_graph
from processor.medallion import MedallionLayer, classify_all, classify_object
from processor.models import ObjectType, UnifiedObject


def _obj(tipo, nome, fontes=None, destinos=None, atributos=None):
    return UnifiedObject(
        id=UnifiedObject.make_id(tipo, nome),
        tipo=tipo,
        nome_tecnico=nome,
        camada=UnifiedObject.camada_for(tipo),
        fontes=fontes or [],
        destinos=destinos or [],
        atributos_especificos=atributos or {},
    )


def test_pipeline_types_are_never_a_data_layer():
    transf = _obj(ObjectType.TRANSFORMACAO, "T1")
    dtp = _obj(ObjectType.DTP, "DTP1")
    chain = _obj(ObjectType.PROCESS_CHAIN, "C1")
    graph = build_graph([transf, dtp, chain])
    for obj in (transf, dtp, chain):
        assert classify_object(obj, graph) == MedallionLayer.PIPELINE


def test_reference_types_are_silver():
    iobj = _obj(ObjectType.INFO_OBJECT, "0MATERIAL")
    hier = _obj(ObjectType.HIERARQUIA, "H1")
    graph = build_graph([iobj, hier])
    assert classify_object(iobj, graph) == MedallionLayer.SILVER
    assert classify_object(hier, graph) == MedallionLayer.SILVER


def test_reporting_types_are_gold():
    graph = build_graph([])
    for tipo in (ObjectType.INFO_CUBE, ObjectType.MULTI_PROVIDER, ObjectType.COMPOSITE_PROVIDER, ObjectType.OPEN_ODS_VIEW):
        obj = _obj(tipo, "X1")
        g = build_graph([obj])
        assert classify_object(obj, g) == MedallionLayer.GOLD


def test_storage_type_without_source_is_bronze():
    dso = _obj(ObjectType.DSO, "ZDSO1")
    graph = build_graph([dso])
    assert classify_object(dso, graph) == MedallionLayer.BRONZE


def test_storage_type_with_source_is_silver():
    upstream = _obj(ObjectType.DSO, "ZDSO_RAW")
    transf = _obj(ObjectType.TRANSFORMACAO, "T1", fontes=["DSO:ZDSO_RAW"], destinos=["DSO:ZDSO_CLEAN"])
    downstream = _obj(ObjectType.DSO, "ZDSO_CLEAN")
    graph = build_graph([upstream, transf, downstream])

    assert classify_object(upstream, graph) == MedallionLayer.BRONZE
    assert classify_object(downstream, graph) == MedallionLayer.SILVER


def test_classify_all_counts():
    objects = [
        _obj(ObjectType.DSO, "ZDSO1"),
        _obj(ObjectType.INFO_CUBE, "ZSALES"),
        _obj(ObjectType.TRANSFORMACAO, "T1"),
        _obj(ObjectType.INFO_OBJECT, "0MATERIAL"),
    ]
    graph = build_graph(objects)
    classification = classify_all(objects, graph)
    counts = classification.counts()
    assert counts == {"bronze": 1, "silver": 1, "gold": 1, "pipeline": 1}
    assert classification.objects_in(objects, MedallionLayer.GOLD)[0].nome_tecnico == "ZSALES"
