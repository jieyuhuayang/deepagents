# 部署到 192.168.106.114 (Lab 环境) — 流程规范

> 最后核实:2026-05-26。本文档基于实际 ssh 摸盘当时的状态写就;若 114 的远程配置或路径有变,以实际为准并回头更新本文。

## TL;DR(已知正确路径)

```bash
# 1) 本地 PR 已 merge 到 main 之后:
git checkout main && git pull origin main

# 2) push 到 114 的 bare repo(SQUASH 合并导致 history 分叉,必须 force):
git push lab main --force-with-lease

# 3) 114 working repo 强同步 + build + start:
ssh root@192.168.106.114 'cd /root/deepagents && \
    git stash push -u -m "deploy WIP $(date +%F-%H%M)" 2>/dev/null || true ; \
    git fetch origin && git reset --hard origin/main && \
    ./deepagents.sh build && ./deepagents.sh start'

# 4) 健康检查:
ssh root@192.168.106.114 'curl -s http://127.0.0.1:12024/ok && \
    curl -s -o /dev/null -w "frontend HTTP %{http_code}\n" http://127.0.0.1:13000/'
```

打开 `http://192.168.106.114:13000/?assistantId=research` 验证。

---

## 1. 拓扑

```
本地 macOS (你的开发机)
    │
    ├── push ──► GitHub (jieyuhuayang/deepagents)             ← 源真值 / PR review
    │
    └── push ──► ssh://root@192.168.106.114/root/repos/deepagents.git  ← 114 的 bare repo (中转)
                          │
                          │ git pull origin (114 视角的 origin 指向自己的 bare repo)
                          ▼
                  /root/deepagents/  ← 114 working repo
                          │
                          │ ./deepagents.sh build && start
                          ▼
                  backend :12024  (langgraph dev --host 0.0.0.0 --port 12024)
                  frontend :13000 (next start -p 13000)
```

**关键**:114 上 bare repo 没配 GitHub upstream(`git remote -v` 空)。所以必须**本地推 `lab` remote** 而不是寄希望于 114 直接从 GitHub 拉。

## 2. 关键资源清单

| 资源 | 位置 |
|---|---|
| GitHub 源真值 | https://github.com/jieyuhuayang/deepagents |
| 114 bare repo | `ssh://root@192.168.106.114/root/repos/deepagents.git`(`core.bare=true`,约 700K) |
| 114 working repo | `/root/deepagents/`(`origin` = 上面的 bare repo) |
| 部署脚本 | `/root/deepagents/deepagents.sh`(in-repo,跟主 branch 走) |
| Backend 日志 | `/root/deepagents/backend.log` |
| Frontend 日志 | `/root/deepagents/frontend.log` |
| Frontend 默认配置 | `/root/deepagents/frontend/.env.local`(`NEXT_PUBLIC_DEPLOYMENT_URL` + `NEXT_PUBLIC_ASSISTANT_ID`,构建期注入,免去访客手填弹窗) |
| Backend 反代路径 | `/api/langgraph/*` → `http://127.0.0.1:12024/*`(`next.config.ts` rewrites);前端 `NEXT_PUBLIC_DEPLOYMENT_URL` 建议填 `/api/langgraph`,公网/局域网访客都同 origin 走 |
| backend 端口 | **12024**(我们)— 刻意避开 :8000 之类的常见冲突 |
| frontend 端口 | **13000**(我们)— `\b` 端口边界避免和 130xx 误冲 |
| **绝不动**的端口 | **:3000 = bisheng-openfga**(memory `feedback_shared_lab_host_scope.md` 里那个"曾误杀"的服务) |
| 其他 lab 服务 | 1panel / shougang-portal 等 — 不动 |

## 3. 本地 git remote 配置(一次性)

```bash
git remote -v   # 应看到:
# origin  https://github.com/jieyuhuayang/deepagents.git (fetch/push)
# lab     ssh://root@192.168.106.114/root/repos/deepagents.git (fetch/push)

# 如果没有 lab,补一次:
git remote add lab ssh://root@192.168.106.114/root/repos/deepagents.git
```

ssh key 要先配好(`ssh root@192.168.106.114 'echo OK'` 能不输密码通)。

## 4. 标准部署流程

### Path A:走 PR + main(正式发布,推荐)

```bash
# === 本地 ===
gh pr merge <PR#> --squash --delete-branch         # 合到 GitHub main
git checkout main && git pull origin main          # 本地 main 拉到 squash commit
git push lab main --force-with-lease               # 推到 114 bare repo
#   ↑ 必须 --force-with-lease:GitHub squash 后 main 上的 commit hash 与
#     bare repo 之前的 main 不互为祖先 (history divergent)

# === 114 ===
ssh root@192.168.106.114 'cd /root/deepagents && \
    git stash push -u -m "deploy WIP $(date +%F-%H%M)" 2>/dev/null || true ; \
    git fetch origin && git reset --hard origin/main && \
    git log --oneline -3 && \
    ./deepagents.sh build && \
    ./deepagents.sh start'
```

### Path B:临时部署 feat 分支(预生产验证,不走 PR)

```bash
git push lab feat/<name>

ssh root@192.168.106.114 'cd /root/deepagents && \
    git stash push -u -m "deploy WIP" 2>/dev/null || true ; \
    git fetch origin && \
    git checkout feat/<name> && git reset --hard origin/feat/<name> && \
    ./deepagents.sh build && ./deepagents.sh start'
```

跑完验证后,记得切回 main:
```bash
ssh root@192.168.106.114 'cd /root/deepagents && \
    git checkout main && git reset --hard origin/main && \
    ./deepagents.sh build && ./deepagents.sh start'
```

### Path C:回滚到某个 commit / tag

```bash
ssh root@192.168.106.114 'cd /root/deepagents && \
    git fetch origin && \
    git reset --hard <commit-or-tag> && \
    ./deepagents.sh build && ./deepagents.sh start'
```

## 5. 健康检查

部署完跑这一组,确认服务都活着:

```bash
ssh root@192.168.106.114 '
echo "=== ports ==="
ss -ltnp 2>/dev/null | grep -E ":(12024|13000)\b"

echo "=== backend /ok ==="
curl -s http://127.0.0.1:12024/ok

echo "=== frontend HTTP ==="
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:13000/

echo "=== assistant 注册 ==="
curl -s -X POST http://127.0.0.1:12024/assistants/search \
    -H "Content-Type: application/json" -d "{\"limit\":3}" \
    | grep -oE "\"graph_id\":\"[^\"]+\"" | head -3

echo "=== backend 启动日志 ==="
grep -E "Application started up|ERROR|Traceback" /root/deepagents/backend.log | tail -5
'
```

预期:
- `/ok` 返回 `{"ok":true}`
- frontend 返回 `200`
- assistant 含 `"graph_id":"research"`
- backend 日志含 `Application started up in X.XXXs`,无 Traceback

最后跑一个端到端 smoke:

```bash
ssh root@192.168.106.114 '
TID=$(curl -s -X POST http://127.0.0.1:12024/threads -H "Content-Type: application/json" -d "{}" | grep -oE "thread_id\":\"[^\"]+\"" | cut -d"\"" -f3)
curl -s -X POST "http://127.0.0.1:12024/threads/$TID/runs/wait" \
    -H "Content-Type: application/json" \
    -d "{\"assistant_id\":\"research\",\"input\":{\"messages\":[{\"type\":\"human\",\"content\":\"帮我研究下 LLM agent\"}]},\"config\":{\"recursion_limit\":100}}" >/dev/null
curl -s "http://127.0.0.1:12024/threads/$TID" \
    | grep -oE "\"status\":\"[^\"]+\"|\"name\":\"request_clarification\"" | head -5
echo "thread URL: http://192.168.106.114:13000/?assistantId=research&threadId=$TID"
'
```

预期看到 `"status":"interrupted"` + `"name":"request_clarification"`。

## 6. 故障诊断

| 现象 | 排查 |
|---|---|
| `git push lab main` 报 non-fast-forward | 正常,GitHub squash merge 后 history 分叉。用 `--force-with-lease`(本仓库 bare repo 是 internal mirror,force 安全) |
| 114 `git reset --hard` 报"本地修改将被检出操作覆盖" | working tree 有 untracked / modified。先 `git stash push -u -m "..."` |
| backend 启不来 | `ssh ... 'tail -50 /root/deepagents/backend.log'` 看 Traceback。常见:`pyproject.toml` 加了新依赖但 venv 没装(见 §7 已知陷阱 #3) |
| frontend `next start` 启不来 | `ssh ... 'tail -50 /root/deepagents/frontend.log'`。常见:没跑过 `./deepagents.sh build`,`frontend/.next` 不存在(脚本会报 `frontend/.next 不存在,先跑 ./deepagents.sh build`) |
| 浏览器看到 frontend 但 onClick 不响应 | Next 16 turbopack HMR 在 LAN 子网下挂(见 §7 #4),确认走的是 prod mode(`next start`)而不是 dev |
| 端口被占 | `ss -ltnp \| grep -E ":(12024\|13000)\b"` 看占用 PID,如果不是我们的(语 `langgraph` / `next-server`),先确认是不是 lab 其他业务再处理 |

## 7. 已知陷阱

### 7.1 GitHub squash merge → history 分叉(必踩)

**症状**:`git push lab main` non-fast-forward。
**原因**:GitHub squash 重新生成 commit hash,bare repo 上之前的 commits 不在 GitHub main 的 history 里。
**修法**:`git push lab main --force-with-lease`(`--force-with-lease` 比 `--force` 安全一点,会先确认 remote 没被别人推过)。bare repo 是 internal mirror,丢失的 commits 内容已通过 squash commit 在 main 上。

### 7.2 114 working tree 经常 dirty

**症状**:`git checkout` / `git reset` 报本地修改冲突。
**原因**:lab 上手动 debug / `npm install` 改 lock file / pyproject 临时改 / 中途调过。
**修法**:`git stash push -u -m "..."`(`-u` 含 untracked,如 `backend/web_search.py` 这种)。stash 完后审查 stash 内容是否需要 pop,绝大多数 case 是冗余的可以最终 drop。

### 7.3 backend 新依赖需要手动装

**症状**:backend 启动 ImportError(`tavily` / `httpx` / 等)。
**原因**:`./deepagents.sh build` 只 build 前端,**不 sync backend 依赖**。
**修法**:
```bash
ssh root@192.168.106.114 'cd /root/deepagents/backend && \
    source .venv/bin/activate && \
    pip install -e . 2>&1 | tail -10'
```
然后 `./deepagents.sh start` 重启 backend。

### 7.4 Next 16 turbopack HMR 在 LAN 不稳

**症状**:浏览器看到页面但 onClick 不响应、配置弹窗不出。
**原因**:Next 16 turbopack 的 HMR WebSocket 跨子网 NAT 失败,React client manifest hydration 卡住。
**修法**:114 上**必须用 prod mode**(`next build + next start`),`deepagents.sh` 已经默认这样。**不要在 114 跑 `yarn dev` / `next dev`**。代价:代码改了要 rebuild。

### 7.5 frontend `.env.local` 没创建 → 访客被弹配置窗

**症状**:每个用户首次打开 `http://192.168.106.114:13000/` 都弹"配置 LangGraph 部署"弹窗,要手填 Deployment URL + Assistant ID。
**原因**:`frontend/src/lib/config.ts` 的 `getConfig()` 没在 localStorage 找到记录就触发弹窗。`NEXT_PUBLIC_*` 兜底逻辑只在 114 上配了 `.env.local` 且**重新 build** 之后才生效。
**修法**:
```bash
ssh root@192.168.106.114 'cat > /root/deepagents/frontend/.env.local <<EOF
NEXT_PUBLIC_DEPLOYMENT_URL=/api/langgraph
NEXT_PUBLIC_ASSISTANT_ID=research
EOF
cd /root/deepagents && ./deepagents.sh build && ./deepagents.sh start'
```
**注意**:
- `NEXT_PUBLIC_*` 是**构建期内联**到 bundle 的,改了必须重新 `next build`,不能只 restart。
- `.env.local` 被 `.gitignore`(`.env*` 规则)忽略,不入版本库,每台部署机自己配一次即可。
- `git stash push -u` 不动 ignored 文件(`-u` ≠ `-a`),所以 deploy 脚本里的 stash 不会把 `.env.local` 丢掉。
- `NEXT_PUBLIC_DEPLOYMENT_URL` 填**相对路径** `/api/langgraph`:`next.config.ts` 的 rewrites 会把这个 path 反代到本机 backend。访客通过任何 origin(公网 `110.16.193.170:50071` / 局域网 `192.168.106.114:13000`)进来都能用同一份 bundle 工作,不再依赖访客视角的 backend URL。
- 历史填法 `http://192.168.106.114:12024` 仍然兼容,但只适合所有访客都能直连内网的场景。

### 7.6 deepagents.sh 已经守好端口边界

脚本里有 3 层 stop 保护:
1. `pkill -f "langgraph dev --host 0.0.0.0 --port ${BACKEND_PORT}"` — 严格匹配启动命令
2. `pgrep -f "/root/deepagents/(frontend|backend)"` — 按工作目录精确匹配
3. `ss -ltnp | grep -E ":${port}\b"` — 按 LISTEN 端口兜底(`\b` 防 13000 匹到 130000)

**绝不动** :3000(bisheng-openfga)。已注释在脚本第 11 行。

## 8. 安全约定(shared lab host scope)

按 memory `feedback_shared_lab_host_scope.md`:

- **绝不动** lab 上 `/root/deepagents/` 范围外的进程、端口、docker
- 已知"曾误杀"前科:bisheng-openfga(`:3000`)
- 范围外的 pgrep / lsof / docker ps **read-only 可以查**,任何 kill / stop / restart **必须先问用户**
- 我们的 deploy 脚本 `deepagents.sh` 自己 enforce 这点(只杀 12024 / 13000 + `/root/deepagents/*` 路径匹配的进程)

## 9. 下次 deploy 想偷懒

`scripts/deploy-to-114.sh`(暂未存在,下个 PR 可以顺手加):

```bash
#!/usr/bin/env bash
set -euo pipefail

# 假设当前在 main 且已 pull 最新
[ "$(git branch --show-current)" = "main" ] || { echo "切到 main 再跑"; exit 1; }

git pull origin main
git push lab main --force-with-lease

ssh root@192.168.106.114 'cd /root/deepagents && \
    git stash push -u -m "deploy WIP $(date +%F-%H%M)" 2>/dev/null || true ; \
    git fetch origin && \
    git reset --hard origin/main && \
    ./deepagents.sh build && \
    ./deepagents.sh start'

echo ""
echo "=== smoke ==="
ssh root@192.168.106.114 '
curl -s http://127.0.0.1:12024/ok
echo ""
curl -s -o /dev/null -w "frontend HTTP %{http_code}\n" http://127.0.0.1:13000/
'

echo ""
echo "✓ Deployed. 验证: http://192.168.106.114:13000/?assistantId=research"
```

## 10. 改进 TODO(基础设施层)

按优先级:

1. **bare repo 加 GitHub upstream**:让 `/root/repos/deepagents.git` 配 `git remote add github https://github.com/.../deepagents.git`,然后 cron `git fetch github && git update-ref refs/heads/main refs/remotes/github/main`。这样未来不需要本地 push lab,114 自动 sync GitHub
2. **去掉 force push 需要**:如果走 GitHub merge commit(不 squash)或者 fast-forward,history 不分叉,不需要 force
3. **backend 依赖装入 deploy 脚本**:`deepagents.sh build` 可以加 backend `pip install -e .` 步骤,避免每次依赖变更要手动装
4. **加 CI**:GitHub Actions 跑 `yarn build` + `python -c "from agent import agent"`,PR 时 gate
5. **健康检查 endpoint 自动化**:把本文档 §5 的 smoke 测试封装成 `./deepagents.sh smoke`,部署后自动跑

---

**Owner / 最后维护**:LineWalker · 2026-05-26 实测 verify(摸盘出 bare repo / lab remote / port 配置)。下次部署完更新本文档的"最后核实"日期。
