# Tasks: 多格式报告输出 — HTML / DOCX 扩展

> Spec: [`./spec.md`](./spec.md) · Verification: [`./verification.md`](./verification.md)

## 状态

| 阶段 | 状态 | 备注 |
|---|---|---|
| 已起草 | ☑ | 2026-05-25 |
| 已评审(`/sdd-review tasks` 通过) | ☑ | 2026-05-25 · 自动通过 |
| 已完成(所有任务 ✅ + verification.md 全绿) | ☐ | — |

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

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(代码侧;最终 ✓ 待 verification.md 全绿)
- **文件**:无(纯 git 操作);留底产物 `/tmp/patches-001-multi-format-export.diff`
- **逻辑**:CLAUDE.md §强约束要求"动 `frontend/**` 前必须 `git diff > /tmp/patches-NNN.diff` 留底"。本 feature 要改 `useChat.ts`(既有 patch 文件)+ `types.ts` / `FileViewDialog.tsx` / `TasksFilesSidebar.tsx`(非 patch),所以必须前置执行。
- **验证方式**:`wc -l /tmp/patches-001-multi-format-export.diff` 大于 0(基线 vendored patch 至少 4-6 处)
- **覆盖 AC**:无(基础设施 / 强约束守护)
- **依赖**:无

### T2 — 后端新增 `export_docx` 工具 + pypandoc 依赖

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(代码侧;最终 ✓ 待 verification.md 全绿)
- **文件**:`backend/pyproject.toml`、`backend/tools.py`
- **逻辑**:
  1. `pyproject.toml` 加 `pypandoc-binary`(自带 pandoc 二进制,免 macOS 系统装 pandoc)。
  2. `tools.py` 新增 `@tool export_docx(source_path: str = "report.md", dest_path: str = "report.docx") -> Command`:从 state.files 读 source_path 的 markdown 内容 → `pypandoc.convert_text(md, 'docx', format='md', outputfile=tmp)` → 读字节 → `base64.b64encode().decode()` → 用 `Command(update={"files": {dest_path: FileData(content=b64_str, encoding="base64")}})` 写回 state。
  3. 错误路径:source_path 缺失 → 返回明确 ToolMessage 不抛异常(满足 AC-6);dest_path 非 `.docx` 后缀 → 同样返回错误;转换后 base64 > 10 MB → 错误(对应 spec §3.1 边界)。
- **验证方式**:手动 verification.md §2.AC-4(end-to-end 跑通)+ §2.AC-6(注入测试源文件缺失);可选补 `backend/tests/test_export_docx.py` 单测
- **覆盖 AC**:AC-4, AC-6
- **依赖**:无

### T3 — 后端 prompts.py + agent.py HITL 接入

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(代码侧;最终 ✓ 待 verification.md 全绿)
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

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(代码侧;最终 ✓ 待 verification.md 全绿)
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

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(代码侧;最终 ✓ 待 verification.md 全绿)
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

- **状态**:☐ 待开始 / ☐ 进行中 / ☑ 已完成(代码侧;最终 ✓ 待 verification.md 全绿)
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
