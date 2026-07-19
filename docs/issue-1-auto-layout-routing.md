# Issue #1：设备避障、管线间距与整图自动整理

## 本切片目标

为人工用户和外部 Agent 提供同一套确定性自动整理能力，不让模型直接猜测最终坐标。自动整理必须先生成原子事务预览，用户确认后才写入文档。

## 布局流程

```text
读取当前 revision 和拓扑
→ 识别 symbol、junction 和 connector
→ 按 source/target 拓扑分层
→ 对独立流程分组
→ 保留锁定图层中的元素
→ 避免设备包围盒重叠
→ 对 connector 执行正交避障寻路
→ 对已经占用的管线通道增加代价
→ 返回低层原子事务
→ 用户确认应用
```

## REST

```http
POST /api/v2/documents/{document_id}/layout/preview
Content-Type: application/json
```

示例：

```json
{
  "expected_revision": 12,
  "element_ids": [],
  "direction": "horizontal",
  "rank_gap": 180,
  "node_gap": 90,
  "component_gap": 180,
  "obstacle_margin": 24,
  "lane_gap": 24,
  "reroute_connectors": true,
  "include_hidden": false
}
```

`element_ids` 为空时整理整张可见图纸。传入设备、junction 或 connector ID 时只整理该局部范围；选择 connector 会自动纳入其 source 和 target 设备。

响应包含：

- 可直接提交的 `transaction`；
- 移动的设备和 junction；
- 重新寻路的 connector；
- 跟随设备移动的附属文字；
- 因图层锁定而跳过的元素；
- 整理前后的质量指标；
- 回退到基础正交路径等警告。

预览不会写入数据库，也不会增加 revision。

## 网页

入口：

```text
右侧 → 图层/系统 → 自动整理
```

可配置：

- 整张图或当前选择；
- 从左到右或从上到下；
- 层级间距；
- 同级设备间距；
- 独立流程间距；
- 设备避障边距；
- 管线通道间距；
- 是否重排 connector；
- 是否包含隐藏图层和系统。

生成预览后，网页会高亮将被修改的元素，并显示：

- 设备重叠数量；
- 管线穿越设备数量；
- 共享管线通道数量；
- 总路径长度；
- 布局宽度和高度。

用户确认后仍通过现有 revision 原子事务提交。预览期间 revision 变化时必须重新生成。

## MCP

新增：

```text
preview_auto_layout(document_id, options)
apply_auto_layout(document_id, options)
```

`preview_auto_layout` 只生成预览。`apply_auto_layout` 会重新基于当前 revision 计算，并在存在非空事务时原子应用。

## 工程约束

- 锁定图层中的设备、junction 和 connector 不移动；
- connector 的 element ID、source、target 和 port ID 保持不变；
- 管线路径保持水平/垂直；
- junction 使用中心坐标，不使用符号左上角坐标；
- 循环流程不会导致无限层级传播；
- `metadata.parent_element_id`、`metadata.attached_to` 或 `metadata.element_id` 指向移动设备的文字会随设备移动；
- 每条管线最多使用路径附近 24 个设备障碍生成候选网格，控制中等图纸的寻路复杂度；
- 无完整避障路径时回退到服务端基础正交路径，并在预览中给出警告。

## 诊断事件

```text
layout.preview.started
layout.preview.completed
```

记录范围、方向、耗时、操作数量、移动元素、重排管线、锁定跳过项和整理前后指标。

## 测试范围

新增专项测试覆盖：

- 重叠设备分离；
- 预览不写数据库；
- 应用后 connector 仍绑定真实端口；
- 管线保持正交；
- 锁定图层不移动；
- 管线穿越设备指标不恶化；
- stale revision 被拒绝。

## 尚未覆盖

以下内容放入 Issue #1 后续切片：

- 500～5000 元素大型图纸的性能基准；
- 视口裁剪和只渲染可见区域；
- 自动扩展或裁剪导出范围；
- 多种真实模型下的自然语言稳定性和重规划收敛率。
