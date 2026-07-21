#!/usr/bin/env bash
set -euo pipefail

BASE_SHA=a1a9099e9a68c8f6e950699ca20c68e2b15b9c8a
BRANCH=agent/issue-41-engineering-reports
PAYLOAD_B64_SHA256=6dd8280390516f882ed7cc47d5f6cb66deaee7c2684398b7768e242a51820089
PAYLOAD_TAR_SHA256=a0cfb9e7d96e199270c0c7e32f9724e83b3f686359c11fa2221e7dea62bc7fbb

if [[ "${GITHUB_HEAD_REF:-${GITHUB_REF_NAME:-}}" != "${BRANCH}" ]]; then
  echo "Unexpected branch context" >&2
  exit 1
fi
if [[ "$(git merge-base "${BASE_SHA}" HEAD)" != "${BASE_SHA}" ]]; then
  echo "Feature branch is not based on expected main" >&2
  exit 1
fi

parts=(
  "00:4000:cc3d6c2d23358b12010967f946795c088f1c9f5a5158edd3653905794148be19"
  "01:4000:e928b5d95a4ade3b986e18f6d919572ecc92e7ed7b5640c8830297ecbf0bc061"
  "02:4000:d45f289c8c9512c2ac66bb88a70bad22bf59113f41d467192f6d5483f3fc5a8c"
  "03:4000:46fcebd3f7e82def20b19be0d1b9639f669c608a08f671d1409cc60a69951a11"
  "04:4000:87f15f8e6bb3d02bc0cca66ee58ebd5f3fa5e228a0dcc11bfb0262c7f0a36d20"
  "05:4000:05df937b25044b751b7ca0ad8ea9cb54647de2f08e275ed304eaeedc2a0a4271"
  "06:4000:e76a84341461a75f357f1b4d66cd8cf36b8a29fc04bfd1909a10522de4ee74fd"
  "07:4000:59f9c0c58bfbf4e8461632388b24feef6af9dd12723770fe486cde4c0bfaff6c"
  "08:4000:e854ce02deb6432404321fa565abf33b36db21e6d9f5ed59001b305f13c9b164"
  "09:4000:11dbe98d8acd1f8525367aafe70ada38a1b9503c5b2b425a8ff6e31dfb432058"
  "10:4000:5d53914b386efb02734e904c1b4e380e385bf574d9de101bb164a2af64b64099"
  "11:4000:1b5197043ed24554e8924bc28322562c5a8267fa3dd3ddaa7f2ad8ec3e77bac9"
  "12:4000:6e57baafac2651cb88abe4136d7e5ebcf7a771b35800722abff3019735cf141c"
  "13:4000:2bfeaa801bb011372974ae223614c7525fe32cd2d9d78136b4d0400e5cce34b1"
  "14:1928:c6bec1e23b890511f54a4352bba9045cfa4e8cc3aafb1b31de39727dc021a91c"
)
: > /tmp/issue41-current.b64
for item in "${parts[@]}"; do
  IFS=: read -r index expected_length expected_sha <<< "${item}"
  source=".github/issue41-current-${index}.b64"
  test -f "${source}"
  tr -d '\r\n' < "${source}" > "/tmp/issue41-part-${index}.b64"
  test "$(wc -c < "/tmp/issue41-part-${index}.b64")" -eq "${expected_length}"
  echo "${expected_sha}  /tmp/issue41-part-${index}.b64" | sha256sum --check --strict
  cat "/tmp/issue41-part-${index}.b64" >> /tmp/issue41-current.b64
done

test "$(wc -c < /tmp/issue41-current.b64)" -eq 57928
echo "${PAYLOAD_B64_SHA256}  /tmp/issue41-current.b64" | sha256sum --check --strict
base64 --decode /tmp/issue41-current.b64 > /tmp/issue41-current.tar.gz
test "$(wc -c < /tmp/issue41-current.tar.gz)" -eq 43446
echo "${PAYLOAD_TAR_SHA256}  /tmp/issue41-current.tar.gz" | sha256sum --check --strict

python - <<'PY2'
from pathlib import Path, PurePosixPath
import tarfile

expected = {
    "README.md",
    "backend/agentcad/api_reports.py",
    "backend/agentcad/client.py",
    "backend/agentcad/engineering_reports.py",
    "backend/agentcad/main.py",
    "backend/tests/test_client_engineering_reports.py",
    "backend/tests/test_engineering_reports.py",
    "docs/continuous-integration.md",
    "docs/engineering-reports.md",
    "frontend/e2e/engineering-reports.spec.ts",
    "frontend/src/App.tsx",
    "frontend/src/api.ts",
    "frontend/src/editor/EngineeringReportPanel.tsx",
    "frontend/src/engineeringReports.ts",
    "frontend/src/styles.css",
    "frontend/src/types.ts",
    "frontend/tests/engineeringReports.test.ts",
}
archive = Path('/tmp/issue41-current.tar.gz')
destination = Path('/tmp/issue41-extracted')
destination.mkdir(parents=True, exist_ok=True)
with tarfile.open(archive, 'r:gz') as bundle:
    members = bundle.getmembers()
    names = {member.name for member in members}
    if names != expected:
        raise SystemExit(f'payload whitelist mismatch: {sorted(names ^ expected)}')
    total = 0
    for member in members:
        path = PurePosixPath(member.name)
        if not member.isfile() or path.is_absolute() or '..' in path.parts:
            raise SystemExit(f'unsafe payload member: {member.name}')
        if member.size > 2_000_000:
            raise SystemExit(f'payload member too large: {member.name}')
        total += member.size
    if total > 8_000_000:
        raise SystemExit('payload is unexpectedly large')
    for member in members:
        target = destination / member.name
        target.parent.mkdir(parents=True, exist_ok=True)
        source = bundle.extractfile(member)
        if source is None:
            raise SystemExit(f'cannot read payload member: {member.name}')
        target.write_bytes(source.read())
Path('/tmp/issue41-permanent-paths.txt').write_text(
    '\n'.join(sorted(expected)) + '\n', encoding='utf-8'
)
PY2

while IFS= read -r path; do
  install -D -m 0644 "/tmp/issue41-extracted/${path}" "${path}"
done < /tmp/issue41-permanent-paths.txt

base_symbol_hash="$(git show "${BASE_SHA}:backend/agentcad/data/symbols.json" | sha256sum | cut -d' ' -f1)"
current_symbol_hash="$(sha256sum backend/agentcad/data/symbols.json | cut -d' ' -f1)"
test "${base_symbol_hash}" = "${current_symbol_hash}"

python - <<'PY2'
from pathlib import Path
import re

api_key = re.compile(r'sk-(?:proj-)?[A-Za-z0-9_-]{20,}')
bearer = re.compile(r'Authorization:\s*Bearer\s+[A-Za-z0-9]')
violations = []
for raw_path in Path('/tmp/issue41-permanent-paths.txt').read_text(encoding='utf-8').splitlines():
    text = Path(raw_path).read_text(encoding='utf-8')
    if api_key.search(text) or bearer.search(text):
        violations.append(raw_path)
if violations:
    raise SystemExit(f'potential credential in changed files: {violations}')
PY2

git diff --check

rm_targets=(
  .github/issue41-payload-00.b64 .github/issue41-payload-01.b64 .github/issue41-payload-02.b64 .github/issue41-payload-03.b64 .github/issue41-payload-04.b64 .github/issue41-payload-05.b64
  .github/issue41-current-00.b64 .github/issue41-current-01.b64 .github/issue41-current-02.b64 .github/issue41-current-03.b64 .github/issue41-current-04.b64 .github/issue41-current-05.b64 .github/issue41-current-06.b64 .github/issue41-current-07.b64 .github/issue41-current-08.b64 .github/issue41-current-09.b64 .github/issue41-current-10.b64 .github/issue41-current-11.b64 .github/issue41-current-12.b64 .github/issue41-current-13.b64 .github/issue41-current-14.b64
  .github/issue41-apply.sh
)
for target in "${rm_targets[@]}"; do
  if [[ -e "${target}" ]]; then
    git rm -f -- "${target}"
  fi
done
while IFS= read -r path; do
  git add -- "${path}"
done < /tmp/issue41-permanent-paths.txt

python - <<'PY2'
from pathlib import Path
import subprocess

permanent = set(Path('/tmp/issue41-permanent-paths.txt').read_text(encoding='utf-8').splitlines())
temporary = {
    *{f'.github/issue41-payload-{index:02d}.b64' for index in range(6)},
    *{f'.github/issue41-current-{index:02d}.b64' for index in range(15)},
    '.github/issue41-apply.sh',
}
staged_expected = permanent | temporary
staged = set(subprocess.check_output(['git', 'diff', '--cached', '--name-only'], text=True).splitlines())
if staged != staged_expected:
    raise SystemExit(f'staged diff whitelist mismatch: {sorted(staged ^ staged_expected)}')

final_expected = permanent | {'.github/workflows/issue41-apply.yml'}
final = set(subprocess.check_output(
    ['git', 'diff', '--cached', '--name-only', 'a1a9099e9a68c8f6e950699ca20c68e2b15b9c8a'],
    text=True,
).splitlines())
if final != final_expected:
    raise SystemExit(f'final branch whitelist mismatch: {sorted(final ^ final_expected)}')

unexpected = [
    path.as_posix() for path in Path('.github').rglob('issue41-*')
    if path.is_file() and path.as_posix() != '.github/workflows/issue41-apply.yml'
]
if unexpected:
    raise SystemExit(f'temporary files remain in worktree: {unexpected}')
PY2

git diff --cached --check
test -z "$(git status --porcelain --untracked-files=all | grep '^??' || true)"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git commit -m "feat: add engineering schedules and rule checks"
git push origin "HEAD:${BRANCH}"
