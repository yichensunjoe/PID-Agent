# Provider selection and persistent Agent runs

The Agent panel supports preset OpenAI-compatible Base URLs and a custom mode. After a provider is selected and any required API key is entered, the web client requests the provider's `/models` endpoint through the P&ID-Agent backend and populates the model selector. Base URL and model-name fields remain editable for custom services.

API keys remain in page memory only. They are sent with provider discovery, provider tests and generation requests, but are not persisted to the document database or browser storage.

Automatic Agent execution remains mounted while the user switches between Properties, Layers/Systems, History and Agent tabs. The active request, retry trace, cancellation request and any high-risk approval remain available when the Agent tab is reopened.

Connector route normalization removes small grid-scale orthogonal doglegs while retaining larger intentional detours. Endpoint bindings, junction topology and flow-arrow properties remain unchanged.
