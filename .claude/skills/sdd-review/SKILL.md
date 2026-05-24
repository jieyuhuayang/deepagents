---
name: sdd-review
description: 审查 deepagents 项目的 SDD 产物(spec.md / tasks.md)。spec 模式辅助审查并请求 ★ 用户确认;tasks 模式自动审查并放行。用于 SDD 6 步流程的 Step 3 与 Step 5。
---

# /sdd-review

合并版 SDD 审查 skill,覆盖 deepagents 轻量版 SDD 的两个评审点。
完整流程见 [`docs/sdd/SDD-Guide.md`](../../../docs/sdd/SDD-Guide.md)。

---

## 调用方式

```
/sdd-review <feature_dir> spec      # 审 spec.md,要求 ★ 用户确认
/sdd-review <feature_dir> tasks     # 审 tasks.md,自动通过
```

`<feature_dir>` 例如:`docs/features/v0.2.0/001-skills-runtime`

### 参数校验(失败立即停)

- `<feature_dir>` 不存在 → 报告 `路径不存在: <feature_dir>`,停止
- 第二参数不是 `spec` 或 `tasks` → 报告 `模式参数必须是 spec 或 tasks`,停止
- 对应模式所需的文件(`spec.md` / `tasks.md`)不存在 → 报告 `找不到文件: <path>`,停止

---

## 模式 A:spec 审查

### 流程

1. 读 `<feature_dir>/spec.md`(必需)、`<feature_dir>/../README.md`(可选,版本上下文)、相关 PRD(若 spec.md §1 引用了 `docs/prds/*`)。
2. 对照下方 **spec 检查清单 10 项** 逐项判断,每项给 ✅ / ❌ / ⚠️ + 说明。
3. 输出审查报告(模板见下)。
4. **暂停**:不自动勾状态表。等用户回 `确认通过` 或 `修改后再审`。
5. 用户回 `确认通过` 后,Claude 把 `spec.md` 状态表中"已评审"行打勾、填评审日期与评审人,然后提示可进入 Step 4。

### spec 检查清单(10 项)

1. **状态表完整**:头部含"已起草 / 已评审 / 已完成"三行,checkbox 在位。
2. **用户故事完整**:§1 至少 1 条用户故事写明 `角色 / 能力 / 价值`;`Context / 来源`字段已填(无 PRD 也要写"无")。
3. **AC 数量合理**:§2 AC 表 3-7 条;每条有唯一 ID;每条都"可手动复现"(不能是"性能 < 100ms"这类无法手测的)。
4. **AC ↔ verification 对应**:每条 AC 的"verification.md 位置"列已指明(verification.md 此时无须已存在,只校验列已填)。
5. **边界与非目标**:§3 同时含至少 1 条边界情况(失败/异常路径)+ 至少 1 条非目标。
6. **强约束矩阵填全**:§4 表 8 行全部勾了"是 / 否";凡"是"的行,缓解策略列必填且非空模板字符串。
7. **前端 patch 影响判断**:§5 "是否动 frontend/" 已勾;若"是",已列出预计修改的已 patch 文件 + 留底命令保留(留底命令是模板必有项,不要被删)。
8. **文件清单与前面章节一致**:§6 文件清单包含 §4-§5 标记影响的所有 frontend patch 文件,且新建/修改性质标注清晰。
9. **不复制代码**:§6 没有大段代码块(> 10 行);spec 不是实现,长度控制在 2 屏内。
10. **架构文档同步项**:若引入新 middleware / 新 patch / 新机制,§6 列出 `docs/architecture.md` 的对应更新计划;若不引入,本项 N/A。

### spec 模式输出模板

```
## SDD Review — Spec

Feature: <name>
File: <feature_dir>/spec.md

### 检查结果

1. ✅ 状态表完整
2. ✅ 用户故事完整
3. ❌ AC 数量合理 — 当前 9 条,建议拆分或合并到 7 条以下
4. ✅ AC ↔ verification 对应
5. ⚠️ 边界与非目标 — 仅 1 条边界,建议补"DashScope 429 限流"路径
...
10. N/A 架构文档同步项 — 本 feature 不引入新机制

### 待人确认事项

- [ ] AC-7 与 AC-8 是否实为同一验收?建议合并
- [ ] §5 标记动 ChatInterface.tsx,但 §6 文件清单未列出,请补

### 结论

⚠️ 需要修改后再次评审。修改要点见上。

(或:✅ 全部通过。请回复 `确认通过` 以勾选状态表。)
```

---

## 模式 B:tasks 审查(自动)

### 流程

1. 读 `<feature_dir>/spec.md`(取 AC 列表、§5 前端 patch 标记)+ `<feature_dir>/tasks.md`(必需)+ `<feature_dir>/verification.md`(若存在)。
2. 对照下方 **tasks 检查清单 11 项** 逐项判断。
3. 若全部通过 → **自动**把 `tasks.md` 状态表"已评审"行勾上,填评审日期,提示可进入 Step 6。
4. 若有失败项 → 输出报告,**不**勾状态表,等待修改后重跑。

### tasks 检查清单(11 项)

1. **状态表完整**:含三阶段 checkbox。
2. **任务数合理**:3-8 个;< 3 提示"是否过粗",> 8 提示"考虑拆 feature"。
3. **每任务字段完整**:状态、文件、逻辑、验证方式、覆盖 AC、依赖六项齐全。
4. **AC 双向覆盖**:§"AC 覆盖反查"表中每个 AC 都被至少 1 个任务覆盖;任务里引用的 AC ID 都存在于 spec.md §2。
5. **依赖关系合法**:每个任务的"依赖"字段只引用已定义的 TaskID 或 "无";不允许循环依赖。
6. **前端 patch 留底任务**:若 spec.md §5 "动 frontend/" = 是,tasks.md 第一个任务必须是 `cd frontend && git diff > /tmp/patches-NNN.diff` 留底;否则本项 N/A。
7. **强约束触碰映射到验证**:spec.md §4 标记"是"的强约束,在某个任务的"验证方式"字段或 verification.md 计划里有对应回归项。
8. **verification.md 骨架存在**:同目录有 `verification.md`,且 §0(环境)、§1(启动)、§2(AC 列表占位,无须详细步骤)已经成形。
9. **偏差章节存在**:§"实际偏差记录"表头与示例行存在(允许内容为空)。
10. **依赖图(条件)**:任务数 ≥ 5 时已绘制简单文字依赖图;< 5 时本项 N/A。
11. **无虚构文件路径**:所有"文件"字段引用的路径要么是项目已有的(grep 能找到),要么明确标记为"新建"。

### tasks 模式输出模板

```
## SDD Review — Tasks (auto)

Feature: <name>
Tasks: <feature_dir>/tasks.md

### 检查结果

1. ✅ 状态表完整
2. ✅ 任务数 5 个
3. ✅ 字段完整
4. ✅ AC 双向覆盖(AC-1 ~ AC-5 全覆盖,T1-T5 引用 AC 合法)
5. ✅ 依赖关系合法
6. ✅ 前端 patch 留底任务(T1)
7. ✅ 强约束→验证映射(verification.md §3 含 ResearchCard / HITL 回归项)
8. ✅ verification.md 骨架存在
9. ✅ 偏差章节存在
10. ✅ 依赖图已绘制
11. ✅ 无虚构文件路径

### 结论

✅ 全部通过。已自动勾选 tasks.md 状态表"已评审"。
可以进入 Step 6:拉 feature 分支 → 前端 patch 留底 → 实现 → verification.md 跑完 → /code-review → PR → 合并。
```

---

## 与 deepagents 项目的耦合点

- **模式 A 第 6 项**强约束检查依赖 [`CLAUDE.md` §强约束](../../../CLAUDE.md) 节的 8 条目(顺序与 spec.md §4 表对齐)。若 CLAUDE.md 改动,本 skill 检查清单与 spec.md 模板同步更新。
- **模式 B 第 6 项**依赖 [`docs/architecture.md` §3.1](../../../docs/architecture.md) 的 patch 表。若 patch 表新增/删除文件,本 skill 的检查项 + spec.md §5 模板的 checkbox 列表同步更新。
- **不做 `/task-review` 与 `/e2e-test`**:实现阶段质量由 built-in `/code-review`(审 diff)+ `verification.md`(手动验证清单)兜底。如未来发现 verification.md 频繁漏检,再考虑拆 `/e2e-test` skill。
