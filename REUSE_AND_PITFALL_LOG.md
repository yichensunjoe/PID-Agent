# 本项目踩坑记录（REUSE_AND_PITFALL_LOG）

本项目专属的踩坑/可复用经验明细。总项目库 `/Users/joe/ai/reasonix/REUSE_AND_PITFALL_LOG.md` 为全局汇总。

规则：执行任务前先读本文件；任务完成后**双写**——先追加本文件，再同步追加总库（见 AGENTS.md）。

已有记录：

## 2026-08-19 · UI token 化重构与 e2e 环境坑（P055-PID-Agent）

**场景**：分支 `ui-polish-2026-08-19` 对前端做整体视觉重构（美观简洁大方），只改 CSS 不动 JSX/TS，并保持浅/深双主题与 e2e 视觉回归通过。

**结论做法**：
- 重构策略：`styles.css` 整体重写为设计 token 驱动——`:root` 定义浅色 token、`.app-shell[data-theme="dark"]` 覆盖为深色 token；各文件早已引用但从未定义的 `var(--border)/var(--panel-background)/var(--muted-text)` 等变量顺带生效。工程画布配色（#69778a/#9ba8b8 与 SVG 元素色）严格不动。
- 验收：临时 Playwright 截图脚本（浅/深/命令面板/Agent 面板四张）人工比对 → `test:e2e:update` 重生成 10 张快照 → 全量 e2e。

**踩坑点**：
- **Playwright webServer 端口冲突要杀子进程**：`kill` npm/uvicorn 包装进程后，vite preview 与 uvicorn 的子进程仍占着 4173/8000，`reuseExistingServer:false` 直接报错；必须 `lsof -nP -iTCP:8000 -sTCP:LISTEN` 找到真实 PID 再杀。
- **Playwright 浏览器版本严格绑定**：本机缓存有 chromium-1223/1234，但项目 @playwright/test 1.61.1 只认 1228，需 `npx playwright install chromium`；临时截图脚本可用 `executablePath` 指向其他缓存版本应急。
- 临时 node 脚本放 `/tmp` 会 ERR_MODULE_NOT_FOUND（ESM 从脚本所在目录解析依赖），必须放进 frontend/ 目录内。
- e2e 两个存量失败（基线同样失败，与 CSS 无关）：`document-creation`「effective timeout」期望上限 180s，但 playwright.config.ts 的 webServer env 未设 `PID_AGENT_AGENT_TIMEOUT_SECONDS`（后端默认 600）；`flow-runtime`「OPC double click」跳转失败根因未查。UI 改动验收前先跑基线对照，避免把存量失败算到自己头上。

**适用场景**：大型 CSS token 化重构、Playwright webServer/浏览器版本排障、UI 回归的基线对照方法。

（已同步总库 2026-08-19）

## 2026-08-06 · 全量 review + 修复后提交（P055-PID-Agent）

**场景**：接管 main 分支 63 文件未提交修改（+5118/−373，codex_handoff 称"已准备推送"但实际未提交），两轮 review 子代理 + 未跟踪新文件审查 + 人工验证，修复 4 中危 + 7 低危后分组提交。

**结论做法**：
- 中危修复：`diagram_quality.py` ① `_element_rect` 旋转符号用绕中心旋转的精确包围盒（0/180° 快速路径）；② `_segment_intersects_rect` 非正交段用 Liang-Barsky 裁剪（要求 t1-t0>EPSILON，保持"严格穿过"语义）；③ `route_connector_points` 交叉计数用按主轴排序的一维段索引 + 二分定位（预排除共享端点连接），`_port_direction`/`infer_flow_direction` 增加 element_map 参数复用；④ `svg.py` `embedded_off_page_label` 坐标由硬编码 (47,30) 改为按定义尺寸推导。
- 低危：`_expand_compact_cabinet_branches` 画布底部空间不足时整体上移组而非压缩高度（8 分支场景不再重叠溢出）；`_place_compact_nodes` 候选枚举上限=到画布边界最大距离；`_request_model_json` 用显式 `repair` 参数替代 `user_prompt.startswith("Schema repair attempt:")` 前缀判定（基类调用点传 repair=True）；compiler polish 异常 `pass` → `logging.warning`；`deleted_text_ids` 排序；前端 renameCurrentDocument 补 catch（`messageFromError` 从 store.ts 导出）。
- 提交分组：feat:quality+标准阀门图例 / feat:vision+SVG+agent runtime / feat:frontend / chore:规则与脚本。

**踩坑点**：
- **本机没有 vitest**，`npx vitest run` 会临时拉取 vitest 4 且与项目 `node:test` 风格测试不兼容 → 33 文件全报 "No test suite found"。项目前端测试必须用 `npm test`（`node --experimental-strip-types --test tests/*.test.ts`）。
- review 子代理环境无 git diff/pytest 权限，只能精读文件；未跟踪新文件（diagram_quality.py 等）review 工具看不到，需另开子代理审查。
- `svg.py` 元素 label 的旋转抵消 `rotate(-θ, anchor)` 以锚点为旋转中心时，位置跟随符号旋转且文本保持正立——绕自身抵消是正确模式；embedded label 旧硬编码 (47,30) 与定义中心 (50,25) 不一致导致旋转 180° 偏移 (6,−10)。
- 旋转包围盒测试用例几何要先手算验证（首版对角段 (50,50)→(400,400) 实际不穿过矩形 (200,100)-(260,140)，测试失败是用例错误而非实现错误）。
- 显式参数重构会破坏直接调用私有方法的测试（test_k3_schema_repair 用字符串前缀模拟契约），需同步更新测试。
- `multi_edit` 跨文件编辑（semantic_compiler_engine + annotation_layout 混在一起）因目标文件错误整体回滚——**multi_edit 只用于单文件**，跨文件用并行 edit_file。

**适用场景**：大型未提交工作批次接管、绘图质量检查模块几何正确性、前端 node:test 测试环境识别。

（已同步总库 2026-08-06）
