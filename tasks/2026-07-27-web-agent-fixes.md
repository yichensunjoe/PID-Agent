# 网页 Agent 体验问题修复

日期：2026-07-27

## 结论

实操中有四类问题属于 P&ID-Agent 代码或前后端契约：

- 新建文档依赖内嵌浏览器不支持的 `window.prompt()`；
- Provider 测试只读取模型列表，未验证真实生成权限；
- 前端超时上限与服务端有效上限可能不一致；
- `instrument_tap` 与同标签独立仪表可被同时规划。

本地 35B 模型耗时数分钟以及复杂首稿漏接/错选，主要属于模型速度和指令遵循能力，不是单一程序故障。

## 完成项

- 新建图纸改用应用内受控对话框；
- Provider 测试在 `/models` 后执行最小 completion；
- 新增 `GET /api/v2/agent/runtime-config`，前端显示并限制有效超时；
- 重复仪表标签在语义计划模型层拒绝并进入 schema repair；
- 增强精确设备、边界连接和 utility connector 的规划提示。

## 验证

- 相关后端测试：21 passed；
- 前端单测：85 passed；
- 前端生产构建：通过；
- 全量后端：220 passed，3 个既有 Cairo 动态库缺失导致的 PNG/PDF 环境失败；
- 真实网页：新建对话框可见，8001 显示 600 秒有效上限；
- `glm-5.2:cloud`：真实最小 completion 返回无权限；
- `qwen3.6:35b`：真实最小 completion 成功，约 6103 ms。

## 后续

- 将复杂用户需求编译为完整的应用前目标验收规则；
- 为长规划增加阶段、耗时和取消反馈；
- 扩展标签碰撞检查到符号内部标签、自动注释和独立文字。

## 严格对齐补充

同日复核旧图后，确认主管和仪表支管的错落感还包含三个确定性代码问题：

- `instrument_tap` 默认把支管线宽压到 1.0，主管为 1.5；
- 仪表位置按外框中心估算，真实 `process` 端口不一定在外框中心，会产生微小水平狗腿；
- 规划提示没有明确符号坐标是未旋转外框左上角，模型容易给不同符号相同 `position.y`，但真实端口不共线。

已修复为：支管默认继承主管样式；仪表和根部阀按旋转后的真实端口反算位置；规划提示要求水平工艺链按图例端口偏移计算符号位置。

网页中新建 `严格对齐-废气冷凝器-20260727`（`doc_9d09bcff3da0`），未调用 LLM，直接提交确定性绘图事务。最终 revision 2、48 个元素；主管端口与全部主管段均为 `y=400`，四组仪表支管分别严格位于 `x=410/540/1050/1180`，全部 connector 线宽为 1.5，所有线段正交，工程规则无 error。

验证：`backend/tests/test_semantic_instrument_tap.py`，3 passed。

## OPC、流向和仪表图例补充

用户复核 revision 2 后发现 OPC IN 视觉箭头朝左、主管部分分段未显示流向，并要求移除变送器图例。

处理结果：

- OPC IN 原端口语义正确，但轮廓尖端坐标确实朝左；已改为朝右并保留右侧 `process/out` 端口；
- `严格对齐-废气冷凝器-20260727` 更新至 revision 3，`gas_01`—`gas_08` 全部为 `flow_direction=forward`；
- 当前图的 PT/TT 变送器替换为 PI/TI 指示仪，过程端口仍精确位于原支管中心线；
- pressure/temperature/flow/level transmitter 从网页图例和 Agent 目录隐藏；底层定义保留，避免旧图纸失效；
- 仪表图例由 8 项精简为 4 项，工程规则仍为 0 error，未连接信号端口 warning 从 4 个降至 0。

验证：相关后端测试 12 passed；离线 quality harness 3/3 passed，57 个可见图例全部验证并渲染。

## LongCat 跨模型精确复现

使用 `/Users/joe/ai/cc/P002-可用模型清单/.env` 中已有的 LongCat 配置启动 P009，未输出或复制密钥内容。`LongCat-2.0` 真实最小 completion 测试成功，连接测试耗时约 18.9 秒。

在网页中新建空白文档 `LongCat复现-严格对齐废气冷凝器-20260727`（`doc_53d1ba949772`），通过 Automatic Agent Runner 提交施工级提示词。LongCat 首次规划即通过，`attempt=0`、无修复重试，约 106.8 秒生成 48 个语义操作，并以唯一一条 `source=llm` 历史从 revision 0 更新到 revision 1。

生成后未进行人工或程序化图纸修改，只取消全选并执行“适应全部”。与基准文档 `doc_9d09bcff3da0` 逐 ID 比对后，48 个元素 ID 完全一致；可见图面和工程拓扑相关的符号类型、坐标、尺寸、旋转、junction、真实端口、connector 折点、介质、流向、文字和样式差异数为 0。主管所有点均为 `y=400`，connector 线宽唯一值为 1.5，不含 transmitter，工程报表为 0 error。两份文档不是逐字节相同：基准图额外保留了不参与渲染和连接关系的 `name`、`metadata`、部分 `properties` 与人工路由来源记录。

完整提示词见 `docs/longcat-exact-condenser-replica-prompt.md`。

## 服务重启记录

2026-07-27 重新拉起体验实例：

- 服务：`pid-agent serve --host 0.0.0.0 --port 8001`
- 数据库：`/Users/joe/Documents/Codex/projects/active/P009-PID-Agent/data/pid-agent.db`
- 环境：`PID_AGENT_AGENT_TIMEOUT_SECONDS=600`
- 日志：`/Users/joe/Documents/Codex/projects/active/P009-PID-Agent/logs/server-8001.log`
- 健康检查：`http://127.0.0.1:8001/health` 返回 `{"status":"ok","service":"P&ID-Agent","version":"2.1.0-alpha.1"}`
