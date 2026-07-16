from agentcad.models import Document, JunctionElement, Point
from agentcad.svg import render_svg
from agentcad.symbols import SymbolRegistry


def test_junction_is_preserved_in_svg_export():
    document = Document(
        name="Export junction",
        elements=[
            JunctionElement(
                id="junction_svg",
                position=Point(x=240, y=160),
                radius=5,
                label="J-101",
            )
        ],
    )

    svg = render_svg(document, SymbolRegistry())

    assert 'data-element-type="junction"' in svg
    assert 'id="junction_svg"' in svg
    assert '>J-101</text>' in svg
