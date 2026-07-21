#!/usr/bin/env bash
set -euo pipefail

BASE_SHA=e051ec3594e0c941c2a2cb7f63519a815dfddefa
BRANCH=agent/issue-37-pdf-print-titleblock
PAYLOAD_B64_SHA256=4538d08a73d06b559198af88cf1c9daabd9414502893176316977f35a79fc168
PAYLOAD_TAR_SHA256=fcd5caf7388cb1efb9399df8f5f7f6c6077a18d87b2bb7ce08e0d5fbdf55a5c2

if [[ "${GITHUB_HEAD_REF:-${GITHUB_REF_NAME:-}}" != "${BRANCH}" ]]; then
  echo "Unexpected branch context" >&2
  exit 1
fi
if [[ "$(git merge-base "${BASE_SHA}" HEAD)" != "${BASE_SHA}" ]]; then
  echo "Feature branch is not based on the expected main commit" >&2
  exit 1
fi

parts=(
  "00:16000:4532705227b278a852638281faec5a0be4bf8fd93e51c258f45a081cdd531a7b"
  "01:16000:7a65cdd9bc1f50cc7d51b3d807bc619cd5ee8e78b9b4caff898b1b8d83a0e4b0"
  "02:13932:183dfd40f272c18c80ac7980cf0692460085223148e959236ee91a4d2039ad88"
)
: > /tmp/issue37-payload.b64
for item in "${parts[@]}"; do
  IFS=: read -r index expected_length expected_sha <<< "${item}"
  source=".github/issue37-payload-${index}.b64"
  test -f "${source}"
  tr -d '\r\n' < "${source}" > "/tmp/issue37-part-${index}.b64"
  test "$(wc -c < "/tmp/issue37-part-${index}.b64")" -eq "${expected_length}"
  echo "${expected_sha}  /tmp/issue37-part-${index}.b64" | sha256sum --check --strict
  cat "/tmp/issue37-part-${index}.b64" >> /tmp/issue37-payload.b64
done

test "$(wc -c < /tmp/issue37-payload.b64)" -eq 45932
echo "${PAYLOAD_B64_SHA256}  /tmp/issue37-payload.b64" | sha256sum --check --strict
base64 --decode /tmp/issue37-payload.b64 > /tmp/issue37-payload.tar.gz
echo "${PAYLOAD_TAR_SHA256}  /tmp/issue37-payload.tar.gz" | sha256sum --check --strict

python - <<'PY'
from pathlib import Path, PurePosixPath
import tarfile

expected = {
    "README.md",
    "backend/agentcad/api_export.py",
    "backend/agentcad/client.py",
    "backend/agentcad/main.py",
    "backend/agentcad/pdf_export.py",
    "backend/agentcad/svg.py",
    "backend/tests/test_client_pdf_export.py",
    "backend/tests/test_pdf_export.py",
    "docs/continuous-integration.md",
    "docs/pdf-print-export.md",
    "frontend/e2e/pdf-export.spec.ts",
    "frontend/src/editor/ExportPanel.tsx",
    "frontend/src/pdfExport.ts",
    "frontend/src/styles.css",
    "frontend/tests/pdfExport.test.ts",
    "pyproject.toml",
}
archive = Path("/tmp/issue37-payload.tar.gz")
destination = Path("/tmp/issue37-extracted")
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
Path("/tmp/issue37-permanent-paths.txt").write_text(
    "\n".join(sorted(expected)) + "\n", encoding="utf-8"
)
PY

while IFS= read -r path; do
  install -D -m 0644 "/tmp/issue37-extracted/${path}" "${path}"
done < /tmp/issue37-permanent-paths.txt

base_symbol_hash="$(git show "${BASE_SHA}:backend/agentcad/data/symbols.json" | sha256sum | cut -d' ' -f1)"
current_symbol_hash="$(sha256sum backend/agentcad/data/symbols.json | cut -d' ' -f1)"
test "${base_symbol_hash}" = "${current_symbol_hash}"

python - <<'PY'
from pathlib import Path
import re

api_key = re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}")
bearer = re.compile(r"Authorization:\s*Bearer\s+[A-Za-z0-9]")
violations = []
for raw_path in Path("/tmp/issue37-permanent-paths.txt").read_text(encoding="utf-8").splitlines():
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
  .github/issue37-payload-00.b64 \
  .github/issue37-payload-01.b64 \
  .github/issue37-payload-02.b64 \
  .github/issue37-apply.sh
while IFS= read -r path; do
  git add -- "${path}"
done < /tmp/issue37-permanent-paths.txt

python - <<'PY'
from pathlib import Path
import subprocess

permanent = set(Path("/tmp/issue37-permanent-paths.txt").read_text(encoding="utf-8").splitlines())
staged_expected = permanent | {
    ".github/issue37-payload-00.b64",
    ".github/issue37-payload-01.b64",
    ".github/issue37-payload-02.b64",
    ".github/issue37-apply.sh",
}
staged = set(
    subprocess.check_output(["git", "diff", "--cached", "--name-only"], text=True).splitlines()
)
if staged != staged_expected:
    raise SystemExit(f"staged diff whitelist mismatch: {sorted(staged ^ staged_expected)}")

final_expected = permanent | {".github/workflows/issue37-apply.yml"}
final = set(
    subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "e051ec3594e0c941c2a2cb7f63519a815dfddefa"],
        text=True,
    ).splitlines()
)
if final != final_expected:
    raise SystemExit(f"final branch whitelist mismatch: {sorted(final ^ final_expected)}")

unexpected_temp = [
    path for path in Path(".github").rglob("issue37-*")
    if path.is_file() and path.as_posix() != ".github/workflows/issue37-apply.yml"
]
if unexpected_temp:
    raise SystemExit(f"temporary payload files remain: {unexpected_temp}")
PY

git diff --cached --check
test -z "$(git status --porcelain --untracked-files=all | grep '^??' || true)"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git commit -m "feat: add PDF print sheets and title blocks"
git push origin "HEAD:${BRANCH}"
