# Issue #1 最终联合验收

## 状态

Issue #1 的确定性编辑、语义事务、诊断、自动整理和大型图纸能力已经实现。最终剩余项是不同真实模型的自然语言稳定性和重规划收敛率。

这些项目不能通过假模型或静态检查替代。仓库现在提供可重复的真实 Provider 矩阵，只有报告达到阈值后才关闭 Issue #1。

## 五个场景

每个 Provider 对以下场景独立创建临时 SQLite 文档：

1. `add_connect`：新增设备并用指定 connector ID 连接真实端口；
2. `move`：局部移动设备，并保持原 connector 端口绑定；
3. `replace`：替换设备，保持 element ID、connector ID 和端口关系；
4. `reconnect`：把现有 connector 的指定端点重连到另一真实端口；
5. `delete`：使用连接策略删除设备和关联管线，不误删无关设备。

模型返回合法 JSON 不代表通过。每个场景必须经过：

```text
自然语言规划
→ 语义 schema 校验
→ 语义 operation 编译
→ 完整文档副本验证
→ 必要时最多 3 次结构化重规划
→ 原子应用到临时数据库
→ 最终设备、connector 和端口拓扑断言
```

临时数据库在场景结束后删除，不污染用户文档。

## 单 Provider 验收阈值

- 至少重复 3 次；
- 5 个场景每次都通过；
- 不允许 `blocked`；
- 不允许事务已应用但最终拓扑断言失败；
- 重规划候选必须最终收敛；
- API Key 不得出现在响应、报告或诊断日志中。

达到阈值时报告中的 `accepted` 才为 `true`。少于 3 次的运行属于试跑，即使全部通过也不会标记正式验收通过。

## Issue #1 关闭阈值

至少提供 3 份 `accepted=true` 的不同模型报告：

1. Agnes API，例如 `agnes-2.0-flash`；
2. Ollama 本地模型；
3. 另一个 OpenAI-compatible 云端或本地模型。

同时完成：

```bash
pytest -q
ruff check backend
cd frontend && npm run build
PYTHONPATH=backend python backend/benchmarks/benchmark_large_documents.py \
  --counts 500 1000 2500 5000 --iterations 5
```

## 浏览器运行

启动服务后打开：

```text
http://127.0.0.1:8000/api/v2/acceptance/model-matrix/ui
```

页面字段：

- Base URL；
- Model；
- API Key；
- 超时；
- 重复次数；
- 最大重规划次数。

API Key 只存在页面内存和当前请求中，不使用 localStorage、sessionStorage 或 SQLite。完成后点击“下载 JSON 报告”。

## CLI 运行

Agnes 示例：

```bash
read -s AGNES_API_KEY
export AGNES_API_KEY

pid-agent model-matrix \
  --base-url https://apihub.agnes-ai.com/v1 \
  --model agnes-2.0-flash \
  --api-key "$AGNES_API_KEY" \
  --timeout 180 \
  --repetitions 3 \
  --max-replans 3 \
  --output reports/agnes-2.0-flash.json
```

Ollama 示例：

```bash
pid-agent model-matrix \
  --base-url http://127.0.0.1:11434/v1 \
  --model qwen3.6:35b \
  --timeout 240 \
  --repetitions 3 \
  --max-replans 3 \
  --output reports/ollama-qwen.json
```

退出码：

- `0`：该 Provider 达到正式验收阈值；
- `2`：试跑、失败、阻塞或未达到重复次数阈值。

## REST

```http
POST /api/v2/acceptance/model-matrix
Content-Type: application/json
```

```json
{
  "provider": {
    "base_url": "https://apihub.agnes-ai.com/v1",
    "model": "agnes-2.0-flash",
    "api_key": "request-memory-only",
    "timeout_seconds": 180
  },
  "repetitions": 3,
  "max_replans": 3
}
```

报告包含：

- Provider Base URL 和模型名；
- 总场景数；
- passed、failed、blocked 数量；
- pass rate；
- 重规划 convergence rate；
- 每个场景的尝试次数、issue code、耗时和最终拓扑断言结果；
- `accepted`。

不包含 API Key、Authorization、完整 Prompt、完整工程上下文或模型原始正文。

## 诊断事件

```text
acceptance.model_matrix.started
acceptance.model_matrix.completed
acceptance.model_matrix.failed
```

记录 Provider 地址、模型、重复次数、重规划上限、通过/失败/阻塞数量、通过率、收敛率、总耗时和最终 accepted 状态。`api_key_present` 只表示是否配置，不保存值。

## 当前执行环境限制

本切片尝试使用 Hugging Face 托管作业执行公开模型实测，但服务返回 HTTP 402：预付余额不足。该结果属于外部执行环境阻塞，不计入模型通过报告，也不能用于关闭 Issue #1。
