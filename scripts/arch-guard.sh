#!/bin/bash
# arch-guard.sh — deepagents L0 实时架构守卫
#
# 两种调用方式:
#   1. 手动 / pytest 镜像参考:  bash scripts/arch-guard.sh <file_path>
#   2. PostToolUse hook(无参): 从 stdin 读 Claude Code 传入的 JSON,
#      取 .tool_input.file_path(见 .claude/settings.json)。
#
# 行为:无违规完全静默(exit 0);命中红线把 ⚠️ 打到 stderr 并 exit 2
#       —— PostToolUse 下 exit 2 会把 stderr 反馈给 Claude 但【不阻断】工具
#       (工具已执行完)。是提醒不是阻断,grep 启发式可能误报,最终由人判断。
#
# 守护 CLAUDE.md §强约束 中【可机检的 5 条 + prompts 语序】:
#   1. GenerativeUIMiddleware 不能删        (agent.py)
#   2. LLM provider 锁 ChatOpenAI + DashScope(agent.py)
#   3. streaming=True 不改回 False          (agent.py)
#   4. 不引入 MemorySaver(checkpointer 由 server lifespan 注入)(agent.py)
#   5. useChat.ts fetch monkey-patch 不删    (frontend useChat.ts)
#   + prompts.py 强制语序(emit_research_card)未弱化
#
# 无法 grep 的 3 条(前端 patch 留底、HITL 全 approve/reject 语义、其它)靠
# spec.md §4 矩阵 + /code-review 人工守。同组不变量也镜像在
# backend/tests/test_arch_invariants.py(pre-PR / CI 执行点)。
# 注意:本脚本用 basename/后缀匹配,任意 worktree 根目录可独立运行。

# ── 取被改文件路径:优先 $1(手动/测试),否则从 stdin JSON 取 ───────────────
FILE="$1"
if [ -z "$FILE" ] && [ ! -t 0 ]; then
    # hook 模式:stdin 是 PostToolUse JSON,提取 .tool_input.file_path
    FILE="$(python3 -c 'import sys,json;
try:
    print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))
except Exception:
    print("")' 2>/dev/null)"
fi

[ -z "$FILE" ] && exit 0
[ ! -f "$FILE" ] && exit 0

VIOL=0
violation() {
    echo "⚠️  [arch-guard] VIOLATION: $1" >&2
    echo "    详见 CLAUDE.md §强约束 / docs/architecture.md。这是提醒,非阻断——请确认是否有意为之。" >&2
    VIOL=1
}

# ── backend/agent.py:LLM provider / middleware / streaming / checkpointer ─────
if [[ "$FILE" == *"backend/agent.py" ]]; then
    grep -q "GenerativeUIMiddleware" "$FILE" \
        || violation "agent.py 不再含 GenerativeUIMiddleware —— 删了 push_ui_message 会被默默丢弃(§2.2)"

    if ! grep -q "ChatOpenAI" "$FILE" || ! grep -qi "dashscope" "$FILE"; then
        violation "agent.py 的 LLM 不再是 ChatOpenAI + DashScope base_url(§2.1)"
    fi
    if grep -q "init_chat_model(" "$FILE"; then
        violation "agent.py 出现 init_chat_model() —— provider registry 指不到 DashScope(§2.1)"
    fi

    if grep -Eq "streaming[[:space:]]*=[[:space:]]*False" "$FILE"; then
        violation "agent.py 出现 streaming=False —— 现代模型支持 tools+stream,不要改回(§2.1)"
    fi

    if grep -q "MemorySaver" "$FILE"; then
        violation "agent.py 引入 MemorySaver —— checkpointer 应由 server.py lifespan 注入,勿在此硬塞(§强约束 #3)"
    fi
fi

# ── backend/prompts.py:强制语序(先 emit_research_card 再 write_file) ────────
if [[ "$FILE" == *"backend/prompts.py" ]]; then
    grep -q "emit_research_card" "$FILE" \
        || violation "prompts.py 不再提 emit_research_card —— 强制语序疑似弱化,模型会跳过卡片直接写文件(troubleshooting §2)"
fi

# ── frontend useChat.ts:stream_mode 'tools' 过滤 fetch monkey-patch ──────────
if [[ "$FILE" == *"hooks/useChat.ts" ]]; then
    if ! grep -q "window.fetch" "$FILE" || ! grep -q "stream_mode" "$FILE"; then
        violation "useChat.ts 的 fetch monkey-patch(过滤 stream_mode \"tools\")疑似被删 —— 会触发 SDK 与 server 的 422(§3.3)"
    fi
fi

[ "$VIOL" -eq 1 ] && exit 2
exit 0
