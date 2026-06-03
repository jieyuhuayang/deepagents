/**
 * code-review 回归:saveConfig 不得清空 activeSkillIds。
 *
 * ConfigDialog 的 StandaloneConfig 不带 activeSkillIds,若整体覆写会把 skill
 * 白名单清空(数据丢失)。saveConfig 应保留已存白名单。
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  saveConfig,
  saveActiveSkillIds,
  getActiveSkillIds,
} from "./config";

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
});

describe("saveConfig × activeSkillIds", () => {
  it("不带 activeSkillIds 的 saveConfig 保留已存白名单", () => {
    saveActiveSkillIds(["deep-research"]);
    saveConfig({ deploymentUrl: "http://x", assistantId: "research" });
    expect(getActiveSkillIds()).toEqual(["deep-research"]);
  });

  it("显式带 activeSkillIds 时以新值为准", () => {
    saveActiveSkillIds(["deep-research"]);
    saveConfig({ deploymentUrl: "http://x", assistantId: "research", activeSkillIds: [] });
    expect(getActiveSkillIds()).toEqual([]);
  });

  it("saveActiveSkillIds 不 clobber 既有 deploymentUrl", () => {
    saveConfig({ deploymentUrl: "http://x", assistantId: "research" });
    saveActiveSkillIds(["a", "b"]);
    const raw = JSON.parse(localStorage.getItem("deep-agent-config") || "{}");
    expect(raw.deploymentUrl).toBe("http://x");
    expect(raw.activeSkillIds).toEqual(["a", "b"]);
  });
});
