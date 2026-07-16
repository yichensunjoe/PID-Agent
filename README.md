# AgentCAD 2

AgentCAD 是一个面向 AI Agent、工程人员和 P&ID 场景的二维流程图文档引擎。

核心目标不是让模型直接“画一张不可编辑的图片”，而是让模型与人在同一份结构化文档上协作：

- Agent 根据自然语言和工艺上下文生成经过校验的绘图事务；
- 浏览器编辑器可以继续移动、删除、补充图元和单位图例；
- 每次修改都会形成新的 document revision；
- Agent 可以读取最新场景摘要，理解人工修改后的设备、位号和连接关系；
- 单位图例使用声明式 JSON 文件维护，替换图例无需修改 CAD 内核。

> 当前版本为 `2.0.0-alpha.1`。旧仓库中的原型实现已被替换，但 `/api/v1` 主要绘图接口仍由新的文档内核提供兼容。

## 已实现能力

### 结构化 P&ID 文档

- 文档、图层、图元、符号和工艺连接线统一数据模型
- 设备符号包含可供 Agent 理解的端口、方向和介质类型
- SQLite 文档持久化
- 原子批量事务
- revision 乐观并发控制，避免 Agent 覆盖人工刚完成的修改
- 撤销/重做使用完整文档快照，不再只支持“撤销新增”

### Agent 接入

- OpenAI-compatible Chat Completions 规划器
- 服务端 JSON Schema 验证
- REST API
- Python Client
- MCP stdio server
- 适用于云模型和本地 OpenAI-compatible 服务
- 场景摘要接口，避免 Agent 每次都读取整份大文档

### 浏览器编辑器

- React + TypeScript + Vite + Zustand
- SVG 编辑画布
- 选择、拖动、删除、撤销、重做
- 直线、矩形、圆、文字、工艺管线和工业符号
- 网格吸附、中键平移、滚轮缩放
- 自然语言生成面板

### 导入与导出基础

- JSON 文档
- SVG
- PNG

DXF、PDF、工艺文件知识库和严格标准图例属于后续阶段。

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

agentcad serve --host 0.0.0.0 --port 8000
```

打开 `http://localhost:8000`。

开发前端：

```bash
# 终端 1
agentcad serve --reload

# 终端 2
cd frontend
npm run dev
```

前端开发地址为 `http://localhost:5173`，Vite 会把 `/api` 代理到后端。

## 模型配置

服务端默认读取：

```bash
export AGENTCAD_LLM_BASE_URL="http://localhost:11434/v1"
export AGENTCAD_LLM_MODEL="your-model-name"
export AGENTCAD_LLM_API_KEY="optional-api-key"
```

`AGENTCAD_LLM_BASE_URL` 指向任意 OpenAI-compatible `/v1` 服务。网页生成面板也可以对单次请求覆盖 Base URL 和模型名称。

规划流程：

1. 后端读取最新 document revision、完整文档和场景摘要；
2. 把单位图例目录和事务 JSON Schema 提供给模型；
3. 模型只返回结构化事务；
4. 后端重新验证图例名称、图层、字段和 revision；
5. 整个事务一次成功，或完全不写入。

## Python 接入

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

安装 MCP 可选依赖后运行：

```bash
agentcad-mcp
# 或
agentcad mcp
```

通用 MCP 客户端配置形式：

```json
{
  "mcpServers": {
    "agentcad": {
      "command": "agentcad-mcp",
      "env": {
        "AGENTCAD_DATABASE_PATH": "/absolute/path/to/agentcad.db"
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

不同客户端的 MCP 配置文件位置不同，但服务端本身使用标准输入输出，不依赖某一家模型供应商。

## 替换为单位图例

内置占位图例位于：

```text
backend/agentcad/data/symbols.json
```

也可以不改仓库文件，通过环境变量加载一个或多个外部 JSON 文件或目录：

```bash
export AGENTCAD_SYMBOL_PATHS="/path/company-symbols:/path/project-symbols"
```

后加载的相同 `key` 会覆盖内置定义。图例结构见 [docs/symbol-schema.md](docs/symbol-schema.md)。

单位图例建议至少提供：

- 稳定的英文 `key`
- 中文名称和分类
- 默认宽高
- SVG 基础形状
- 可连接端口及其方向
- 位号或设备属性说明

## API 概览

### v2 文档 API

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
GET    /api/v2/documents/{document_id}/export.svg
GET    /api/v2/documents/{document_id}/export.png
POST   /api/v2/documents/{document_id}/agent/generate
GET    /api/v2/symbols
GET    /api/v2/agent/tool-schema
```

运行服务后可访问 `/docs` 查看 OpenAPI 文档。

### v1 兼容层

保留了原型中的主要端点：基本图元、工业符号、批量绘制、图元查询/删除、图层、撤销/重做、清空和 SVG 导出。所有数据实际写入新的 `doc_legacy` 文档。

## 本地校验

本仓库不依赖 GitHub Actions。提交前可运行：

```bash
pytest -q
cd frontend && npm run build
```

## 目录

```text
backend/agentcad/
  models.py       领域模型和事务 Schema
  service.py      文档操作、并发和历史
  store.py        SQLite 持久化
  symbols.py      声明式图例注册表
  svg.py          SVG/PNG 导出基础
  llm.py          OpenAI-compatible Agent 规划器
  api_v2.py       文档、导出与 Agent API
  api_v1.py       旧接口兼容层
  client.py       Python REST Client
  mcp_server.py   MCP 工具服务
frontend/src/
  editor/         SVG 编辑器和图例面板
  store.ts        共享工作区状态
  api.ts          v2 API 客户端
docs/
  architecture.md
  agent-integration.md
  symbol-schema.md
```

## 下一阶段

1. 上传工艺设计文件并建立可检索的项目知识库；
2. 图例图片/SVG 自动转换为声明式符号；
3. 连接口吸附、自动正交布管和自动布局；
4. 设备表、管线表和仪表索引双向同步；
5. DXF/PDF 导出；
6. 图纸规则检查和单位内部标准校验。

## License

MIT
