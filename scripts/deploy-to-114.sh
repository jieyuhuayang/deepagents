#!/usr/bin/env bash
# Deploy `main` to lab host 192.168.106.114.
#
# Full deployment guide & topology:  .claude/docs/deploy-114.md
#
# Preconditions:
#   - Current branch is `main` and clean working tree (or you've reviewed dirty
#     files;all uncommitted changes will be left in the working tree of the
#     lab host's stash).
#   - `lab` remote is configured (see deploy-114.md §3).
#   - ssh root@192.168.106.114 works without password.
#
# Usage:
#   ./scripts/deploy-to-114.sh

set -euo pipefail

LAB_HOST=root@192.168.106.114
LAB_DIR=/root/deepagents

c_blue() { printf '\033[1;34m%s\033[0m\n' "$*"; }
c_red()  { printf '\033[1;31m%s\033[0m\n' "$*" >&2; }
c_gray() { printf '\033[2;37m%s\033[0m\n' "$*"; }

# ── preflight ─────────────────────────────────────────────────────────
[ "$(git branch --show-current)" = "main" ] || {
    c_red "must be on main branch (current: $(git branch --show-current))"
    exit 1
}
git remote get-url lab >/dev/null 2>&1 || {
    c_red "missing 'lab' remote. add it once:"
    c_red "  git remote add lab ssh://${LAB_HOST}/root/repos/deepagents.git"
    exit 1
}

# ── pipeline ──────────────────────────────────────────────────────────
c_blue "[1/4] sync local main from GitHub origin"
git pull origin main --ff-only

c_blue "[2/4] push to lab bare repo (force-with-lease in case of GitHub squash divergence)"
git push lab main --force-with-lease

c_blue "[3/4] 114: stash WIP + reset --hard origin/main + build + start"
ssh "$LAB_HOST" "cd $LAB_DIR && \
    git stash push -u -m \"deploy WIP \$(date +%F-%H%M)\" 2>/dev/null || true ; \
    git fetch origin && \
    git reset --hard origin/main && \
    git log --oneline -3 && \
    ./deepagents.sh build && \
    ./deepagents.sh start"

c_blue "[4/4] smoke (backend /ok + frontend HTTP)"
ssh "$LAB_HOST" "
    printf '  backend  : '
    curl -s http://127.0.0.1:12024/ok
    echo
    printf '  frontend : '
    curl -s -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:13000/
    last_log=\$(grep -E 'Application started up|ERROR|Traceback' /root/deepagents/backend.log | tail -1)
    [ -n \"\$last_log\" ] && echo \"  backend log: \$last_log\"
"

c_gray ""
c_gray "✓ deployed. open: http://192.168.106.114:13000/?assistantId=research"
