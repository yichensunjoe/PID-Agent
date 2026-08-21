# Provider selection and persistent Agent runs

The Agent panel supports preset OpenAI-compatible Base URLs and custom endpoints (such as local Ollama, LM Studio, or remote OpenAI-compatible proxies). After entering a Base URL and optional API key, the web client can request the provider's `/models` endpoint to discover available models dynamically, or the user can manually enter any model identifier.

API keys remain in page memory only. They are sent with provider discovery, provider tests and generation requests, but are not persisted to the document database or browser storage. Diagnostics record only whether a key was present.

Automatic Agent execution remains mounted while the user switches between Properties, Layers/Systems, History and Agent tabs. The active request, retry trace, cancellation request and any high-risk approval remain available when the Agent tab is reopened.

Connector route normalization removes local orthogonal doglegs whose transverse offset is no larger than one document grid interval. Larger intentional detours remain unchanged. Endpoint bindings, junction topology and flow-arrow properties are preserved.
