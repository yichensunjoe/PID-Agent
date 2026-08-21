# OpenAI-Compatible Model Provider

P&ID-Agent connects to any standard OpenAI-compatible API endpoint (such as local Ollama, LM Studio, vLLM, or remote gateways).

```text
Base URL: http://127.0.0.1:11434/v1 (or your provider's OpenAI-compatible base URL)
Model:    your-model-name
API Key:  optional / your API key
```

The Web UI automatically discovers available models from the `/models` endpoint when clicking "发现模型", or you can directly type any model identifier supported by your service.

## Configuration via Environment Variables

You can also configure the server default via environment variables:

```bash
export PID_AGENT_LLM_BASE_URL="http://127.0.0.1:11434/v1"
export PID_AGENT_LLM_MODEL="your-model-name"
export PID_AGENT_LLM_API_KEY="optional-api-key"
```
