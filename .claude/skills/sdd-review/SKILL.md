---
name: sdd-review
description: 审查 deepagents 项目的 SDD 产物(spec.md / tasks.md)。spec 模式辅助审查并用选项式确认请求用户拍板;tasks 模式自动审查并放行。用于 SDD 6 步流程的 Step 3 与 Step 5。
---

# /sdd-review

deepagents SDD 的两个评审点。完整流程见 [`docs/sdd/SDD-Guide.md`](../../../docs/sdd/SDD-Guide.md)。
本项目是 **2 件套(spec + tasks)+ 三层测试** 模型,无独立 verification.md。

---

## 调用方式

```
/sdd-review <feature_dir> spec      # 审 spec.md,选项式请用户确认
/sdd-review <feature_dir> tasks     # 审 tasks.md,自动通过
```

`<feature_dir>` 例如:`docs/features/v0.6.0/001-some-feature`

### 参数校验(失败立即停)

- `<feature_dir>` 不存在 → 报 `路径不存在: <feature_dir>`,停止
- 第二参数不是 `spec` / `tasks` → 报 `模式参数必须是 spec 或 tasks`,停止
- 对应文件(`spec.md` / `tasks.md`)不存在 → 报 `找不到文件: <path>`,停止

---

## 模式 A:spec 审查

### 流程

1. 读 `<feature_dir>/spec.md`(必需)+ spec §1 引用的 PRD(若有)+ [`CLAUDE.md §强约束`](../../../CLAUDE.md)。
2. 对照 **spec 检查清单 9 项** 逐项判断,每项 ✅ / ❌ / ⚠️ + 说明。
3. 输出审查报告。
4. **★ 选项式确认**:用 AskUserQuestion 发一个问题"spec 评审结论如何处理?",选项:`通过(勾状态表)` / `我来改后再审` / `按报告改完再审`。**不开放式多轮对话,不自动勾状态表。**
5. 用户选"通过"后,把 `spec.md` 状态表"已评审"行打勾、填日期与评审人,提示可进入 Step 4。

### spec 检查清单(9 项)

1. **状态表完整**:含"已起草 / 已评审 / 已完成"三行 checkbox。
2. **用户故事完整**:§1 至少 1 条写明 `角色 / 能力 / 价值`;`Context / 来源` 已填(无则写"无")。
3. **AC 数量与可测**:§2 表 3-7 条;每条有唯一 ID;**每条"验证方式"指向一个可自动跑的测试**(`pytest::` / `vitest::` / `e2e::`);写"手动"的必须说明为何无法自动化(仅限纯 lab host 部署类)。
4. **UI 交互有 E2E**:凡 §1/§2 含界面交互(卡片渲染、HITL 审批、导出下载、文件查看等)的 AC,至少 1 条由 `e2e::` 覆盖。
5. **边界与非目标**:§3 含至少 1 条边界(失败/异常路径)+ 至少 1 条非目标。
6. **强约束矩阵填全**:§4 表 8 行全勾"是/否";凡"是"的行缓解策略非空;触碰的可机检项确认 `scripts/arch-guard.sh` + `backend/tests/test_arch_invariants.py` 仍覆盖(必要时已计划补断言)。
7. **前端 patch 影响判断**:§5 "是否动 frontend/" 已勾;若"是",列出预计修改的已 patch 文件 + 留底命令保留 + 改动组件有配对 `vitest::`;若新增前端测试依赖/配置,已登记 architecture.md §3.1。
8. **文件清单一致**:§6 清单含 §2(测试文件)、§4-§5(强约束/patch 文件),新建/修改性质清晰;不复制大段代码(spec 长度 ≤ 2 屏)。
9. **架构文档同步项**:若引入新 middleware / 新 patch / 新机制,§6 列出 `docs/architecture.md` 更新计划;否则 N/A。

### spec 模式输出模板

```
## SDD Review — Spec

Feature: <name> · File: <feature_dir>/spec.md

### 检查结果
1. ✅ 状态表完整
2. ✅ 用户故事完整
3. ❌ AC 可测 — AC-4 验证方式写"手动"但属 UI 渲染,应改 e2e::xxx
4. ⚠️ UI 交互有 E2E — 有卡片渲染 AC 但未见 e2e:: 覆盖
...
9. N/A 架构文档同步项 — 本 feature 不引入新机制

### 待人确认事项
- [ ] AC-4 改为 e2e:: 还是确实无法自动化?
- [ ] §5 标记动 ChatMessage.tsx,但 §6 文件清单未列其 .test.tsx,请补

### 结论
⚠️ 需要修改后再次评审(或:✅ 全部通过)。
```
随后用 AskUserQuestion 做 ★ 选项式确认。

---

## 模式 B:tasks 审查(自动)

### 流程

1. 读 `<feature_dir>/spec.md`(取 AC、§5 前端 patch 标记)+ `<feature_dir>/tasks.md`(必需)。
2. 对照 **tasks 检查清单 11 项** 逐项判断。
3. 全过 → **自动**勾 `tasks.md` 状态表"已评审"、填日期,提示进 Step 6。
4. 有失败项 → 输出报告,**不**勾状态表,等修改后重跑。

### tasks 检查清单(11 项)

1. **状态表完整**:三阶段 checkbox。
2. **任务数合理**:3-8 个;<3 提示"过粗",>8 提示"考虑拆 feature"。
3. **每任务字段完整**:状态 / 文件 / 逻辑 / 验证方式 / 覆盖 AC / 依赖。
4. **AC 双向覆盖**:§AC 覆盖反查表中每个 AC 被 ≥1 任务覆盖;任务引用的 AC ID 都存在于 spec §2;反查表标了验证测试。
5. **依赖关系合法**:依赖字段只引用已定义 TaskID 或 "无";无循环依赖;任务数 ≥5 已画文字依赖图。
6. **后端 Test-First 配对**:确定性后端面(tools/web_search/server 工具函数/路由)有"测试任务在前、实现任务在后"的配对;基础设施任务可无配对。
7. **前端 Test-Alongside**:改动前端组件的任务,文件含配对 `.test.tsx`,验证方式标 `vitest::`。
8. **E2E 任务存在**:spec 有 UI 交互类 AC 时,末尾有一个 Playwright E2E 任务(验证方式 `e2e::`,文件含 `frontend/e2e/*.spec.ts` + fixture)。
9. **前端 patch 留底任务**:若 spec §5 "动 frontend/" = 是,tasks 第一个任务是 `cd frontend && git diff > /tmp/patches-NNN.diff` 留底;否则 N/A。
10. **偏差章节存在**:§实际偏差记录表头存在(内容可空)。
11. **无虚构文件路径**:"文件"字段引用的路径要么项目已有(grep 能找到),要么明确标"新建"。

### tasks 模式输出模板

```
## SDD Review — Tasks (auto)

Feature: <name> · Tasks: <feature_dir>/tasks.md

### 检查结果
1. ✅ 状态表完整
2. ✅ 任务数 5 个
...
6. ✅ 后端 Test-First 配对(T2 测试 → T3 实现)
7. ✅ 前端 Test-Alongside(T4 含 Comp.test.tsx)
8. ✅ E2E 任务存在(T5,e2e::research-card)
...

### 结论
✅ 全部通过。已自动勾选 tasks.md "已评审"。
可进入 Step 6:拉分支/worktree → 前端 patch 留底 → 实现(测试先红→实现绿)→ 6.5 强制 E2E → 三层全绿 → /code-review → PR → 合并。
```

---

## 与 deepagents 项目的耦合点

- **spec 第 6 项**强约束检查依赖 [`CLAUDE.md §强约束`](../../../CLAUDE.md) 的 8 条(顺序与 spec §4 表对齐),并与 `scripts/arch-guard.sh` + `backend/tests/test_arch_invariants.py` 的可机检 5 条一致。CLAUDE.md 改动时,本清单 + spec 模板 §4 + arch-guard + test_arch_invariants **四处同步**。
- **spec 第 7 项 / tasks 第 9 项**依赖 [`docs/architecture.md §3.1`](../../../docs/architecture.md) 的 patch 表。patch 表增删时,本检查项 + spec 模板 §5 同步。
- **不做 `/task-review`**:实现阶段质量由三层测试 + built-in `/code-review` 兜底。E2E 生成见 [`/e2e-test`](../e2e-test/SKILL.md)。
