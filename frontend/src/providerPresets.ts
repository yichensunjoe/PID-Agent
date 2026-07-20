export type ProviderPreset = {
  id: string;
  label: string;
  baseUrl: string;
  requiresApiKey: boolean;
  note: string;
};

export const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    id: "openai",
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    requiresApiKey: true,
    note: "OpenAI 官方 API",
  },
  {
    id: "deepseek",
    label: "DeepSeek",
    baseUrl: "https://api.deepseek.com",
    requiresApiKey: true,
    note: "DeepSeek OpenAI-compatible API",
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    baseUrl: "https://openrouter.ai/api/v1",
    requiresApiKey: true,
    note: "统一访问多家模型",
  },
  {
    id: "groq",
    label: "Groq",
    baseUrl: "https://api.groq.com/openai/v1",
    requiresApiKey: true,
    note: "Groq OpenAI-compatible API",
  },
  {
    id: "ollama",
    label: "Ollama（本机）",
    baseUrl: "http://127.0.0.1:11434/v1",
    requiresApiKey: false,
    note: "本机 Ollama 服务",
  },
  {
    id: "lmstudio",
    label: "LM Studio（本机）",
    baseUrl: "http://127.0.0.1:1234/v1",
    requiresApiKey: false,
    note: "本机 LM Studio 服务",
  },
  {
    id: "custom",
    label: "自定义",
    baseUrl: "",
    requiresApiKey: false,
    note: "手工输入任意 OpenAI-compatible 服务",
  },
];

export function presetForBaseUrl(baseUrl: string): string {
  const normalized = baseUrl.trim().replace(/\/$/, "");
  return PROVIDER_PRESETS.find((preset) => preset.baseUrl.replace(/\/$/, "") === normalized)?.id ?? "custom";
}
