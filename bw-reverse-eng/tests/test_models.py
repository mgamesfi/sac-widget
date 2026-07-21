from processor.models import ObjectType, UnifiedObject


def test_camada_for_classifies_nextgen_types():
    assert UnifiedObject.camada_for(ObjectType.ADSO) == "next-gen"
    assert UnifiedObject.camada_for(ObjectType.COMPOSITE_PROVIDER) == "next-gen"
    assert UnifiedObject.camada_for(ObjectType.OPEN_ODS_VIEW) == "next-gen"


def test_camada_for_classifies_classic_types():
    assert UnifiedObject.camada_for(ObjectType.INFO_CUBE) == "classico"
    assert UnifiedObject.camada_for(ObjectType.DSO) == "classico"
    assert UnifiedObject.camada_for(ObjectType.TRANSFORMACAO) == "classico"


def test_make_id_is_stable_and_type_prefixed():
    assert UnifiedObject.make_id(ObjectType.INFO_CUBE, "ZSALES") == "InfoCube:ZSALES"


def test_unified_object_defaults():
    obj = UnifiedObject(
        id="InfoCube:ZSALES",
        tipo=ObjectType.INFO_CUBE,
        nome_tecnico="ZSALES",
        camada="classico",
    )
    assert obj.descricao == ""
    assert obj.fontes == []
    assert obj.destinos == []
    assert obj.atributos_especificos == {}
