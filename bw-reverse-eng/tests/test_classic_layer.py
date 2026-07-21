from extractor import classic_layer
from extractor.filters import ExtractionFilters


def test_extract_infocubes_joins_text_table(fake_connection_factory):
    conn = fake_connection_factory(
        [
            ("FROM RSDCUBE", [
                {"INFOCUBE": "ZSALES", "CUBETYPE": "0", "DEVCLASS": "ZBW", "TIMESTMP": "20260101", "LASTUSER": "JDOE", "TXTLG": "Vendas"},
            ]),
        ]
    )
    rows = classic_layer.extract_infocubes(conn, ExtractionFilters())
    assert rows == [
        {"INFOCUBE": "ZSALES", "CUBETYPE": "0", "DEVCLASS": "ZBW", "TIMESTMP": "20260101", "LASTUSER": "JDOE", "TXTLG": "Vendas"}
    ]


def test_extract_transformations_aggregates_rule_count(fake_connection_factory):
    conn = fake_connection_factory(
        [
            # RSTRANSTEPS antes de RSTRAN: "RSTRAN" é prefixo de "RSTRANSTEPS", então a
            # entrada mais específica precisa vir primeiro no FakeConnection.
            ("FROM RSTRANSTEPS", [{"TRANID": "T1", "NUM_REGRAS": 12}]),
            ("FROM RSTRAN", [
                {"TRANID": "T1", "SOURCE": "ZDSO", "SOURCETYPE": "ODSO", "TARGET": "ZSALES", "TARGETTYPE": "CUBE", "DEVCLASS": "ZBW", "TIMESTMP": "20260101"},
            ]),
        ]
    )
    rows = classic_layer.extract_transformations(conn, ExtractionFilters())
    assert rows[0]["NUM_REGRAS"] == 12


def test_extraction_filters_wants_respects_object_types():
    filters = ExtractionFilters(object_types=frozenset({"InfoCube"}))
    assert filters.wants("InfoCube")
    assert not filters.wants("DSO")

    unrestricted = ExtractionFilters()
    assert unrestricted.wants("anything")


def test_package_and_changed_since_clauses_build_params():
    filters = ExtractionFilters(packages=frozenset({"ZBW1", "ZBW2"}), changed_since=None)
    clause, params = filters.package_clause("DEVCLASS")
    assert "DEVCLASS IN" in clause
    assert set(params) == {"ZBW1", "ZBW2"}

    no_filter = ExtractionFilters()
    clause, params = no_filter.package_clause("DEVCLASS")
    assert clause == "" and params == ()


def test_extract_all_skips_disabled_types(fake_connection_factory):
    conn = fake_connection_factory([("FROM RSDCUBE", [])])
    filters = ExtractionFilters(object_types=frozenset({"InfoCube"}))
    results = classic_layer.extract_all(conn, filters)
    assert list(results.keys()) == ["InfoCube"]


def test_extract_all_tolerates_partial_failure(fake_connection_factory):
    conn = fake_connection_factory([("FROM RSDIOBJ", [])])  # só InfoObject responde
    filters = ExtractionFilters(object_types=frozenset({"InfoObject", "InfoCube"}))
    results = classic_layer.extract_all(conn, filters)
    assert results["InfoObject"] == []
    assert results["InfoCube"] == []  # falhou mas não propagou exceção
