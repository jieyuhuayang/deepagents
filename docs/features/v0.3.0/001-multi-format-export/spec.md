# Spec: 多格式报告输出 — HTML / DOCX 扩展

> Feature ID: `001-multi-format-export` · 版本归属: `v0.3.0` · Owner: jieyuhuayang · 创建日期: `2026-05-25`

## 状态

| 阶段 | 状态 | 备注 |
|---|---|---|
| 已起草 | ☑ | 2026-05-25 |
| 已评审(`/sdd-review spec` 通过 + ★ 用户确认) | ☑ | 2026-05-25 · 评审人 `sdd-review` + ★ 用户确认 |
| 已完成(verification.md 全绿) | ☑ | 2026-05-25 · ★ 用户在浏览器手测确认 |

---

## 1. 概述与用户故事

**Feature 描述**:在不破坏现有 markdown 报告主流程的前提下,允许用户额外要求把 Deep Research 产出的报告以 **HTML**(浏览器直接打开 / 对外分享)和 **DOCX**(线下文档协作 / 客户交付)形式输出。`report.md` 仍是基础产物 + 唯一真理来源;HTML 由 LLM 直接生成完整文档(自带 inline CSS),DOCX 由后端新工具 `export_docx` 基于 `report.md` 通过 pandoc 转换。

**Context / 来源**:用户口头需求 2026-05-25 — "现在 deepagents 的产出格式只能是 markdown,深度思考能否再扩展下,例如 word/PPT/html,规划具体方案"。经澄清确认本期只做 **HTML + DOCX**(PPT/PDF 延后);触发方式选 **Step 0 clarification 询问**;HTML 由 LLM 直接生成,不走 markdown→HTML 转换库。完整规划见 `/Users/lilu/.claude/plans/deepagents-markdown-snoopy-lemon.md`。

**用户故事**:

1. 作为研究报告使用者,我希望在调研开始时一次性指定想要的产出格式(markdown / html / docx 可多选),以便流程结束后直接拿到能在浏览器打开 / 发给同事 Word 编辑的多种文件,**不用再手动转换**。
2. 作为只需要 markdown 的轻度用户,我希望默认行为不变 — Step 0 不强行问我格式,只在我自己提到"想要 word"或类似线索时才补问,以便保持现有快速调研体验。
3. 作为审阅人,我希望每个产出文件(`report.md` / `report.html` / `report.docx`)都独立经过 HITL 审批,以便随时拒绝某个格式而不影响其他格式。

**检查点**:
- [x] 至少 1 条用户故事写明 `角色 / 能力 / 价值`
- [x] 描述里不引入新术语

---

## 2. 验收标准 (Acceptance Criteria)

| AC ID | 标准描述 | 验证方式 | verification.md 位置 |
|---|---|---|---|
| AC-1 | 用户未指定格式时,行为完全等同现状:Step 0 不再追问格式,Step 4 只产出 `report.md`(回归) | 浏览器手动:发"调研 X",Step 0 给定标准 scope,确认只有 1 个文件 `report.md` | §2.AC-1 |
| AC-2 | Step 0 clarification 触发时,把"输出格式"作为高优先级询问项(scope 之后 / output shape 之前;默认 markdown,可多选 html/docx) | 浏览器手动:发模糊请求触发 Step 0,确认问句中包含格式询问且默认值为 markdown | §2.AC-2 |
| AC-3 | 用户选 `markdown + html` → 文件列表出现 `report.md` 和 `report.html`;后者点开走 iframe 预览正常显示;下载得到 `.html`,浏览器双击能打开,排版与预览一致 | 浏览器手动 + 文件系统检查 | §2.AC-3 |
| AC-4 | 用户选 `markdown + docx` → 文件列表出现 `report.md` 和 `report.docx`;后者预览显示"二进制文件,请下载查看"占位卡片;下载得到 `.docx`,**Pages / Word / LibreOffice 任一打开后标题/列表/链接结构正确** | 浏览器手动 + 桌面 Office 打开 | §2.AC-4 |
| AC-5 | 用户选 `markdown + html + docx` 三选 → 三个文件并存,每个独立触发一次 HITL 审批;统一 approve 后三者都落盘,统一 reject 后均不落盘(沿用现有 broadcast 语义) | 浏览器手动:观察 HITL 拦截次数 = 3 | §2.AC-5 |
| AC-6 | `export_docx` 在 `report.md` 不存在时返回清晰错误给 LLM(不抛 traceback 中断 graph) | 后端注入测试:手动构造缺失场景,确认 ToolMessage 内容明确 | §2.AC-6 |

**检查点**:
- [x] 每条 AC 都有唯一 ID
- [x] 每条 AC 都可在本地浏览器 + `langgraph dev` 复现
- [x] AC 数量 6 条(在 3-7 区间)

---

## 3. 边界情况与非目标

### 3.1 边界情况

- **`report.md` 内容超 max_file_size_mb(10MB)**:深度调研极少触发,但 pandoc 转换后 docx 也受同限制。在 `export_docx` 中预校验 base64 后大小,超限返回错误给 LLM 让它截短重写。
- **LLM 在 Step 4b 写出的 HTML 含外部 CDN 链接**:违反"不依赖外部 CDN"约束。在 prompt 4b 子项目里硬性规定 inline CSS / 无外链;前端 iframe 用 `sandbox="allow-same-origin"`(不开 `allow-scripts`)防 XSS 兜底。
- **`pypandoc-binary` 在 macOS 上首次运行需要解压打包的 pandoc 二进制**:首次调用 `export_docx` 可能延迟数秒;接受,在 docstring 注明。
- **HITL 中用户拒绝其中一个 write_file**:由于 broadcast 语义是"全 approve / 全 reject"(强约束),实际拒绝任一即全部拒绝。在 AC-5 中明确这一行为,**不**尝试细粒度拒绝。
- **用户在 Step 0 自然语言回答"我要 word 版本"而非选 docx**:prompt 应能识别"word"→docx 的同义映射(在 4c 触发条件里写清)。**由 prompt 设计兜底,不进 AC 单测** — 同义词覆盖面无限,单测无法穷举,只在 prompt 里给若干常见映射示例(word / 文档 → docx;网页 / 链接形态 → html)。

### 3.2 非目标(本期不做)

- **PPTX 导出**:需要 LLM 单独提供 slide outline + `python-pptx`,复杂度大,延后到 v0.3.x 增量。
- **PDF 导出**:WeasyPrint 依赖系统 cairo/pango 库,macOS 安装折腾;延后。
- **前端"导出为..."按钮**:按需触发需要新增独立 HTTP endpoint(后端要起 FastAPI 旁路),改动过大;本期所有导出由 LLM 在工作流内调用工具完成。
- **HTML 主题可定制 / CSS 模板系统**:MVP 信任 LLM 直生成的 inline-CSS,不做模板配置。
- **细粒度 HITL**(单独 approve/reject 某个文件):受现有 broadcast 语义限制,不在本期范围。
- **文件版本管理 / 历史导出归档**:文件仍只存 langgraph state,不落本地磁盘。

**检查点**:
- [x] 边界情况包含至少 1 条"失败/异常路径"(`export_docx` 缺源文件 / 超大 / HTML 外链违规)
- [x] 非目标列出明确的、可能被误以为属于本期的事项

---

## 4. 涉及强约束

| 强约束条目 | 是否触碰 | 缓解策略 |
|---|---|---|
| `GenerativeUIMiddleware` 不能删 | ☐ 否 | 本 feature 不改 middlewares.py,中间件仍保留;新增的 `export_docx` 走标准 tool 路径,不引入新 middleware |
| LLM provider 锁 `ChatOpenAI` + DashScope | ☐ 否 | `agent.py` 中 ChatOpenAI 构造不动 |
| 不传 `checkpointer` 给 `create_deep_agent` | ☐ 否 | `agent.py` 中 create_deep_agent 调用只加 `interrupt_on` 一项,不引入 checkpointer |
| `streaming=True` 不改回 False | ☐ 否 | 不动 |
| 前端 vendored patch(详见 §5) | ☑ 是 | 详见 §5,实施 Step 6 第一动作 `git diff` 留底 |
| HITL 批量审批"全 approve / 全 reject"语义 | ☑ 是 | **保留**该语义;AC-5 明示"全部"语义,**不**尝试细粒度。新增 `export_docx` 也加入 `interrupt_on` 走相同 broadcast 路径,语义一致 |
| `useChat.ts` fetch monkey-patch 不删 | ☑ 是 | 仅在 `useChat.ts` 调整 `StateType.files` 的类型签名(从 `Record<string, string>` 放宽到 union 类型),**不**触碰 monkey-patch 代码块。改动后需在 verification.md §3 跑一次"问 Hi → 不应 422"回归 |
| `prompts.py` 强制语序不弱化 | ☑ 是 | **不弱化**现有 "MUST call `emit_research_card` before `write_file`" 等。Step 4 拆出 4a/4b/4c,但 4a 仍是 `write_file('report.md')`,且 4b/4c 同样要求 emit_research_card 已渲染。新增的语序约束 only-add,不删 / 不软化。Step 0 priority 列表**仅做顺序重排**(把"输出格式"提到第 2 位,scope 之后 / output shape 之前),原有问询项一个不删 |

**检查点**:
- [x] 凡是"是"的条目,缓解策略不为空
- [x] 触碰的条目需在 verification.md §3 加对应回归项(stream_mode 兼容性 / HITL broadcast / prompt 语序)

---

## 5. 前端 patch 影响

**是否动 `frontend/**`**:☑ 是

**预计修改的已 patch 文件**(勾选):
- [ ] `frontend/src/app/components/ChatInterface.tsx`(broadcastResumeInterrupt)— **不动**
- [ ] `frontend/src/app/components/ChatMessage.tsx`(LOCAL_UI_COMPONENTS 注入)— **不动**
- [ ] `frontend/src/app/components/ToolCallBox.tsx`(components prop)— **不动**
- [x] `frontend/src/app/hooks/useChat.ts`(fetch monkey-patch)— **只改 `StateType.files` 类型签名,monkey-patch 代码块原样保留**
- [ ] `frontend/src/app/components/generative-ui/registry.tsx` — **不动**
- [ ] `frontend/src/app/components/generative-ui/ResearchCard.tsx` — **不动**
- 其他既有 patch 文件:无

**本 feature 新增/修改的非 patch 前端文件**(不属于既有 patch,但属于本次改动):
- `frontend/src/app/types/types.ts` — 给 `FileItem` 增加 `encoding?` 可选字段(向后兼容,缺省视为 utf-8)
- `frontend/src/app/components/FileViewDialog.tsx` — 加 MIME 表 / base64 下载 / HTML iframe 预览 / 二进制占位
- `frontend/src/app/components/TasksFilesSidebar.tsx` — (可选)按扩展名换图标,纯视觉

**留底命令**(实施 Step 6 第一动作必须执行):

```bash
cd frontend && git diff > /tmp/patches-001-multi-format-export.diff
```

**对 `architecture.md` §3.1 patch 表的预期更新**:**无新增 patch**(`useChat.ts` 是改既有 patch 文件,但只动类型签名而非 monkey-patch 块本身;types.ts / FileViewDialog.tsx / TasksFilesSidebar.tsx 不属于既有 patch 列表)。需要在 `architecture.md` §2.4(渲染层)或新增小节里补一段"多格式产物的前端识别(encoding 字段 + MIME 表)",作为后续维护参考。

**检查点**:
- [x] 留底命令在 tasks.md 是第一个任务
- [x] 若新增/删除 patch,已在本节登记后续如何更新 §3.1(本期无新增 patch,但 architecture.md 需补一段说明)

---

## 6. 实现概要 & 文件清单

**实现思路**:LLM 仍以 markdown 为唯一真理来源(`report.md`),HTML 由 LLM 在 Step 4b 直接 `write_file('report.html', <完整 HTML 文档,带 inline CSS>)` —— 跳过任何 md→HTML 转换库,质量更可控。DOCX 由新工具 `export_docx` 内部读 `report.md` → 调用 `pypandoc.convert_text(..., 'docx')` → 字节流 base64 编码 → 通过 `Command(update={"files": {...: FileData(encoding="base64")}})` 写回 state(deepagents 的 `FileData` 已支持 `encoding` 字段)。前端扩展 `FileItem.encoding?` 类型,在 `FileViewDialog` 按 encoding 路由:utf-8 走现有 markdown / HTML iframe / 代码高亮分支;base64 走"二进制下载"占位 + 正确 MIME 的 Blob 下载。

**文件清单**:

| 文件 | 改动性质 | 简要说明 |
|---|---|---|
| `backend/pyproject.toml` | 修改 | 加 `pypandoc-binary` 依赖(自带 pandoc 二进制,无系统依赖) |
| `backend/tools.py` | 修改 | 新增 `export_docx(source_path, dest_path) -> Command`,用 `pypandoc` 转 + base64 编码 + Command 写回 |
| `backend/prompts.py` | 修改 | Step 0 priority 列表**把"输出格式"提到第 2 位**(scope 之后 / output shape 之前),确保高优先级问到(不会因为 1-3 个问题上限而被挤掉);Step 4 拆 4a(`report.md`,总是写)/ 4b(html,LLM 直生成,给 HTML 骨架模板)/ 4c(docx,调 `export_docx`);Step 5 终结回复列出所有产出 |
| `backend/agent.py` | 修改 | `interrupt_on` 字典加 `"export_docx": True`,沿用统一 HITL |
| `frontend/src/app/types/types.ts` | 修改 | `FileItem` 加 `encoding?: "utf-8" \| "base64"` 可选字段 |
| `frontend/src/app/hooks/useChat.ts` | 修改 | `StateType.files` 类型放宽为 `Record<string, string \| { content: string; encoding: "utf-8" \| "base64" }>`;读取处 normalize 成 `FileItem`。**monkey-patch 块原样保留** |
| `frontend/src/app/components/FileViewDialog.tsx` | 修改 | MIME 表 / base64 下载 / HTML iframe(`sandbox="allow-same-origin"`,不开 `allow-scripts`)/ 二进制占位卡片 / 二进制时禁用复制 |
| `frontend/src/app/components/TasksFilesSidebar.tsx` | 修改(可选) | 按扩展名换 lucide 图标(纯视觉) |
| `docs/architecture.md` | 修改(§2.4 或新增小节) | 补一段"多格式产物前端识别(`encoding` 字段 + MIME 表)"作为维护参考 |

**检查点**:
- [x] 文件清单与 §4-§5 标记一致
- [x] 引入新机制(后端工具产二进制 + 前端识别 base64),架构文档同步项已列出
- [x] 不出现大段代码块,长度控制在 2 屏内
