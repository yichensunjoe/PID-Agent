import { useEffect } from "react";

const MAJOR_GRID_SIZE = 20;
const MAJOR_GRID_PATH = `M ${MAJOR_GRID_SIZE} 0 L 0 0 0 ${MAJOR_GRID_SIZE}`;

export function GridVisualCompatibility() {
  useEffect(() => {
    const apply = () => {
      const pattern = document.querySelector<SVGPatternElement>('svg[data-testid="editor-canvas"] pattern#smallGrid');
      const path = pattern?.querySelector<SVGPathElement>("path");
      if (!pattern || !path) return;
      const size = String(MAJOR_GRID_SIZE);
      if (pattern.getAttribute("width") !== size) pattern.setAttribute("width", size);
      if (pattern.getAttribute("height") !== size) pattern.setAttribute("height", size);
      if (path.getAttribute("d") !== MAJOR_GRID_PATH) path.setAttribute("d", MAJOR_GRID_PATH);
    };

    apply();
    const observer = new MutationObserver(apply);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["width", "height", "d"],
    });
    return () => observer.disconnect();
  }, []);

  return null;
}
