from agentcad.models import Point
from agentcad.semantic_compiler_engine import SemanticTransactionCompiler


def test_small_horizontal_dogleg_is_collapsed():
    points = [
        Point(x=0, y=100),
        Point(x=100, y=100),
        Point(x=100, y=112),
        Point(x=180, y=112),
        Point(x=180, y=100),
        Point(x=300, y=100),
    ]

    result = SemanticTransactionCompiler._collapse_micro_doglegs(points, tolerance=20)

    assert result == [Point(x=0, y=100), Point(x=300, y=100)]


def test_large_horizontal_detour_is_preserved():
    points = [
        Point(x=0, y=100),
        Point(x=100, y=100),
        Point(x=100, y=160),
        Point(x=180, y=160),
        Point(x=180, y=100),
        Point(x=300, y=100),
    ]

    result = SemanticTransactionCompiler._collapse_micro_doglegs(points, tolerance=20)

    assert result == points


def test_small_vertical_dogleg_is_collapsed():
    points = [
        Point(x=200, y=0),
        Point(x=200, y=80),
        Point(x=188, y=80),
        Point(x=188, y=150),
        Point(x=200, y=150),
        Point(x=200, y=260),
    ]

    result = SemanticTransactionCompiler._collapse_micro_doglegs(points, tolerance=20)

    assert result == [Point(x=200, y=0), Point(x=200, y=260)]
