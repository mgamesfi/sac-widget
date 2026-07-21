from processor.models import ObjectType
from processor.normalizer import normalize


def _raw_snapshot():
    return {
        "InfoCube": [
            {"INFOCUBE": "ZSALES", "DEVCLASS": "ZBW", "TXTLG": "Vendas", "LASTUSER": "JDOE", "TIMESTMP": "20260101"},
        ],
        "DSO": [
            {"ODSOBJECT": "ZDSO1", "DEVCLASS": "ZBW", "TXTLG": "DSO Vendas", "LASTUSER": "JDOE", "TIMESTMP": "20260101"},
        ],
        "Transformacao": [
            {
                "TRANID": "T1", "SOURCE": "ZDSO1", "SOURCETYPE": "ODSO",
                "TARGET": "ZSALES", "TARGETTYPE": "CUBE",
                "DEVCLASS": "ZBW", "TIMESTMP": "20260101", "NUM_REGRAS": 5,
            },
        ],
        "ADSO": [
            {"ADSONM": "ZADSO1", "DEVCLASS": "ZBW", "TXTLG": "ADSO Vendas", "LASTUSER": "JDOE", "TIMESTMP": "20260101"},
        ],
        "CompositeProvider": [
            {
                "COMPPROV": "ZCP1", "DEVCLASS": "ZBW", "TXTLG": "Composite Vendas",
                "LASTUSER": "JDOE", "TIMESTMP": "20260101", "NUM_ELEMENTS": 2,
                "SOURCES": [{"source": "ZADSO1", "source_type": "ADSO"}, {"source": "ZUNKNOWN", "source_type": "ADSO"}],
            },
        ],
    }


def test_normalize_produces_unified_objects_for_every_type():
    result = normalize(_raw_snapshot())
    ids = {obj.id for obj in result.objects}
    assert "InfoCube:ZSALES" in ids
    assert "DSO:ZDSO1" in ids
    assert "Transformacao:T1" in ids
    assert "ADSO:ZADSO1" in ids
    assert "CompositeProvider:ZCP1" in ids


def test_normalize_resolves_transformation_lineage():
    result = normalize(_raw_snapshot())
    by_id = {obj.id for obj in result.objects}
    transformation = next(o for o in result.objects if o.tipo == ObjectType.TRANSFORMACAO)
    assert transformation.fontes == ["DSO:ZDSO1"]
    assert transformation.destinos == ["InfoCube:ZSALES"]
    assert "DSO:ZDSO1" in by_id and "InfoCube:ZSALES" in by_id


def test_normalize_resolves_composite_provider_source_by_name_fallback():
    result = normalize(_raw_snapshot())
    cp = next(o for o in result.objects if o.tipo == ObjectType.COMPOSITE_PROVIDER)
    assert "ADSO:ZADSO1" in cp.fontes


def test_normalize_reports_unresolved_reference_as_warning():
    result = normalize(_raw_snapshot())
    assert any("ZUNKNOWN" in w for w in result.warnings)
    cp = next(o for o in result.objects if o.tipo == ObjectType.COMPOSITE_PROVIDER)
    # referência não resolvida é mantida como texto cru, não descartada silenciosamente
    assert "ZUNKNOWN" in cp.fontes


def test_normalize_unknown_object_type_is_reported_and_skipped():
    result = normalize({"TipoInexistente": [{"foo": "bar"}]})
    assert result.objects == []
    assert any("TipoInexistente" in w for w in result.warnings)
