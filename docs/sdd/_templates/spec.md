# Spec: _(Feature 名称)_

> Feature ID: `NNN-feature-slug` · 版本归属: `vX.Y.Z` · Owner: _(姓名/handle)_ · 创建日期: `YYYY-MM-DD`

## 状态

| 阶段 | 状态 | 备注 |
|---|---|---|
| 已起草 | ☐ | 完成 §1-§6 后勾选 |
| 已评审(`/sdd-review spec` 通过 + ★ 用户确认) | ☐ | 评审日期 / 评审人 |
| 已完成(verification.md 全绿) | ☐ | 完成日期 |

---

## 1. 概述与用户故事

> 用一段话讲清"这个 feature 是什么、给谁用、解决什么痛点"。然后列 1-3 条用户故事。可引用 `docs/prds/` 中的 PRD 作为 Context。

**Feature 描述**:_(在此填写:1-3 句话)_

**Context / 来源**:_(在此填写:例如 `docs/prds/skills.md` §3、用户口头需求 2026-MM-DD 等。无则填"无")_

**用户故事**:

1. 作为 _(角色)_,我希望 _(能力)_,以便 _(价值)_。
2. _(在此填写)_

**检查点**:
- [ ] 至少 1 条用户故事写明 `角色 / 能力 / 价值`
- [ ] 描述里不引入新术语(必要时在 §2 之前补术语表小节)

---

## 2. 验收标准 (Acceptance Criteria)

> 验收标准是 feature 是否"完成"的唯一裁判。**每条 AC 必须可手动复现验证**(在 verification.md 里有对应步骤)。

| AC ID | 标准描述 | 验证方式 | verification.md 位置 |
|---|---|---|---|
| AC-1 | _(在此填写:用户做 X,系统返回 Y)_ | 浏览器手动 / 接口手动 / 日志检查 | §2.AC-1 |
| AC-2 | _(在此填写)_ | _(在此填写)_ | §2.AC-2 |
| AC-3 | _(在此填写)_ | _(在此填写)_ | §2.AC-3 |

**检查点**:
- [ ] 每条 AC 都有唯一 ID(AC-1, AC-2, ...),后续 tasks.md 引用同一 ID
- [ ] 每条 AC 都可在本地浏览器 + `langgraph dev` 复现,不依赖外部环境
- [ ] AC 数量建议 3-7 条(少于 3 太粗,多于 7 应拆 feature)

---

## 3. 边界情况与非目标

### 3.1 边界情况

> 列出"系统应正确处理但不属于主流程"的场景(失败路径、并发、空输入等)。

- _(在此填写:例如"DashScope API key 失效时前端如何提示")_

### 3.2 非目标(本期不做)

> 显式列出"看起来相关但本期不做"的事,避免范围蔓延。

- _(在此填写:例如"不支持多用户登录")_

**检查点**:
- [ ] 边界情况包含至少 1 条"失败/异常路径"
- [ ] 非目标列出明确的、可能被误以为属于本期的事项

---

## 4. 涉及强约束

> 列出本 feature 触碰 [`CLAUDE.md` §强约束](../../../../CLAUDE.md) 中的哪几条。若不触碰则写"否",但要解释为何无(例如"纯前端展示改动")。

| 强约束条目 | 是否触碰 | 缓解策略 |
|---|---|---|
| `GenerativeUIMiddleware` 不能删 | ☐ 是 / ☐ 否 | _(若是,说明如何保留)_ |
| LLM provider 锁 `ChatOpenAI` + DashScope | ☐ 是 / ☐ 否 | _(若是,说明如何保留)_ |
| 不传 `checkpointer` 给 `create_deep_agent` | ☐ 是 / ☐ 否 | _(若是,说明如何保留)_ |
| `streaming=True` 不改回 False | ☐ 是 / ☐ 否 | _(若是,说明如何保留)_ |
| 前端 vendored patch(详见 §5) | ☐ 是 / ☐ 否 | 详见 §5 |
| HITL 批量审批"全 approve / 全 reject"语义 | ☐ 是 / ☐ 否 | _(若是,说明)_ |
| `useChat.ts` fetch monkey-patch 不删 | ☐ 是 / ☐ 否 | _(若是,说明)_ |
| `prompts.py` 强制语序不弱化 | ☐ 是 / ☐ 否 | _(若是,说明)_ |

**检查点**:
- [ ] 凡是"是"的条目,缓解策略不能为空
- [ ] 触碰的条目需在 verification.md §3 加对应回归项

---

## 5. 前端 patch 影响

> deepagents 的 `frontend/` 是 `langchain-ai/deep-agents-ui` 的 vendored 副本,有 4-6 处本地 patch(见 [`docs/architecture.md` §3.1](../../architecture.md))。本节识别本 feature 是否影响 patch。

**是否动 `frontend/**`**:☐ 是 / ☐ 否

> 若否,跳过本章其余内容。

**预计修改的已 patch 文件**(勾选):
- [ ] `frontend/src/app/components/ChatInterface.tsx`(broadcastResumeInterrupt)
- [ ] `frontend/src/app/components/ChatMessage.tsx`(LOCAL_UI_COMPONENTS 注入)
- [ ] `frontend/src/app/components/ToolCallBox.tsx`(components prop)
- [ ] `frontend/src/app/hooks/useChat.ts`(fetch monkey-patch,过滤 stream_mode "tools")
- [ ] `frontend/src/app/components/generative-ui/registry.tsx`(本地新增)
- [ ] `frontend/src/app/components/generative-ui/ResearchCard.tsx`(本地新增)
- [ ] 其他既有 patch 文件:_(在此填写)_

**留底命令**(实施 Step 6 第一动作必须执行):

```bash
cd frontend && git diff > /tmp/patches-NNN.diff   # 把 NNN 换成本 feature 序号
```

**对 architecture.md §3.1 patch 表的预期更新**:_(在此填写:是新增 patch / 修改既有 patch / 删除 patch;若都不是填"无")_

**检查点**:
- [ ] 若动 `frontend/`,留底命令在 tasks.md 是第一个任务
- [ ] 若新增/删除 patch,已在本节登记后续如何更新 §3.1

---

## 6. 实现概要 & 文件清单

> 概要描述实现思路(3-5 句话),列出本 feature 将新增/修改的文件。**不要复制具体代码**——细节留给 tasks.md。

**实现思路**:_(在此填写:3-5 句话讲方案要点)_

**文件清单**:

| 文件 | 改动性质 | 简要说明 |
|---|---|---|
| `backend/xxx.py` | 新建 / 修改 | _(一句话)_ |
| `frontend/src/app/xxx.tsx` | 新建 / 修改 | _(一句话)_ |
| `docs/architecture.md` | 修改 §X.Y | _(可选;若引入新机制必填)_ |

**检查点**:
- [ ] 文件清单与 §4-§5 标记一致(动 frontend 的 patch 文件已列出)
- [ ] 若引入新机制(新 middleware / 新 patch / 新前端组件树),架构文档同步项已列出
- [ ] 不出现大段代码块(spec 不是实现,长度控制在 2 屏内)
