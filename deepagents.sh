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
    # 自研 FastAPI server (002 起):uvicorn server:app。
    # 老的 langgraph dev 模式保留兜底 pkill,以防旧进程还在跑(本地 dev quick smoke 用)。
    pkill -f "uvicorn server:app --host 0.0.0.0 --port ${BACKEND_PORT}" 2>/dev/null
    pkill -f "langgraph dev --host 0.0.0.0 --port ${BACKEND_PORT}"     2>/dev/null
    pkill -f "next-server.*${FRONTEND_PORT}"                            2>/dev/null
    pkill -f "next start.*-p ${FRONTEND_PORT}"                          2>/dev/null
    pkill -f "next dev.*-p ${FRONTEND_PORT}"                            2>/dev/null
    # 兜底 1：按工作目录精确匹配（不会误伤 /root 外的 next/node 进程）
    for pid in $(pgrep -f "/root/deepagents/(frontend|backend)" 2>/dev/null); do
        kill "$pid" 2>/dev/null
    done
    # 兜底 2：按监听端口杀。next-server 的 process title 被 node 改写成
    # "next-server (vX.Y.Z)",命令行里既没有端口也没有 /root/deepagents 路径,
    # 上面两层 pkill / pgrep 都匹配不到。这里直接从 ss -ltnp 抓 LISTEN 端口
    # 的 PID 兜底。\b 端口边界避免 13000 误匹配 130000。
    for port in "${BACKEND_PORT}" "${FRONTEND_PORT}"; do
        for pid in $(ss -ltnp 2>/dev/null | grep -E ":${port}\b" | grep -oP 'pid=\K\d+' | sort -u); do
            kill "$pid" 2>/dev/null
        done
    done
    sleep 1
}

case "$cmd" in
start)
    stop_all
    if [ ! -d "$ROOT/frontend/.next" ]; then
        echo "frontend/.next 不存在,先跑 $0 build"; exit 1
    fi
    cd "$ROOT/backend"
    # 自研 FastAPI server(002):由 DATABASE_URL env 决定 saver(SQLite 本地 /
    # Postgres lab host)。uvicorn 默认 worker 配置足够 demo 量级,不再需要
    # langgraph dev 的 --n-jobs-per-worker。
    setsid nohup .venv/bin/uvicorn server:app --host 0.0.0.0 --port ${BACKEND_PORT} \
        < /dev/null > "$BACKEND_LOG" 2>&1 &
    cd "$ROOT/frontend"
    setsid nohup npm run start -- -H 0.0.0.0 -p ${FRONTEND_PORT} \
        < /dev/null > "$FRONTEND_LOG" 2>&1 &
    sleep 1
    echo "started (production mode); 用 $0 status 查端口"
    ;;
build)
    cd "$ROOT/frontend"
    npm run build
    ;;
stop)
    stop_all
    echo "stopped"
    ;;
status)
    echo "=== procs ==="
    ps -ef | grep -E "uvicorn server:app|langgraph dev|next-server|next start|next dev" | grep -v grep || echo "(no procs)"
    echo "=== ports ==="
    ss -ltn 2>/dev/null | grep -E ":(${BACKEND_PORT}|${FRONTEND_PORT})\b" || echo "(no listeners on ${BACKEND_PORT}/${FRONTEND_PORT})"
    ;;
logs)
    tail -n 50 "$BACKEND_LOG" "$FRONTEND_LOG"
    ;;
*)
    echo "usage: $0 {build|start|stop|status|logs}"
    exit 1
    ;;
esac
