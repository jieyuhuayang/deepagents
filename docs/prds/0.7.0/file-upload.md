# PRD:deepagents 项目支持「用户首查带文件上传」

> 状态:Draft · 2026-06-03 · Owner: lilu
> 关联文档:[architecture.md](../../architecture.md)([§2.2](../../architecture.md#22-状态层四字段-state-与-generative-ui-扩展) files 字段 / [§2.5](../../architecture.md) 多格式产物 FileData / [§3](../../architecture.md#3-跨上游适配的硬约束) vendored 约束) · [troubleshooting.md](../../troubleshooting.md)

## 1. Context

当前 deep-research demo **完全无法接收用户上传的文件**:

- **prompts.py 通篇没有"文件 / 附件"概念**:`read_file` / `ls` 在 "Tools You Have" 段(`prompts.py:131`)仅列了工具名,无任何使用语境。即便 `state.files` 里塞了文件,模型也不知道该读、何时读——会直接忽略。
- **后端没有上传通道**:`server.py` 只有 `POST /threads/{id}/state`(`server.py:566`)写 JSON state,没有接收文件的端点,更没有 PDF/docx 抽取能力。
- **二进制不可直接喂模型**:deepagents 的虚拟文件系统(`state.files: dict[str, FileData]`)存二进制时是 `encoding="base64"`,`read_file` 读出来是 base64 乱码(`architecture.md:214` 实证),模型无法理解。

结果:用户最自然的诉求——"基于我上传的这份 PDF 报告 / Word 文档做调研"——做不到。

deepagents 0.6.3 的虚拟文件系统本身就是为这个场景设计的 **context engineering 答案**:文件不进 prompt,只进 `state.files`;模型通过分页的 `read_file(offset, limit)` 按需拉取。本方案据此引入"首查带文件上传",**核心策略锁定为纯按需读取(offload-first)**:把文件**统一解析为 markdown**落 `state.files`,prompt 只加"如何按需读"的元指令 + 首条消息带轻量路径指针,**文件正文绝不进 prompt**。

解析结果统一用 **markdown**(而非纯文本),因为它保留标题/表格/列表结构,利于模型按结构导航定位;含图文档的图片被抽成独立文件、markdown 用 `![]()` 引用,所以**一次上传的产物是一个虚拟"文件夹"**(`index.md` + `images/`)。图片只保留供前端展示 / 未来多模态,**模型只读 markdown 文本,不读图**。

预期产出:
- 用户在聊天框可上传 PDF / docx / 纯文本,首个 query 即可"基于上传材料做调研"。
- 后端统一解析为 markdown 落 `/uploads/<name>/index.md`(含图则附 `images/`),模型用 `ls` / `read_file` 按需分页读、按源引用。
- 现有澄清逻辑、强制工具语序、HITL、前端 vendored patch **全部不破坏**。

---

## 2. 目标 / 非目标

### 目标
- G1:用户首个 query 可附带 1 个文件(PDF / docx / txt / md / csv),后端**统一解析为 markdown**,模型据此做调研并在报告中按文件名引用。
- G2:**offload-first 接入**——文件正文只进 `state.files`,prompt 与 messages 的 token 增量恒定且极小,不随对话轮次放大。
- G3:模型被明确告知"有上传文件(markdown 在 `/uploads/<name>/index.md`)、用 `read_file` 按需分页读、绝不全文入推理、不读图片文件",且 research sub-agent 也能读上传文件。
- G4b:含图文档的图片被**抽取保留**为文件(markdown `![]()` 引用),供前端展示;**模型不读图**(不引入 OCR/视觉)。
- G4:**不破坏澄清逻辑**——文件存在不作为跳过 Step 0 澄清的条件;vague query + 文件仍弹澄清卡。
- G5:不破坏 `CLAUDE.md` §强约束 8 条(尤其 #8 prompts 语序、#5 前端 vendored patch、binary FileData encoding 坑)。

### 非目标(本期不做)
- N1:**图片的语义消费**——OCR 把图内文字内联进 markdown、或换视觉模型让模型"看"图,均不做(P2 再评估)。注:图片本身会被**抽取保留为文件**(见 G4b),非目标指的是"模型理解图内容"。
- N2:**跨会话持久化文件库**(StoreBackend / 文件复用)——本期文件只活在当前 thread。
- N3:**digest / 摘要注入**——明确砍掉,与 offload-first 相悖(理由见 §5.4)。
- N4:**原始二进制留底 + 原文下载回看**——P0 只落抽取后的文本,原文不留(见 §5.2)。
- N5:多文件批量上传 + 逐文件错误反馈 UI——P0 单文件,多文件留 P1。
- N6:扫描版 PDF 的 OCR、加密 PDF 解密。

---

## 3. 核心用户故事

1. **基于 PDF 做调研**:用户上传 `行业研报2024.pdf`,首个 query 问"结合这份报告,分析该行业 2025 趋势"。模型 `ls` 看到 `/uploads/行业研报2024/index.md`,`read_file` 分页读关键章节(图表以 markdown 引用,模型据上下文文字理解),委托 sub-agent 补充报告外的最新动态,报告里按文件名引用原文。
2. **Word 文档做背景**:用户传 `需求说明.docx`,问"按这个需求调研可选技术方案"。`mammoth` 抽取保留标题/列表结构,模型据结构定位。
3. **澄清不被污染**:用户传一个文件但 query 含糊("帮我看看这个")。模型**仍按 Step 0 弹澄清卡**(问输出格式/范围),不因"有文件"就跳过澄清。
4. **offload 验证**:无论文件多大,对话 messages 里**看不到文件正文**——只有一个 `<uploaded_files>` 路径指针块;文件全文只在 `state.files`,模型按需读。
5. **抽取失败兜底**:用户传了扫描版 PDF(抽取为空),后端返回 422 + 文件名,前端提示"该文件无法提取文本",不静默落空文件。

---

## 4. 前端方案

### 4.1 聊天框上传入口

- 在 `ChatInterface.tsx` 的 form 底部 bar(参考 skills PRD 改的同一区域)发送按钮左侧加"📎 附件"按钮 + 拖拽区,接受 `.pdf` / `.docx` / `.txt` / `.md` / `.csv`,单文件 ≤ 10 MB(前端先做大小校验,后端复核)。
- 选中文件后在输入框上方显示文件 chip(文件名 + 大小 + ✕ 移除),发送前可撤销。

### 4.2 上传时机与链路(`useChat.ts`)

- 新增 `uploadFiles(threadId, files)`:`POST /threads/{id}/files`(multipart),**在 submit 首条消息之前**完成。后端抽取 + 落 `state.files` 成功后,返回落盘后的虚拟路径 + 行数/字节量级。
- `sendMessage`(`useChat.ts` 现有 `stream.submit` 入参处)在用户 content 前**拼接 `<uploaded_files>` 路径指针块**(格式见 §5.3.2),**只含元数据(路径 / 原始文件名 / 行数 / 字节量级),零正文、零预览**。
- **不碰 `useChat.ts` 的 fetch monkey-patch**(`architecture.md §3.3`);`StateType.files` 类型已是 `Record<string, RawFileEntry>`(`architecture.md:218`),抽取产物是 utf-8 文本,`TasksFilesSidebar.tsx` 的 `normalizeFileEntry()` 已能展示,无需改类型。

### 4.3 复用资产清单

| 需求 | 已有 | 文件 |
|---|---|---|
| 文件在 sidebar 展示 | ✅ `normalizeFileEntry()` 已处理 utf-8/base64 | `TasksFilesSidebar.tsx`(`architecture.md:218`) |
| 文件查看 / 下载 | ✅ `FileViewDialog` + `MIME_BY_EXT` | `FileViewDialog.tsx`(`architecture.md:221`) |
| 拖拽上传组件 | ❌ 需新增 | 参考 skills PRD 的 `FilesPopover` 拖拽模式 |
| state.files 写入端点 | ✅ `aupdate_state` 机制 | `server.py:578`(新端点同源复用) |

> **⚠️ 前端 vendored patch 留底**:`ChatInterface.tsx` / `useChat.ts` 属 `frontend/**` 已 patch 文件,实现第一步必须 `cd frontend && git diff > /tmp/patches-NNN.diff`(`CLAUDE.md:58,87`)。

---

## 5. 后端方案(Context Engineering 优先,本 PRD 重头)

### 5.1 上传链路(新增端点)

新增 **`POST /threads/{id}/files`**(multipart),**不复用 `POST /threads/{id}/state`**。理由:

- 抽取必须在服务端做(PDF/docx 解析库都在后端,前端无解析能力且不该承担);multipart 是二进制原生通道,避免前端先 base64 膨胀 33% 再走 JSON。
- 抽取有副作用、可能失败,独立端点能返回 422 + 逐文件错误详情,比 `POST /state` 的 thin checkpoint 返回更合适。
- 端点内部仍调 `agent.aupdate_state(cfg, {"files": {...}})`(与 `server.py:578` 同机制),与现有状态写入路径同源,checkpointer 持久化行为一致。

```
前端选文件
  → POST /threads/{id}/files (multipart)
  → extract.py 统一解析为 markdown(+ 抽取图片)
  → 手工构造 FileData 落 state.files["/uploads/<name>/index.md" + ".../images/*"] (aupdate_state)
  → 返回 {md_path, original_name, lines, image_count} 给前端
  → 前端 sendMessage 拼 <uploaded_files> 指针块 + 用户 query
  → 模型按 prompts 指引 ls / read_file 按需读
```

### 5.2 抽取(新增独立模块 `backend/extract.py`)

纯函数 `extract_to_markdown(filename: str, raw: bytes) -> ParseResult`,按扩展名路由。返回 **一组 FileData**(一个 markdown 主文件 + 0..N 张抽取出的图片),不是单个字符串——因为**解析结果统一为 markdown,且支持解析含图文档,产物可能是一个"文件夹"**。**放独立模块而非 `tools.py`**:抽取发生在 graph 运行**之前**(首查准备阶段),不进 LLM 工具调用循环,放 `tools.py`(都是 `@tool`)语义不符;独立模块也便于纯函数单测。

| 类型 | 库 | 说明 |
|---|---|---|
| `.pdf` | **`pymupdf4llm`**(基于 PyMuPDF) | PDF→markdown,`write_images=True` 把内嵌图片抽成 png 文件,markdown 用 `![](images/x.png)` 引用 |
| `.docx` | **`mammoth`**(纯 Python,docx→markdown) | 保留标题/列表/表格结构;用 `convert_image` handler 把内嵌图片导出为文件并写成 markdown img 引用 |
| `.md` | `bytes.decode("utf-8")` | 已是 markdown,原样保留 |
| `.txt/.csv` | `decode` + 包成 markdown | txt 原样;csv 转 markdown 表格或 fenced 代码块 |

> **图片消费策略(已定)**:图片只**抽取保留**为文件,markdown 用 `![](images/x.png)`(带 caption/alt)引用;**模型只读 markdown 文本,不读图、不做 OCR/视觉**。图片留给前端展示 + 未来多模态。故本期**不**引入 OCR(RapidOCR 等)、**不**换视觉模型(守强约束 #2)。

> ⚠️ **抽取库当前一个都没装**(`backend/.venv` Python 3.14 实测无 pymupdf4llm/mammoth/PyMuPDF/pypdf)。P0 第一个任务是把 `pymupdf4llm` + `mammoth` 加进 `backend/pyproject.toml`。`mammoth` 是纯 Python wheel;`PyMuPDF`(pymupdf4llm 的底座)**ship 预编译 wheel,无需本地编译**,pip 可直接装,但 wheel 体积较大(~20-40MB),SOCKS 代理下载需走 pip 镜像(见风险 R10)。**排除** `marker-pdf`/`unstructured`(依赖 torch 等重型 + 需联网拉模型)。

**落盘约定(文件夹结构)**:一次上传产出一个虚拟"文件夹" `/uploads/<sanitized_name>/`:

```
/uploads/<sanitized_name>/
├── index.md            ← 解析后的 markdown 主文件 (encoding="utf-8") —— 模型读这个
└── images/
    ├── img-1.png       ← 抽取的图片 (encoding="base64") —— 模型不读,前端展示
    └── img-2.png
```

- 命名 sanitize:去空格/特殊字符(避免触发 deepagents `validate_path` 拒绝)、同名加 `-2` 后缀防覆盖。markdown 内图片引用用**相对路径** `images/img-1.png`(前端渲染时按 `/uploads/<name>/` 解析;对模型无影响)。
- **每个 FileData 都手工构造**(参考 `tools.py:239` 的 `_binary_file_data`),**绝不用 `StateBackend.upload_files()`**——它对 bytes 做 base64 时漏传 `encoding`,会被默认成 utf-8(`architecture.md:214` 实证)。
  - `index.md` → `{content: <md>, encoding: "utf-8", created_at, modified_at}`
  - 图片 → `{content: <b64>, encoding: "base64", created_at, modified_at}`(**必须显式 `encoding="base64"`**,否则前端按 encoding 路由失效、图当文本)。
- **P0 不留原始二进制**:offload-first 下模型只读 markdown,原始 PDF/docx 对模型无用且占 state 体积。原文下载回看留 P2。
- **状态体积**:图片以 base64 进 state,多图文档可能逼近 10MB state 上限;抽取后对**整个文件夹总字节**做校验(见 §6 / R3),超限时降级(丢弃图片只留 markdown 文本,并提示用户)。

### 5.3 Prompt 工程(offload-first 核心,详列措辞)

**核心原则:文件正文绝不进 prompt / 首条消息,只进 `state.files`;prompt 只加"如何按需读"的元指令 + 首条消息带路径指针。**

#### 5.3.1 `ORCHESTRATOR_PROMPT` 改动(`backend/prompts.py`)

1. **Step 0 澄清语序一字不改**(`prompts.py:11-21`,强约束 #8)。文件存在**不**作为"已有 scoping signal、可跳过澄清"的条件。
2. **在 Step 0 之后、Step 1 之前新增独立小节 `# Uploaded Files`**(措辞要点):
   - "If the conversation includes an `<uploaded_files>` block, the user attached source documents. Each was parsed into **markdown** at `/uploads/<name>/index.md` in the virtual filesystem."
   - "**Do NOT treat the presence of files as a reason to skip clarification** — apply Step 0 exactly as written."
   - "**Read them on demand with `read_file`, paginated. NEVER assume their full content; NEVER paste their full text into your reasoning or into any message.** Use `ls` to list, `read_file(path, offset, limit)` to read only the slice you need."
   - "The markdown may contain image references like `![](images/x.png)`. **You cannot read those image files (they are binary); rely on the surrounding text and captions.** Do NOT call `read_file` on anything under `images/`."
   - "When delegating, **do not ask the research-agent to re-search facts already stated in an uploaded file** — point it at the `/uploads/<name>/index.md` path instead."
3. **"Tools You Have" 段给 `read_file` 补说明**(`prompts.py:131`,现仅列名):
   - "`read_file(path, offset, limit)`: read a slice of a file (default 100 lines). For uploaded files under `/uploads/`, read **only the sections you need**; do not read the whole file into context unless it is small."
4. **Step 2 委托段补一句**(`prompts.py:24-26`,不动 "Never do web search yourself"):在 `task` 的 description 里注明相关 `/uploads/...` 文件路径,让 sub-agent 自行按需读。

#### 5.3.2 首条消息路径指针格式(`useChat.ts`)

在用户 content 前拼接(**只含元数据,零正文、零预览**):

```
<uploaded_files>
- /uploads/行业研报2024/index.md  (from "行业研报2024.pdf", 1240 lines, 6 images)
</uploaded_files>

{用户原始问题}
```

要点:指向解析后的 `index.md`、行数(帮模型决定 `offset/limit` 分页)、原始文件名(报告引用用)、图片数(让模型知道有图但不必去读)。**绝不放摘要或首段预览**——一旦放预览就破坏 offload-first,且会随多轮 messages 放大。

#### 5.3.3 research sub-agent 改动

- **`agent.py:59` 给 sub-agent `tools` 加 `read_file`**(现为 `[web_search, bisheng_retrieve, think_tool]`)。否则上传文件是核心素材时,主 agent 要么自己读后转述(正文回流进 prompt,违背 offload-first),要么 sub-agent 根本碰不到。
- **`RESEARCH_SUBAGENT_PROMPT`(`prompts.py:142`)补 `read_file` 用法**:"If the task description references an `/uploads/<name>/index.md` file, use `read_file(path, offset, limit)` to read the relevant slices as a **source**, and cite it by its original filename (like a `bisheng_retrieve` document). Ignore image references (`images/*`); do not read binary image files. Do not re-search the web for facts the uploaded file already states. Read paginated; never dump the whole file."
- ⚠️ **实现期需验证**:deepagents 内置 `read_file` 如何引用给 subagent 的 `tools` 列表,以及 sub-agent 是否与主线程共享同一 StateBackend `files`(应共享,因 files 是 graph state 字段)。见风险 R6。

### 5.4 Context Engineering 取舍论证(为什么 offload-first)

| 维度 | 全文注入 | 摘要注入 | **offload-first(本方案)** |
|---|---|---|---|
| 首轮 token | 全文入 prompt,大文件直接爆 context | 需先跑一次 LLM 抽要,且丢信息 | **~0**,仅几十 token 元指令 + 指针 |
| 多轮放大 | **致命**:正文随每轮 messages 重发 ×N,成本线性爆炸 | 摘要每轮重发,小一些 | 指针块恒定小,重发成本低 |
| 推理空间 | 全文挤占 attention(lost-in-the-middle) | 可能丢模型真正需要的细节 | 按需取当下要的页,attention 聚焦 |
| 精确引用 | 有全文但被淹没 | 摘要无法精确引原文 | `read_file` 取到精确行,引用可溯源 |
| 失败模式 | context overflow → 直接报错 | 摘要遗漏 → 答非所问 | 模型可能忽略文件(见 R1,prompt+指针缓解) |

**read_file 分页配合大文件**:指针给出行数 → 模型 `read_file(limit=100)` 先扫结构 → `read_file(offset=N, limit=200)` 取目标段(deepagents `DEFAULT_READ_LIMIT=100`)。deepagents FilesystemMiddleware 还有 `tool_token_limit_before_evict`(默认 20000),超大 read 结果会被自动 evict 回 filesystem,与 offload-first 同向兜底。

---

## 6. 数据约定

- **文件夹约定**:一次上传 = 虚拟文件夹 `/uploads/<sanitized_name>/`,内含 `index.md`(必有)+ `images/*.png`(含图才有)。`/uploads/` 与产物文件(`report.md` / `report.docx`)分区。
- **FileData(两类)**:markdown → `{content, encoding:"utf-8", created_at, modified_at}`;图片 → `{content:<b64>, encoding:"base64", created_at, modified_at}`(**图片必须显式 base64**)。均手工构造(`tools.py:239` 范式),禁 `upload_files()`。
- **文件名 sanitize**:文件夹名取原文件名去扩展名,`[a-z0-9_\-]` 之外替换 `_`,同名加 `-N`;图片名 `img-{N}.png`。markdown 内图片引用用相对路径 `images/img-N.png`。
- **大小上限**:单文件原始 ≤ 10 MB(前后端双校验);解析后**整个文件夹总字节**(md + 全部图片 base64)也校验(参考 `tools.py:236` 的 `_MAX_DOCX_BYTES = 7_500_000` 量级,留 state 余量);超限**降级**:丢图只留 markdown,仍超则拒绝并提示。

---

## 7. 关键文件改动锚点

| 模块 | 文件 | 改动性质 |
|---|---|---|
| 后端 | `backend/extract.py` | **新建** `extract_to_markdown(filename, raw)->ParseResult`(一个 md FileData + N 张图片 FileData),按扩展名路由 pymupdf4llm/mammoth/decode |
| 后端 | `backend/server.py` | **新增端点** `POST /threads/{id}/files`(multipart),调 extract + `aupdate_state`(紧邻 `:566`) |
| 后端 | `backend/prompts.py` | **改 3+1 处**:Step 0 后加 `# Uploaded Files` 小节(含"不读图片文件")/ Tools 段 `read_file` 说明(`:131`)/ Step 2 委托一句(`:24-26`)/ `RESEARCH_SUBAGENT_PROMPT` 补 read_file(`:142`) |
| 后端 | `backend/agent.py` | **改 1 行**:sub-agent `tools` 加 `read_file`(`:59`) |
| 后端 | `backend/pyproject.toml` | **加依赖** `pymupdf4llm`(PDF→md+图,带 PyMuPDF) + `mammoth`(docx→md+图) |
| 前端 | `frontend/.../ChatInterface.tsx` | 上传按钮 + 拖拽 + 文件 chip — **vendored,留底** |
| 前端 | `frontend/src/app/hooks/useChat.ts` | 新增 `uploadFiles()`;`sendMessage` 拼 `<uploaded_files>` 指针块;**不碰 fetch monkey-patch** — **vendored,留底** |
| 配置 | `backend/.env.example` | (如需)上传体积/路径相关 env |
| 文档 | `docs/architecture.md` | §2.5 同步 `/uploads/` 约定 + offload-first 决策 |
| 测试 | `backend/tests/` + `frontend/e2e/` | extract 单测 + 端点测 + E2E(见 §9) |

---

## 8. 阶段拆分

### P0(MVP)
- `backend/pyproject.toml` 加 `pymupdf4llm` + `mammoth`(**第一个任务**,验证代理环境可装)。
- `extract.py`(pymupdf4llm PDF→md+图 / mammoth docx→md+图 / 纯文本包成 md)+ `POST /threads/{id}/files` 端点。
- 落文件夹 `/uploads/<name>/`(`index.md` utf-8 + `images/*.png` base64,均手工 FileData)。
- `prompts.py` 3+1 处改动(含"不读图片文件");`agent.py:59` sub-agent 加 `read_file`。
- 前端单文件上传 + 指针块。
- 范围:**单文件、≤10MB、PDF/docx/txt/md/csv;含图文档图片抽取保留(模型不读图)**。

### P1
- 多文件批量上传 + 逐文件抽取错误反馈 UI。
- 上传文件夹在 `TasksFilesSidebar` 的 `/uploads/` 分区展示;`FileViewDialog` 渲染 markdown 内 `images/` 相对引用(base64 路由已有,`architecture.md:221`)。
- `.xlsx/.pptx` 等扩展格式(评估 `markitdown` 兜底)。

### P2(按需)
- **图片语义消费**:OCR 内联 / 视觉模型读图(本期只抽取保留,见 §2 N1)。
- 跨会话持久化文件库(`StoreBackend` + `CompositeBackend` 路由)。
- 原始二进制留底 + 原文下载回看。
- **明确不做**:digest / 摘要注入(违背 offload-first,见 §5.4)。

---

## 9. 验证

**后端单测 / 接口测**:
1. `extract.py` 单测:给定 PDF/docx 字节 → 返回非空 markdown + 含图文档产出 ≥1 张 base64 图片 FileData;扫描版/损坏 PDF → 抛可捕获异常。
2. `POST /threads/{id}/files`:上传含图 PDF → 200 + `state.files` 出现 `/uploads/xxx/index.md`(`encoding="utf-8"`)+ `/uploads/xxx/images/*.png`(`encoding="base64"`);抽取失败 → 422 + 文件名;超 10MB → 拒绝;超 state 上限 → 降级丢图。

**E2E(Playwright fixture 模式,`frontend/e2e/`)**:
1. **基本链路**:上传 PDF → 首查 → 录制 SSE 回放显示模型 `ls`/`read_file index.md` → 报告引用文件名。
2. **澄清不被污染**(守护 G4):vague query + 文件 → **仍弹澄清卡**,不因有文件跳过 Step 0。
3. **offload 验证**(守护 G2):断言对话 `messages` 里**无文件正文/无图片 base64**,只有 `<uploaded_files>` 指针块。
4. **不读图守护**(守护 G3/G4b):SSE 回放中模型不对 `images/*` 调 `read_file`。

---

## 10. 兼容性 & 强约束守护

| 已有约束(`CLAUDE.md` §强约束) | 本方案如何不冲突 |
|---|---|
| #1 不删 `GenerativeUIMiddleware` | 不动 middleware 装配。 |
| #2 LLM provider 锁 ChatOpenAI + DashScope | 不动 `model`。 |
| #3 显式传 checkpointer | 新端点复用现有 `cfg` + `aupdate_state`,不动 saver 注入。 |
| #4 `streaming=True` 保留 | 不动。 |
| **#5 前端 vendored patch 留底** | `ChatInterface.tsx` / `useChat.ts` 改动前 `git diff > /tmp/patches-NNN.diff`;记入 `architecture.md §3.1` patch 表。 |
| #6 HITL 全 approve/reject | 上传不走 HITL,无影响。 |
| #7 `useChat.ts` fetch monkey-patch 不删 | 新增 `uploadFiles`,不碰 monkey-patch。 |
| **#8 prompts 语序不弱化** | Step 0 澄清语序**一字不改**,新增 `# Uploaded Files` 小节明确"文件存在不跳过澄清";`emit_research_card → write_file` 强制语序不动。改 `prompts.py` 会触发 `arch-guard.sh` + `test_arch_invariants.py`,需确认守护规则不误报(R7)。 |
| **binary FileData encoding 坑** | markdown 手工构造 `encoding="utf-8"`、**抽取的图片手工构造 `encoding="base64"`**;**绝不用 `StateBackend.upload_files()`**(`architecture.md:214`)。图片是本功能首次大量写 base64 FileData,encoding 必须显式正确,否则前端图当文本(R4)。 |

---

## 11. 关键风险

| # | 风险 | 缓解 |
|---|---|---|
| R1 | 模型忽略上传文件、不主动 `read_file` | (1) prompt 明示 `# Uploaded Files` 小节;(2) 首条消息带指针块(模型必看 messages);(3) P1 可在 think_tool 引导里加"先确认是否需读 /uploads"。 |
| R2 | PDF/docx 抽取失败(扫描版、加密、损坏) | 端点抽取空/异常 → 422 + 文件名,前端提示;不静默落空文件。 |
| R3 | 含图文档图片以 base64 进 state,多图逼近/超 10MB 上限 | 抽取后校验**文件夹总字节**(md + 全部图片,参考 `tools.py:236` `_MAX_DOCX_BYTES` 量级);超限**降级丢图只留 markdown**,仍超则拒绝并提示。 |
| R4 | 误用 `upload_files()` 或图片漏设 `encoding="base64"` → 前端图当文本 | 手工构造每个 FileData 显式设 encoding;代码评审检查不出现 `StateBackend.upload_files`;单测断言图片 FileData 的 encoding。 |
| R5 | 模型 `read_file` 不带 limit 读全文,吃光 context | prompt 明示分页;FilesystemMiddleware `tool_token_limit_before_evict=20000` 自动 evict 兜底。 |
| R6 | sub-agent 拿不到主线程 `files`(state 隔离) | 实现期验证 deepagents subagent 是否共享 StateBackend files;若隔离,改为主 agent 读后传 minimal snippet(退而求其次)。 |
| R7 | 改 `prompts.py` 触发 arch-guard 误报 #8 | 只新增不删/改现有强制语序;必要时同步更新 `arch-guard.sh` + `test_arch_invariants.py`(`CLAUDE.md:67` 四处同步)。 |
| R8 | 澄清逻辑被文件"污染"(模型因有文件跳过 Step 0) | prompt 显式"文件存在不跳过澄清";E2E 用例 2 守护(vague query + 文件 → 仍弹澄清卡)。 |
| R9 | 文件名含特殊字符过不了 `validate_path` | 抽取/落盘前 sanitize 文件名。 |
| **R10** | **抽取库需新装,SOCKS 代理环境装包失败** | `mammoth` 纯 Python;`pymupdf4llm`/`PyMuPDF` ship 预编译 wheel(无需编译)但体积大(~20-40MB),P0 第一步用 pip 国内镜像验证可装(参考项目既有 npm 镜像实践);PyMuPDF 装不上则 PDF 降级为 `pypdf`(纯文本无图)或仅支持 docx+文本 MVP。**排除** `marker-pdf`/`unstructured`(torch 重型 + 需联网拉模型)。 |
| R11 | `pymupdf4llm` markdown 质量 / 图片引用相对路径在前端渲染不正确 | 抽取产物先人工抽检几份真实 PDF;前端 `FileViewDialog` 渲染 `images/` 相对引用需按 `/uploads/<name>/` 解析(P1 实现,对模型无影响)。 |
