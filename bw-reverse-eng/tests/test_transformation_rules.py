"""Testa a extração de regras de transformação via RFC (extractor/transformation_rules.py)
contra uma conexão RFC fake — nunca contra pyrfc/SAP real (ver módulo docstring)."""
from extractor.rfc_connection import RfcCallError
from extractor.transformation_rules import (
    enrich_transformations_with_rules,
    extract_routine_source,
    extract_transformation_rules,
)


def test_extract_transformation_rules_normalizes_common_column_names(fake_rfc_connection_factory):
    rfc = fake_rfc_connection_factory(
        {
            "Z_BWREVENG_GET_TRFN_RULES": {
                "ET_RULES": [
                    {"SOURCE_FIELD": "MATNR", "TARGET_FIELD": "0MATERIAL", "RULETYPE": "MOVE", "ROUTINE": ""},
                    {"SOURCE_FIELD": "MENGE", "TARGET_FIELD": "0AMOUNT", "RULETYPE": "ROUTINE", "ROUTINE": "FIELD_ROUTINE_01"},
                ]
            }
        }
    )
    rules = extract_transformation_rules(rfc, "T1", "Z_BWREVENG_GET_TRFN_RULES")

    assert rules == [
        {"campo_origem": "MATNR", "campo_destino": "0MATERIAL", "tipo_regra": "MOVE", "rotina": None},
        {"campo_origem": "MENGE", "campo_destino": "0AMOUNT", "tipo_regra": "ROUTINE", "rotina": "FIELD_ROUTINE_01"},
    ]


def test_extract_transformation_rules_tries_alternate_table_keys(fake_rfc_connection_factory):
    rfc = fake_rfc_connection_factory(
        {"MY_CUSTOM_FM": {"REGRAS": [{"SOURCE": "A", "TARGET": "B", "RULE_TYPE": "MOVE"}]}}
    )
    rules = extract_transformation_rules(rfc, "T1", "MY_CUSTOM_FM")
    assert rules == [{"campo_origem": "A", "campo_destino": "B", "tipo_regra": "MOVE", "rotina": None}]


def test_extract_transformation_rules_degrades_gracefully_when_function_missing(fake_rfc_connection_factory):
    rfc = fake_rfc_connection_factory({"Z_BWREVENG_GET_TRFN_RULES": RfcCallError("função não encontrada")})
    rules = extract_transformation_rules(rfc, "T1", "Z_BWREVENG_GET_TRFN_RULES")
    assert rules == []


def test_extract_routine_source_joins_lines(fake_rfc_connection_factory):
    rfc = fake_rfc_connection_factory(
        {
            "RPY_PROGRAM_READ": {
                "SOURCE_EXTENDED": [{"LINE": "DATA: lv_x TYPE i."}, {"LINE": "lv_x = 1."}]
            }
        }
    )
    source = extract_routine_source(rfc, "GP_ZTRFN_ROUTINE_01")
    assert source == "DATA: lv_x TYPE i.\nlv_x = 1."


def test_extract_routine_source_degrades_gracefully_when_program_missing(fake_rfc_connection_factory):
    rfc = fake_rfc_connection_factory({"RPY_PROGRAM_READ": RfcCallError("programa não existe")})
    assert extract_routine_source(rfc, "GP_INEXISTENTE") == ""


def test_enrich_transformations_with_rules_attaches_regras(fake_rfc_connection_factory):
    rfc = fake_rfc_connection_factory(
        {
            "Z_BWREVENG_GET_TRFN_RULES": {
                "ET_RULES": [{"SOURCE_FIELD": "MATNR", "TARGET_FIELD": "0MATERIAL", "RULETYPE": "MOVE"}]
            }
        }
    )
    transformations = [{"TRANID": "T1", "NUM_REGRAS": 1}]
    enrich_transformations_with_rules(rfc, transformations, "Z_BWREVENG_GET_TRFN_RULES")

    assert transformations[0]["REGRAS"] == [
        {"campo_origem": "MATNR", "campo_destino": "0MATERIAL", "tipo_regra": "MOVE", "rotina": None}
    ]


def test_enrich_transformations_with_rules_fetches_routine_source_when_requested(fake_rfc_connection_factory):
    rfc = fake_rfc_connection_factory(
        {
            "Z_BWREVENG_GET_TRFN_RULES": {
                "ET_RULES": [{"SOURCE_FIELD": "MENGE", "TARGET_FIELD": "0AMOUNT", "RULETYPE": "ROUTINE", "ROUTINE": "GP_R01"}]
            },
            "RPY_PROGRAM_READ": {"SOURCE_EXTENDED": [{"LINE": "result = source_field * 2."}]},
        }
    )
    transformations = [{"TRANID": "T1"}]
    enrich_transformations_with_rules(
        rfc, transformations, "Z_BWREVENG_GET_TRFN_RULES", fetch_routine_source=True
    )

    assert transformations[0]["REGRAS"][0]["rotina_fonte"] == "result = source_field * 2."


def test_enrich_transformations_with_rules_tolerates_missing_function(fake_rfc_connection_factory):
    rfc = fake_rfc_connection_factory({"Z_BWREVENG_GET_TRFN_RULES": RfcCallError("sem autorização")})
    transformations = [{"TRANID": "T1", "NUM_REGRAS": 3}]
    enrich_transformations_with_rules(rfc, transformations, "Z_BWREVENG_GET_TRFN_RULES")

    assert transformations[0]["REGRAS"] == []
    assert transformations[0]["NUM_REGRAS"] == 3  # extração principal preservada
