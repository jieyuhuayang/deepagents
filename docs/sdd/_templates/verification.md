# Verification: _(Feature 名称)_

> Spec: [`./spec.md`](./spec.md) · Tasks: [`./tasks.md`](./tasks.md)
>
> **本文档是 feature 完成的最终凭证。** 所有 AC 必须在此手动验证通过;所有触碰的强约束必须在 §3 回归检查中确认仍生效。

## 状态

| 阶段 | 状态 | 验证日期 | 验证人 |
|---|---|---|---|
| 全部 AC 验证通过 | ☐ | | |
| 全部回归检查通过 | ☐ | | |
| 截图已附在 `./screenshots/` | ☐ | | |

---

## 0. 环境信息

| 项 | 值 |
|---|---|
| 后端启动命令 | `cd backend && source .venv/bin/activate && langgraph dev` |
| 后端端口 | `:2024` |
| 前端启动命令 | `cd frontend && yarn dev` |
| 前端端口 | `:3000` |
| 浏览器 Assistant ID | `research`(`backend/langgraph.json` 的 graph 名) |
| `.env` 必填 | `DEEPAGENTS_MODEL`、`DASHSCOPE_API_KEY`(或 OpenAI 兼容 base_url 所需的 key) |
| Node 版本 | 20.x |
| Yarn 版本 | 1.22.22 |
| 验证 git commit | _(填本次验证基于的 commit hash)_ |

---

## 1. 启动序列

按顺序执行:

```bash
# 终端 A
cd backend && source .venv/bin/activate && langgraph dev

# 等 backend 显示 "Application startup complete" 后,开终端 B
cd frontend && yarn dev

# 浏览器打开 http://localhost:3000,确认 Assistant ID 填的是 research
```

**预期**:
- [ ] backend 日志无 ERROR / 无未处理异常
- [ ] frontend 编译成功,浏览器 console 无 error
- [ ] 能发出至少一条消息得到回复(基线 smoke test)

---

## 2. AC 逐条验证

### AC-1: _(从 spec.md §2 复制描述)_

**步骤**:
1. _(浏览器点哪里 / 输入什么)_
2. _(观察什么)_

**预期**:_(在此填写)_

**截图**:`./screenshots/ac-1.png`

**结果**:☐ 通过 / ☐ 不通过(备注:______)

---

### AC-2: _(从 spec.md §2 复制描述)_

**步骤**:
1. _(在此填写)_

**预期**:_(在此填写)_

**截图**:`./screenshots/ac-2.png`

**结果**:☐ 通过 / ☐ 不通过

---

### AC-3: _(同上,按 spec.md AC 数量复制)_

---

## 3. 回归检查(强约束守护)

> 凡是 spec.md §4 标记"是"的强约束,**必须**在这里有对应回归项。
> 未触碰的项也建议跑一遍,确保没有意外副作用。具体故障对照参见 [`docs/troubleshooting.md`](../../../troubleshooting.md)。

- [ ] **GenerativeUI 卡片仍渲染**:发出"调研一下 Rust async runtime",对话流中看到至少 1 张 `ResearchCard`。
- [ ] **HITL 批量审批仍工作**:主 agent 同一 step 派 ≥ 2 个 task 时,点一次 Approve 全部放行;点一次 Reject 全部拒绝。
- [ ] **ToolApprovalInterrupt 仍弹卡**:触发 `write_file` 时审批卡正常显示。
- [ ] **fetch monkey-patch 仍生效**:浏览器网络面板里 `/runs/stream` 的 body 中 `stream_mode` 不含 `"tools"`;无 422 响应。
- [ ] **DashScope 模型未被换**:`backend/agent.py` 仍是 `ChatOpenAI(base_url=...)`,`.env` 仍指向 DashScope。
- [ ] **streaming=True 未被改**:`backend/agent.py` 中 `streaming` 参数仍为 `True`。
- [ ] **未传 checkpointer**:`create_deep_agent(...)` 调用中无 `checkpointer=` 参数。
- [ ] **prompts.py 强制语序**:发出调研类提示,模型先调 `emit_research_card`,再 `write_file`(查 backend 日志或对话流顺序)。

---

## 4. 跨上游适配验证(仅当动了 frontend/)

> 仅当 spec.md §5 标记"是"时填本节;否则整节标 N/A。

- [ ] **patch 留底文件存在**:`/tmp/patches-NNN.diff` 已生成且非空。
- [ ] **既有 patch 仍在源码中**:核对 [`docs/architecture.md` §3.1](../../../architecture.md) 列出的 4-6 处 patch 仍存在(diff `git log -p` 或人工巡检对应文件)。
- [ ] **架构文档已同步**:若新增/删除 patch,`docs/architecture.md` §3.1 表已更新;若仅修改既有 patch 内部实现,确认条目描述仍准确。
- [ ] **前端 lint/format/build 通过**:`cd frontend && yarn format:check && yarn lint && yarn build` 全绿。

---

## 5. 后端单测(可选)

> 仅当 tasks.md 某任务采用单测验证时填本节。**本项目不强制单测**,但 `tools.py` / `middlewares.py` 等纯函数允许补。

| 任务 | 测试文件 | 跑法 | 结果 |
|---|---|---|---|
| T_(N)_ | `backend/tests/test_xxx.py` | `pytest backend/tests/test_xxx.py` | ☐ 通过 |

---

## 6. 截图归档

所有截图放在 `./screenshots/`,命名:
- AC 截图:`ac-N.png`(N 与 spec.md AC ID 对应)
- 回归截图:`regression-<name>.png`(例如 `regression-hitl-batch.png`)

提 PR 时把这些图附在 PR 描述里给 reviewer。
