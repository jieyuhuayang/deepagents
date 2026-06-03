# SDD Guide(deepagents 版)

> 本项目的 Spec-Driven Development(SDD)开发流程。**所有非琐碎 feature 必须走 SDD**——琐碎(改一行字、修 typo、调一句 prompt 措辞)直接 commit 即可。
>
> 本指南以 [`OpenOntology/SDD-Guide.md`](https://github.com/) 的完整方法论为蓝本,按 deepagents(Deep Research agent demo)的实际形态适配。三个核心取舍:
> - **2 件套**(`spec.md` + `tasks.md`),不再单独维护 verification.md——AC 由**三层自动化测试**验证,在 tasks.md 里追溯。
> - **采访模式**做需求澄清——一轮批量提问 + 预填选项,降低交互门槛。
> - **三层测试 + L0 arch-guard** 守护质量——后端 Test-First(pytest)、前端 Test-Alongside(vitest)、E2E 强制(Playwright,确定性 fixture)。

---

## 1. 何时走 SDD

| 场景 | 走 SDD? |
|---|---|
| 改 typo / prompt 措辞 / `.env.example` 字段名 | 否,直接 commit |
| 调一两行 frontend 样式(无组件结构变化) | 否,直接 commit |
| 更新依赖小版本(无 API 变化) | 否,直接 commit |
| 新增 1 个 backend tool(只动 `tools.py`,有可测纯函数) | 边界,建议走精简 SDD(spec 简要 + tasks,后端测试照配) |
| 引入新机制(middleware、新 graph 节点、新前端组件树、新 generative-ui 卡片) | **是** |
| 升级 `deepagents`/`langgraph` 主版本或换 LLM provider | **是** |
| 改动触碰 [CLAUDE.md §强约束](../../CLAUDE.md) 任一条 | **必须是**(spec.md §4 强约束矩阵强制审视) |
| 改动会影响 frontend vendored patch(见 [architecture.md §3.1](../architecture.md)) | **必须是**(spec.md §5 强制留底 + 组件测试守护) |

判断口诀:**"是否会被未来的我忘记初衷"**——会就走 SDD,不会就直接干。

---

## 2. 6 步流程

```
1. Spec Discovery(采访模式:一轮批量提问)        ──★ 选项式确认 ──>
2. 起草 spec.md                                    ──>
3. /sdd-review <dir> spec                           ──★ 选项式确认 ──>
4. 起草 tasks.md(Test-First 配对 + Test-Alongside + E2E 任务)──>
5. /sdd-review <dir> tasks(自动)                   ──>
6. 拉分支/worktree → 前端 patch 留底(如需) → 逐任务实现
   → 6.5 强制 E2E(Playwright fixture) → 三层测试全绿 → /code-review → PR → 合并
```

**两个 ★ 暂停点不能跳过**,但都**用 [AskUserQuestion 选项式]轻量确认**,不走开放式多轮对话:
- **Step 1 后**:Claude 把"理解的目标 / 范围 / 待澄清问题"做成一轮采访(见下),用户一次性作答即视为确认,直接进 Step 2。
- **Step 3 后**:`/sdd-review spec` 给出报告 + 一个"通过 / 修改后再审"的选项确认,用户选定后 skill 才勾状态表。

### 每步详解

#### Step 1 — Spec Discovery(采访模式)

**前置阅读**:用户需求 + 既有 PRD(若有,在 `docs/prds/`)+ [`CLAUDE.md §强约束`](../../CLAUDE.md) + [`docs/architecture.md`](../architecture.md) 相关章节。

**采访模式**:Claude 只读不写,把 PRD 中的不确定性整理成**一轮批量问题**(用 AskUserQuestion 一次发出,每题 2-4 个预填选项 + 允许"其它"),维度沿用通用 Spec Discovery:

- **边界条件**:极端值、空状态、超长输入、批量上限
- **异常路径**:API 失效(DashScope 429/超时)、并发、部分成功、空返回
- **数据约束**:字段上限、唯一性、持久化范围(哪些进 checkpointer)
- **回滚与降级**:操作失败的恢复、上游升级的兼容
- **跨上游影响**:是否触碰强约束 / frontend vendored patch / generative-ui 渲染链

规则:只就 PRD 未明确处提问,已明确的跳过;PRD 足够清晰时可声明"无需提问"并说明理由。用户一轮答完即 ★ 确认,进 Step 2。

#### Step 2 — 起草 spec.md

从 [`_templates/spec.md`](_templates/spec.md) 复制到 `docs/features/vX.Y.Z/NNN-feature-slug/spec.md`。版本号 `vX.Y.Z` 与 `backend/pyproject.toml` + `frontend/package.json` 同步管理;序号 `NNN` 在该版本内从 001 起递增;slug 用 kebab-case。**§2 AC 表的"验证方式"列必须落到具体测试**(`pytest::test_x` / `vitest::Comp` / `e2e::flow`),没有可自动验证手段的 AC 视为规格不完整。

#### Step 3 — `/sdd-review <dir> spec`

调用 [sdd-review skill](../../.claude/skills/sdd-review/SKILL.md) 的 spec 模式,对照检查清单产出报告,**选项式**请用户确认。不自动勾"已评审"。

#### Step 4 — 起草 tasks.md

从 [`_templates/tasks.md`](_templates/tasks.md) 复制。把 spec 拆成自包含原子任务,按下方[测试模型](#5-测试模型本规范核心)编排:后端 **Test-First 配对**(测试任务在前)、前端 **Test-Alongside**(组件+vitest 同任务)、feature 末尾一个 **E2E 任务**。每任务标 `覆盖 AC`,并用 AC 反查表双向确认。

#### Step 5 — `/sdd-review <dir> tasks`

tasks 模式**自动通过**:全部检查通过即自动勾状态表;有问题才停下来要求修复。

#### Step 6 — 实现并合并

子流程(按顺序):
1. `git checkout -b feat/vX.Y.Z/NNN-slug`(基于 main),或并发/长跑场景用 worktree(见 [§7](#7-worktree-工作空间))。
2. **若 spec.md §5 "动 frontend/" = 是**:`cd frontend && git diff > /tmp/patches-NNN.diff` 留底。
3. 逐任务实现:
   - 后端确定性面 — 先写 pytest(红)→ 实现(绿);
   - 前端组件 — 实现 + vitest 同任务完成;
   - 实施中发现与 spec 不符,**立刻**登记 tasks.md §实际偏差记录;严重偏差回 Step 2 改 spec。
4. **6.5 强制 E2E**:跑 `/e2e-test <dir>` 或手写 `e2e/*.spec.ts`,用 Playwright fixture 模式覆盖 spec 的 UI 交互类 AC(最多 3 轮修复)。即使纯后端 feature,也要跑一遍既有 E2E 确认页面无回归。
5. 三层测试全绿:`pytest` + `npm test`(vitest)+ `npm run e2e`(Playwright)。
6. 调用 built-in `/code-review` 审 diff,修复发现项。
7. 提 PR(英文 conventional commits,如 `feat(skills): add runtime skill loader`),squash merge 回 main。

---

## 3. 产物布局

```
docs/sdd/                                # 本目录:指南与模板(改这里 ≈ 改流程本身)
├── SDD-Guide.md
└── _templates/
    ├── spec.md
    └── tasks.md

docs/features/                           # feature 实际产物(每个 feature 一个子目录)
└── vX.Y.Z/
    └── NNN-feature-slug/
        ├── spec.md                      # What + Why
        └── tasks.md                     # How + When(含验证追溯)

backend/tests/                           # 后端 pytest(Test-First)
frontend/src/**/<Component>.test.tsx     # 前端 vitest(Test-Alongside,与组件同目录)
frontend/e2e/                            # Playwright E2E + fixtures/

.claude/skills/sdd-review/SKILL.md       # 合并版文档审查 skill
.claude/skills/e2e-test/SKILL.md         # E2E 生成/运行 skill
scripts/arch-guard.sh                    # L0 实时守卫脚本
```

> 不再有独立 `verification.md`——它原本承载的"逐 AC 步骤 + 回归清单"被吸收为:确定性回归 → pytest;UI/agent 回归 → 组件测试 + E2E;强约束回归 → arch-guard + `backend/tests/test_arch_invariants.py`。

---

## 4. 与既有文档的关系

```
CLAUDE.md §强约束 (8 条)
       │
       ↓ 派生为 spec.md §4 "涉及强约束" 8 行 checkbox 矩阵
       ↓ 5 条可机检的派生为 scripts/arch-guard.sh + backend/tests/test_arch_invariants.py
       │
docs/architecture.md §3.1 (前端 patch 表)
       │
       ↓ 派生为 spec.md §5 "前端 patch 影响" + 前端组件测试(vitest)
       │
docs/prds/                               # 业务需求(Step 1 采访的输入)
       │
docs/troubleshooting.md                  # 跑期问题清单(排错对照)
```

**约定**:
- `CLAUDE.md` / `architecture.md` 是"宪法",变动需谨慎,且要同步更新 `_templates/` 的对应章节(强约束矩阵、patch 清单)、`arch-guard.sh` 的规则、`test_arch_invariants.py` 的断言——**四处口径必须一致**。
- PRD 可频繁修改,但被某 feature 引用后该 feature 的 spec.md 是定稿;后续 PRD 改动若与已完成 feature 冲突,起新 feature 修正,不回改旧 feature。

---

## 5. 测试模型(本规范核心)

三层自动化测试,AC 全程可追溯(`spec §2 验证方式列` ↔ `tasks 覆盖 AC` ↔ 测试 ID):

### ① 后端 Test-First — pytest

- **顺序**:确定性面先写测试(红)→ 实现(绿);tasks.md 中测试任务排在配对实现任务之前。
- **覆盖面**:`tools.py` / `web_search.py` 纯函数;`server.py` 路由契约(FastAPI `TestClient`,含 SSE 协议形状、`stream_mode` 过滤兼容);`_parse_db_url` 等工具函数;`backend/tests/test_arch_invariants.py`(强约束不变量,见 [§6](#6-l0-arch-guard))。
- **不测**:`agent.py` 装配出的 graph 本身——它由非确定性 LLM 驱动,交给 E2E fixture。
- **跑法**:`cd backend && source .venv/bin/activate && pip install -e ".[test]" && pytest`

### ② 前端 Test-Alongside — vitest + @testing-library/react

- **顺序**:实现与测试同任务完成。
- **覆盖面**:**vendored patch 最易回归的本地组件**——`generative-ui/ResearchCard`(给定 props 渲染)、`ClarificationCard`、`ToolApprovalInterrupt`(approve/reject 交互)、`FileViewDialog`(MIME/下载分支)、`registry` 注册。确定性、快、无后端依赖。
- **跑法**:`cd frontend && npm test`(本项目 vendored 前端用 npm,非 yarn;详见 CLAUDE.md 常用命令)

### ③ E2E 强制 — Playwright(确定性 fixture 模式)

- **时机**:feature 全部任务完成后(Step 6.5),覆盖 spec 的 **UI 交互流程类 AC**。
- **确定性 fixture 机制**:agent 核心是非确定性 LLM,**不打真 LLM**。前端真实运行(`next start`),用 Playwright `page.route('**/runs/stream', …)` 等**拦截 SDK 请求并 fulfill 录制好的 SSE 事件序列**(`frontend/e2e/fixtures/*.txt`);thread/assistant 端点同样桩化。这样 ResearchCard 渲染、HITL 审批卡、导出下载、文件查看器等交互可稳定可重复地验证。
- **真·LLM 全栈 smoke**(可选、慢速):不拦截,直接打 `uvicorn` + DashScope,定位为"PR 前手动跑一次"的端到端贯通验证,不进紧 CI。
- **跑法**:`cd frontend && npm run e2e`(fixture 模式)。fixture 捕获见 [`/e2e-test`](../../.claude/skills/e2e-test/SKILL.md):真后端可用时从 DevTools/`curl -N` 抓 SSE 落盘,不可用时照种子手写。

**E2E 数据隔离红线**(真·LLM smoke 时必守):

| 规则 | 说明 |
|---|---|
| 禁止无条件删全部资源 | cleanup 必须按前缀/白名单过滤 |
| 测试数据前缀 | thread id 统一 `e2e-<feature>-` 前缀 |
| 双重 cleanup | setup 清上次残留 + 末尾清本次 |
| 绝不 wipe checkpointer 库 | 只删带前缀的 thread,非测试数据前后必须完好 |

---

## 6. L0 arch-guard

[`scripts/arch-guard.sh`](../../scripts/arch-guard.sh) 在每次 `Write`/`Edit` 后由 [`.claude/settings.json`](../../.claude/settings.json) 的 `PostToolUse` hook 同步触发。无违规**完全静默**;命中红线打印 `⚠️ [arch-guard] VIOLATION: ...`。

守护 [CLAUDE.md §强约束](../../CLAUDE.md) 中**可机检的 5 条**(grep 启发式):

| 触发文件 | 检查 |
|---|---|
| `backend/agent.py` | `GenerativeUIMiddleware` 未删 / `ChatOpenAI`+DashScope 未换 / `streaming=True` 未改回 / 未引入 `MemorySaver` |
| `backend/prompts.py` | `emit_research_card` 强制语序未弱化 |
| `frontend/src/app/hooks/useChat.ts` | `window.fetch` monkey-patch + `stream_mode` 过滤未删 |

另 3 条(前端 patch 留底、HITL 全 approve/reject 语义、其它)无法 grep,靠 spec.md §4 矩阵 + `/code-review` 人工守。

**arch-guard 是提醒不是阻断**——它是 grep 启发式,可能误报;最终由人判断。同一组不变量也镜像在 `backend/tests/test_arch_invariants.py`(pre-PR / CI 全量执行点),两处口径一致。

---

## 7. Worktree 工作空间

> 文档阶段(Step 1-5)始终在主工作区(main)完成;只有进入代码实现(Step 6)才考虑 worktree。

**何时用**:口诀 **"并发 ≥2 个 feature,或单任务长跑 >10 分钟"**(E2E、数据迁移、大重构)。单人单任务串行用普通分支即可,worktree 反增管理负担。

**命名**:worktree 路径 `../deepagents-NNN-slug`,与分支 `feat/vX.Y.Z/NNN-slug` 对齐,扫一眼 `git worktree list` 就能定位。

**本项目隔离红线**(凡写到工作目录外的副作用都要显式隔离):

| 资源 | 默认行为 | 做法 |
|---|---|---|
| `backend/.venv` / `frontend/node_modules` | 各 worktree 各一份 | 创建后立即重装 |
| `backend/local.db`(SQLite) | **默认共享,会互污** ⚠️ | 各 worktree 改 `DATABASE_URL` 指不同文件 |
| 端口 2024(后端)/ 3000(前端) | **默认冲突** ⚠️ | 各 worktree 改启动端口 + `.env` |
| `.env` / `.env.local` | 各 worktree 各一份 | 从主区复制后改端口/DB |
| `.claude/settings.local.json` | 不应进 git | 各 worktree 各自维护 |

> lab host 部署仍走 [`scripts/deploy-to-114.sh`](../../scripts/deploy-to-114.sh)(端口 12024/13000),worktree 只用于本地并发开发。

**命令速查**:
```bash
git worktree add ../deepagents-NNN-slug -b feat/vX.Y.Z/NNN-slug   # 新建 + 拉分支
git worktree list                                                  # 列出
git worktree remove ../deepagents-NNN-slug                         # 合并后清理(工作树需干净)
git worktree prune                                                 # 兜底清理外部删除的注册
```

**Hook 路径陷阱**:`.claude/settings.json` 里脚本路径用 `$CLAUDE_PROJECT_DIR`(不要写绝对路径),否则跨 worktree 会指错文件。

---

## 8. 命名约定

- **feature 目录**:`docs/features/vX.Y.Z/NNN-feature-slug/`(`NNN` 三位零填充,每版本内递增;slug kebab-case,3-5 词)。
- **分支**:`feat/vX.Y.Z/NNN-feature-slug`(与目录同名,前缀 `feat/`)。
- **commit**:英文 conventional commits,作用域可选:
  - `feat(skills): add runtime skill loader and whitelist`
  - `test(tools): add web_search provider routing cases`
  - `docs(sdd): tweak spec template strong-constraint matrix`
- **测试**:后端 `backend/tests/test_<module>.py`;前端组件 `<Component>.test.tsx`(与组件同目录);E2E `frontend/e2e/<flow>.spec.ts`,fixture `frontend/e2e/fixtures/<flow>.txt`。

---

## 9. 何时跳过 / 持续演进

**可直接 commit(不走 SDD)**:修 README typo、调一句 prompt 措辞(注意若动到强制语序仍要走 SDD)、调 `.env.example` 字段顺序、更新依赖小版本、改一两行前端样式。跳过时仍写清楚 commit message。

**持续演进**:本流程本身也是演进对象。若某步骤经常被跳过、某检查项总是 N/A、某模板字段总是空 —— 改这份 Guide 与对应模板,**不要默默跳过**。修改本目录任何文件,commit 用 `docs(sdd):` 前缀。
