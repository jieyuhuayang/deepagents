#!/usr/bin/env bash
# 启停 deepagents 前后端 (远程 192.168.106.114 部署用)
set -u
cmd="${1:-start}"

ROOT=/root/deepagents
BACKEND_LOG=$ROOT/backend.log
FRONTEND_LOG=$ROOT/frontend.log
BACKEND_PORT=12024
FRONTEND_PORT=13000

# 只杀我们自己启的进程，绝不动 :3000 (bisheng-openfga) 等其他业务
stop_all() {
    pkill -f "langgraph dev --host 0.0.0.0 --port ${BACKEND_PORT}"  2>/dev/null
    pkill -f "next dev .* -p ${FRONTEND_PORT}"                       2>/dev/null
    # 兜底：按工作目录精确匹配（不会误伤 /root 外的 next/node 进程）
    for pid in $(pgrep -f "/root/deepagents/(frontend|backend)" 2>/dev/null); do
        kill "$pid" 2>/dev/null
    done
    sleep 1
}

case "$cmd" in
start)
    stop_all
    cd "$ROOT/backend"
    source .venv/bin/activate
    setsid nohup langgraph dev --host 0.0.0.0 --port ${BACKEND_PORT} --no-browser \
        < /dev/null > "$BACKEND_LOG" 2>&1 &
    cd "$ROOT/frontend"
    setsid nohup npm run dev -- -H 0.0.0.0 -p ${FRONTEND_PORT} \
        < /dev/null > "$FRONTEND_LOG" 2>&1 &
    sleep 1
    echo "started; tailing logs (Ctrl-C to detach)"
    ;;
stop)
    stop_all
    echo "stopped"
    ;;
status)
    echo "=== procs ==="
    ps -ef | grep -E "langgraph dev|next dev|next-server" | grep -v grep || echo "(no procs)"
    echo "=== ports ==="
    ss -ltn 2>/dev/null | grep -E ":(${BACKEND_PORT}|${FRONTEND_PORT})\b" || echo "(no listeners on ${BACKEND_PORT}/${FRONTEND_PORT})"
    ;;
logs)
    tail -n 50 "$BACKEND_LOG" "$FRONTEND_LOG"
    ;;
*)
    echo "usage: $0 {start|stop|status|logs}"
    exit 1
    ;;
esac
