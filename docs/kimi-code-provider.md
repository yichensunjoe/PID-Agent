# Kimi Code provider

Use the Kimi Code OpenAI-compatible endpoint in P&ID-Agent:

```text
Base URL: https://api.kimi.com/coding/v1
Model: kimi-for-coding
API Key: a Kimi Code API key
```

Supported Kimi Code model identifiers include:

- `k3`
- `kimi-for-coding`
- `kimi-for-coding-highspeed`

The Agent panel's **Kimi Code** preset fills the recommended Base URL and default model automatically. A manually entered `https://api.kimi.com/coding/` URL is normalized to the OpenAI-compatible `/coding/v1` endpoint before model discovery, connection tests and generation.

Kimi Code models require `temperature=1`. P&ID-Agent applies that value to normal planning, semantic/schema-repair requests and the minimal connection test while preserving existing sampling values for other OpenAI-compatible providers.

## Troubleshooting

`invalid temperature: only 1 is allowed for this model`

: Update P&ID-Agent to a version containing Issue #43. Confirm that the selected model is one of the Kimi Code identifiers above.

`404` or an incompatible request path

: Use `https://api.kimi.com/coding/v1` for OpenAI-compatible Chat Completions. The address without `/v1` is the Anthropic-compatible entry point in Kimi's documentation.

Authentication failure

: Use a key issued for Kimi Code. Do not interchange Kimi Code keys with Moonshot Open Platform credentials.
