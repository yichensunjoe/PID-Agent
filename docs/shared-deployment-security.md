# 共享部署安全基线

P&ID-Agent 默认使用 `local` 部署模式，保持单机和可信内网用户的现有行为。部署到多人服务器、容器平台或反向代理后，应显式切换到 `shared` 模式。

## 模式与认证

本地模式不强制登录，并允许 Ollama、LM Studio 等回环或私网模型服务：

```bash
export PID_AGENT_DEPLOYMENT_MODE=local
pid-agent serve --host 127.0.0.1 --port 8000
```

共享模式必须配置服务访问令牌和明确的浏览器 Origin；缺少令牌、使用 `*` CORS 或 Origin 格式错误时，进程会拒绝启动：

```bash
export PID_AGENT_DEPLOYMENT_MODE=shared
export PID_AGENT_API_TOKEN='replace-with-a-long-random-token'
export PID_AGENT_CORS_ORIGINS='https://pid.example.com'
pid-agent serve --host 0.0.0.0 --port 8000
```

所有 `/api/` HTTP 接口在配置令牌后都要求：

```text
Authorization: Bearer <token>
```

`/health` 保持公开，供容器和负载均衡健康检查使用。共享模式关闭 `/docs`、`/redoc` 和 `/openapi.json`。MCP stdio 直接调用本地服务层，不经过 HTTP Bearer 认证，因此本地 MCP 工作流不受影响。

浏览器中的服务访问令牌默认只写入当前标签页的 `sessionStorage`，不写入 URL 或 `localStorage`；关闭标签页后失效。Python Client 可直接传入令牌：

```python
from agentcad.client import AgentCADClient

with AgentCADClient("https://pid.example.com", token="service-token") as cad:
    documents = cad.list_documents()
```

不要把令牌放入 query string、书签、反向代理访问日志或前端构建环境变量。

## Provider 网络出口策略

Provider Base URL 只接受 `http` 和 `https`，不得包含 username、password、query 或 fragment。所有模型列表、连接测试、普通规划、语义规划、Schema 修复和自动重规划都使用同一后端策略。

`shared` 模式会检查字面 IPv4/IPv6、IPv4-mapped IPv6 以及 hostname 的全部 A/AAAA 解析结果，并默认拒绝：

- loopback；
- private network；
- link-local；
- multicast；
- unspecified；
- reserved；
- 常见云元数据地址。

HTTP redirect 默认不跟随；返回 redirect 时会先验证目标，再要求管理员直接配置最终 Base URL。这样不会因为前端按钮状态或某个单独 planner 的遗漏而绕过策略。

企业内网模型必须显式 allowlist：

```bash
# 精确 hostname 或 *.example.com 通配后缀
export PID_AGENT_PROVIDER_ALLOW_HOSTS='models.internal,*.model.corp.example'

# 或精确允许的网络范围
export PID_AGENT_PROVIDER_ALLOW_CIDRS='10.20.0.0/16,fd42:100::/48'
```

allowlist 是安全边界，应尽量小，并与网络防火墙或容器 egress policy 一起使用。`local` 模式仍允许 `http://localhost:11434/v1` 和 `http://127.0.0.1:1234/v1`。

## 请求与响应边界

可通过环境变量调整单实例边界：

| 环境变量 | 默认值 | 用途 |
| --- | ---: | --- |
| `PID_AGENT_MAX_JSON_BODY_BYTES` | 2 MiB | 普通 JSON 请求正文 |
| `PID_AGENT_MAX_IMPORT_BODY_BYTES` | 25 MiB | 文档/项目包导入正文 |
| `PID_AGENT_PROVIDER_MAX_RESPONSE_BYTES` | 4 MiB | Provider 响应 |
| `PID_AGENT_MAX_CONCURRENT_REQUESTS` | 32 | 单进程并发请求 |
| `PID_AGENT_AGENT_TIMEOUT_SECONDS` | 180 | Agent/Provider 超时上限 |

超限分别返回明确的 `413`、`429`、`502` 或 `504` 错误。内存并发限制只作用于单实例；多副本部署仍应在反向代理或 API Gateway 配置全局限流、连接限制和上传上限。

## 浏览器响应安全

应用响应包含 `X-Content-Type-Options`、`Referrer-Policy`、frame 防护及与当前 React/Vite production 前端兼容的 Content Security Policy。共享模式只允许配置的 Origin，并继续允许 `Authorization` 请求头。

P&ID-Agent 不负责终止公网 TLS。生产部署应在 Caddy、Nginx、Traefik、云负载均衡或同类反向代理上：

1. 终止 HTTPS；
2. 将请求代理到仅内网可达的 P&ID-Agent 端口；
3. 设置上传大小、全局频率和连接上限；
4. 不记录 Authorization、Cookie 或请求正文；
5. 限制容器到非必要内网和云元数据网络的出口。

## 诊断与凭据

诊断记录会脱敏 Authorization、Cookie、API Key、token、password、完整 prompt/context 和异常正文。诊断导出只包含文档 ID、revision 和计数，不包含完整项目快照、上传正文或 Provider credential。

仍应把 diagnostics 文件视为内部运维数据，限制文件权限、保留周期和下载权限。Playwright CI 使用虚构令牌，不使用真实 Provider Key，并检查文本测试产物中不存在测试令牌。
