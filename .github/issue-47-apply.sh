#!/usr/bin/env bash
set -euxo pipefail

BRANCH='agent/issue-47-sqlite-recovery'
BASE_SHA='c1aee10dd701ac2f1fc2ca937bff91c4cbe10498'

git fetch --quiet --depth=1 origin main:refs/remotes/origin/main
test "$(git branch --show-current)" = "$BRANCH"
test "$(git rev-parse refs/remotes/origin/main)" = "$BASE_SHA"
test -z "$(git status --porcelain)"

echo 'ee8425b20467cff9bda1b50f58ce7a756a7fca9a9de792393b4e94ef87ef81a6  .github/issue-47.patch.gz.b64.00' | sha256sum -c -
echo '3ea3af59fca57e7d8dd0355280f72cac0594331cab67a417067fee0d0c552b16  .github/issue-47.patch.gz.b64.01' | sha256sum -c -
echo '4fc45a37d7acd1bdbd909c870b8b6d8d2ea2c7836526d620ab330df0bfa1c99e  .github/issue-47.patch.gz.b64.02' | sha256sum -c -
echo 'c7df0606e000ad47cabe164cbe7c2bb8f5a91c92574b89cf8b06623eb70d10d0  .github/issue-47.patch.gz.b64.03' | sha256sum -c -

cat .github/issue-47.patch.gz.b64.* | base64 --decode > /tmp/issue-47.patch.gz
echo '282292b6b67a8bcb5e74a32d091e52c2210541fdb92e6751a4145e708253d15e  /tmp/issue-47.patch.gz' | sha256sum -c -
gzip --decompress --stdout /tmp/issue-47.patch.gz > /tmp/issue-47.patch
echo '9f27606adabf638fe347e3539b472ee4c56d777905652fc8739c46f87d5938f0  /tmp/issue-47.patch' | sha256sum -c -

cat > /tmp/issue-47-expected-paths <<'EOF'
.gitignore
README.md
backend/agentcad/cli.py
backend/agentcad/database_recovery.py
backend/agentcad/store.py
backend/tests/test_database_recovery.py
docs/sqlite-backup-restore.md
EOF

git apply --numstat /tmp/issue-47.patch | awk '{print $3}' | LC_ALL=C sort -u > /tmp/issue-47-actual-paths
LC_ALL=C sort -u /tmp/issue-47-expected-paths -o /tmp/issue-47-expected-paths
diff -u /tmp/issue-47-expected-paths /tmp/issue-47-actual-paths
git apply --check /tmp/issue-47.patch
git apply /tmp/issue-47.patch

rm -f .github/issue-47.patch.gz.b64.*
rm -f .github/issue-47-apply.sh

git diff --check
PYTHONDONTWRITEBYTECODE=1 python -m compileall -q backend
git diff --exit-code refs/remotes/origin/main -- backend/agentcad/data/symbols.json

git add -A

# Reject generated or credential-bearing artifacts unless they are deletions of this one-time payload.
if git diff --cached --name-status | awk '$1 != "D" {print $2}' | grep -E '(^|/)(node_modules|dist|playwright-report|test-results|__pycache__)(/|$)|\.(db|sqlite|sqlite3|pidbak|trace|webm|mp4)$'; then
  echo 'unexpected generated artifact in staged changes' >&2
  exit 1
fi

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git commit -m 'storage: add SQLite migrations, backup, and atomic restore'
git push origin "HEAD:$BRANCH"
