from processor.models import ObjectType, UnifiedObject
from processor.reports import complexity_report, missing_docs_report, summary_report


def _cp(nome, num_fontes):
    return UnifiedObject(
        id=UnifiedObject.make_id(ObjectType.COMPOSITE_PROVIDER, nome),
        tipo=ObjectType.COMPOSITE_PROVIDER,
        nome_tecnico=nome,
        camada="next-gen",
        pacote="ZBW",
        fontes=[f"ADSO:X{i}" for i in range(num_fontes)],
    )


def _transf(nome, num_regras):
    return UnifiedObject(
        id=UnifiedObject.make_id(ObjectType.TRANSFORMACAO, nome),
        tipo=ObjectType.TRANSFORMACAO,
        nome_tecnico=nome,
        camada="classico",
        pacote="ZBW",
        atributos_especificos={"num_regras": num_regras},
    )


def test_summary_report_counts_by_tipo_pacote_camada():
    objects = [_cp("ZCP1", 2), _transf("T1", 3)]
    summary = summary_report(objects)
    assert summary.total == 2
    assert summary.por_tipo == {"CompositeProvider": 1, "Transformacao": 1}
    assert summary.por_camada == {"classico": 1, "next-gen": 1}


def test_missing_docs_report_flags_empty_description():
    documented = _cp("ZCP1", 1)
    documented.descricao = "Tem descrição"
    undocumented = _cp("ZCP2", 1)
    result = missing_docs_report([documented, undocumented])
    assert result == [undocumented]


def test_complexity_report_flags_above_threshold_only():
    objects = [_cp("ZCP_SIMPLES", 2), _cp("ZCP_COMPLEXO", 8), _transf("T_SIMPLES", 3), _transf("T_COMPLEXO", 15)]
    findings = complexity_report(objects, composite_provider_source_threshold=5, transformation_rule_threshold=10)
    flagged_ids = {f.id for f in findings}
    assert "CompositeProvider:ZCP_COMPLEXO" in flagged_ids
    assert "Transformacao:T_COMPLEXO" in flagged_ids
    assert "CompositeProvider:ZCP_SIMPLES" not in flagged_ids
    assert "Transformacao:T_SIMPLES" not in flagged_ids


def test_complexity_report_sorted_descending_by_value():
    objects = [_cp("ZCP_A", 6), _cp("ZCP_B", 20)]
    findings = complexity_report(objects, composite_provider_source_threshold=5, transformation_rule_threshold=10)
    assert [f.nome_tecnico for f in findings] == ["ZCP_B", "ZCP_A"]
