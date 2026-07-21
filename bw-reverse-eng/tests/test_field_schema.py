"""Cobre a extração de Estrutura/schema (campos, tipos, chaves) via tabelas de
metadados BW (RSDCHA/RSDKYF/RSDCUBEIOBJ/RSDODSOIOBJ) e catálogo HANA
(SYS.TABLE_COLUMNS), e a normalização desses dados em atributos_especificos.
"""
from extractor import classic_layer
from extractor.csv_source import CsvConnection
from extractor.filters import ExtractionFilters
from processor.normalizer import normalize


def _write_csv(path, header, rows):
    path.write_text(
        ",".join(header) + "\n" + "\n".join(",".join(r) for r in rows) + "\n",
        encoding="utf-8",
    )


def test_csv_source_loads_field_schema_tables_end_to_end(tmp_path):
    """Regressão de ponta a ponta para o mesmo bug coberto por
    test_csv_source.py::test_known_tables_include_field_schema_tables: prova que,
    com CsvConnection real (não a FakeConnection dos outros testes deste arquivo),
    RSDCUBEIOBJ/RSDCHA/RSDKYF são de fato lidos e chegam ao InfoCube extraído."""
    _write_csv(tmp_path / "RSDCUBE.csv", ["INFOCUBE", "CUBETYPE", "OBJVERS", "DEVCLASS", "TIMESTMP", "LASTUSER"],
               [["ZSALES", "0", "A", "ZBW", "20260101", "JDOE"]])
    _write_csv(tmp_path / "RSDCUBET.csv", ["INFOCUBE", "LANGU", "TXTLG"], [["ZSALES", "EN", "Vendas"]])
    _write_csv(tmp_path / "RSDCUBEIOBJ.csv", ["INFOCUBE", "OBJVERS", "IOBJNM"], [["ZSALES", "A", "0MATERIAL"]])
    _write_csv(tmp_path / "RSDCHA.csv", ["IOBJNM", "OBJVERS", "DATATYPE", "LENGTH"], [["0MATERIAL", "A", "CHAR", "18"]])

    with CsvConnection(tmp_path) as conn:
        rows = classic_layer.extract_infocubes(conn, ExtractionFilters())

    assert rows[0]["CAMPOS"] == [{"nome": "0MATERIAL", "tipo_dado": "CHAR", "comprimento": "18"}]


def test_extract_infoobjects_merges_datatype_from_rsdcha_and_rsdkyf(fake_connection_factory):
    conn = fake_connection_factory(
        [
            ("FROM RSDCHA", [{"IOBJNM": "0MATERIAL", "DATATYPE": "CHAR", "LENGTH": 18}]),
            ("FROM RSDKYF", [{"IOBJNM": "0AMOUNT", "DATATYPE": "CURR", "LENGTH": 15, "CURRENCY": "BRL", "UNIT": None}]),
            ("FROM RSDIOBJ", [
                {"IOBJNM": "0MATERIAL", "IOBJTP": "CHA", "DEVCLASS": "ZBW", "TIMESTMP": "20260101", "LASTUSER": "JDOE", "TXTLG": "Material"},
                {"IOBJNM": "0AMOUNT", "IOBJTP": "KYF", "DEVCLASS": "ZBW", "TIMESTMP": "20260101", "LASTUSER": "JDOE", "TXTLG": "Valor"},
            ]),
        ]
    )
    rows = classic_layer.extract_infoobjects(conn, ExtractionFilters())

    material = next(r for r in rows if r["IOBJNM"] == "0MATERIAL")
    amount = next(r for r in rows if r["IOBJNM"] == "0AMOUNT")
    assert material["tipo_dado"] == "CHAR"
    assert material["comprimento"] == 18
    assert amount["tipo_dado"] == "CURR"
    assert amount["moeda"] == "BRL"


def test_extract_infocubes_merges_fields_from_rsdcubeiobj(fake_connection_factory):
    conn = fake_connection_factory(
        [
            ("FROM RSDCUBEIOBJ", [
                {"INFOCUBE": "ZSALES", "IOBJNM": "0MATERIAL"},
                {"INFOCUBE": "ZSALES", "IOBJNM": "0AMOUNT"},
            ]),
            ("FROM RSDCHA", [{"IOBJNM": "0MATERIAL", "DATATYPE": "CHAR", "LENGTH": 18}]),
            ("FROM RSDKYF", [{"IOBJNM": "0AMOUNT", "DATATYPE": "CURR", "LENGTH": 15}]),
            ("FROM RSDCUBE", [
                {"INFOCUBE": "ZSALES", "CUBETYPE": "0", "DEVCLASS": "ZBW", "TIMESTMP": "20260101", "LASTUSER": "JDOE", "TXTLG": "Vendas"},
            ]),
        ]
    )
    rows = classic_layer.extract_infocubes(conn, ExtractionFilters())

    campos = rows[0]["CAMPOS"]
    assert {c["nome"] for c in campos} == {"0MATERIAL", "0AMOUNT"}
    material = next(c for c in campos if c["nome"] == "0MATERIAL")
    assert material["tipo_dado"] == "CHAR"
    assert material["comprimento"] == 18


def test_extract_dsos_marks_key_fields_from_rsdodsoiobj(fake_connection_factory):
    conn = fake_connection_factory(
        [
            ("FROM RSDODSOIOBJ", [
                {"ODSOBJECT": "ZDSO1", "IOBJNM": "0MATERIAL", "FIELDTYPE": "KEY"},
                {"ODSOBJECT": "ZDSO1", "IOBJNM": "0AMOUNT", "FIELDTYPE": "DATA"},
            ]),
            ("FROM RSDCHA", [{"IOBJNM": "0MATERIAL", "DATATYPE": "CHAR", "LENGTH": 18}]),
            ("FROM RSDKYF", []),
            ("FROM RSDODSO", [
                {"ODSOBJECT": "ZDSO1", "DEVCLASS": "ZBW", "TIMESTMP": "20260101", "LASTUSER": "JDOE", "TXTLG": "DSO Vendas"},
            ]),
        ]
    )
    rows = classic_layer.extract_dsos(conn, ExtractionFilters())

    campos = rows[0]["CAMPOS"]
    material = next(c for c in campos if c["nome"] == "0MATERIAL")
    amount = next(c for c in campos if c["nome"] == "0AMOUNT")
    assert material["chave"] is True
    assert material["tipo_dado"] == "CHAR"
    assert amount["chave"] is False


def test_extract_field_tables_missing_degrades_gracefully(fake_connection_factory):
    """Se RSDCUBEIOBJ/RSDCHA/RSDKYF não existirem (ex: export CSV parcial), o
    InfoCube ainda é extraído, só sem 'CAMPOS' preenchido."""
    conn = fake_connection_factory(
        [
            # RSDCUBEIOBJ antes de RSDCUBE: "RSDCUBE" é prefixo de "RSDCUBEIOBJ" no
            # FakeConnection (que casa por substring).
            ("FROM RSDCUBEIOBJ", []),
            ("FROM RSDCHA", []),
            ("FROM RSDKYF", []),
            ("FROM RSDCUBE", [
                {"INFOCUBE": "ZSALES", "CUBETYPE": "0", "DEVCLASS": "ZBW", "TIMESTMP": "20260101", "LASTUSER": "JDOE", "TXTLG": "Vendas"},
            ]),
        ]
    )
    rows = classic_layer.extract_infocubes(conn, ExtractionFilters())
    assert rows[0]["CAMPOS"] == []


def test_normalize_maps_infoobject_datatype_into_atributos(fake_connection_factory=None):
    raw = {
        "InfoObject": [
            {"IOBJNM": "0MATERIAL", "IOBJTP": "CHA", "TXTLG": "Material", "tipo_dado": "CHAR", "comprimento": 18},
        ]
    }
    result = normalize(raw)
    obj = result.objects[0]
    assert obj.atributos_especificos["tipo_dado"] == "CHAR"
    assert obj.atributos_especificos["comprimento"] == 18


def test_normalize_maps_infocube_campos_into_atributos():
    raw = {
        "InfoCube": [
            {
                "INFOCUBE": "ZSALES", "TXTLG": "Vendas",
                "CAMPOS": [{"nome": "0MATERIAL", "tipo_dado": "CHAR", "comprimento": 18}],
            }
        ]
    }
    result = normalize(raw)
    obj = result.objects[0]
    assert obj.atributos_especificos["campos"] == [{"nome": "0MATERIAL", "tipo_dado": "CHAR", "comprimento": 18}]


def test_normalize_maps_composite_provider_campos_from_hana_view():
    raw = {
        "CompositeProvider": [
            {
                "COMPPROV": "ZCP1", "TXTLG": "Composite Vendas",
                "HANA_VIEW": {"view_type": "CALC", "num_columns": 1, "campos": [{"nome": "MATERIAL", "tipo_dado": "NVARCHAR"}]},
            }
        ]
    }
    result = normalize(raw)
    obj = result.objects[0]
    assert obj.atributos_especificos["campos"] == [{"nome": "MATERIAL", "tipo_dado": "NVARCHAR"}]


def test_normalize_composite_provider_without_hana_view_has_empty_campos():
    raw = {"CompositeProvider": [{"COMPPROV": "ZCP1", "TXTLG": "Composite Vendas"}]}
    result = normalize(raw)
    assert result.objects[0].atributos_especificos["campos"] == []
