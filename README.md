# P&ID-Agent

P&ID-Agent 是一款轻量、专注于工艺流程图的浏览器 P&ID 软件。

它不是 AutoCAD 的通用替代品，也不计划加入三维建模、机械零件、BIM 或与 P&ID 无关的复杂命令。它只围绕一件事设计：让工程人员和 AI Agent 使用同一套单位图例、同一份结构化图纸和同一套连接语义，共同创建、修改、解释和检查工艺流程图。

> 当前版本：`2.1.0-alpha.1`
>
> 仓库 slug 的规范名称为 `PID-Agent`，产品显示名称为 `P&ID-Agent`。Python 导入路径暂时保留为 `agentcad`，避免已有客户端立即失效。

## 产品目标

- 工程人员可以像使用轻量流程图工具一样自由放置设备、阀门、仪表和文字；
- 工艺管线连接到明确的设备端口或连接节点，而不是退化为无意义线段；
- Agent 可以读取最新设备、位号、端口、管线、分支和汇合拓扑；
- Agent 的修改经过 JSON Schema 和原子事务验证，并且可撤销；
- 单位图例使用声明式 JSON 维护，人工编辑器和 Agent 共用同一份符号定义；
- 最终支持生成和继续编辑与实际复杂 P&ID 相当的工程图纸。

完整产品边界见 [`docs/product-vision.md`](docs/product-vision.md)。

## 当前能力

### P&ID 文档内核

- 文档、图层、图元、设备符号、连接节点和工艺管线统一模型；
- SQLite 持久化；
- 原子批量事务；
- document revision 乐观并发，防止 Agent 覆盖人工修改；
- 完整文档快照撤销和重做；
- JSON、SVG、PNG、标准图幅 PDF 导出；
- 版本化单文档 JSON 与原子项目包导入/导出，可在导入后继续编辑、撤销和重做；
- 场景摘要包含符号端口、连接节点和管线 source/target。

### 浏览器编辑器

- React、TypeScript、Vite、Zustand 和 SVG；
- 设备符号、基础图元、文字和工艺管线；
- 设备端口显示与吸附；
- 正交管线；
- 移动设备后关联管线自动保持连接；
- 单选、Shift 多选和拖拽框选；
- 多元素移动、删除和复制；
- `Ctrl/Cmd+D` 复制选择；
- `Ctrl/Cmd+A` 全选；
- 连接节点工具；
- 在既有管线上放置连接节点时，主管线原子拆分为两段；
- 支路可以吸附到同一连接节点，形成 Agent 可查询的真实分支/汇合拓扑；
- 选择管线后可拖动内部线段手柄，调整折线路径并保持正交；
- 中键平移、滚轮缩放和网格吸附。

### Agent 接入

- OpenAI-compatible Chat Completions 规划器；
- REST API；
- Python Client；
- MCP stdio Server；
- 适用于 OpenAI API、Ollama、LM Studio 及其他 OpenAI-compatible 服务；
- 模型只生成结构化事务，不能绕过服务层直接写数据库。

## 快速开始

要求 Python 3.11+ 和 Node.js 20+。

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[mcp]"

cd frontend
npm install
npm run build
cd ..

pid-agent serve --host 0.0.0.0 --port 8000
```

打开 `http://localhost:8000`。

开发模式：

```bash
# 终端 1
pid-agent serve --reload

# 终端 2
cd frontend
npm run dev
```

旧命令 `agentcad` 和 `agentcad-mcp` 暂时保留为兼容别名。

## 模型配置

```bash
export PID_AGENT_LLM_BASE_URL="http://localhost:11434/v1"
export PID_AGENT_LLM_MODEL="your-model-name"
export PID_AGENT_LLM_API_KEY="optional-api-key"
```

旧的 `AGENTCAD_LLM_*` 环境变量仍可使用，但新部署应使用 `PID_AGENT_*`。

规划流程：

1. 后端读取最新文档、revision 和语义场景摘要；
2. 将单位图例目录与事务 JSON Schema 提供给模型；
3. 模型只返回结构化事务；
4. 后端重新验证图例 key、端口、连接节点、图层和 revision；
5. 整个事务一次成功，或完全不写入。

## 单位图例

内置占位图例：

```text
backend/agentcad/data/symbols.json
```

通过外部路径加载单位图例：

```bash
export PID_AGENT_SYMBOL_PATHS="/path/company-symbols:/path/project-symbols"
```

相同 `key` 的后加载定义会覆盖内置图例。结构说明见 [`docs/symbol-schema.md`](docs/symbol-schema.md)。

每个单位符号建议至少提供：

- 稳定的英文 `key`；
- 中文名称、分类和工程用途；
- 默认宽高和 SVG 基础形状；
- 可连接端口、端口方向和介质类型；
- 位号规则和可填写属性；
- Agent 可理解的使用约束。

## Python 接入

安装的发行包名称为 `pid-agent`，兼容导入路径仍为 `agentcad`：

```python
from agentcad.client import AgentCADClient

with AgentCADClient("http://127.0.0.1:8000") as cad:
    document = cad.create_document("压缩空气系统")
    cad.apply_transaction(document.id, {
        "expected_revision": document.revision,
        "operations": [
            {
                "op": "add_element",
                "element": {
                    "type": "symbol",
                    "symbol_key": "gas_tank",
                    "position": {"x": 180, "y": 160},
                    "width": 90,
                    "height": 140,
                    "label": "V-101"
                }
            }
        ]
    })
```

## MCP 接入

```bash
pid-agent-mcp
# 或
pid-agent mcp
```

通用配置示例：

```json
{
  "mcpServers": {
    "pid-agent": {
      "command": "pid-agent-mcp",
      "env": {
        "PID_AGENT_DATABASE_PATH": "/absolute/path/to/pid-agent.db"
      }
    }
  }
}
```

MCP 工具包括：

- `list_documents`
- `create_document`
- `get_scene_summary`
- `get_document`
- `apply_transaction`
- `list_symbols`

## API 概览

```text
GET    /api/v2/documents
POST   /api/v2/documents
GET    /api/v2/documents/{document_id}
DELETE /api/v2/documents/{document_id}
POST   /api/v2/documents/{document_id}/transactions
POST   /api/v2/documents/{document_id}/undo
POST   /api/v2/documents/{document_id}/redo
GET    /api/v2/documents/{document_id}/scene-summary
GET    /api/v2/documents/{document_id}/export.json
GET    /api/v2/documents/{document_id}/export-v1.json
POST   /api/v2/imports/document
GET    /api/v2/project/settings
PUT    /api/v2/project/settings
GET    /api/v2/project/export.json
POST   /api/v2/imports/project-package
GET    /api/v2/documents/{document_id}/export.svg
GET    /api/v2/documents/{document_id}/export.png
GET    /api/v2/documents/{document_id}/print-preview.svg
GET    /api/v2/documents/{document_id}/export-v2.pdf
POST   /api/v2/documents/{document_id}/agent/generate
GET    /api/v2/symbols
GET    /api/v2/agent/tool-schema
```

运行后访问 `/docs` 查看 OpenAPI。

JSON 格式、冲突策略、原子失败语义、浏览器操作和 Python Client 示例见 [`docs/project-json-import.md`](docs/project-json-import.md)。

PDF 图幅、分页、标题栏、预览和 Python Client 用法见 [`docs/pdf-print-export.md`](docs/pdf-print-export.md)。

`/api/v1` 主要旧端点仍由新文档引擎提供兼容。

## 本地验证

本仓库不依赖 GitHub Actions：

```bash
pytest -q
ruff check backend
cd frontend
npm test
npm run build
npm run test:e2e
```

Playwright 安装、headed 模式、视觉基线更新和 trace 查看方式见 [`docs/browser-e2e-visual-acceptance.md`](docs/browser-e2e-visual-acceptance.md)。

## 近期路线

1. 完善属性编辑、图层和系统显隐；
2. 增加管线折点增删、自动整理和跨线表达；
3. 增加流向箭头、介质、管径、颜色和线型面板；
4. 让 Agent 按自然语言执行局部移动、替换、删除和重新连接；
5. 导入单位图例及历史图纸知识；
6. 自动布局、避让和大型图纸性能优化；
7. 设备表、管线表、仪表索引、规则检查和 DXF。

## License

MIT
