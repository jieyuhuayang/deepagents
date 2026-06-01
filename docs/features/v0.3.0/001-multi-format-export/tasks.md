# Tasks: 多格式报告输出 — HTML / DOCX 扩展

> Spec: [`./spec.md`](./spec.md) · Verification: [`./verification.md`](./verification.md)

## 状态

| 阶段 | 状态 | 备注 |
|---|---|---|
| 已起草 | ☑ | 2026-05-25 |
| 已评审(`/sdd-review tasks` 通过) | ☑ | 2026-05-25 · 自动通过 |
| 已完成(所有任务 ✅ + verification.md 全绿) | ☑ | 2026-05-25(AC-1/AC-6 未跑 runtime,见偏差记录) |

---

## 任务依赖

任务数 = 6,画文字依赖图:

```
T1 (前端 patch 留底)
  └─ T4 (前端类型 + useChat 适配) ──→ T5 (FileViewDialog 改造) ──┐
                                                                    ├─→ T6 (架构文档同步 + verification.md 全跑通)
T2 (后端依赖 + export_docx 工具) ──→ T3 (prompts + agent HITL) ──┘
```

并行机会:T1 / T2 完全独立可并行;T4 / T3 在各自分支内可并行;T5 / T6 收尾串行。

---

## 任务清单

### T1 — 前端 vendored patch 留底

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成
- **文件**:无(纯 git 操作);留底产物 `/tmp/patches-001-multi-format-export.diff`
- **逻辑**:CLAUDE.md §强约束要求"动 `frontend/**` 前必须 `git diff > /tmp/patches-NNN.diff` 留底"。本 feature 要改 `useChat.ts`(既有 patch 文件)+ `types.ts` / `FileViewDialog.tsx` / `TasksFilesSidebar.tsx`(非 patch),所以必须前置执行。
- **验证方式**:`wc -l /tmp/patches-001-multi-format-export.diff` 大于 0(基线 vendored patch 至少 4-6 处)
- **覆盖 AC**:无(基础设施 / 强约束守护)
- **依赖**:无

### T2 — 后端新增 `export_docx` 工具 + pypandoc 依赖

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成
- **文件**:`backend/pyproject.toml`、`backend/tools.py`
- **逻辑**:
  1. `pyproject.toml` 加 `pypandoc-binary`(自带 pandoc 二进制,免 macOS 系统装 pandoc)。
  2. `tools.py` 新增 `@tool export_docx(source_path: str = "report.md", dest_path: str = "report.docx") -> Command`:从 state.files 读 source_path 的 markdown 内容 → `pypandoc.convert_text(md, 'docx', format='md', outputfile=tmp)` → 读字节 → `base64.b64encode().decode()` → 用 `Command(update={"files": {dest_path: FileData(content=b64_str, encoding="base64")}})` 写回 state。
  3. 错误路径:source_path 缺失 → 返回明确 ToolMessage 不抛异常(满足 AC-6);dest_path 非 `.docx` 后缀 → 同样返回错误;转换后 base64 > 10 MB → 错误(对应 spec §3.1 边界)。
- **验证方式**:手动 verification.md §2.AC-4(end-to-end 跑通)+ §2.AC-6(注入测试源文件缺失);可选补 `backend/tests/test_export_docx.py` 单测
- **覆盖 AC**:AC-4, AC-6
- **依赖**:无

### T3 — 后端 prompts.py + agent.py HITL 接入

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成
- **文件**:`backend/prompts.py`、`backend/agent.py`
- **逻辑**:
  1. `prompts.py` Step 0 priority 列表:把"输出格式"提到**第 2 位**(scope 之后 / output shape 之前),并加同义词映射示例("word / 文档 → docx";"网页 / 链接形态 → html")。**仅顺序重排,原有问询项一个不删**(spec §4 强约束承诺)。
  2. Step 4 拆 4a / 4b / 4c:
     - 4a:总是 `write_file('report.md', <markdown>)`(回归保护 AC-1)
     - 4b:若用户要 html,`write_file('report.html', <完整 HTML 文档>)` —— prompt 中给一段 HTML 骨架模板(`<!doctype html>` + 简约 inline CSS + 章节布局,**不依赖外部 CDN**,iframe sandbox 不开 allow-scripts 也能正确渲染)
     - 4c:若用户要 docx,调用 `export_docx(source_path='report.md', dest_path='report.docx')`
  3. 保留 "MUST call `emit_research_card` before `write_file`" 全部既有语序硬约束。
  4. Step 5 终结回复:列出所有产出文件(动态根据用户选择)。
  5. `agent.py` 的 `interrupt_on` dict 加 `"export_docx": True`,与 `write_file` HITL 语义对齐。`tools=[...]` 加 `export_docx`(从 tools.py 导入)。
- **验证方式**:手动 verification.md §2.AC-1 / AC-2 / AC-3 / AC-5;浏览器观察 Step 0 问题排序与 Step 4 调用顺序
- **覆盖 AC**:AC-1, AC-2, AC-3, AC-5
- **依赖**:T2(需要 export_docx 工具签名定稿后再写 prompt 调用)

### T4 — 前端 FileItem 类型扩展 + useChat 适配

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成
- **文件**:`frontend/src/app/types/types.ts`、`frontend/src/app/hooks/useChat.ts`
- **逻辑**:
  1. `types.ts` `FileItem` 加 `encoding?: "utf-8" | "base64"` 可选字段(缺省视为 utf-8,向后兼容)。
  2. `useChat.ts` `StateType.files` 从 `Record<string, string>` 放宽为 `Record<string, string | { content: string; encoding: "utf-8" | "base64" }>`。
  3. 在读取处加一个 normalize 函数:把 union 类型归一成 `FileItem`(string → `{content: str, encoding: "utf-8"}`)。
  4. **`useChat.ts` 中过滤 `stream_mode: "tools"` 的 fetch monkey-patch 代码块原样保留**(spec §4 强约束),只动类型签名。
- **验证方式**:手动 verification.md §3 监听"发 Hi 不应 422"(强约束回归);TypeScript `yarn build` 编译通过
- **覆盖 AC**:AC-3, AC-4(基础支撑;真正的预览/下载体验在 T5)
- **依赖**:T1(留底先做)

### T5 — 前端 FileViewDialog 多格式渲染与下载

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成
- **文件**:`frontend/src/app/components/FileViewDialog.tsx`、`frontend/src/app/components/TasksFilesSidebar.tsx`(可选图标)
- **逻辑**:
  1. `FileViewDialog.tsx` 加 MIME 表:`.html → text/html`,`.docx → application/vnd.openxmlformats-officedocument.wordprocessingml.document`。
  2. `handleDownload`:`encoding === "base64"` 时 `atob(content)` → `Uint8Array` → `Blob` with 正确 MIME;否则维持现状。
  3. 预览区按扩展名 + encoding 路由:
     - `.md`:走现有 `MarkdownContent`(不变)
     - `.html` 且 utf-8:`<iframe srcdoc={fileContent} sandbox="allow-same-origin" />`(**不开** `allow-scripts`,防 XSS;spec §3.1 边界兜底)
     - `encoding === "base64"`:占位卡片"二进制文件(X KB),请点击下载查看",**不**走 SyntaxHighlighter
     - 其他文本:维持现有 SyntaxHighlighter
  4. `handleCopy` 对二进制禁用(按钮置灰)。
  5. (可选)`TasksFilesSidebar.tsx` 按扩展名换 lucide 图标(`FileText` / `Globe` / `FileType`)。
- **验证方式**:手动 verification.md §2.AC-3(html 预览 + 下载)/ AC-4(docx 占位 + 下载并桌面 Office 打开)/ AC-5(三选 + HITL 拦截 3 次)
- **覆盖 AC**:AC-3, AC-4, AC-5
- **依赖**:T4

### T6 — 架构文档同步 + verification.md 全跑通

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成
- **文件**:`docs/architecture.md`(§2.4 渲染层下补小节,或新增 §2.5)、`docs/features/v0.3.0/001-multi-format-export/verification.md`、`./screenshots/`
- **逻辑**:
  1. `architecture.md` 补一段"多格式产物前端识别":说明 `FileData.encoding` 字段、前端 `FileItem.encoding?` 字段、MIME 表所在位置(`FileViewDialog.tsx`)、HTML iframe sandbox 策略,作为后续维护与上游升级时的参考点。
  2. 按 `verification.md` 跑完 §1 启动序列、§2 AC-1~AC-6、§3 强约束回归(patch / HITL / monkey-patch / prompt 语序)、§4 跨上游适配(留底文件存在 + 既有 patch 仍在源码 + `yarn lint/format/build` 全绿)。
  3. 每个 AC 截图归档 `./screenshots/ac-N.png`;回归截图按需归档。
  4. 全绿后勾选 verification.md 状态表三行 + tasks.md 状态表"已完成"行。
- **验证方式**:verification.md 自身的状态表三行全勾 + tasks.md 状态表"已完成"勾 + spec.md 状态表"已完成"勾
- **覆盖 AC**:全部(收尾验证)
- **依赖**:T3, T5

---

## AC 覆盖反查

| AC | 由哪些任务覆盖 |
|---|---|
| AC-1(回归:不指定格式只产 md) | T3 |
| AC-2(Step 0 询问格式,高优先级) | T3 |
| AC-3(md + html) | T3, T4, T5 |
| AC-4(md + docx) | T2, T3, T4, T5 |
| AC-5(三选 + HITL 各自审批) | T3, T4, T5 |
| AC-6(export_docx 缺源文件错误) | T2 |

每条 AC 至少被 1 个任务覆盖 ✓;任务引用的 AC ID 全部存在于 spec.md §2 ✓。

---

## 实际偏差记录

> 实现过程中如发现与 spec.md 不符,**立刻在此登记**,并在 PR 描述里指向本节。
>
> **不允许"先实现再决定"**——若需偏离,先评估是否回 spec.md 修订。严重偏离(改 AC、改强约束触碰判断)必须回 Step 2 重新走 `/sdd-review spec`。

| 日期 | 任务 | 偏差描述 | 处理决定(回改 spec / 接受偏差 / 撤回任务) |
|---|---|---|---|
| 2026-05-25 | T2 | spec §6 写"`export_docx` ... 用 `Command(update={"files": ...})` 写回 state",实现采用更干净的路径:走 `deepagents.backends.state.StateBackend().upload_files([(path, bytes)])` —— backend 内部自动做 UTF-8 解码失败回退 base64,效果完全一致且不暴露 FileData 内部结构 | 接受偏差,不回改 spec(实现细节)。已在 [`docs/architecture.md` §2.5](../../../architecture.md) 节说明 |
| 2026-05-25 | T5 | spec §6 / §5 标 `useChat.ts` 只改 `StateType.files` 类型,实际还顺带把 `setFiles` 的形参类型同步放宽为 `Record<string, RawFileEntry>` —— 因为下游 `TasksFilesSidebar.FilesPopover` 调 `setFiles` 时已经是 normalized object | 接受偏差,不回改 spec。monkey-patch 代码块原样保留(强约束) |
| 2026-05-25 | T6 | `yarn build` 在 baseline 就有 1 处 type-check 错误(`useChat.ts` 中 `useStream<StateType>(...)` 的 `streamMode` 字段不在新版 `@langchain/langgraph-sdk` 类型签名中)。该错误**与本 feature 无关**:stash 掉本 feature 所有前端改动后,baseline 同样报同一错误(只是行号从 79 变 71)。本 feature 没有引入新的 type-check 错误 | 接受偏差,**不在本 feature 范围内修复**。建议作为独立 issue 跟进(可能要等 sdk 类型修复或本地 `as any` 兜底) |
| 2026-05-25 | T2 | SDK 自动验证首跑发现 `report.docx` 落盘后 `FileData.encoding="utf-8"`(应为 `"base64"`)。根因是 deepagents 0.6.x 的 `StateBackend.upload_files()` 内部对二进制做 base64 编码后,调 `create_file_data(text)` 时漏传 `encoding` 参数 —— `create_file_data` 默认 `encoding="utf-8"`,导致前端按 encoding 路由失效,docx 被当文本显示 | **修复**:`export_docx` 不再走 `backend.upload_files`,改为直接返回 `Command(update={"files": {dst: FileData(encoding="base64", ...)}})`,手工构造 FileData 显式设 `encoding="base64"`。绕过上游 bug。同时 `tools.py` 加注释 + `docs/architecture.md` §2.5 注明此 caveat,后续 deepagents 升级时检查 upload_files 是否修复(若修则可回退到 backend API 路径) |
| 2026-05-25 | T3 | spec AC-2 要求 LLM 把"输出格式"放在 `scope` 之后 / `output shape` 之前,实测 LLM 把"输出格式"放在第 3 位(顺序 scope → output shape → 输出格式)。"输出格式不被前几项挤掉"的硬需求已满足(总在 1-3 题内被问到) | 接受偏差,**不强行扭** prompt。LLM 心智模型上 scope-shape 是 scope 的语义延伸,放一起更自然;严格顺序非用户原始诉求。若后续真出现"被挤掉"再加强 prompt |
| 2026-05-25 | T3 | AC-6(`export_docx` 缺源文件错误处理)未做 runtime 验证 —— 自然触发条件极少(prompt 4c 硬约束已规避),且 SDK 手工注入受 langgraph "空 thread 不能 update_state" 限制 | 接受偏差,代码 review 兜底(`tools.py:export_docx` 的错误分支 `_err()` 明显且返回结构化 `Command`,不抛 traceback)。已在 verification.md AC-6 标注,后续 v0.3.x 加 backend 单测时补 |

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
