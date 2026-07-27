# LongCat 精确复现废气冷凝器 P&ID 提示词

## 实测结论

- 模型：`LongCat-2.0`
- 目标文档：`LongCat复现-严格对齐废气冷凝器-20260727`
- 文档 ID：`doc_53d1ba949772`
- 生成方式：网页 Automatic Agent Runner
- 生成历史：revision 0 → revision 1，`source=llm`
- 规划结果：首次通过，`attempt=0`，无修复重试
- 操作数：48
- 规划耗时：约 106.8 秒
- 图面与工程结构比对：与基准图 48 个元素 ID 完全一致；坐标、尺寸、旋转、真实端口、连接折点、流向、文字和样式差异为 0
- 人工修改：无；生成后只取消全选并执行“适应全部”，未修改文档数据

这里的“一样”指可见图面和工程拓扑一致，不是两份 JSON 逐字节相同。基准图由确定性事务创建，额外带有 `name`、`metadata`、部分 `properties` 和人工路由来源记录；LongCat 图没有复制这些不参与渲染和连接关系的内部注释字段，直线连接的 `routing` 来源也记录为 `orthogonal` 而非基准图的 `manual`。

## 完整提示词

```text
在这张空白 1600×900 P&ID 画布中，一次性生成一张与“严格对齐-废气冷凝器-20260727”基准图同构、同坐标、同样式的完整图纸。不要发挥，不要添加额外设备，最终必须恰好 48 个元素。所有 symbol.position 都是未旋转外框左上角，不是中心点；所有连接必须绑定真实 port，所有管段只能水平或垂直，connector 统一 stroke=#111827、stroke_width=1.5、fill=none、opacity=1。不要使用任何 transmitter，只使用 pressure_indicator 和 temperature_indicator。为保证几何完全一致，本任务不要使用 instrument_tap 自动组件；请逐个 add_element 创建 symbol/junction/text，再用 connect_ports 建立真实连接。不得用 raw connector add_element。

一、必须按以下 ID、symbol_key、左上角位置和原生尺寸创建 symbol，label 均留空，避免自动标签重复：
1. opc_in：off_page_connector_in，position=(50,375)，size=100×50；
2. v101：globe_valve，position=(245,360)，size=70×65，properties.tag=V-101、valve_state=open；
3. e101：condenser，position=(730,366)，size=140×100，properties.tag=E-101；
4. v102：globe_valve，position=(1305,360)，size=70×65，properties.tag=V-102、valve_state=open；
5. opc_out：off_page_connector_out，position=(1450,375)，size=100×50。

二、在主管 y=400 创建 4 个独立 junction，radius=3、label 空：
j_pt101=(410,400)，j_te101=(540,400)，j_pt102=(1050,400)，j_te102=(1180,400)。再创建空气边界 junction：j_air_out=(300,520)，j_air_in=(1400,520)，radius=3。

三、四组仪表必须逐个创建，中心线严格对准 junction：
- root_pt101：ball_valve，position=(380,330)，size=60×40，rotation=-90；pt101：pressure_indicator，position=(385,220)，size=50×60；
- root_te101：ball_valve，position=(510,330)，size=60×40，rotation=-90；te101：temperature_indicator，position=(515,220)，size=50×60；
- root_pt102：ball_valve，position=(1020,330)，size=60×40，rotation=-90；pt102：pressure_indicator，position=(1025,220)，size=50×60；
- root_te102：ball_valve，position=(1150,330)，size=60×40，rotation=-90；te102：temperature_indicator，position=(1155,220)，size=50×60。
仪表 symbol label 都留空；用下面的独立 text 显示位号。

四、按下列顺序用 connect_ports 创建 8 段废气主管。每段 medium=waste_gas、process_tag=L-GAS-101、flow_direction=forward、arrow_position=middle、style.stroke_width=1.5。不得有 waypoint，因为全部真实端口天然位于 y=400：
- gas_01：opc_in.process → v101.in；
- gas_02：v101.out → j_pt101.node；
- gas_03：j_pt101.node → j_te101.node；
- gas_04：j_te101.node → e101.process_in；
- gas_05：e101.process_out → j_pt102.node；
- gas_06：j_pt102.node → j_te102.node；
- gas_07：j_te102.node → v102.in；
- gas_08：v102.out → opc_out.process。
八段端点必须全部精确位于 y=400，流向从左到右连续，OPC IN 的箭头朝右。

五、用 connect_ports 创建 8 段仪表支管，medium=waste_gas、process_tag=L-GAS-101、flow_direction=none、stroke_width=1.5，全部严格竖直，不得有水平小狗腿：
- branch_pt101_a：j_pt101.node → root_pt101.in；branch_pt101_b：root_pt101.out → pt101.process；
- branch_te101_a：j_te101.node → root_te101.in；branch_te101_b：root_te101.out → te101.process；
- branch_pt102_a：j_pt102.node → root_pt102.in；branch_pt102_b：root_pt102.out → pt102.process；
- branch_te102_a：j_te102.node → root_te102.in；branch_te102_b：root_te102.out → te102.process。
四条支管中心线必须分别只有 x=410、540、1050、1180。

六、创建冷却空气线路，medium=cooling_air、process_tag=L-AIR-101、flow_direction=forward、stroke_width=1.5，整体从右向左：
- air_in：j_air_in.node → e101.utility_in，waypoints 依次为 (900,520)、(900,436)；
- air_out：e101.utility_out → j_air_out.node，waypoints 依次为 (700,436)、(700,520)。
必须使用 condenser 的真实 utility_in/utility_out 端口，不得编造端口，不得与主管交叉。

七、创建以下 11 个独立 text，stroke=#111827、anchor=middle：
- label_upstream：position=(100,340)，text=上游废气来气，font_size=16；
- label_v101：(280,455)，V-101，13；
- label_pt101：(410,185)，PT-101，13；
- label_te101：(540,185)，TE-101，13；
- label_e101：(800,335)，气体冷凝器 E-101，16；
- label_pt102：(1050,185)，PT-102，13；
- label_te102：(1180,185)，TE-102，13；
- label_v102：(1340,455)，V-102，13；
- label_tailgas：(1500,340)，尾气处理系统，16；
- label_air_out：(350,555)，空气出口，14；
- label_air_in：(1350,555)，空气进口，14。

八、最终自检后再返回事务：恰好 19 个 symbol/junction、18 个 connector、11 个 text，共 48 元素；白色背景；主管全为 y=400；所有 connector 线宽都是 1.5；不存在 transmitter、斜线、自由端点、重复标签、额外箭头文字、额外设备。expected_revision=0，事务 label 使用“LongCat exact condenser replica”。
```

## 适用边界

这是一份针对当前 P009 符号库和语义操作协议的确定性提示词。若图例 key、原生尺寸、端口 ID 或坐标语义发生变化，应先更新这些约束，再做跨模型复现。
