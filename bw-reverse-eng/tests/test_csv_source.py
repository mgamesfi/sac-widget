"""Testa a fonte CSV (extractor/csv_source.py) isoladamente e integrada com
classic_layer/nextgen_layer — as mesmas funções/consultas usadas contra o HANA
real, só que executadas sobre um SQLite em memória carregado a partir de CSVs.
"""
from __future__ import annotations

import pytest

from extractor import classic_layer, nextgen_layer
from extractor.csv_source import CsvConnection, CsvSourceError
from extractor.filters import ExtractionFilters


def _write_csv(path, header, rows, delimiter=","):
    path.write_text(
        delimiter.join(header) + "\n" + "\n".join(delimiter.join(r) for r in rows) + "\n",
        encoding="utf-8",
    )


def test_connect_raises_for_missing_directory(tmp_path):
    conn = CsvConnection(tmp_path / "nao_existe")
    with pytest.raises(CsvSourceError):
        conn.connect()


def test_connect_loads_only_recognized_tables(tmp_path):
    _write_csv(tmp_path / "RSDCUBE.csv", ["INFOCUBE", "OBJVERS"], [["ZSALES", "A"]])
    (tmp_path / "notas.txt").write_text("arquivo irrelevante, deve ser ignorado")

    with CsvConnection(tmp_path) as conn:
        assert conn.loaded_tables == {"RSDCUBE": 1}


def test_execute_runs_real_sql_against_loaded_table(tmp_path):
    _write_csv(
        tmp_path / "RSDCUBE.csv",
        ["INFOCUBE", "CUBETYPE", "OBJVERS", "DEVCLASS", "TIMESTMP", "LASTUSER"],
        [["ZSALES", "0", "A", "ZBW", "20260101", "JDOE"]],
    )
    _write_csv(tmp_path / "RSDCUBET.csv", ["INFOCUBE", "LANGU", "TXTLG"], [["ZSALES", "EN", "Vendas"]])

    with CsvConnection(tmp_path) as conn:
        rows = classic_layer.extract_infocubes(conn, ExtractionFilters())

    assert rows == [
        {"INFOCUBE": "ZSALES", "CUBETYPE": "0", "DEVCLASS": "ZBW", "TIMESTMP": "20260101", "LASTUSER": "JDOE", "TXTLG": "Vendas"}
    ]


def test_execute_supports_semicolon_delimiter(tmp_path):
    _write_csv(
        tmp_path / "RSDIOBJ.csv",
        ["IOBJNM", "IOBJTP", "OBJVERS", "DEVCLASS", "TIMESTMP", "LASTUSER"],
        [["0MATERIAL", "CHA", "A", "ZBW", "20260101", "JDOE"]],
        delimiter=";",
    )
    _write_csv(tmp_path / "RSDIOBJT.csv", ["IOBJNM", "LANGU", "TXTLG"], [["0MATERIAL", "EN", "Material"]], delimiter=";")

    with CsvConnection(tmp_path) as conn:
        rows = classic_layer.extract_infoobjects(conn, ExtractionFilters())

    assert rows[0]["IOBJNM"] == "0MATERIAL"


def test_missing_text_table_does_not_break_the_join(tmp_path):
    """RSDIOBJ presente mas RSDIOBJT (tabela de texto) ausente: o LEFT JOIN não pode
    quebrar a extração inteira — a tabela de texto é criada vazia e a descrição
    apenas fica em branco (ver _TEXT_TABLE_STUBS)."""
    _write_csv(
        tmp_path / "RSDIOBJ.csv",
        ["IOBJNM", "IOBJTP", "OBJVERS", "DEVCLASS", "TIMESTMP", "LASTUSER"],
        [["0MATERIAL", "CHA", "A", "ZBW", "20260101", "JDOE"]],
    )

    with CsvConnection(tmp_path) as conn:
        rows = classic_layer.extract_infoobjects(conn, ExtractionFilters())

    assert rows[0]["IOBJNM"] == "0MATERIAL"
    assert rows[0]["TXTLG"] is None


def test_missing_optional_enrichment_table_does_not_lose_main_object_type(tmp_path):
    """RSTRAN presente mas RSTRANSTEPS ausente: Transformação ainda deve ser extraída,
    só que sem NUM_REGRAS (enriquecimento é opcional, ver _run_optional)."""
    _write_csv(
        tmp_path / "RSTRAN.csv",
        ["TRANID", "SOURCE", "SOURCETYPE", "TARGET", "TARGETTYPE", "OBJVERS", "DEVCLASS", "TIMESTMP"],
        [["T1", "ZDSO1", "ODSO", "ZSALES", "CUBE", "A", "ZBW", "20260101"]],
    )

    with CsvConnection(tmp_path) as conn:
        rows = classic_layer.extract_transformations(conn, ExtractionFilters())

    assert rows[0]["TRANID"] == "T1"
    assert rows[0]["NUM_REGRAS"] == 0


def test_missing_main_table_raises_and_is_tolerated_by_extract_all(tmp_path):
    """Sem nenhuma tabela RSD*/RSTRAN* etc., extract_all() não deve propagar exceção —
    cada tipo falho é reportado vazio (mesma tolerância a erro usada com HANA real)."""
    with CsvConnection(tmp_path) as conn:
        results = classic_layer.extract_all(conn, ExtractionFilters())

    assert results["InfoCube"] == []
    assert results["DTP"] == []


def test_composite_provider_sources_and_elements_loaded_from_csv(tmp_path):
    _write_csv(tmp_path / "RSOHCPR.csv", ["COMPPROV", "OBJVERS", "DEVCLASS", "TIMESTMP", "LASTUSER"], [["ZCP1", "A", "ZBW", "20260101", "JDOE"]])
    _write_csv(tmp_path / "RSOHCPRT.csv", ["COMPPROV", "LANGU", "TXTLG"], [["ZCP1", "EN", "Composite Vendas"]])
    _write_csv(tmp_path / "RSOHCPRSRC.csv", ["COMPPROV", "SOURCE", "SOURCETYPE", "OBJVERS"], [["ZCP1", "ZADSO1", "ADSO", "A"]])
    _write_csv(tmp_path / "RSOHCPRELEMENT.csv", ["COMPPROV", "OBJVERS"], [["ZCP1", "A"], ["ZCP1", "A"]])

    with CsvConnection(tmp_path) as conn:
        rows = nextgen_layer.extract_composite_providers(conn, ExtractionFilters())

    assert rows[0]["NUM_ELEMENTS"] == 2
    assert [s["source"] for s in rows[0]["SOURCES"]] == ["ZADSO1"]


def test_test_connection_reports_loaded_and_missing_tables(tmp_path):
    _write_csv(tmp_path / "RSDCUBE.csv", ["INFOCUBE", "OBJVERS"], [["ZSALES", "A"]])

    conn = CsvConnection(tmp_path)
    with conn:
        info = conn.test_connection()

    assert info["ok"] is True
    assert info["permissions"]["RSDCUBE"] is True
    assert info["permissions"]["RSOADSO"] is False


def test_test_connection_reports_not_ok_without_core_tables(tmp_path):
    _write_csv(tmp_path / "RSTRAN.csv", ["TRANID", "OBJVERS"], [["T1", "A"]])

    conn = CsvConnection(tmp_path)
    with conn:
        info = conn.test_connection()

    assert info["ok"] is False
