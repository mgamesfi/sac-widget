"""Smoke test do fluxo completo (extract -> process -> generate-docs -> summary),
usando uma conexão fake em vez de um HANA real (RF01-RF06 / seção 8 da especificação).
"""
from extractor.export import load_snapshot
from extractor.filters import ExtractionFilters
from extractor.pipeline import run_extraction
from processor.pipeline import run_process
from processor.reports import summary_report
from docgen.markdown_generator import generate_documentation


def _script():
    # Ordem importa: entradas mais específicas antes de entradas mais genéricas,
    # já que o FakeConnection casa pela primeira substring encontrada.
    return [
        ("FROM RSDIOBJ", [
            {"IOBJNM": "0MATERIAL", "IOBJTP": "CHA", "DEVCLASS": "ZBW", "TIMESTMP": "20260101", "LASTUSER": "JDOE", "TXTLG": "Material"},
        ]),
        ("CUBETYPE = '0'", [
            {"INFOCUBE": "ZSALES", "DEVCLASS": "ZBW", "TIMESTMP": "20260101", "LASTUSER": "JDOE", "TXTLG": "Vendas"},
        ]),
        ("FROM RSDODSO", [
            {"ODSOBJECT": "ZDSO1", "DEVCLASS": "ZBW", "TIMESTMP": "20260101", "LASTUSER": "JDOE", "TXTLG": "DSO Vendas"},
        ]),
        ("CUBETYPE = '1'", []),
        ("FROM RSDMPRO", []),
        ("FROM RSTRANSTEPS", [{"TRANID": "T1", "NUM_REGRAS": 4}]),
        ("FROM RSTRAN", [
            {"TRANID": "T1", "SOURCE": "ZDSO1", "SOURCETYPE": "ODSO", "TARGET": "ZSALES", "TARGETTYPE": "CUBE", "DEVCLASS": "ZBW", "TIMESTMP": "20260101"},
        ]),
        ("FROM RSBKDTP", [
            {"DTP": "DTP1", "SOURCE": "0MATERIAL", "SOURCETYPE": "IOBJ", "TARGET": "ZDSO1", "TARGETTYPE": "ODSO", "DTPTYPE": "F", "DEVCLASS": "ZBW", "TIMESTMP": "20260101"},
        ]),
        ("FROM RSPCLOGCHAIN", []),
        ("FROM RSPCCHAIN", [{"CHAIN_ID": "ZCHAIN1", "DEVCLASS": "ZBW", "TIMESTMP": "20260101"}]),
        ("FROM RSDHIE", []),
        ("FROM RSOADSO", [
            {"ADSONM": "ZADSO1", "DEVCLASS": "ZBW", "TIMESTMP": "20260101", "LASTUSER": "JDOE", "TXTLG": "ADSO Vendas"},
        ]),
        ("FROM RSOHCPRSRC", [{"COMPPROV": "ZCP1", "SOURCE": "ZADSO1", "SOURCETYPE": "ADSO"}]),
        ("FROM RSOHCPRELEMENT", [{"COMPPROV": "ZCP1", "NUM_ELEMENTS": 2}]),
        ("FROM RSOHCPR", [
            {"COMPPROV": "ZCP1", "DEVCLASS": "ZBW", "TIMESTMP": "20260101", "LASTUSER": "JDOE", "TXTLG": "Composite Vendas"},
        ]),
        ("FROM RSOOSVIEW", []),
    ]


def test_full_pipeline_extract_process_generate_docs(tmp_path, fake_connection_factory):
    conn = fake_connection_factory(_script())
    filters = ExtractionFilters()

    snapshot_dir = run_extraction(conn, filters, tmp_path / "data", language="EN", hana_schema=None)
    raw = load_snapshot(snapshot_dir)
    assert raw["InfoCube"][0]["INFOCUBE"] == "ZSALES"
    assert raw["Transformacao"][0]["NUM_REGRAS"] == 4

    process_result = run_process(snapshot_dir, tmp_path / "processed")
    ids = {o.id for o in process_result.objects}
    assert "InfoCube:ZSALES" in ids
    assert "DSO:ZDSO1" in ids
    assert "CompositeProvider:ZCP1" in ids
    assert process_result.graph.has_edge("DSO:ZDSO1", "Transformacao:T1")
    assert process_result.graph.has_edge("Transformacao:T1", "InfoCube:ZSALES")
    assert process_result.graph.has_edge("ADSO:ZADSO1", "CompositeProvider:ZCP1")

    summary = summary_report(process_result.objects)
    assert summary.total == len(process_result.objects) > 0

    docs_dir = tmp_path / "docs"
    generate_documentation(process_result.objects, process_result.graph, docs_dir)
    assert (docs_dir / "index.md").exists()
    assert (docs_dir / "reports.md").exists()
    assert (docs_dir / "objects" / "InfoCube_ZSALES.md").exists()

    object_page = (docs_dir / "objects" / "InfoCube_ZSALES.md").read_text()
    assert "```mermaid" in object_page
    # A fonte direta de InfoCube:ZSALES no grafo é a Transformação (contexto imediato);
    # ZDSO1 só aparece na página da própria Transformação (RF05: drill-down por objeto).
    assert "T1" in object_page
