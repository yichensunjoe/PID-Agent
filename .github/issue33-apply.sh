#!/usr/bin/env bash
set -euo pipefail

BASE_SHA=875227cd824685b536f16a4cbdd2b50619b940a9
PAYLOAD_SHA256=d28693c84aa5564555a39df56119814807dbff58481e84130f62f3583629d1d7
BRANCH=agent/issue-33-browser-e2e-visual

if [[ "${GITHUB_HEAD_REF:-${GITHUB_REF_NAME:-}}" != "${BRANCH}" ]]; then
  echo "Unexpected branch context" >&2
  exit 1
fi
git merge-base --is-ancestor "${BASE_SHA}" HEAD

: > /tmp/issue33-payload.b64
for index in 00 01 02 03 04 05; do
  file=".github/issue33-payload-${index}.b64"
  test -f "${file}"
  tr -d '\r\n' < "${file}" >> /tmp/issue33-payload.b64
done
test "$(wc -c < /tmp/issue33-payload.b64)" -eq 84408
base64 --decode /tmp/issue33-payload.b64 > /tmp/issue33-text.tar.gz
echo "${PAYLOAD_SHA256}  /tmp/issue33-text.tar.gz" | sha256sum --check --strict

python - <<'PY'
from pathlib import Path, PurePosixPath
import tarfile

expected = {
    ".github/workflows/ci.yml",
    ".gitignore",
    "README.md",
    "docs/browser-e2e-visual-acceptance.md",
    "docs/continuous-integration.md",
    "frontend/e2e/engineering.spec.ts",
    "frontend/e2e/fixtures.ts",
    "frontend/e2e/performance.spec.ts",
    "frontend/e2e/visual.spec.ts",
    "frontend/e2e/workspace.spec.ts",
    "frontend/package-lock.json",
    "frontend/package.json",
    "frontend/playwright.config.ts",
    "frontend/src/App.tsx",
    "frontend/src/e2eBridge.ts",
    "frontend/src/editor/EditorCanvas.tsx",
    "frontend/src/styles.css",
    "frontend/src/vite-env.d.ts",
    "frontend/vite.config.ts",
}
archive = Path("/tmp/issue33-text.tar.gz")
destination = Path("/tmp/issue33-extracted")
destination.mkdir(parents=True, exist_ok=True)
with tarfile.open(archive, "r:gz") as bundle:
    members = bundle.getmembers()
    names = {member.name for member in members}
    if names != expected:
        raise SystemExit(f"payload whitelist mismatch: {sorted(names ^ expected)}")
    total = 0
    for member in members:
        path = PurePosixPath(member.name)
        if not member.isfile() or path.is_absolute() or ".." in path.parts:
            raise SystemExit(f"unsafe payload member: {member.name}")
        if member.size > 2_000_000:
            raise SystemExit(f"payload member too large: {member.name}")
        total += member.size
    if total > 8_000_000:
        raise SystemExit("payload is unexpectedly large")
    bundle.extractall(destination, members=members)
Path("/tmp/issue33-text-paths.txt").write_text(
    "\n".join(sorted(expected)) + "\n", encoding="utf-8"
)
PY
while IFS= read -r path; do
  install -D "/tmp/issue33-extracted/${path}" "${path}"
done < /tmp/issue33-text-paths.txt

sudo apt-get update
sudo apt-get install --yes libcairo2 fonts-noto-cjk
python -m pip install --upgrade pip
python -m pip install -e ".[mcp,dev]"
(
  cd frontend
  npm ci --no-audit --no-fund
  npx playwright install --with-deps chromium
  npm run build:e2e
  npx playwright test e2e/visual.spec.ts --update-snapshots --retries=0
)

python - <<'PY'
from pathlib import Path

expected = {
    "agent-ghost-preview.png",
    "blank-editor-dark.png",
    "blank-editor-light.png",
    "bulk-properties-mixed.png",
    "command-palette.png",
    "connector-route-anchors.png",
    "engineering-drawing.png",
    "locked-element-badges.png",
    "minimap-large-zones.png",
    "multi-selection-toolbar.png",
}
directory = Path("frontend/e2e/visual.spec.ts-snapshots")
actual = {path.name for path in directory.glob("*.png")}
if actual != expected:
    raise SystemExit(f"visual baseline mismatch: {sorted(actual ^ expected)}")
PY

git diff --check
if git grep -nE 'sk-(proj-)?[A-Za-z0-9_-]{20,}' -- . ':!frontend/package-lock.json'; then
  echo "Potential API key found" >&2
  exit 1
fi
if git grep -nE 'Authorization:[[:space:]]*Bearer[[:space:]]+[A-Za-z0-9]' -- .; then
  echo "Potential bearer credential found" >&2
  exit 1
fi

rm -rf frontend/dist frontend/test-results frontend/playwright-report
git rm -f \
  .github/issue33-payload-00.b64 \
  .github/issue33-payload-01.b64 \
  .github/issue33-payload-02.b64 \
  .github/issue33-payload-03.b64 \
  .github/issue33-payload-04.b64 \
  .github/issue33-payload-05.b64 \
  .github/issue33-apply.sh \
  .github/workflows/issue33-apply.yml
rm -f .github/workflows/issue33-source-snapshot.yml
while IFS= read -r path; do
  git add -- "${path}"
done < /tmp/issue33-text-paths.txt
git add -- frontend/e2e/visual.spec.ts-snapshots/*.png

python - <<'PY'
from pathlib import Path
import subprocess

expected = {
    ".github/workflows/ci.yml",
    ".gitignore",
    "README.md",
    "docs/browser-e2e-visual-acceptance.md",
    "docs/continuous-integration.md",
    "frontend/e2e/engineering.spec.ts",
    "frontend/e2e/fixtures.ts",
    "frontend/e2e/performance.spec.ts",
    "frontend/e2e/visual.spec.ts",
    "frontend/e2e/workspace.spec.ts",
    "frontend/package-lock.json",
    "frontend/package.json",
    "frontend/playwright.config.ts",
    "frontend/src/App.tsx",
    "frontend/src/e2eBridge.ts",
    "frontend/src/editor/EditorCanvas.tsx",
    "frontend/src/styles.css",
    "frontend/src/vite-env.d.ts",
    "frontend/vite.config.ts",
}
expected.update(
    f"frontend/e2e/visual.spec.ts-snapshots/{name}"
    for name in {
        "agent-ghost-preview.png",
        "blank-editor-dark.png",
        "blank-editor-light.png",
        "bulk-properties-mixed.png",
        "command-palette.png",
        "connector-route-anchors.png",
        "engineering-drawing.png",
        "locked-element-badges.png",
        "minimap-large-zones.png",
        "multi-selection-toolbar.png",
    }
)
output = subprocess.check_output(
    ["git", "diff", "--cached", "--name-only", "875227cd824685b536f16a4cbdd2b50619b940a9"],
    text=True,
)
actual = {line for line in output.splitlines() if line}
if actual != expected:
    raise SystemExit(f"final diff whitelist mismatch: {sorted(actual ^ expected)}")
temporary = [path for path in Path(".github").rglob("issue33-*") if path.is_file()]
if temporary:
    raise SystemExit(f"temporary files remain: {temporary}")
PY

git diff --cached --check
test -z "$(git status --porcelain --untracked-files=all | grep -v '^M  \|^A  \|^D  ' || true)"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git commit -m "test: add browser E2E and visual acceptance"
git push origin "HEAD:${BRANCH}"
