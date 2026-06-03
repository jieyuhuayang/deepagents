---
name: deep-research
description: Use this skill whenever the user asks to research, investigate, survey, compare, or gather multi-source evidence on a topic. It defines the structured deep-research workflow — plan subtopics, delegate parallel research, render result cards, then synthesize a cited report. Trigger on phrases like "调研", "研究", "investigate", "compare X and Y", "summarize the state of ...".
license: MIT
metadata:
  author: lilu
  version: "1.0"
  source: built-in
---

# Deep Research

结构化深度研究流程。当用户要"调研 / 研究 / 对比 / 综述"某主题时,按下面步骤推进,产出有引用的报告。

> 本 skill 是**附加指引**,与主 system prompt 中既有的研究流程一致、互为补充。主 prompt 里的强制工具语序(如 `emit_research_card` 必须先于 `write_file`)始终优先,本文件不覆盖、不弱化它。

## When to use

- 用户请求匹配"研究某主题"领域:`调研 X` / `研究一下 Y` / `compare A and B` / `summarize the latest on ...`。
- 需要多来源取证、交叉验证、并最终给出带引用的结论时。
- 不适用:简单事实问答、闲聊、单步操作 —— 那些直接回答即可,不必走完整流程。

## Instructions

1. **必要时先澄清**:问题含糊(范围/对象/约束不清)时,先调用 `request_clarification` 一次问清,不要在同一轮里夹带其他工具调用;拿到回答再继续。
2. **先规划**:用 `write_todos` 写一份 3-6 条的子主题清单,作为研究骨架。
3. **委派研究**:对每个子主题,调用 `task(subagent_type="research-agent")` 委派给研究子 agent(它会用 `web_search` / `bisheng_retrieve` + `think_tool` 反复取证)。一个子主题一次委派,不在主 agent 里手动搜索。
4. **渲染卡片**:每个 research-agent 返回后,**立即**调用 `emit_research_card`(title / summary / sources)把该子主题的发现渲染成卡片,再处理下一个子主题。
5. **综合成文**:全部子主题完成后,产出 markdown 报告(`write_file` 到 `report.md`);如需 DOCX,在 `report.md` 已存在后调用 `export_docx`。

## Best practices

- 每条结论尽量挂可点击的来源 URL;无法证实的点标注"未证实",不要编造引用。
- 子主题之间用 `think_tool` 做小结与下一步判断,避免一次塞太多检索。
- 内部领域知识(如企业知识库)优先 `bisheng_retrieve`;公网话题用 `web_search`。
- 取证空返回时换关键词重试,不要单次失败就放弃。
