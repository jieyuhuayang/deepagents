# SDD Guide(deepagents 轻量版)

> 本项目的 Spec-Driven Development(SDD)开发流程。**所有非琐碎 feature 必须走 SDD**——琐碎(改一行字、修一个 typo、调一个 prompt 措辞)直接 commit 即可。

deepagents 是 demo 项目,这份指南是 bisheng 9 步 SDD 的**轻量版适配**:6 步流程、3 件套模板、1 个合并版审查 skill,无 release-contract、无 arch-guard、无双库兼容、无 5 位错误码。

---

## 1. 何时走 SDD

| 场景 | 走 SDD? |
|---|---|
| 改 typo / prompt 措辞 / `.env.example` 字段名 | 否,直接 commit |
| 调一两行 frontend 样式 | 否,直接 commit |
| 新增 1 个 backend tool(只动 `tools.py`) | 边界,建议走精简 SDD(只起 spec + verification 两件) |
| 引入 1 个新机制(middleware、新 graph 节点、新前端组件树) | **是** |
| 升级 deepagents/langgraph 主版本或换 LLM provider | **是** |
| 改动触碰 [CLAUDE.md §强约束](../../CLAUDE.md) 任一条 | **必须是**(spec.md §4 强约束矩阵会强制审视) |
| 改动会影响 frontend vendored patch(见 [architecture.md §3.1](../architecture.md)) | **必须是**(spec.md §5 前端 patch 影响会强制留底) |

判断口诀:**"是否会被未来的我"忘记初衷"**——会就走 SDD,不会就直接干。

---

## 2. 6 步流程

```
1. Spec Discovery           ──★ 用户确认 ──>
2. 起草 spec.md             ──>
3. /sdd-review <dir> spec   ──★ 用户确认 ──>
4. 起草 tasks.md + verification.md 骨架  ──>
5. /sdd-review <dir> tasks  (自动)       ──>
6. 拉分支 → 前端 patch 留底(如需)→ 实现 → verification.md 全绿 → /code-review → PR → 合并
```

**两个 ★ 暂停点不能跳过**:
- **Step 1 后**:Claude 不能擅自开始写 spec.md。必须把"我理解的目标 / 范围 / 关键问题"列出来,等用户回 "OK 开写"。
- **Step 3 后**:`/sdd-review spec` 给出"待人确认事项"清单,用户必须打勾或回 "修改后再来"。Skill 不自动勾状态表。

### 每步详解

#### Step 1 — Spec Discovery

输入:用户需求 + 既有 PRD(若有,在 `docs/prds/`)。
产出:口头/笔记形式的"需求理解 + 范围 + 待澄清问题"。
Claude 行为:**只问问题、只列范围**,不写文档。

#### Step 2 — 起草 spec.md

从模板 `docs/sdd/_templates/spec.md` 复制到 `docs/features/vX.Y.Z/NNN-feature-slug/spec.md`。
版本号 `vX.Y.Z` 与 `backend/pyproject.toml` + `frontend/package.json` 同步管理;序号 `NNN` 在该版本内从 001 起递增。
slug 用 kebab-case,与 feature 主题一致(如 `001-skills-runtime`)。

#### Step 3 — `/sdd-review <dir> spec`

调用合并版 skill 的 spec 模式,对照 10 项检查清单产出报告。
**辅助审查**:skill 不会自动勾"已评审"——必须由用户回 "确认通过" 后才打勾。

#### Step 4 — 起草 tasks.md + verification.md 骨架

- `tasks.md` 必须完整(任务清单 + AC 反查 + 偏差记录)。
- `verification.md` 此时只要骨架(§0 环境 / §1 启动 / §2 AC 列表占位即可),具体步骤在 Step 6 实施过程中补全。

#### Step 5 — `/sdd-review <dir> tasks`

tasks 模式是**自动通过**:全部检查通过即自动勾状态表;有问题才停下来要求修复。

#### Step 6 — 实现并合并

子流程(按顺序):
1. `git checkout -b feat/vX.Y.Z/NNN-slug`(基于 main)
2. **若 spec.md §5 "动 frontend/" = 是**:`cd frontend && git diff > /tmp/patches-NNN.diff` 留底(让 reviewer 与未来的你都能 diff 出新增 patch)
3. 逐任务实现 → 每完成一个勾 tasks.md 中该任务的状态 checkbox
4. 实施中如发现与 spec 不符,**立刻**登记 tasks.md §实际偏差记录;严重偏差回 Step 2 改 spec
5. 边实现边补 verification.md 步骤细节
6. 全部任务完成后,亲手按 verification.md 跑一遍,所有 AC + 回归 + 跨上游适配通过,截图归档到同目录 `screenshots/`
7. 调用 built-in `/code-review` 审 diff,修复发现项
8. 提 PR(英文 conventional commits,如 `feat(skills): add runtime skill loader and whitelist`)
9. squash merge 回 main

---

## 3. 产物布局

```
docs/sdd/                                # 本目录:指南与模板(改这里 ≈ 改流程本身)
├── SDD-Guide.md
└── _templates/
    ├── spec.md
    ├── tasks.md
    └── verification.md

docs/features/                           # feature 实际产物(每个 feature 一个子目录)
└── vX.Y.Z/
    └── NNN-feature-slug/
        ├── spec.md
        ├── tasks.md
        ├── verification.md
        └── screenshots/
            ├── ac-1.png
            └── ...

.claude/skills/sdd-review/SKILL.md       # 合并版审查 skill
```

---

## 4. 与既有文档的关系

```
CLAUDE.md §强约束 (7+1 条)
       │
       ↓ 派生为 spec.md §4 "涉及强约束" 8 行 checkbox
       │ 派生为 verification.md §3 "回归检查" 具体浏览器/网络面板检查点
       ↓
docs/architecture.md §3.1 (前端 patch 表)
       │
       ↓ 派生为 spec.md §5 "前端 patch 影响" checkbox 文件列表
       ↓ 派生为 verification.md §4 "跨上游适配验证"
       │
docs/prds/                               # 业务需求文档(SDD 的 Context 输入)
       │
       ↓ Step 1 Spec Discovery 的输入
       ↓ spec.md §1 概述里引用
       │
docs/troubleshooting.md                  # 跑期问题清单
       │
       ↓ verification.md §3 回归检查的故障对照参考
```

**约定**:
- CLAUDE.md / architecture.md 是"宪法",变动需谨慎,且要同步更新 `docs/sdd/_templates/` 中的相应章节(checkbox 条目)。
- PRD 是"长篇议案",可以频繁修改,但被某个 feature 引用后,该 feature 的 spec.md 是定稿——后续 PRD 改动若与已完成 feature 冲突,起新 feature 修正,不回改旧 feature。

---

## 5. 模板使用速查

| 模板 | 在哪步用 | 关键约束 |
|---|---|---|
| [`_templates/spec.md`](_templates/spec.md) | Step 2 | 6 章节齐全;状态表头部必填;AC 3-7 条 |
| [`_templates/tasks.md`](_templates/tasks.md) | Step 4 | 任务 3-8 个;每任务覆盖 AC;偏差表必有 |
| [`_templates/verification.md`](_templates/verification.md) | Step 4 骨架 / Step 6 补全 | AC 逐条对应步骤 + 截图;回归项对齐 spec.md §4 |

---

## 6. 命名约定

- **feature 目录**:`docs/features/vX.Y.Z/NNN-feature-slug/`
  - `NNN`:三位零填充,每版本内递增(`001`, `002`, ...)
  - `feature-slug`:kebab-case,3-5 词
- **分支**:`feat/vX.Y.Z/NNN-feature-slug`(与目录同名,前缀 `feat/`)
- **commit**:英文 conventional commits,作用域可选,例:
  - `feat(skills): add runtime skill loader and whitelist`
  - `docs(sdd): tweak spec template strong-constraint matrix`
  - `fix(hitl): broadcastResumeInterrupt now handles empty interrupts list`
- **截图**:`docs/features/vX.Y.Z/NNN-slug/screenshots/ac-N.png` 或 `regression-<name>.png`

---

## 7. 何时跳过本流程

- 修 README 的 typo
- 调 `prompts.py` 一句措辞(注意 [CLAUDE.md §强约束](../../CLAUDE.md) 强制语序条目,若动到强制语序仍要走 SDD)
- 调 `.env.example` 字段顺序
- 更新依赖小版本(无 API 变化)
- 改 frontend 一两行样式(无组件结构变化)

跳过时仍要写清楚 commit message,便于将来回溯。

---

## 8. 持续演进

本流程本身也是版本演进对象。如果发现某个步骤经常被跳过、某个检查项总是 N/A、某个模板字段总是空 —— 改这份 Guide 与对应模板,**不要默默跳过**。

修改本目录任何文件,commit message 用 `docs(sdd):` 前缀。
