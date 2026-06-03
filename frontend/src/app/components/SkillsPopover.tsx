"use client";

import { useCallback, useState } from "react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  getActiveSkillIds,
  getConfig,
  resolveDeploymentUrl,
  saveActiveSkillIds,
} from "@/lib/config";

export interface SkillSummary {
  id: string;
  name: string;
  description: string;
  source: string;
  path: string;
}

/**
 * 聊天框内的 Skill 开关入口。
 *
 * - 打开时向后端拉 `GET /api/skills`(不缓存,避免与磁盘不一致)。
 * - 每个 skill 一行:名称 + 描述 + Switch;勾选写入 `deep-agent-config.activeSkillIds`
 *   (存 skill `name`),由 useChat 在 submit 时读出随 run 提交。
 * - 触发按钮显示已激活数量 chip。
 *
 * 详见 docs/features/v0.6.0/001-skill-loading-whitelist/spec.md §4.1 / AC-4 / AC-5。
 */
export function SkillsPopover() {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [activeIds, setActiveIds] = useState<string[]>(() => getActiveSkillIds());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSkills = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const cfg = getConfig();
      const base = resolveDeploymentUrl(cfg?.deploymentUrl ?? "");
      const res = await fetch(`${base}/api/skills`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSkills((await res.json()) as SkillSummary[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
      setSkills([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const onOpenChange = useCallback(
    (open: boolean) => {
      if (open) {
        setActiveIds(getActiveSkillIds());
        void fetchSkills();
      }
    },
    [fetchSkills]
  );

  const toggle = useCallback((name: string, on: boolean) => {
    setActiveIds((prev) => {
      const next = on ? [...new Set([...prev, name])] : prev.filter((n) => n !== name);
      // 在 updater 外持久化:updater 须为纯函数(StrictMode/transition 可能重放)。
      saveActiveSkillIds(next);
      return next;
    });
  }, []);

  const activeCount = activeIds.length;

  return (
    <Popover onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <Button variant="outline" type="button" aria-label="Skills">
          <Sparkles size={16} />
          <span>Skills</span>
          {activeCount > 0 && (
            <span
              data-testid="skills-active-count"
              className="ml-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs text-primary-foreground"
            >
              {activeCount}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent>
        <div className="px-2 py-1.5 text-sm font-medium text-primary">Skills</div>
        {loading && (
          <div className="px-2 py-3 text-xs text-tertiary">加载中…</div>
        )}
        {error && !loading && (
          <div className="px-2 py-3 text-xs text-destructive">加载失败:{error}</div>
        )}
        {!loading && !error && skills.length === 0 && (
          <div className="px-2 py-3 text-xs text-tertiary">暂无 skill</div>
        )}
        <ul className="flex flex-col gap-1">
          {skills.map((s) => {
            const on = activeIds.includes(s.name);
            return (
              <li
                key={s.id}
                className="flex items-start justify-between gap-2 rounded-md px-2 py-2 hover:bg-muted"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-primary">{s.name}</div>
                  <div className="line-clamp-2 text-xs text-tertiary">{s.description}</div>
                </div>
                <Switch
                  checked={on}
                  onCheckedChange={(v) => toggle(s.name, v)}
                  aria-label={`toggle ${s.name}`}
                />
              </li>
            );
          })}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
