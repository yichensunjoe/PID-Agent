export type ProviderPreset = {
  id: string;
  label: string;
  baseUrl: string;
  requiresApiKey: boolean;
  note: string;
  aliases?: string[];
};

export const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    id: "openai-compatible",
    label: "OpenAI 兼容端点",
    baseUrl: "https://api.openai.com/v1",
    requiresApiKey: true,
    note: "标准 OpenAI-compatible API 端点",
  },
  {
    id: "ollama",
    label: "Ollama（本地）",
    baseUrl: "http://127.0.0.1:11434/v1",
    requiresApiKey: false,
    note: "本地 Ollama 开源模型服务",
  },
  {
    id: "lmstudio",
    label: "LM Studio（本地）",
    baseUrl: "http://127.0.0.1:1234/v1",
    requiresApiKey: false,
    note: "本地 LM Studio 模型服务",
  },
  {
    id: "custom",
    label: "自定义端点",
    baseUrl: "",
    requiresApiKey: false,
    note: "手动输入任意 OpenAI-compatible 服务地址",
  },
];

function normalizePresetUrl(baseUrl: string): string {
  return baseUrl.trim().replace(/\/$/, "");
}

export function presetForBaseUrl(baseUrl: string): string {
  const normalized = normalizePresetUrl(baseUrl);
  return PROVIDER_PRESETS.find((preset) =>
    [preset.baseUrl, ...(preset.aliases ?? [])].some((candidate) => normalizePresetUrl(candidate) === normalized),
  )?.id ?? "custom";
}
