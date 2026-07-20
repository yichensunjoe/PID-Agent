# Manual connector editing

The editor supports three direct connector workflows:

1. Hover or select a symbol or junction to reveal its ports. Drag from a port to another real port to create an orthogonal process connector without first choosing the connector tool.
2. Select an existing connector and drag its blue source or target handle. Release on a real port or junction to rebind the endpoint, or release in empty space to create a free endpoint.
3. Drag an internal square segment handle to adjust an existing orthogonal route.

Symbols, junctions, lines and connectors use invisible screen-sized hit targets, so selection does not require clicking the exact visible stroke. These hit targets do not change exported SVG/PNG geometry.

Locked-layer elements remain non-editable. Port and junction snapping remains active in both grid and free-coordinate modes.
