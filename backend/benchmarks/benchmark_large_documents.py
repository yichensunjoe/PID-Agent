from __future__ import annotations

import argparse
import json
import statistics
import tracemalloc
from math import ceil, sqrt
from time import perf_counter

from agentcad.exporting import ExportBounds, content_bounds
from agentcad.models import CanvasSettings, ConnectorElement, Document, Point, SymbolElement
from agentcad.svg import render_svg
from agentcad.symbols import SymbolRegistry


def make_document(element_count: int) -> Document:
    symbol_count = max(2, int(element_count * 0.6))
    connector_count = element_count - symbol_count
    columns = max(2, ceil(sqrt(symbol_count * 1.7)))
    rows = ceil(symbol_count / columns)
    x_gap = 180
    y_gap = 110
    elements = []
    centers: list[Point] = []

    for index in range(symbol_count):
        column = index % columns
        row = index // columns
        x = 80 + column * x_gap
        y = 60 + row * y_gap
        elements.append(
            SymbolElement(
                id=f"symbol_{index}",
                symbol_key="ball_valve",
                position=Point(x=x, y=y),
                width=60,
                height=40,
                label=f"V-{index + 1:04d}",
            )
        )
        centers.append(Point(x=x + 30, y=y + 20))

    for index in range(connector_count):
        source = centers[index % symbol_count]
        target = centers[(index + 1 + index // symbol_count) % symbol_count]
        middle_x = (source.x + target.x) / 2
        points = [
            source,
            Point(x=middle_x, y=source.y),
            Point(x=middle_x, y=target.y),
            target,
        ]
        elements.append(
            ConnectorElement(
                id=f"connector_{index}",
                points=points,
                routing="manual",
                crossing_style="jump" if index % 25 == 0 else "none",
                flow_direction="forward" if index % 5 == 0 else "none",
            )
        )

    return Document(
        id=f"benchmark_{element_count}",
        name=f"Benchmark {element_count}",
        canvas=CanvasSettings(
            width=max(1600, columns * x_gap + 160),
            height=max(900, rows * y_gap + 140),
            grid_size=20,
        ),
        elements=elements,
    )


def timed(operation, iterations: int):
    durations = []
    result = None
    for _ in range(iterations):
        started = perf_counter()
        result = operation()
        durations.append((perf_counter() - started) * 1000)
    return result, {
        "minimum_ms": round(min(durations), 3),
        "median_ms": round(statistics.median(durations), 3),
        "maximum_ms": round(max(durations), 3),
    }


def benchmark(element_count: int, iterations: int) -> dict:
    registry = SymbolRegistry()
    document = make_document(element_count)
    viewport = ExportBounds(0, 0, min(1600, document.canvas.width), min(900, document.canvas.height))

    tracemalloc.start()
    bounds, bounds_time = timed(lambda: content_bounds(document, registry, padding=24), iterations)
    full_svg, full_time = timed(lambda: render_svg(document, registry), iterations)
    viewport_svg, viewport_time = timed(lambda: render_svg(document, registry, viewport), iterations)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    rendered_marker = 'data-rendered-elements="'
    marker_index = viewport_svg.index(rendered_marker) + len(rendered_marker)
    rendered_count = int(viewport_svg[marker_index:viewport_svg.index('"', marker_index)])

    return {
        "element_count": element_count,
        "canvas": {"width": document.canvas.width, "height": document.canvas.height},
        "content_bounds": bounds.as_dict(),
        "content_bounds_time": bounds_time,
        "full_svg_time": full_time,
        "viewport_svg_time": viewport_time,
        "full_svg_bytes": len(full_svg.encode("utf-8")),
        "viewport_svg_bytes": len(viewport_svg.encode("utf-8")),
        "viewport_rendered_elements": rendered_count,
        "viewport_cull_ratio": round(rendered_count / element_count, 4),
        "peak_traced_memory_bytes": peak,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark P&ID-Agent large drawing exports")
    parser.add_argument(
        "--counts",
        nargs="+",
        type=int,
        default=[500, 1000, 2500, 5000],
        help="Element counts to benchmark",
    )
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--output", choices=["json", "jsonl"], default="json")
    args = parser.parse_args()

    results = [benchmark(count, max(1, args.iterations)) for count in args.counts]
    if args.output == "jsonl":
        for result in results:
            print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
