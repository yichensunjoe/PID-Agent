# 自定义模型 API

P&ID-Agent 网页内置 Agent 支持任意 OpenAI-compatible 模型服务。用户可以在右侧 **自定义模型 API** 面板填写：

- Base URL，可包含主机、端口和 `/v1` 路径；
- API Key，本地无鉴权服务可留空；
- Model，必须使用服务端实际识别的模型名称；
- Timeout，范围 10～600 秒。

示例：

```text
Base URL: http://127.0.0.1:11434/v1
API Key:  留空
Model:    qwen3.6:35b
```

云端兼容服务示例：

```text
Base URL: https://provider.example.com/v1
API Key:  sk-...
Model:    provider-model-name
```

Kimi Code 示例：

```text
Base URL: https://api.kimi.com/coding/v1
API Key:  从 Kimi Code 控制台创建的 Key
Model:    kimi-for-coding
```

也可以输入 `https://api.kimi.com/coding/`，后端会将其规范化为 OpenAI-compatible `/coding/v1` 地址。`k3`、`kimi-for-coding` 和 `kimi-for-coding-highspeed` 会自动使用 Kimi 要求的 `temperature=1`；其他 OpenAI-compatible 模型继续使用原有采样值。不要将 Kimi Code Key 与 `api.moonshot.cn` 的开放平台 Key 混用。

## 连接测试

点击 **测试连接** 后，后端优先请求：

```text
{base_url}/models
```

如果供应商没有实现模型列表接口并返回 404 或 405，P&ID-Agent 会改用一次最小 `/chat/completions` 请求验证模型调用能力。

测试结果会显示：

- 连接是否成功；
- 指定模型是否出现在模型列表中；
- 使用的测试方式；
- 请求耗时；
- 鉴权、超时或连接错误。

## 密钥处理

API Key：

- 只保存在当前网页组件的内存状态；
- 只随“测试连接”或“生成并应用”请求发送；
- 不写入 SQLite 文档数据库；
- 不写入浏览器 localStorage；
- 不包含在成功响应或结构化错误响应中。

关闭或刷新页面后，需要重新输入 API Key。

## 环境变量模式

也可以不在网页填写连接信息，改为在服务端设置：

```bash
export PID_AGENT_LLM_BASE_URL=http://127.0.0.1:11434/v1
export PID_AGENT_LLM_MODEL=qwen3.6:35b
export PID_AGENT_LLM_API_KEY=optional
```

网页字段优先于环境变量。通过 MCP 使用外部 Agent 时，不需要填写网页中的自定义模型 API。
