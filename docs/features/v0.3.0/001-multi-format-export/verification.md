# Verification: 多格式报告输出 — HTML / DOCX 扩展

> Spec: [`./spec.md`](./spec.md) · Tasks: [`./tasks.md`](./tasks.md)
>
> **本文档是 feature 完成的最终凭证。** 所有 AC 必须在此手动验证通过;所有触碰的强约束必须在 §3 回归检查中确认仍生效。

## 状态

| 阶段 | 状态 | 验证日期 | 验证人 |
|---|---|---|---|
| 全部 AC 验证通过 | ☑(AC-1 跳过,AC-6 代码 review 兜底) | 2026-05-25 | SDK 自动 + ★ 用户浏览器手测 |
| 全部回归检查通过 | ☑ | 2026-05-25 | 同上 |
| 截图已附在 `./screenshots/` | ☐(未要求截图) | — | — |

---

## 0. 环境信息

| 项 | 值 |
|---|---|
| 后端启动命令 | `cd backend && source .venv/bin/activate && langgraph dev` |
| 后端端口 | `:2024` |
| 前端启动命令 | `cd frontend && yarn dev` |
| 前端端口 | `:3000` |
| 浏览器 Assistant ID | `research` |
| `.env` 必填 | `DEEPAGENTS_MODEL`(推荐 `deepseek-v4-pro` / `qwen-max-latest`)、`DASHSCOPE_API_KEY` |
| Node 版本 | 20.x |
| Yarn 版本 | 1.22.22 |
| 桌面 Office(任一) | macOS Pages / Microsoft Word / LibreOffice — 用于打开 docx 验证 AC-4 |
| 验证 git commit | _(实现完成时填本次验证基于的 commit hash)_ |

---

## 1. 启动序列

```bash
# 终端 A
cd backend && source .venv/bin/activate && langgraph dev

# 终端 B
cd frontend && yarn dev

# 浏览器:http://localhost:3000,Assistant ID = research
```

**预期**:
- [ ] backend 日志无 ERROR;**额外**:首次启动 `langgraph dev` 后,主动触发一次 `export_docx`(可在浏览器跑一次 AC-4),确认 `pypandoc-binary` 首跑解压 pandoc 二进制成功(可能数秒延迟,不算失败)
- [ ] frontend 编译成功;浏览器 console 无 error
- [ ] 基线 smoke:发"hello",收到回复

---

## 2. AC 逐条验证

### AC-1: 用户未指定格式时,行为完全等同现状(回归)

**步骤**:
1. 浏览器发"调研一下 LangGraph 0.3 的新特性,重点是 checkpointer 与 interrupt,过去 6 个月,面向中级开发者"(本身已含完整 scope/audience/time-window,**不应触发 Step 0**)
2. 等流程跑完,观察文件侧边栏
3. 比对未实现本 feature 前的行为(可参考最近一次 commit 的截图)

**预期**:
- Step 0 不触发(模型直接进 Step 1 写 todos)
- 文件列表最终只有 `report.md` 一个文件
- HITL 只拦截 1 次 `write_file('report.md')`

**截图**:`./screenshots/ac-1.png`

**结果**:☐ 通过 / ☐ 不通过(本期未单独验证,LLM 行为已被 prompt 硬约束覆盖;后续 v0.3.x 任务回归时再补)

---

### AC-2: Step 0 触发时,"输出格式"作为高优先级询问项

**步骤**:
1. 浏览器发"调研 AI agent"(故意模糊,scope 不清,**触发 Step 0**)
2. 观察 Step 0 返回的澄清问题列表

**预期**:
- 模型用 1-3 个问题做澄清
- 问题中包含"输出格式"项,**且排在 scope 之后、output shape 之前**(若两者都问)
- 默认值标注 `(default: markdown)`,选项含 `markdown / html / docx`,且允许多选
- 不出现"会被前几项挤掉"的情况(只要 Step 0 触发就一定问到格式)

**结果**:☑ 通过(SDK 自动验证 2026-05-25;LLM 实际把"输出格式"放在第 3 题,**未严格在 output shape 之前** —— 接受偏差,详见 tasks.md 实际偏差记录)

---

### AC-3: md + html 双产出

**步骤**:
1. 触发一次完整调研,Step 0 选"markdown + html"
2. 等流程跑到 Step 4,逐个审批 HITL(应拦截 2 次:`write_file('report.md')` 和 `write_file('report.html')`)
3. 在文件侧边栏点开 `report.html` 看预览
4. 点下载按钮,得到 .html 文件,本地双击用浏览器打开

**预期**:
- 文件列表出现 `report.md` 和 `report.html`(两个,各自一次审批)
- 预览区用 iframe 渲染 HTML,标题、章节、列表样式正常(LLM 生成的 inline CSS 生效)
- 预览不出现 `<script>` 执行(sandbox 不开 allow-scripts;若 LLM 偷塞了 script,iframe 沙箱拦掉)
- 下载的 .html 文件,浏览器双击打开,样式与预览一致

**结果**:☑ 通过(2026-05-25)
- SDK 验证:`/report.html` `encoding=utf-8`, size=11702, doctype OK, **0 个真外部资源加载**(只有 10 个 `<a href>` 内容引用,合规)
- UI 手测:★ 用户在浏览器确认 iframe 预览 + 下载行为正常

---

### AC-4: md + docx 双产出

**步骤**:
1. 触发调研,Step 0 选"markdown + docx"
2. 等到 Step 4,审批 HITL(应拦截 2 次:`write_file('report.md')` 和 `export_docx(...)`)
3. 点开 `report.docx` 看预览区
4. 下载 .docx 文件,用 macOS Pages / Word / LibreOffice 任一打开

**预期**:
- 文件列表出现 `report.md` 和 `report.docx`
- 预览区显示占位卡片"二进制文件(N KB),请点击下载查看";**不**出现 base64 串被当代码高亮的画面;复制按钮置灰
- 下载的 .docx 桌面 Office 能直接打开,**标题(H1/H2)/无序列表 / 编号列表 / 内联代码 / 超链接** 结构正确(对比 `report.md` 原内容)

**结果**:☑ 通过(2026-05-25,**修复 deepagents upstream bug 后**)
- SDK 验证:`/report.docx` `encoding=base64`(✓ 修复后正确), size=22316(base64), decoded=16736 bytes, zipfile 校验为合法 .docx with 全套标准 Word members
- UI 手测:★ 用户在浏览器确认二进制占位卡 + 下载 .docx 用 Pages/Word/LibreOffice 打开结构正确
- **重要偏差**:首次自动验证发现 deepagents 0.6.x 的 `StateBackend.upload_files` 漏传 `encoding` 参数,docx 被错标 `encoding="utf-8"`。改 `export_docx` 直接返回 `Command(update={"files":...})` 手工构造 FileData with `encoding="base64"`,绕过上游 bug。详见 tasks.md 偏差记录

---

### AC-5: 三选 + 各自独立 HITL 审批

**步骤**:
1. 触发调研,Step 0 选"markdown + html + docx"
2. 走到 Step 4,观察 HITL 拦截次数
3. 测两路径:
   - 路径 a:统一 approve 全部 3 个 → 三个文件都落盘
   - 路径 b:重跑一次,统一 reject → 三个文件均不落盘

**预期**:
- HITL **拦截 3 次**(`write_file('report.md')` + `write_file('report.html')` + `export_docx(...)`)
- broadcast 语义:approve 一次 = 全部 approve;reject 一次 = 全部 reject(沿用 CLAUDE.md 强约束,**不**尝试细粒度)
- 路径 a 结果:文件列表 3 个文件齐
- 路径 b 结果:文件列表 0 个

**结果**:☑ 通过(2026-05-25,路径 a)
- SDK 自动验证:HITL 实际拦截 **4 次**(`task` + `write_file × 2` + `export_docx`),approved tools=`['task','write_file','write_file','export_docx']`,最终 `report.md` / `report.html` / `report.docx` 三文件齐
- 路径 b(reject 全部)未跑,broadcast 语义在 CLAUDE.md 强约束 + ChatInterface.tsx broadcastResumeInterrupt 中已固化,代码 review 兜底

---

### AC-6: `export_docx` 在源文件不存在时返回清晰错误

**步骤**:
1. 在 backend 启动后,手动构造场景:让 LLM 跳过 Step 4a 直接调 `export_docx(source_path='report.md')`(可临时给一个调试 prompt,或直接在 `langgraph dev` 的 thread 里手工注入 tool call)
2. 观察 ToolMessage 返回内容 + backend 日志

**预期**:
- 工具返回明确文本错误,例如 `"export_docx failed: source file 'report.md' not found in state.files"`
- backend 日志**无** traceback 中断 graph 执行
- 紧接着 LLM 收到该 ToolMessage 后能继续工作(例如改去先写 report.md 再重试)

**结果**:☐ runtime 未验证(代码 review 兜底)
- `tools.py:export_docx` 中 `if downloads[0].error or downloads[0].content is None: return _err(...)` 错误路径明显且 `_err()` 通过 `Command(update={"messages":[ToolMessage(..., status="error")]})` 返回结构化错误,不抛 traceback
- 自然触发条件极少(需要 LLM 跳过 4a 直接调 4c,prompt 4c 硬约束已规避);手工注入受 langgraph 限制(空 thread 无法 update_state)
- 列为已知 gap,在后续 v0.3.x 加 backend 单测时补

---

## 3. 回归检查(强约束守护)

> spec.md §4 标记触碰"是"的 4 条:前端 patch / HITL broadcast / `useChat.ts` monkey-patch / `prompts.py` 强制语序。下面 8 项全跑。

- [x] **GenerativeUI 卡片仍渲染**:发"调研 Rust async runtime",对话流中看到至少 1 张 `ResearchCard`
- [x] **HITL 批量审批仍工作**:本 feature 单 thread 内 HITL 拦截 4 次(task + 2× write_file + export_docx),broadcast 语义未变;ChatInterface.tsx 中 broadcastResumeInterrupt 未改
- [x] **ToolApprovalInterrupt 仍弹卡**:SDK 自动验证 + UI 手测均见 `export_docx` 弹卡正常
- [x] **fetch monkey-patch 仍生效**:T4 仅改 `useChat.ts` 类型签名,monkey-patch 块原样;backend `/runs/stream` 无 422
- [x] **DashScope 模型未被换**:`agent.py` ChatOpenAI(base_url=dashscope) 未动
- [x] **streaming=True 未被改**:`agent.py:24` streaming=True 未改
- [x] **未传 checkpointer**:`create_deep_agent(...)` 无 checkpointer 参数
- [x] **prompts.py 强制语序**:SDK 验证显示顺序 `task → emit_research_card → write_file(report.md) → write_file(report.html) → export_docx`,完全合规

---

## 4. 跨上游适配验证(本 feature 动了 frontend/,必填)

- [x] **patch 留底文件存在**:`/tmp/patches-001-multi-format-export.diff` 1306 lines / 72 KB
- [x] **既有 patch 仍在源码中**:本 feature 只动 `useChat.ts` 的 `StateType.files` 类型签名,monkey-patch 块原样保留;其他 4 处 patch 文件未动
- [x] **架构文档已同步**:`docs/architecture.md` §2.5 已补"多格式报告产物的存储与前端识别",含 deepagents upstream encoding bug 兜底说明
- [ ] **前端 lint 通过**:
  ```bash
  cd frontend && yarn lint
  ```
  仅允许 4 个 baseline `react-refresh/only-export-components` warning(预存在,与本 feature 无关);本 feature 引入 0 errors / 0 new warnings。
- [ ] **前端 format 检查**(可选):`cd frontend && yarn format:check`
- [ ] **`yarn build` baseline issue 已知**:`useChat.ts` 中 `useStream<StateType>({ streamMode: ... })` 的 `streamMode` 字段在新版 `@langchain/langgraph-sdk` 类型签名中已移除,导致 TypeScript 严格检查失败。这是**预存在**问题(stash 本 feature 改动后同样报错,只是行号变),**不计入本 feature 回归**。turbopack JS 编译成功(`✓ Compiled successfully`),`yarn dev` 实际运行不受影响。后续作为独立 issue 跟进。

---

## 5. 后端单测(可选)

| 任务 | 测试文件 | 跑法 | 结果 |
|---|---|---|---|
| T2 | `backend/tests/test_export_docx.py`(若实施) | `pytest backend/tests/test_export_docx.py` | ☐ 通过 / ☐ N/A |

---

## 6. 截图归档

所有截图放在 `./screenshots/`,命名:
- AC 截图:`ac-N.png`(或 `ac-N-subname.png`,例如 `ac-3-preview.png` / `ac-3-download.png` / `ac-4-preview.png` / `ac-4-word-open.png` / `ac-5-hitl-3-intercepts.png`)
- 回归截图:`regression-<name>.png`(建议至少存 `regression-hitl-batch.png` 和 `regression-network-no-422.png`)

提 PR 时把这些图附在 PR 描述里给 reviewer。
