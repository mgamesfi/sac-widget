from extractor import nextgen_layer
from extractor.filters import ExtractionFilters


def test_extract_composite_providers_merges_sources_and_elements(fake_connection_factory):
    conn = fake_connection_factory(
        [
            # Entradas específicas (RSOHCPRSRC/RSOHCPRELEMENT) antes da genérica (RSOHCPR),
            # já que "RSOHCPR" é prefixo de ambas.
            ("FROM RSOHCPRSRC", [
                {"COMPPROV": "ZCP1", "SOURCE": "ZADSO1", "SOURCETYPE": "ADSO"},
                {"COMPPROV": "ZCP1", "SOURCE": "ZADSO2", "SOURCETYPE": "ADSO"},
            ]),
            ("FROM RSOHCPRELEMENT", [{"COMPPROV": "ZCP1", "NUM_ELEMENTS": 3}]),
            ("FROM RSOHCPR", [
                {"COMPPROV": "ZCP1", "DEVCLASS": "ZBW", "TIMESTMP": "20260101", "LASTUSER": "JDOE", "TXTLG": "Composite 1"},
            ]),
        ]
    )
    rows = nextgen_layer.extract_composite_providers(conn, ExtractionFilters())
    assert len(rows) == 1
    assert rows[0]["NUM_ELEMENTS"] == 3
    assert [s["source"] for s in rows[0]["SOURCES"]] == ["ZADSO1", "ZADSO2"]


def test_enrich_with_hana_catalog_adds_view_metadata_and_real_columns(fake_connection_factory):
    conn = fake_connection_factory(
        [
            ("FROM SYS.VIEWS", [{"VIEW_NAME": "ZCP1", "VIEW_TYPE": "CALC"}]),
            ("FROM SYS.TABLE_COLUMNS", [
                {"TABLE_NAME": "ZCP1", "COLUMN_NAME": "MATERIAL", "DATA_TYPE_NAME": "NVARCHAR", "LENGTH": 18, "IS_NULLABLE": "FALSE", "POSITION": 1},
                {"TABLE_NAME": "ZCP1", "COLUMN_NAME": "AMOUNT", "DATA_TYPE_NAME": "DECIMAL", "LENGTH": 15, "IS_NULLABLE": "TRUE", "POSITION": 2},
            ]),
        ]
    )
    providers = [{"COMPPROV": "ZCP1"}]
    nextgen_layer.enrich_with_hana_catalog(conn, providers, hana_schema="BW_SCHEMA")

    hana_view = providers[0]["HANA_VIEW"]
    assert hana_view["view_type"] == "CALC"
    assert hana_view["num_columns"] == 2
    assert hana_view["campos"] == [
        {"nome": "MATERIAL", "tipo_dado": "NVARCHAR", "comprimento": 18, "obrigatorio": True},
        {"nome": "AMOUNT", "tipo_dado": "DECIMAL", "comprimento": 15, "obrigatorio": False},
    ]


def test_enrich_open_ods_views_pulls_columns_from_source_table(fake_connection_factory):
    conn = fake_connection_factory(
        [
            ("FROM SYS.TABLE_COLUMNS", [
                {"TABLE_NAME": "ZSRC_TABLE", "COLUMN_NAME": "ID", "DATA_TYPE_NAME": "INTEGER", "LENGTH": 10, "IS_NULLABLE": "FALSE", "POSITION": 1},
            ]),
        ]
    )
    views = [{"VIEWNAME": "ZVIEW1", "SOURCE": "ZSRC_TABLE"}]
    nextgen_layer.enrich_open_ods_views_with_hana_catalog(conn, views, hana_schema="BW_SCHEMA")

    assert views[0]["CAMPOS"] == [
        {"nome": "ID", "tipo_dado": "INTEGER", "comprimento": 10, "obrigatorio": True}
    ]


def test_enrich_adsos_with_hana_catalog_best_effort_by_name(fake_connection_factory):
    conn = fake_connection_factory(
        [
            ("FROM SYS.TABLE_COLUMNS", [
                {"TABLE_NAME": "ZADSO1", "COLUMN_NAME": "CUSTOMER", "DATA_TYPE_NAME": "NVARCHAR", "LENGTH": 10, "IS_NULLABLE": "TRUE", "POSITION": 1},
            ]),
        ]
    )
    adsos = [{"ADSONM": "ZADSO1"}, {"ADSONM": "ZADSO_SEM_MATCH"}]
    nextgen_layer.enrich_adsos_with_hana_catalog(conn, adsos, hana_schema="BW_SCHEMA")

    assert adsos[0]["CAMPOS"] == [
        {"nome": "CUSTOMER", "tipo_dado": "NVARCHAR", "comprimento": 10, "obrigatorio": False}
    ]
    assert "CAMPOS" not in adsos[1]


def test_extract_all_skips_hana_enrichment_without_schema(fake_connection_factory):
    conn = fake_connection_factory(
        [
            ("FROM RSOADSO", []),
            ("FROM RSOHCPRSRC", []),
            ("FROM RSOHCPRELEMENT", []),
            ("FROM RSOHCPR", []),
            ("FROM RSOOSVIEW", []),
        ]
    )
    results = nextgen_layer.extract_all(conn, ExtractionFilters(), hana_schema=None)
    assert set(results.keys()) == {"ADSO", "CompositeProvider", "OpenODSView"}
