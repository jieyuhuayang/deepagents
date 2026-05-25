# PRD:deepagents 项目引入 Skill 能力

> 状态:Draft · 2026-05-23 · Owner: lilu
> 关联文档:[architecture.md](../architecture.md)([§2.2](../architecture.md#22-状态层四字段-state-与-generative-ui-扩展) middleware 扩展模式 / [§3](../architecture.md#3-跨上游适配的硬约束) vendored 约束) · [troubleshooting.md](../troubleshooting.md)

## 1. Context

当前 `prompts.py` 把"研究流程""强制工具语序""卡片渲染契约"等大段领域知识硬编码在主 agent 与 sub-agent 的 system prompt 里。带来两个问题:

- **常驻 token 浪费**:无论用户是否在做研究,这段流程指令每轮都进 prompt。
- **能力扩展只能改源码**:加一个"调研学术论文""生成 PPT 草稿"等新流程都得改 `prompts.py` 重启服务,普通用户无法自助扩展。

deepagents 0.6.3 已经内置 `SkillsMiddleware`,实现 Anthropic Agent Skills 规范(progressive disclosure:启动只注入 frontmatter,LLM 按需 `read_file` 读 body)。本方案把 skill 能力作为一等公民引入产品:**前端可视化挑选/管理 skill,后端按 context engineering 原则注入 prompt**,把"流程知识"从源码挪到可热插拔的 skill 包里。

预期产出:
- 用户在聊天框旁能开关 skill,在 Skills 管理页能创建/上传/编辑/删除 skill。
- 后端按白名单加载,只把激活的 skill metadata 注入 system prompt;body 走 progressive disclosure。
- `prompts.py` 里的"研究流程"逐步抽出为 `built-in-skills/deep-research/`,成为可被禁用的官方 skill。

---

## 2. 目标 / 非目标

### 目标
- G1:用户在前端能"看到、挑选、开关、上传、新建、删除"skill,体验对齐 Claude 网页版。
- G2:支持 markdown skill(纯指令/参考资料)+ 静态资源 + interpreter skill(可执行代码)。
- G3:skill 跨 thread 持久化,本地磁盘可见可备份。
- G4:Skill 注入对 deepseek-v4-pro 友好(progressive disclosure + 显式触发提示)。
- G5:不破坏 4 处前端 vendored patch、4 条后端硬约束(`CLAUDE.md` §强约束)。

### 非目标(本期不做)
- N1:多用户/多租户隔离(假设单用户本地 demo)。
- N2:skill marketplace、社区分享、版本管理。
- N3:GitHub URL 导入(用户选项里被剔除)。
- N4:skill 内调用外部 MCP / 远程工具的鉴权流。
- N5:skill 推荐/搜索/智能排序(列表按名字字典序即可)。

---

## 3. 核心用户故事

1. **新用户开箱**:打开网站,看到一个 "Deep Research" skill 已默认启用,直接问"调研 X"得到完整研究流程。
2. **自定义流程**:研究员想加一个"arXiv 论文摘要"流程,在 Skills 管理页点 "Create with editor" 写 SKILL.md → 保存 → 回聊天框勾选 → 在对话中触发。
3. **导入官方 skill**:用户从 anthropics/skills repo 下载 `brand-guidelines.zip`,拖进上传弹窗,几秒后出现在列表里,默认未启用,手动开关。
4. **临时禁用**:用户在做闲聊,把所有 skill 关掉避免污染 prompt;之后做研究再打开。
5. **debug skill**:用户点开 skill 详情,看到 frontmatter / body 渲染 + 文件树 + 上次被触发的时间(P2)。

---

## 4. 前端方案

### 4.1 聊天框内的 Skill 入口(对应 Claude 网页 "+" 菜单)

- 改 `frontend/src/app/components/ChatInterface.tsx:542-563` 的 form 底部 bar:在发送按钮左侧加一个 "+" / 工具图标按钮 → 触发 Popover。
- Popover 一级菜单(参考 Claude "+" 菜单风格):**Skills →** 二级菜单。
- 二级菜单:列出当前已上传的所有 skill(name + 描述 tooltip)+ 末尾分隔线 + "Manage skills"(跳 `/skills` 页) + "Add skill"(直接弹上传/创建对话框)。
- 每个 skill 项右侧有 ✓ 标记表示已激活(白名单);点击切换。
- 状态实时反映在 form 上方的小 chip 区域(显示"3 skills active"),方便用户感知本轮会带哪些 skill。

### 4.2 Skills 管理页(对应 Claude Skills 管理页 + 上传弹窗)

新增路由 **`/skills`**(`frontend/src/app/skills/page.tsx`),布局复用 `ResizablePanelGroup`(参考 `page.tsx:161-199`):

- **左侧栏**:
  - 顶部:搜索框 + "+ Create skill" 下拉(子项:`Create with editor` / `Upload a file`)。
  - 列表:按 source 分组("Personal" / "Built-in")。每项显示 skill 名 + 启用开关。展开后能看到该 skill 的文件树(SKILL.md / resources/*)。
- **右侧详情**:
  - 顶部:skill 名 + 来源 chip + 启用开关 + ⋮ 菜单(Delete / Export zip)。
  - description(灰色单行)。
  - 主体:tab 切换 `Preview`(markdown 渲染) / `Source`(YAML + body 原文,可编辑)。
  - 底部固定栏:Save / Cancel(编辑态显形)。
- **上传弹窗**(`Upload a file`):drag & drop,接受 `.md` / `.zip`,显示官方规范要点(`name <= 64`, `description <= 1024`, zip 必须含 `<name>/SKILL.md` 顶层目录)。
- **编辑器模式**(`Create with editor`):右侧用 textarea + frontmatter 表单(name / description 必填、license / allowed-tools 可选),实时校验长度上限,保存后落 `/data/skills/personal/<name>/SKILL.md`。

入口:在 `page.tsx` header(行 114-158)的"设置"按钮旁加一个 "Skills" 按钮,跳 `/skills`。

### 4.3 复用资产清单

| 需求 | 已有 | 文件 |
|---|---|---|
| Dialog | ✅ shadcn Dialog | `frontend/src/components/ui/dialog.tsx` |
| Select / Switch / Tabs | ✅ Radix | `frontend/src/components/ui/` |
| ResizablePanelGroup | ✅ | 已在 `page.tsx:161` 使用 |
| 文件上传(drag & drop) | ❌ 需新增组件 | 参考 `TasksFilesSidebar.tsx` 的 `FilesPopover` 模式 |
| Popover | ❌ 未装 | 需 `yarn add @radix-ui/react-popover` + 写 `popover.tsx` |
| Markdown 渲染 | ✅(项目已用于 message) | 复用 ChatMessage 的 markdown 组件 |

### 4.4 状态与持久化

- **激活白名单**(`activeSkillIds: string[]`):浏览器 `localStorage` 的 `deep-agent-active-skills`,跟 `deep-agent-config` 同模式(`frontend/src/lib/config.ts`)。
- **Skill 元数据列表**:**不在前端缓存**,每次进 `/skills` 页或打开 Popover 都向后端拉(轻量 API)。避免与磁盘上的真实 skill 不一致。
- **传给后端**:激活白名单通过 `config.configurable.active_skills`(数组)随 run 提交,改 `useChat.ts:91-106` 的 `stream.submit` 入参。**不要碰 `useChat.ts:44-69` 的 fetch monkey-patch**(详见 architecture.md §3.3)。

---

## 5. 后端方案(Context Engineering 优先)

### 5.1 装配改造(`backend/agent.py`)

```python
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.middleware.skills import SkillsMiddleware  # 也可让 create_deep_agent 自动注入

SKILLS_ROOT = os.environ.get("DEEPAGENTS_SKILLS_ROOT", "./data/skills")
backend = FilesystemBackend(root_dir=SKILLS_ROOT)

agent = create_deep_agent(
    model=model,
    tools=[...],
    system_prompt=ORCHESTRATOR_PROMPT,
    subagents=[research_subagent],
    backend=backend,                           # ← 新增
    skills=["/built-in/", "/personal/"],       # ← 新增,顺序决定覆盖优先级
    context_schema=AgentContext,               # ← 新增,接受前端白名单
    middleware=[GenerativeUIMiddleware()],     # 保持不动
    interrupt_on={"write_file": True, "edit_file": True, "task": True},
)
```

目录布局(磁盘):
```
backend/data/skills/
├── built-in/
│   └── deep-research/SKILL.md     ← 把 prompts.py 的研究流程抽出来
└── personal/
    └── <user-uploaded>/SKILL.md
```

### 5.2 白名单过滤(关键)

deepagents 默认是"加载到的所有 skill frontmatter 全部进 prompt"。我们要做 **per-run 过滤**:

- 新建一个 `SkillWhitelistMiddleware`(在 `backend/middlewares.py` 中,与 `GenerativeUIMiddleware` 并列):
  - 声明一个 `context_schema` 字段 `active_skills: list[str] | None`。
  - 在 `modify_model_request` 钩子里,如果 context 提供了白名单,就用 `append_to_system_message`(deepagents 内部工具) **覆盖** `SkillsMiddleware` 注入的内容,只保留命中的 skill。
  - 若白名单为空 → 不注入任何 skill 段(允许用户全关)。
  - 若白名单 = `None`(前端没传) → 走 deepagents 默认行为(全注入)。
- 中间件顺序:`SkillsMiddleware`(底层注入)→ `SkillWhitelistMiddleware`(过滤)→ `GenerativeUIMiddleware`(UI 字段)。

### 5.3 Skill 管理 HTTP API(新增,与 LangGraph SSE 独立)

LangGraph SDK 走 SSE 跑 graph,**不适合做文件管理 CRUD**。在 backend 起一个轻量 FastAPI/Starlette 子路由(挂在同进程同端口,通过 `langgraph dev` 的自定义 routes 或独立 `uvicorn` 子进程):

| Method | Path | 用途 |
|---|---|---|
| `GET` | `/api/skills` | 列出所有 skill(扫 `data/skills/**/SKILL.md` 解析 frontmatter) |
| `GET` | `/api/skills/{id}` | 单 skill 详情(frontmatter + body + 文件树) |
| `POST` | `/api/skills/upload` | 上传 `.md` / `.zip`,服务端校验 + 落盘 |
| `PUT` | `/api/skills/{id}` | 编辑器保存(覆写 SKILL.md) |
| `DELETE` | `/api/skills/{id}` | 删除整个目录 |

上传校验规则(对应 §6):
- `name` ≤ 64 字符,小写字母/数字/连字符;若已存在同名 → 409。
- `description` ≤ 1024 字符。
- `.zip` 必须含 `<name>/SKILL.md` 单顶层目录;防 zip-slip(拒绝 `../`、绝对路径)。
- 单文件 ≤ 10 MB(对齐 `SkillsMiddleware` 的 `MAX_SKILL_FILE_SIZE`)。
- 解析 frontmatter 失败 → 422 带原因。

### 5.4 Interpreter skill 支持(P2,见 §8 阶段拆分)

如果一个 skill frontmatter 含 `module:` 字段,标记为 interpreter skill。需要:

- 引入 deepagents 的 `CodeInterpreterMiddleware`(0.6.3 是否存在需验证,见 §11 风险 R3)。若 deepagents 自带的不可用,P2 阶段评估 `langchain-sandbox` 或自研子进程隔离。
- 上传时:`.zip` 中允许 `.py` 文件;**禁止 `.sh` 或带 shebang 的可执行**;扫描敏感导入(`subprocess`, `os.system`)给警告但不阻止。
- 默认 **interpreter skill 必须在白名单内 + 触发时弹 HITL 审批**(类似 `write_file`)。
- UI 上 interpreter skill 用红色标识,详情页强提示"可执行代码"。

### 5.5 Prompt 工程配合

`backend/prompts.py` 改两处:

1. **`ORCHESTRATOR_PROMPT` 末尾追加固定段落**(由代码模板拼接,不写进 skill):
   > "Before planning, review the **Available Skills** section above. If a skill's description matches the user's request, you MUST read its full instructions via `read_file(path, limit=1000)` before executing other tools. Do not invent flows that contradict an applicable skill."
2. **把现有的"调研流程"完整抽到 `data/skills/built-in/deep-research/SKILL.md`**:`prompts.py` 主 prompt 只保留 agent 定位 + 工具约定;研究流程改为该 skill body。`tools.py` 的 `emit_research_card` 强制语序也搬过去。

> 对 deepseek-v4-pro:progressive disclosure 减少了 prompt 噪声,但模型可能仍跳过 `read_file`。补救:在 `ORCHESTRATOR_PROMPT` 里用"You MUST" + 在 deep-research skill 的 description 用强动词("Use this skill whenever the user asks to research, investigate, or compare topics")。

---

## 6. 数据模型 / Skill 文件规范

按 Anthropic Agent Skills 规范 + deepagents 实际兼容上限:

```yaml
---
name: deep-research              # 必填, ≤64 char, [a-z0-9-]
description: Use this skill ...  # 必填, ≤1024 char(deepagents);UI 提示用 ≤200(对齐 Anthropic)
license: MIT                     # 可选
compatibility: ...               # 可选, ≤500 char
metadata:                        # 可选, 自由键值
  author: lilu
  version: "1.0"
allowed-tools: read_file write_file   # 可选(deepagents 当前仅展示不强制,UI 标注此限制)
module: index.py                 # 可选,interpreter skill 才填
---

# 标题
## When to use
## Instructions
...
```

目录约定:
```
<name>/
├── SKILL.md         (必须, ≤10 MB)
├── resources/       (可选,任意静态资源)
└── *.py             (interpreter skill 才允许)
```

---

## 7. 关键文件改动锚点

| 模块 | 文件 | 改动性质 |
|---|---|---|
| 前端 | `frontend/src/app/components/ChatInterface.tsx:542` | 新增 Skills Popover 入口 |
| 前端 | `frontend/src/app/skills/page.tsx` | **新建** Skills 管理页 |
| 前端 | `frontend/src/app/components/Skills*.tsx` | **新建** 列表/详情/上传/编辑器 子组件 |
| 前端 | `frontend/src/app/hooks/useChat.ts:91` | 在 `stream.submit` 的 config 加 `active_skills`;**不改 44-69 monkey-patch** |
| 前端 | `frontend/src/lib/config.ts` | 增 `activeSkillIds` 持久化 |
| 前端 | `frontend/src/app/page.tsx:114-158` | header 加 "Skills" 入口 |
| 后端 | `backend/agent.py` | 加 `backend=FilesystemBackend(...)` + `skills=[...]` + `context_schema=` |
| 后端 | `backend/middlewares.py` | 新增 `SkillWhitelistMiddleware` |
| 后端 | `backend/prompts.py` | 主 prompt 抽研究流程 + 追加 skill 指引段 |
| 后端 | `backend/api/skills.py` | **新建** CRUD HTTP 路由 |
| 后端 | `backend/data/skills/built-in/deep-research/SKILL.md` | **新建** 内建 skill |
| 配置 | `backend/.env.example` | 加 `DEEPAGENTS_SKILLS_ROOT=./data/skills` |
| 文档 | `docs/architecture.md` | 加 §2.5 "Skills 系统",并把 §2.1/§2.4 与 skill 的交互写清 |

---

## 8. 阶段拆分

### P0(MVP,约 1-2 周)
- 后端 FilesystemBackend + skills 加载 + 白名单中间件 + Skill CRUD API。
- 前端聊天框 Skills Popover + 白名单状态传递。
- `.md` 单文件上传 + 列表/启用/删除。
- 把 `deep-research` 流程抽成 built-in skill,验证 deepseek 能稳定触发。

### P1(2-3 周)
- 完整 Skills 管理页(`/skills` 路由 + 详情 + Source 编辑器 + Tab)。
- `.zip` 上传(含解压 + zip-slip 防御 + `<name>/SKILL.md` 校验)。
- 浏览器内"Create with editor"。
- frontmatter 字段全集支持(license / allowed-tools 等)+ UI 警示。

### P2(按需)
- Interpreter skill(`module:` + `CodeInterpreterMiddleware`/sandbox + HITL 审批)。
- Skill 使用统计(上次触发时间、命中次数)。
- 多 source 分组("Built-in" / "Personal" / "Team")。
- Skill 导出 `.zip`。

---

## 9. 验证

P0 验证步骤(端到端):

1. **后端启动**:`cd backend && source .venv/bin/activate && langgraph dev`,日志能看到 `SkillsMiddleware loaded 1 skill from /built-in/`(deep-research)。
2. **API 联通**:
   - `curl http://localhost:2024/api/skills` → 返回 `[{name: deep-research, source: built-in, ...}]`。
   - `curl -F file=@test.md http://localhost:2024/api/skills/upload` → 201 + 列表多一项。
3. **前端 UI**:
   - 启动 `cd frontend && yarn dev`,聊天框看到 "+ Skills" 按钮,展开能看到 deep-research,默认勾选。
   - 进 `/skills` 看到列表 + 详情。
   - 上传 `.md` 文件成功落到 `backend/data/skills/personal/<name>/SKILL.md`。
4. **白名单生效**:
   - 关掉 deep-research → 问"调研一下 Rust async runtime",观察主 agent 不再走 todo + sub-agent 流程(变成直接答)。
   - 重新打开 → 同一问题恢复完整研究流程。
5. **HITL 不破**:研究流程中 `task` / `write_file` 审批卡照常弹出。
6. **Vendored patch 不破**:看 `useChat.ts:44-69` 仍存在;`broadcastResumeInterrupt` 仍工作(同时派 2 个 task 时点一次 approve 通过)。

P1 额外:
- 上传一个 `brand-guidelines.zip`(从 anthropics/skills 拉),验证目录解压 + frontmatter 解析 + body 渲染正确。
- 在编辑器里改一段 description → 保存 → 重启后端 → 列表里反映新 description。

P2 额外:
- 上传含 `module: handler.py` 的 skill → 触发时弹审批卡 → 拒绝则不执行。

---

## 10. 兼容性 & 强约束守护

| 已有约束 | 本方案如何不冲突 |
|---|---|
| `GenerativeUIMiddleware` 不能删 | 保持 middleware 链,只在前面追加 `SkillWhitelistMiddleware`。 |
| LLM provider 锁定 ChatOpenAI + DashScope | 不动 `model` 实例化。 |
| 不传 `checkpointer` | 不传。 |
| `streaming=True` 保留 | 不动。 |
| `useChat.ts` fetch monkey-patch | 改 `stream.submit` 入参但不动 `useEffect` 内的 fetch 拦截。 |
| HITL 批量审批的 broadcast 兼容 | interpreter skill 走 `interrupt_on` 加新 key 即可。 |
| Vendored frontend 升级流程 | 新增文件不影响 `git apply`;改 `ChatInterface.tsx` 等已 patch 文件,记入 `docs/architecture.md §3.1` patch 表。 |

---

## 11. 关键风险

| # | 风险 | 缓解 |
|---|---|---|
| R1 | deepseek-v4-pro 仍跳过 `read_file` 不展开 skill body | (1) prompt 加强制语序;(2) skill description 用强动词;(3) P0 验证时若失败,允许"用户强制激活 = 全文注入"作 fallback 选项。 |
| R2 | `langgraph dev` 是否支持自定义 HTTP 路由挂同端口 | 若不支持,独立起 `uvicorn skill_api:app --port 2025`,前端 `lib/config.ts` 加 `skillsApiUrl` 配置。 |
| R3 | deepagents 0.6.3 的 `CodeInterpreterMiddleware` 可能不存在 | P0 不依赖;P2 启动前先 `python -c "from deepagents.middleware import ..."` 验证,缺失则评估 `langchain-sandbox` 或推后。 |
| R4 | Skills 注入显著拉长 system prompt → token 成本 / 上下文窗口 | 白名单机制 + progressive disclosure 已覆盖;UI 显示"当前 active N skills, ~XK tokens"提醒。 |
| R5 | zip 上传带恶意路径(zip slip) | 强制校验所有 entry 路径相对、不含 `..`、归一化后必须以 `<name>/` 开头。 |
| R6 | 同名 skill 冲突(personal 覆盖 built-in) | deepagents 的"last source wins"语义 + UI 上对 personal 覆盖项加 ⚠️ 标识。 |
| R7 | docs/architecture.md 未同步 → 后续维护者踩坑 | 与代码改动同 PR 提交 §2.5 + §3.x 更新,纳入 review checklist。 |
