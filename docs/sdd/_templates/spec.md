# Spec: _(Feature 名称)_

> Feature ID: `NNN-feature-slug` · 版本归属: `vX.Y.Z` · Owner: _(姓名/handle)_ · 创建日期: `YYYY-MM-DD`

## 状态

| 阶段 | 状态 | 备注 |
|---|---|---|
| 已起草 | ☐ | 完成 §1-§6 后勾选 |
| 已评审(`/sdd-review spec` 通过 + ★ 用户确认) | ☐ | 评审日期 / 评审人 |
| 已完成(三层测试全绿) | ☐ | 完成日期 |

---

## 1. 概述与用户故事

> 用一段话讲清"这个 feature 是什么、给谁用、解决什么痛点",然后列 1-3 条用户故事。可引用 `docs/prds/` 的 PRD 作为 Context。

**Feature 描述**:_(1-3 句话)_

**Context / 来源**:_(例如 `docs/prds/skills.md §3`、采访模式 2026-MM-DD 决策等。无则填"无")_

**用户故事**:

1. 作为 _(角色)_,我希望 _(能力)_,以便 _(价值)_。
2. _(……)_

**检查点**:
- [ ] 至少 1 条用户故事写明 `角色 / 能力 / 价值`
- [ ] 描述里不引入新术语(必要时补术语表小节)

---

## 2. 验收标准 (Acceptance Criteria)

> AC 是 feature 是否"完成"的唯一裁判。**每条 AC 的"验证方式"必须落到具体自动化测试**——后端 `pytest::test_x`、前端组件 `vitest::<Component>`、端到端 `e2e::<flow>`。极少数确无自动化手段的(纯外网 lab host 部署类)才允许写 `手动`,并说明原因。

| AC ID | 标准描述 | 验证方式 | 覆盖测试/任务 |
|---|---|---|---|
| AC-1 | _(用户做 X,系统返回/显示 Y)_ | `pytest::test_xxx` / `vitest::Comp` / `e2e::flow` | T_(N)_ |
| AC-2 | _(边界/错误场景)_ | _(……)_ | T_(N)_ |
| AC-3 | _(UI 交互流程)_ | `e2e::xxx` | T_(N)_ |

**检查点**:
- [ ] 每条 AC 有唯一 ID(AC-1, AC-2, …),tasks.md 引用同一 ID
- [ ] 每条 AC 的验证方式指向一个可自动跑的测试(三层之一);写"手动"的需说明为何无法自动化
- [ ] UI 交互类 AC 至少 1 条由 `e2e::` 覆盖
- [ ] AC 数量建议 3-7 条(少于 3 太粗,多于 7 应拆 feature)

---

## 3. 边界情况与非目标

### 3.1 边界情况

> 系统应正确处理但不属于主流程的场景(失败路径、并发、空输入、外部 API 失效等)。

- _(例如"DashScope API 429 限流时前端如何提示")_

### 3.2 非目标(本期不做)

> 显式列出"看起来相关但本期不做"的事,避免范围蔓延。

- _(例如"不支持多用户登录"、"PPTX 导出延后到 vX.Y.Z")_

**检查点**:
- [ ] 边界情况含至少 1 条"失败/异常路径"
- [ ] 非目标列出可能被误以为属于本期的事项

---

## 4. 涉及强约束

> 列出本 feature 触碰 [`CLAUDE.md` §强约束](../../../../CLAUDE.md) 的哪几条(8 行与 CLAUDE.md 顺序对齐)。不触碰填"否"并简述为何无。凡"是"的行缓解策略必填;5 条可机检项由 `scripts/arch-guard.sh` + `backend/tests/test_arch_invariants.py` 兜底,其余靠本矩阵 + `/code-review`。

| 强约束条目 | 是否触碰 | 缓解策略 |
|---|---|---|
| `GenerativeUIMiddleware` 不能删 | ☐ 是 / ☐ 否 | _(若是,说明如何保留)_ |
| LLM provider 锁 `ChatOpenAI` + DashScope | ☐ 是 / ☐ 否 | _(……)_ |
| checkpointer 传法(CLI 模式不传 / 自研 server 模式必传) | ☐ 是 / ☐ 否 | _(若是,说明遵守哪种模式语义)_ |
| `streaming=True` 不改回 False | ☐ 是 / ☐ 否 | _(……)_ |
| 前端 vendored patch(详见 §5) | ☐ 是 / ☐ 否 | 详见 §5 |
| HITL 批量审批"全 approve / 全 reject"语义 | ☐ 是 / ☐ 否 | _(……)_ |
| `useChat.ts` fetch monkey-patch 不删 | ☐ 是 / ☐ 否 | _(……)_ |
| `prompts.py` 强制语序不弱化 | ☐ 是 / ☐ 否 | _(……)_ |

**检查点**:
- [ ] 凡"是"的条目缓解策略不为空
- [ ] 触碰的可机检项,确认 arch-guard / `test_arch_invariants` 仍能覆盖(必要时补断言)

---

## 5. 前端 patch 影响

> deepagents 的 `frontend/` 是 `langchain-ai/deep-agents-ui` 的 vendored 副本,有多处本地 patch(见 [`docs/architecture.md` §3.1](../../../architecture.md))。本节识别本 feature 是否影响 patch,以及测试栈自身是否新增 patch。

**是否动 `frontend/**`**:☐ 是 / ☐ 否

> 若否,跳过本章其余内容。

**预计修改的已 patch 文件**(勾选):
- [ ] `frontend/src/app/components/ChatInterface.tsx`(broadcastResumeInterrupt)
- [ ] `frontend/src/app/components/ChatMessage.tsx`(LOCAL_UI_COMPONENTS 注入 / task-skip / clarification 分支)
- [ ] `frontend/src/app/components/ToolCallBox.tsx`(components props 透传)
- [ ] `frontend/src/app/hooks/useChat.ts`(fetch monkey-patch + StateType.files 放宽)
- [ ] `frontend/src/app/components/generative-ui/{ResearchCard,ClarificationCard,registry}.tsx`
- [ ] 其他既有 patch 文件:_(……)_

**测试栈新增 patch**(vendored 副本里加 vitest/playwright 配置/devDeps 算本地新增 patch):
- [ ] 本 feature 是否新增前端测试依赖/配置?若是,登记到 architecture.md §3.1。

**留底命令**(实施 Step 6 第一动作):
```bash
cd frontend && git diff > /tmp/patches-NNN.diff   # NNN 换成本 feature 序号
```

**对 architecture.md §3.1 patch 表的预期更新**:_(新增/修改/删除 patch,或填"无")_

**检查点**:
- [ ] 若动 `frontend/`,留底命令是 tasks.md 第一个任务
- [ ] 改动的前端组件有配对 `vitest::` 测试(在 §2 AC 验证方式里体现)

---

## 6. 实现概要 & 文件清单

> 概要描述实现思路(3-5 句话),列出新增/修改的文件。**不要复制具体代码**——细节留给 tasks.md。

**实现思路**:_(3-5 句话讲方案要点)_

**文件清单**:

| 文件 | 改动性质 | 简要说明 |
|---|---|---|
| `backend/xxx.py` | 新建 / 修改 | _(一句话)_ |
| `backend/tests/test_xxx.py` | 新建 | 对应 AC 的 pytest |
| `frontend/src/app/xxx.tsx` | 新建 / 修改 | _(一句话)_ |
| `frontend/src/app/xxx.test.tsx` | 新建 | 组件 vitest |
| `frontend/e2e/xxx.spec.ts` | 新建 | UI 交互 E2E |
| `docs/architecture.md` | 修改 §X.Y | _(可选;若引入新机制必填)_ |

**检查点**:
- [ ] 文件清单与 §2(测试文件)、§4-§5(强约束/patch 文件)一致
- [ ] 若引入新机制(新 middleware / 新 patch / 新组件树),架构文档同步项已列
- [ ] 无大段代码块(spec 不是实现,长度控制在 2 屏内)
