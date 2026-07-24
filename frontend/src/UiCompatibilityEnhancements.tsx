import { useEffect } from "react";

function applyUiCompatibilityCopy(): void {
  document.querySelectorAll<HTMLButtonElement>(".toolbar button[title]").forEach((button) => {
    const match = button.title.match(/^(.+?) \(/);
    if (match) button.setAttribute("aria-label", match[1]);
  });

  document.querySelectorAll<HTMLButtonElement>(".right-panel-tabs button").forEach((button) => {
    if (button.textContent?.trim() === "报表/检查") {
      button.textContent = "工程报表";
      button.setAttribute("aria-label", "工程报表");
    }
  });

  document.querySelectorAll<HTMLHeadingElement>(".inspector-panel > h2").forEach((heading) => {
    if (heading.textContent?.trim() === "工程报表与规则检查") {
      heading.textContent = "工程报表";
    }
  });
}

export function UiCompatibilityEnhancements() {
  useEffect(() => {
    applyUiCompatibilityCopy();
    const observer = new MutationObserver(applyUiCompatibilityCopy);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);
  return null;
}
