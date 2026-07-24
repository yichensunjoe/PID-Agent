# 内置标准 P&ID 图例库

P&ID-Agent 的内置图例库以工程语义为主：每个图例必须同时具备稳定 `key`、清晰中文名称、
声明式矢量图形和可验证的真实端口。图例不是截图贴图，人工编辑器、Agent、SVG/PDF/DXF
导出和拓扑检查读取的是同一份定义。

本轮图例整理参考了用户提供的单位图例截图，并采用以下公开标准的适用范围作为分类依据：

- [ISO 10628-2:2012](https://www.iso.org/standard/51841.html)：化工和石化流程图的图形符号；
- [ANSI/ISA-5.1-2024](https://www.isa.org/products/ansi-isa-5-1-2024-instrumentation-and-control-symb)：仪表与控制的符号和标识；
- [IEC 62424:2016](https://webstore.iec.ch/en/publication/25442)：P&ID 中过程控制工程请求的表达和数据交换。

这些图例是基于通用工程惯例的可编辑实现，不代表对任何标准的完整复制或认证。具体项目仍应以
单位制图规定、项目图例首页和设计审查要求为准。

## 库结构

- `backend/agentcad/data/symbols.json`：11 个历史内置 key，保持既有图纸兼容；
- `backend/agentcad/data/standard_symbols.json`：50 个标准化扩展图例；
- `PID_AGENT_SYMBOL_PATHS`：单位级、项目级图例覆盖层。

加载顺序为“历史内置 → 标准扩展 → 环境变量路径 → 调用方追加路径”。后加载的相同 `key`
覆盖前一层，因此单位可以替换画法而不修改产品代码。

标准扩展覆盖：

- 阀门与安全附件：截止阀、止回阀、安全泄放阀、蝶阀、针型阀、旋塞阀、三通阀、电动阀、
  电磁阀、隔膜阀、爆破片和阻火器；
- 旋转设备：容积式泵、真空泵和轴流风机；
- 换热设备：冷凝器、板式换热器、空冷器和电加热器；
- 容器与分离：卧式容器、立式分离器、开口槽、反应釜和排液罐；
- 过滤与混合：管道过滤器、篮式过滤器、筒式过滤器和搅拌器；
- 管件与附件：法兰、盲法兰、同心/偏心异径管、三通、软管、膨胀节、疏水器、孔板、
  八字盲板和管线断开标记；
- 排放与边界：地漏、开口漏斗、喷嘴、跨图连接符和放空至大气；
- 仪表：PT、TT、FT、LT 和就地液位计。

截图中的运输车、轨道平台、钢桶推车等运动控制图元没有纳入 P&ID 核心库；它们更适合总图、
物流或机械布置图。这样可避免 Agent 在工艺流程图中误用与管道拓扑无关的设备。

## 端口约定

- 直通设备和阀门通常使用 `in` / `out`；
- 泵使用 `suction` / `discharge`；
- 双介质设备区分 `process_*` 和 `utility_*`；
- 仪表区分 `process` 和 `signal`；
- 多接口容器使用 `feed`、`gas_out`、`liquid_out`、`vent`、`drain` 等语义名称；
- 边界或单端附件只声明真实可连接的一端，不为图形对称性编造端口。

端口的 `direction` 和 `medium` 会进入 Agent 提示目录、语义事务校验和最终 scene summary。
已有图纸一旦使用某个 `key` 或 `port_id`，后续修改应保持兼容，或提供显式迁移。

## 验收

```bash
source .venv/bin/activate
pid-agent quality-harness
pytest -q backend/tests/test_symbol_library.py

cd frontend
npm test
npm run build
```

离线 quality harness 会动态扫描实际加载的全部图例，检查名称、分类、key、端口 ID、端口边界、
shape 字段和全库 SVG 渲染，并用真实端口完成 junction 拓扑和 Agent 事务验收。
