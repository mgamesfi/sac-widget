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


def test_enrich_with_hana_catalog_adds_view_metadata(fake_connection_factory):
    conn = fake_connection_factory(
        [
            ("FROM SYS.VIEWS", [{"VIEW_NAME": "ZCP1", "VIEW_TYPE": "CALC"}]),
            ("FROM SYS.TABLE_COLUMNS", [{"TABLE_NAME": "ZCP1", "NUM_COLUNAS": 42}]),
        ]
    )
    providers = [{"COMPPROV": "ZCP1"}]
    nextgen_layer.enrich_with_hana_catalog(conn, providers, hana_schema="BW_SCHEMA")
    assert providers[0]["HANA_VIEW"] == {"view_type": "CALC", "num_columns": 42}


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
