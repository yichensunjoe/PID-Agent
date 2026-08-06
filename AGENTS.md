# AGENTS.md — 项目规则（P009-PID-Agent）

> 本文件包含「总库复用与踩坑日志」一节，是 Codex 项目库的统一约定，见 `/Users/joe/ai/reasonix/NEW_PROJECT_SOP.md`。

## 项目概览

- Purpose：轻量浏览器 P&ID 软件，让工程人员与 AI Agent 共用同一套单位图例、结构化图纸和连接语义，共同创建、修改、解释和检查工艺流程图。
- Stack：Python 后端（`backend/agentcad`）+ React/TypeScript 前端（`frontend/`，Vite），Docker 部署。
- 产品显示名：P&ID-Agent；仓库 slug 规范名：PID-Agent；Python 导入路径暂保留 `agentcad`。

## 编码规则

- P&ID 的"连接正确"与"图面共线"分开验收；水平工艺链检查全局 y 唯一值，竖直支管检查全局 x 唯一值。
- 方向符号联合验收"端口 direction、connector flow_direction、图形尖端方向"三层。
- "能列模型"不等于"能生成"；模型可用性用真实最小 completion 验证。
- DELETE 等破坏性动作携带 `expected_revision`，由数据库原子比较；异步响应写状态前复核 document/revision 与请求代际。
- 关键输入不用 `window.prompt()`，使用应用内受控对话框。
- 修改后至少运行后端测试、前端构建与一次端到端画布验收。
## 总库复用与踩坑日志（双写）

本项目的可复用经验、踩坑教训、方案验证和项目复盘，按以下约定记录：

- **项目内日志**：`本项目根/REUSE_AND_PITFALL_LOG.md`——本项目踩坑明细，**执行任务前先读它**，避免重复踩坑。
- **总项目库**：`/Users/joe/ai/reasonix/REUSE_AND_PITFALL_LOG.md`——全局汇总，跨会话共享。
- 写入顺序：任务完成后 → ① 追加项目内日志（顶部，时间倒序）→ ② 同步追加总库（引用本项目 P055-PID-Agent）。
- 条目格式：`## YYYY-MM-DD · 主题（P055-PID-Agent）` + 场景/结论做法/踩坑点/适用场景。
- 触发时机：重要问题修复、踩坑排查、方案验证、项目复盘后。
- 写入失败降级：总库写不了则至少写项目内日志并注明「待同步总库」。
- 不记录：密钥、个人数据、一次性琐碎操作。

