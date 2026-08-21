# P&ID-Agent 路演 PPT（青创大赛）

- 成品：`P&ID-Agent-路演.pptx`（18 页，16:9，深色科技风）
- 生成脚本：`deck.js`（PptxGenJS，可改可重建）
- 插图素材：`assets/`（来自仓库真实产物：氩气系统 P&ID、国标阀门图例、编辑器 e2e 截图）
- 逐页渲染预览：`rendered/slide-01..18.png`；总览图 `montage.png`

## 重建

```bash
cd pitch
npm install            # 首次
node deck.js           # 输出 P&ID-Agent-路演.pptx
# 可选：使用 LibreOffice 导出预览图
soffice --headless --convert-to pdf "P&ID-Agent-路演.pptx"
```

## 字体说明

- 全篇指定 `Microsoft YaHei`（微软雅黑）：Windows / WPS 直接命中；本机 macOS 用 LibreOffice 预览时自动以冬青黑体（Hiragino Sans GB）替代渲染，中文均为全角等宽，版式不变。
- 若要改字体，全局替换 `deck.js` 顶部 `const FONT` 一处即可。

## 数据出处（路演口径）

- 模型验收矩阵：仓库 `reports/*.json`（DeepSeek-V4-Flash 15/15、Qwen3.6-35B 15/15、第三方未达标模型 11/15 判不可用）
- 测试规模：后端 pytest 271 / 前端 92 / e2e 37，CI 全绿（`HANDOFF.md`）
- 图例库：`backend/agentcad/data/standard_symbols.json`（55 符号、12 分类）
- 收入预期、市场与团队口径：与项目计划书（青创大赛修订版）一致
