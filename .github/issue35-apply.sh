#!/usr/bin/env bash
set -euo pipefail

BASE_SHA=fcb77d51120ca47a542dd15844f4d205391e70db
BRANCH=agent/issue-35-project-json-import
PAYLOAD_B64_SHA256=f28519152af78d0cf36f47f2f9acdaa7c3656bec2538ca2d18292060b43d2275
PAYLOAD_TAR_SHA256=304df62e0cea225ecf7920882ff7a2a18360a88220ee0af8a4b241e192b69b6b

if [[ "${GITHUB_HEAD_REF:-${GITHUB_REF_NAME:-}}" != "${BRANCH}" ]]; then
  echo "Unexpected branch context" >&2
  exit 1
fi
if [[ "$(git merge-base "${BASE_SHA}" HEAD)" != "${BASE_SHA}" ]]; then
  echo "Feature branch is not based on the expected main commit" >&2
  exit 1
fi

parts=(
  "00:b2c4f6845e87740794d733605030791e3df9760680fff4b847ed43b53c4a86b7"
  "01:2a6082b5a98dc79e591febe71831bd99fd4c6f4e7f258ec862d9689249573263"
  "02:d8956dad47e33d062d3d51a48d92237a8fd9f464fefd9e403503a17484953329"
  "03:96f8eec6d73d3358c3d747efa273f1f13589b64c4188a6ee4551acb3bce9a5c4"
)
: > /tmp/issue35-payload.b64
for item in "${parts[@]}"; do
  index="${item%%:*}"
  expected_sha="${item#*:}"
  source=".github/issue35-payload-${index}.b64"
  test -f "${source}"
  tr -d '\r\n' < "${source}" > "/tmp/issue35-part-${index}.b64"
  test "$(wc -c < "/tmp/issue35-part-${index}.b64")" -eq 16902
  echo "${expected_sha}  /tmp/issue35-part-${index}.b64" | sha256sum --check --strict
  cat "/tmp/issue35-part-${index}.b64" >> /tmp/issue35-payload.b64
done

test "$(wc -c < /tmp/issue35-payload.b64)" -eq 67608
echo "${PAYLOAD_B64_SHA256}  /tmp/issue35-payload.b64" | sha256sum --check --strict
base64 --decode /tmp/issue35-payload.b64 > /tmp/issue35-payload.tar.gz
echo "${PAYLOAD_TAR_SHA256}  /tmp/issue35-payload.tar.gz" | sha256sum --check --strict

python - <<'PY'
from pathlib import Path, PurePosixPath
import tarfile

expected = {
    "README.md",
    "docs/project-json-import.md",
    "backend/agentcad/project_io.py",
    "backend/agentcad/store.py",
    "backend/agentcad/service.py",
    "backend/agentcad/api_v2.py",
    "backend/agentcad/client.py",
    "backend/tests/test_project_io.py",
    "backend/tests/test_client_project_io.py",
    "frontend/src/types.ts",
    "frontend/src/api.ts",
    "frontend/src/store.ts",
    "frontend/src/App.tsx",
    "frontend/src/styles.css",
    "frontend/src/projectImport.ts",
    "frontend/tests/projectImport.test.ts",
    "frontend/e2e/project-import.spec.ts",
    "frontend/playwright.config.ts",
}
archive = Path("/tmp/issue35-payload.tar.gz")
destination = Path("/tmp/issue35-extracted")
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
Path("/tmp/issue35-permanent-paths.txt").write_text(
    "\n".join(sorted(expected)) + "\n", encoding="utf-8"
)
PY

while IFS= read -r path; do
  install -D -m 0644 "/tmp/issue35-extracted/${path}" "${path}"
done < /tmp/issue35-permanent-paths.txt

# The symbol library is explicitly outside this slice and must remain byte-identical.
git show "${BASE_SHA}:backend/agentcad/data/symbols.json" | sha256sum > /tmp/issue35-symbol-base.sha
sha256sum backend/agentcad/data/symbols.json | sed 's#  backend/agentcad/data/symbols.json#  -#' > /tmp/issue35-symbol-current.sha
base_hash="$(cut -d' ' -f1 /tmp/issue35-symbol-base.sha)"
current_hash="$(cut -d' ' -f1 /tmp/issue35-symbol-current.sha)"
test "${base_hash}" = "${current_hash}"

python - <<'PY'
from pathlib import Path
import re

api_key = re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}")
bearer = re.compile(r"Authorization:\s*Bearer\s+[A-Za-z0-9]")
violations = []
for raw_path in Path("/tmp/issue35-permanent-paths.txt").read_text(encoding="utf-8").splitlines():
    text = Path(raw_path).read_text(encoding="utf-8")
    if api_key.search(text) or bearer.search(text):
        violations.append(raw_path)
if violations:
    raise SystemExit(f"potential credential in changed files: {violations}")
PY

git diff --check
sudo apt-get update
sudo apt-get install --yes libcairo2 fonts-noto-cjk
python -m pip install --upgrade pip
python -m pip install -e ".[mcp,dev]"
ruff check backend
pytest -q

(
  cd frontend
  npm ci --no-audit --no-fund
  npx playwright install --with-deps chromium
  npm test
  npm run build
  if grep -R --binary-files=without-match -n "__PID_AGENT_E2E__" dist; then
    echo "E2E bridge leaked into the production bundle" >&2
    exit 1
  fi
  npm run build:e2e
  npx playwright test
)

rm -rf frontend/dist frontend/test-results frontend/playwright-report

git rm -f \
  .github/issue35-payload-00.b64 \
  .github/issue35-payload-01.b64 \
  .github/issue35-payload-02.b64 \
  .github/issue35-payload-03.b64 \
  .github/issue35-apply.sh
while IFS= read -r path; do
  git add -- "${path}"
done < /tmp/issue35-permanent-paths.txt

python - <<'PY'
from pathlib import Path
import subprocess

permanent = set(Path("/tmp/issue35-permanent-paths.txt").read_text(encoding="utf-8").splitlines())
staged_expected = permanent | {
    ".github/issue35-payload-00.b64",
    ".github/issue35-payload-01.b64",
    ".github/issue35-payload-02.b64",
    ".github/issue35-payload-03.b64",
    ".github/issue35-apply.sh",
}
staged = set(
    subprocess.check_output(["git", "diff", "--cached", "--name-only"], text=True).splitlines()
)
if staged != staged_expected:
    raise SystemExit(f"staged diff whitelist mismatch: {sorted(staged ^ staged_expected)}")

final_expected = permanent | {
    ".github/workflows/issue35-source-snapshot.yml",
    ".github/workflows/issue35-apply.yml",
}
final = set(
    subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "fcb77d51120ca47a542dd15844f4d205391e70db"],
        text=True,
    ).splitlines()
)
if final != final_expected:
    raise SystemExit(f"final branch whitelist mismatch: {sorted(final ^ final_expected)}")

unexpected_temp = [
    path for path in Path(".github").rglob("issue35-*")
    if path.is_file()
    and path.as_posix() not in {
        ".github/workflows/issue35-source-snapshot.yml",
        ".github/workflows/issue35-apply.yml",
    }
]
if unexpected_temp:
    raise SystemExit(f"temporary payload files remain: {unexpected_temp}")
PY

git diff --cached --check
test -z "$(git status --porcelain --untracked-files=all | grep '^??' || true)"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git commit -m "feat: add atomic JSON and project package import"
git push origin "HEAD:${BRANCH}"
