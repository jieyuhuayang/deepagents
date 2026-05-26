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
