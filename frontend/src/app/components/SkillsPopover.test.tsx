/**
 * AC-4 — SkillsPopover 渲染 / toggle / 持久化。
 *
 * 覆盖 docs/features/v0.6.0/001-skill-loading-whitelist/spec.md AC-4:
 * 打开 popover 渲染拉取到的 skill 列表;toggle Switch 翻转激活态、active-count
 * chip 同步、deep-agent-config.activeSkillIds 写入 localStorage。
 */
import { describe, it, expect, beforeEach, beforeAll, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SkillsPopover, type SkillSummary } from "./SkillsPopover";

// ── Radix Popover 在 jsdom 缺失的浏览器 API 兜底 ──────────────────────────
beforeAll(() => {
  const proto = Element.prototype as unknown as Record<string, unknown>;
  proto.hasPointerCapture = () => false;
  proto.setPointerCapture = () => {};
  proto.releasePointerCapture = () => {};
  proto.scrollIntoView = () => {};
  if (!("ResizeObserver" in globalThis)) {
    (globalThis as unknown as Record<string, unknown>).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const SKILLS: SkillSummary[] = [
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

// jsdom/Node 的全局 localStorage 在本环境缺 clear();用纯内存 Storage 替身,
// 让组件与测试共用同一实现,行为确定。
function memoryStorage(): Storage {
  const m = new Map<string, string>();
  return {
    get length() {
      return m.size;
    },
    clear: () => m.clear(),
    getItem: (k: string) => (m.has(k) ? m.get(k)! : null),
    setItem: (k: string, v: string) => void m.set(k, String(v)),
    removeItem: (k: string) => void m.delete(k),
    key: (i: number) => Array.from(m.keys())[i] ?? null,
  } as Storage;
}

beforeEach(() => {
  vi.stubGlobal("localStorage", memoryStorage());
  localStorage.setItem(
    "deep-agent-config",
    JSON.stringify({ deploymentUrl: "http://localhost:2024", assistantId: "research" })
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 200, json: async () => SKILLS }))
  );
});

function openPopover() {
  fireEvent.click(screen.getByRole("button", { name: "Skills" }));
}

describe("SkillsPopover", () => {
  it("打开后渲染后端返回的 skill 列表(名称 + 描述)", async () => {
    render(<SkillsPopover />);
    openPopover();

    expect(await screen.findByText("deep-research")).toBeInTheDocument();
    expect(screen.getByText("brand-guidelines")).toBeInTheDocument();
    expect(screen.getByText("结构化深度研究流程")).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith("http://localhost:2024/api/skills");
  });

  it("toggle 一个 skill:激活态翻转 + chip 计数 + 持久化到 localStorage", async () => {
    render(<SkillsPopover />);
    openPopover();

    const sw = await screen.findByRole("switch", { name: "toggle deep-research" });
    expect(sw).toHaveAttribute("aria-checked", "false");

    fireEvent.click(sw);

    // 激活态翻转
    await waitFor(() => expect(sw).toHaveAttribute("aria-checked", "true"));

    // 持久化:只写 deep-research 的 name,不写 id
    await waitFor(() => {
      const cfg = JSON.parse(localStorage.getItem("deep-agent-config") || "{}");
      expect(cfg.activeSkillIds).toEqual(["deep-research"]);
      // 不 clobber 既有字段
      expect(cfg.deploymentUrl).toBe("http://localhost:2024");
    });

    // chip 计数同步
    expect(screen.getByTestId("skills-active-count")).toHaveTextContent("1");

    // 再 toggle 回去 → 清空
    fireEvent.click(sw);
    await waitFor(() => {
      const cfg = JSON.parse(localStorage.getItem("deep-agent-config") || "{}");
      expect(cfg.activeSkillIds).toEqual([]);
    });
    expect(screen.queryByTestId("skills-active-count")).not.toBeInTheDocument();
  });
});
