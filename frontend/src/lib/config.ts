export interface StandaloneConfig {
  deploymentUrl: string;
  assistantId: string;
  langsmithApiKey?: string;
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
  localStorage.setItem(CONFIG_KEY, JSON.stringify(config));
}
