/**
 * skills-whitelist E2E 的 canned 数据。
 *
 * 复用 research-card 的 assistant/thread/state/SSE 形状,只额外提供
 * `GET /api/skills` 的返回(两个 built-in skill),用于驱动 SkillsPopover。
 */
export { ASSISTANT, THREAD, EMPTY_STATE, researchCardStream } from "./research-card";

export const SKILLS = [
  {
    id: "built-in/deep-research",
    name: "deep-research",
    description: "结构化深度研究流程",
    source: "built-in",
    path: "/built-in/deep-research/SKILL.md",
  },
  {
    id: "built-in/brand-guidelines",
    name: "brand-guidelines",
    description: "品牌规范参考",
    source: "built-in",
    path: "/built-in/brand-guidelines/SKILL.md",
  },
];
