from docgen.markdown_generator import generate_documentation, object_slug, render_object_page
from processor.graph_builder import build_graph
from processor.models import ObjectType, UnifiedObject


def _obj(tipo, nome, descricao="", fontes=None, destinos=None, atributos=None):
    return UnifiedObject(
        id=UnifiedObject.make_id(tipo, nome),
        tipo=tipo,
        nome_tecnico=nome,
        descricao=descricao,
        pacote="ZBW",
        camada=UnifiedObject.camada_for(tipo),
        fontes=fontes or [],
        destinos=destinos or [],
        atributos_especificos=atributos or {},
    )


def _sample_objects():
    dso = _obj(ObjectType.DSO, "ZDSO1", descricao="DSO de vendas")
    cube = _obj(ObjectType.INFO_CUBE, "ZSALES", descricao="Cubo de vendas", fontes=["DSO:ZDSO1"])
    dso.destinos = ["InfoCube:ZSALES"]
    return [dso, cube]


def test_object_slug_is_filesystem_safe():
    slug = object_slug("InfoCube:ZSALES/teste")
    assert slug == "InfoCube_ZSALES_teste.md"


def test_render_object_page_includes_description_and_mermaid_block():
    objects = _sample_objects()
    graph = build_graph(objects)
    objects_by_id = {o.id: o for o in objects}
    cube = next(o for o in objects if o.tipo == ObjectType.INFO_CUBE)

    page = render_object_page(cube, graph, objects_by_id)
    assert "ZSALES" in page
    assert "Cubo de vendas" in page
    assert "```mermaid" in page
    assert "ZDSO1" in page  # fonte listada e linkada


def test_generate_documentation_writes_index_objects_and_reports(tmp_path):
    objects = _sample_objects()
    graph = build_graph(objects)

    generate_documentation(objects, graph, tmp_path)

    assert (tmp_path / "index.md").exists()
    assert (tmp_path / "reports.md").exists()
    assert (tmp_path / "objects" / "InfoCube_ZSALES.md").exists()
    assert (tmp_path / "objects" / "DSO_ZDSO1.md").exists()

    index_text = (tmp_path / "index.md").read_text()
    assert "ZSALES" in index_text
    assert "```mermaid" in index_text
