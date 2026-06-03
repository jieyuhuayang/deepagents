export interface StandaloneConfig {
  deploymentUrl: string;
  assistantId: string;
  langsmithApiKey?: string;
  // 激活的 skill 名白名单(随 run 以 config.configurable.active_skills 提交)。
  // 存 skill 的 `name`(SkillsMiddleware 按 name 合并),不是 id。见
  // docs/features/v0.6.0/001-skill-loading-whitelist/spec.md §4.4。
  activeSkillIds?: string[];
}

const CONFIG_KEY = "deep-agent-config";

function envDefaults(): StandaloneConfig | null {
  const deploymentUrl = process.env.NEXT_PUBLIC_DEPLOYMENT_URL;
  const assistantId = process.env.NEXT_PUBLIC_ASSISTANT_ID;
  if (!deploymentUrl || !assistantId) return null;
  return { deploymentUrl, assistantId };
}

// langgraph SDK 的 `new URL(apiUrl + path)` 不接受相对 URL,必须绝对。
// 当 deploymentUrl 是 `/api/langgraph` 这种同 origin 路径时,在浏览器端
// 拼上 window.location.origin。next.config.ts 的 rewrites 负责把这个
// path 反代到 backend。这样公网/局域网访客通过任何 origin 进来都通用。
// 注意:localStorage 始终存原始值,不存解析后的绝对 URL,避免域名变更导致
// 旧值卡死。所有 `new Client({ apiUrl: ... })` 之前都要过这一层。
export function resolveDeploymentUrl(url: string): string {
  if (typeof window !== "undefined" && url.startsWith("/")) {
    return `${window.location.origin}${url}`;
  }
  return url;
}

export function getConfig(): StandaloneConfig | null {
  if (typeof window === "undefined") return null;

  const stored = localStorage.getItem(CONFIG_KEY);
  if (stored) {
    try {
      return JSON.parse(stored);
    } catch {
      // fall through to env defaults
    }
  }

  return envDefaults();
}

export function saveConfig(config: StandaloneConfig): void {
  if (typeof window === "undefined") return;
  // 保留已存的 activeSkillIds:ConfigDialog 的 StandaloneConfig 不带这个字段,
  // 若直接整体覆写会把 skill 白名单清空(数据丢失)。仅当 config 显式带了该字段
  // 才用新值。activeSkillIds 的常规写入走 saveActiveSkillIds(字段级)。
  const merged: StandaloneConfig = { ...config };
  if (merged.activeSkillIds === undefined) {
    const existing = getActiveSkillIds();
    if (existing.length > 0) merged.activeSkillIds = existing;
  }
  localStorage.setItem(CONFIG_KEY, JSON.stringify(merged));
}

// ── 激活 skill 白名单 ──────────────────────────────────────────────────────
// 与主 config 同存 `deep-agent-config` 对象,读写时只动 activeSkillIds 字段,
// 不 clobber deploymentUrl/assistantId(SkillsPopover 与配置弹窗各管各的字段)。

function readRawConfig(): Record<string, unknown> {
  if (typeof window === "undefined") return {};
  const stored = localStorage.getItem(CONFIG_KEY);
  if (!stored) return {};
  try {
    return JSON.parse(stored);
  } catch {
    return {};
  }
}

export function getActiveSkillIds(): string[] {
  const raw = readRawConfig();
  const ids = raw.activeSkillIds;
  return Array.isArray(ids) ? (ids as string[]) : [];
}

export function saveActiveSkillIds(ids: string[]): void {
  if (typeof window === "undefined") return;
  const raw = readRawConfig();
  raw.activeSkillIds = ids;
  localStorage.setItem(CONFIG_KEY, JSON.stringify(raw));
}
