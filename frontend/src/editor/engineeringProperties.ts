import type { Element, SymbolDefinition } from "../types";

export type PropertyCategory = "valve" | "equipment" | "connector" | "instrument" | "node_fitting" | "generic";

export type PropertyFieldDefinition = {
  key: string;
  label: string;
  placeholder?: string;
  description?: string;
  presets: string[];
};

export type CategorySchema = {
  id: PropertyCategory;
  name: string;
  badge: string;
  description: string;
  fields: PropertyFieldDefinition[];
};

// -------------------------------------------------------------
// Standard Engineering Presets (GB/T, HG/T 20559, ASME/ANSI)
// -------------------------------------------------------------

export const NOMINAL_DIAMETER_PRESETS = [
  "DN15 (1/2\")",
  "DN20 (3/4\")",
  "DN25 (1\")",
  "DN32 (1-1/4\")",
  "DN40 (1-1/2\")",
  "DN50 (2\")",
  "DN65 (2-1/2\")",
  "DN80 (3\")",
  "DN100 (4\")",
  "DN125 (5\")",
  "DN150 (6\")",
  "DN200 (8\")",
  "DN250 (10\")",
  "DN300 (12\")",
  "DN350 (14\")",
  "DN400 (16\")",
  "DN500 (20\")",
  "1/4\"",
  "3/8\"",
  "1/2\"",
  "3/4\"",
  "1\"",
  "1-1/2\"",
  "2\"",
  "3\"",
  "4\"",
];

export const PRESSURE_RATING_PRESETS = [
  "PN10 (1.0 MPa)",
  "PN16 (1.6 MPa)",
  "PN25 (2.5 MPa)",
  "PN40 (4.0 MPa)",
  "PN63 (6.3 MPa)",
  "PN100 (10.0 MPa)",
  "Class 150 (2.0 MPa)",
  "Class 300 (5.0 MPa)",
  "Class 600 (10.0 MPa)",
  "Class 900 (15.0 MPa)",
  "常压 (Atm)",
  "全真空 (-0.1 MPa)",
];

export const VALVE_MATERIAL_PRESETS = [
  "304不锈钢 (CF8 / 06Cr19Ni10)",
  "316L不锈钢 (CF3M / 022Cr17Ni12Mo2)",
  "碳钢 (WCB / 25#)",
  "铸铁 (HT200)",
  "球墨铸铁 (QT400-15)",
  "钛合金 (TA2 / Gr.2)",
  "哈氏合金 (Hastelloy C-276)",
  "衬四氟 (PTFE / F46)",
  "UPVC 工业塑料",
  "CPVC 工业塑料",
  "PVDF 耐蚀塑料",
];

export const CONNECTION_TYPE_PRESETS = [
  "法兰连接 (RF / 突面)",
  "对焊连接 (BW / Butt Weld)",
  "承插焊 (SW / Socket Weld)",
  "螺纹连接 (NPT / 锥管螺纹)",
  "对夹式 (Wafer)",
  "卡箍快装 (Tri-Clamp / 卫生级)",
  "活接连接 (Union)",
];

export const ACTUATOR_TYPE_PRESETS = [
  "手动 (手轮/手柄)",
  "气动薄膜执行机构",
  "气动活塞执行机构",
  "电动执行机构 (智能调节型)",
  "电磁驱动 (Solenoid Valve)",
  "自力式调节机构",
  "电液动执行机构",
];

export const NORMAL_STATE_PRESETS = [
  "常开 (NO - Normally Open)",
  "常闭 (NC - Normally Closed)",
  "常锁开 (CSO - Car Seal Open)",
  "常锁闭 (CSC - Car Seal Closed)",
  "连续调节 (Modulating)",
];

export const FAIL_POSITION_PRESETS = [
  "FC (故障关 / 气开 Fail Closed)",
  "FO (故障开 / 气关 Fail Open)",
  "FL (故障保位 Fail Locked)",
  "FI (故障不动 Fail Indeterminate)",
  "不适用 / 无",
];

export const MEDIUM_PRESETS = [
  "PW (工艺水 / Process Water)",
  "CW (循环冷却水 / Cooling Water)",
  "CWR (循环水回水)",
  "WW (生产污水 / Waste Water)",
  "ST (中低压蒸汽 / Steam)",
  "SC (蒸汽凝结水 / Condensate)",
  "IA (仪表空气 / Instrument Air)",
  "PA (工厂压缩空气 / Plant Air)",
  "N2 (高纯氮气 / Nitrogen)",
  "O2 (氧气 / Oxygen)",
  "AR (高纯氩气 / Argon)",
  "NG (天然气 / Natural Gas)",
  "LO (润滑油 / Lube Oil)",
  "FG (燃料气 / Fuel Gas)",
  "CA (浓酸介质 / Chemical Acid)",
  "CB (浓碱介质 / Chemical Base)",
  "GAS (工艺气体)",
  "OIL (工艺油品)",
];

export const CAPACITY_SPEC_PRESETS = [
  "0.5 m³",
  "1.0 m³",
  "2.5 m³",
  "5.0 m³",
  "10 m³",
  "25 m³",
  "50 m³",
  "100 m³",
  "200 m³",
  "500 m³",
  "1000 m³",
  "10 m² (换热面积)",
  "25 m² (换热面积)",
  "50 m² (换热面积)",
  "100 m² (换热面积)",
  "200 m² (换热面积)",
  "流量 25 m³/h · 扬程 50 m",
  "流量 50 m³/h · 扬程 80 m",
  "功率 7.5 kW",
  "功率 15 kW",
  "功率 37 kW",
  "功率 55 kW",
  "功率 110 kW",
];

export const DESIGN_PRESSURE_PRESETS = [
  "常压 (Atm / 0.1 MPa)",
  "微正压 (5 kPa)",
  "0.25 MPa",
  "0.6 MPa",
  "1.0 MPa",
  "1.6 MPa",
  "2.5 MPa",
  "4.0 MPa",
  "6.4 MPa",
  "10.0 MPa",
  "全真空 (-0.1 MPa)",
];

export const DESIGN_TEMPERATURE_PRESETS = [
  "常温 (Amb / -20 ~ 40 ℃)",
  "60 ℃",
  "80 ℃",
  "120 ℃",
  "150 ℃",
  "180 ℃",
  "220 ℃",
  "250 ℃",
  "300 ℃",
  "350 ℃",
  "450 ℃",
  "550 ℃",
  "低温 (-40 ℃)",
  "深冷液氮 (-196 ℃)",
];

export const EQUIPMENT_MATERIAL_PRESETS = [
  "Q245R 锅炉压力容器碳钢",
  "Q345R 低合金容器钢",
  "S30408 (304不锈钢 / 06Cr19Ni10)",
  "S31603 (316L不锈钢 / 022Cr17Ni12Mo2)",
  "S32205 (双相不锈钢 2205)",
  "钛复合板 (TA2+Q245R)",
  "哈氏合金 (Hastelloy C-276)",
  "Inconel 625 镍基合金",
  "玻璃钢 (FRP / 耐腐蚀)",
  "搪玻璃 / 搪瓷",
  "钢衬四氟 (PTFE-Lined)",
];

export const INSULATION_PRESETS = [
  "无保温",
  "保温 (IH - 50mm岩棉)",
  "保冷 (IC - 80mm聚氨酯)",
  "人身防护防烫 (IP)",
  "蒸汽外伴热 (ST)",
  "电伴热带 (ET - 自控温)",
  "夹套伴热 (JK)",
];

export const ELEVATION_PRESETS = [
  "地面基础 (EL +0.000)",
  "一层操作平台 (EL +4.500)",
  "二层操作平台 (EL +8.500)",
  "三层设备平台 (EL +12.500)",
  "塔顶平台 (EL +28.000)",
  "地下防爆池 (EL -2.500)",
  "管廊上层 (EL +6.000)",
];

export const STANDBY_MODE_PRESETS = [
  "单台独立运行",
  "一开一备 (1W1S)",
  "两开一备 (2W1S)",
  "三开一备 (3W1S)",
  "连续运转",
  "批次间歇操作",
];

export const PIPING_MATERIAL_PRESETS = [
  "20# 碳钢无缝钢管 (GB/T 8163)",
  "304不锈钢无缝管 (GB/T 14976)",
  "316L不锈钢洁净管",
  "Q235B 直缝焊接钢管",
  "热镀锌钢管",
  "UPVC 工业塑料给水管",
  "PP-R 热熔承插管",
  "钢衬四氟乙烯复合管 (PTFE)",
  "TA2 工业纯钛管",
];

export const WALL_THICKNESS_PRESETS = [
  "SCH 10S (轻型薄壁)",
  "SCH 20",
  "SCH 40 / STD (标准壁厚)",
  "SCH 80 / XS (加厚重型)",
  "SCH 160 (特厚高压)",
  "3.0 mm",
  "3.5 mm",
  "4.0 mm",
  "4.5 mm",
  "6.0 mm",
  "8.0 mm",
  "10.0 mm",
];

export const MEASURED_VARIABLE_PRESETS = [
  "P (压力 / 差压 Pressure)",
  "T (温度 Temperature)",
  "F (流量 Flow)",
  "L (物位 / 液位 Level)",
  "A (组分 / 分析 Analysis)",
  "D (密度 Density)",
  "V (机械振动 Vibration)",
  "W (重量 / 称重 Weight)",
  "S (转速 / 速度 Speed)",
  "H (手动 Hand / Manual)",
];

export const INSTRUMENT_FUNCTION_PRESETS = [
  "T (变送器 Transmitter)",
  "I (现场指示 Indicator)",
  "C (调节控制器 Controller)",
  "A (越限报警 Alarm)",
  "S (联锁开关 Switch)",
  "R (趋势记录 Recorder)",
  "V (执行控制阀 Valve)",
  "E (一次传感元件 Primary Element)",
  "Y (继电运算转换 Relay/Compute)",
];

export const RANGE_SPAN_PRESETS = [
  "0 ~ 0.6 MPa",
  "0 ~ 1.0 MPa",
  "0 ~ 1.6 MPa",
  "0 ~ 2.5 MPa",
  "0 ~ 4.0 MPa",
  "0 ~ 10.0 MPa",
  "-0.1 ~ 0.5 MPa (复合微正压)",
  "-50 ~ 150 ℃",
  "0 ~ 200 ℃",
  "0 ~ 400 ℃",
  "0 ~ 600 ℃",
  "0 ~ 10 m³/h",
  "0 ~ 50 m³/h",
  "0 ~ 200 m³/h",
  "0 ~ 1000 m³/h",
  "0 ~ 2.0 m (液位)",
  "0 ~ 5.0 m (液位)",
  "0 ~ 100 % (开度/百分比)",
];

export const SIGNAL_TYPE_PRESETS = [
  "4-20mA DC (两线制模拟量)",
  "4-20mA DC + HART 协议",
  "RS485 (Modbus-RTU 现场总线)",
  "Profibus-PA 现场总线",
  "Foundation Fieldbus (FF 总线)",
  "无源干接点 (SPDT 单刀双掷)",
  "无源干接点 (DPDT 双刀双掷)",
  "24V DC 独立供电",
  "220V AC 交流供电",
  "无线 WirelessHART",
];

export const MOUNT_LOCATION_PRESETS = [
  "现场管道/设备就地 (Field Mounted)",
  "就地仪表盘/操作箱 (Local Panel)",
  "DCS主控制室 (Central Control Room)",
  "PLC辅助控制柜 (Auxiliary Cabinet)",
  "现场分析小屋 (Analyzer Shelter)",
  "机柜室安全栅柜 (Rack Room)",
];

export const PROTECTION_RATING_PRESETS = [
  "非防爆安全区 / IP65",
  "Ex d IIC T6 Gb (隔爆型) / IP66",
  "Ex ia IIC T6 Ga (本安型) / IP67",
  "Ex e IIC T4 Gb (增安型) / IP65",
  "Ex nA IIC T4 Gc (无火花型)",
  "NEMA 4X / 耐腐蚀型",
];

export const ALARM_SETPOINTS_PRESETS = [
  "无报警",
  "高报警 (HA: 80%)",
  "低报警 (LA: 20%)",
  "高高联锁 (HHA: 90%) · 低低联锁 (LLA: 10%)",
  "高/低越限报警 (HA: 85% / LA: 15%)",
  "偏差报警 (DA: ±5%)",
];

export const LINKED_DRAWING_PRESETS = [
  "PID-DWG-001 (原料供给与预处理单元)",
  "PID-DWG-002 (核心反应与精馏单元)",
  "PID-DWG-003 (公用工程水电气与储运)",
  "PID-DWG-004 (尾气净化与环保处理)",
  "界区外总管 (Battery Limit)",
];

export const TARGET_PIPE_PRESETS = [
  "PL-101-50 (来自原料储罐区)",
  "CW-201-100 (去循环水冷却塔回水)",
  "ST-301-25 (来自动力车间蒸汽主管)",
  "WW-401-80 (去厂区污水处理站)",
  "IA-501-15 (来自仪表空压站主管)",
  "N2-601-25 (来自制氮机房供气)",
];

export const DIRECTION_PRESETS = [
  "进图 (Inlet / 来料进入)",
  "出图 (Outlet / 送往后续)",
  "双向 (Bidirectional / 双向连通)",
];

// -------------------------------------------------------------
// Category Schemas
// -------------------------------------------------------------

export const VALVE_SCHEMA: CategorySchema = {
  id: "valve",
  name: "阀门 / 安全附件",
  badge: "VALVE",
  description: "适用于闸阀、截止阀、球阀、蝶阀、止回阀、调节阀、安全阀等流体切断与控制元件",
  fields: [
    {
      key: "nominal_diameter",
      label: "出入口管径 / 公称通径",
      placeholder: "例如 DN50 或 2\"",
      description: "阀门两端管道连接口径（标准通径 DN15 ~ DN500 或 1/4\" ~ 20\"）",
      presets: NOMINAL_DIAMETER_PRESETS,
    },
    {
      key: "pressure_rating",
      label: "公称压力 / 压力等级",
      placeholder: "例如 PN16 或 Class 150",
      description: "阀体及连接端面耐压等级",
      presets: PRESSURE_RATING_PRESETS,
    },
    {
      key: "body_material",
      label: "阀体材质",
      placeholder: "例如 304不锈钢 或 碳钢",
      description: "承压壳体与过流部件材质",
      presets: VALVE_MATERIAL_PRESETS,
    },
    {
      key: "connection_type",
      label: "端部连接形式",
      placeholder: "例如 法兰连接 (RF)",
      description: "与相邻管道的对接形式",
      presets: CONNECTION_TYPE_PRESETS,
    },
    {
      key: "actuator_type",
      label: "驱动 / 执行机构形式",
      placeholder: "例如 手动 或 气动薄膜",
      description: "操作与驱动控制方式",
      presets: ACTUATOR_TYPE_PRESETS,
    },
    {
      key: "normal_state",
      label: "工艺常态位置",
      placeholder: "例如 常开 (NO)",
      description: "正常工艺运行工况下的阀位状态",
      presets: NORMAL_STATE_PRESETS,
    },
    {
      key: "fail_position",
      label: "气源/电源故障安全位置",
      placeholder: "例如 FC (故障关)",
      description: "失电或失气时的安全复位方向",
      presets: FAIL_POSITION_PRESETS,
    },
    {
      key: "medium",
      label: "适用工艺介质",
      placeholder: "例如 CW (循环水) 或 ST (蒸汽)",
      description: "流经阀门的工艺介质代码或名称",
      presets: MEDIUM_PRESETS,
    },
  ],
};

export const EQUIPMENT_SCHEMA: CategorySchema = {
  id: "equipment",
  name: "工艺设备 / 储罐机泵",
  badge: "EQUIPMENT",
  description: "适用于离心泵、往复泵、风机、容器、储罐、换热器、塔器、反应釜及过滤混合设备",
  fields: [
    {
      key: "capacity_spec",
      label: "规格容量 / 功率扬程 / 换热面积",
      placeholder: "例如 50 m³ 或 37 kW",
      description: "设备设计容量、电机功率、额定流量扬程或换热面积",
      presets: CAPACITY_SPEC_PRESETS,
    },
    {
      key: "design_pressure",
      label: "设计工作压力",
      placeholder: "例如 1.6 MPa 或 常压",
      description: "壳体或管程/壳程设计耐受压力",
      presets: DESIGN_PRESSURE_PRESETS,
    },
    {
      key: "design_temperature",
      label: "设计工作温度",
      placeholder: "例如 180 ℃ 或 常温",
      description: "最高/最低工艺设计温度",
      presets: DESIGN_TEMPERATURE_PRESETS,
    },
    {
      key: "material",
      label: "主体接触材质",
      placeholder: "例如 S30408 或 Q345R",
      description: "接触介质的主体筒体、叶轮或封头材质",
      presets: EQUIPMENT_MATERIAL_PRESETS,
    },
    {
      key: "standby_mode",
      label: "备用 / 运行方式",
      placeholder: "例如 一开一备 (1W1S)",
      description: "机泵或反应单元的配置冗余方式",
      presets: STANDBY_MODE_PRESETS,
    },
    {
      key: "insulation",
      label: "保温 / 伴热形式",
      placeholder: "例如 保温 (IH) 或 蒸汽外伴热",
      description: "外壳保温防烫、保冷或伴热需求",
      presets: INSULATION_PRESETS,
    },
    {
      key: "elevation",
      label: "安装平台 / 标高",
      placeholder: "例如 地面 (EL +0.000)",
      description: "设备土建基础或平台标高",
      presets: ELEVATION_PRESETS,
    },
    {
      key: "medium",
      label: "主要处理介质",
      placeholder: "例如 PW (工艺水) 或 OIL (油品)",
      description: "设备内部存留或输送的主要介质",
      presets: MEDIUM_PRESETS,
    },
  ],
};

export const CONNECTOR_SCHEMA: CategorySchema = {
  id: "connector",
  name: "工艺管线 / 管道",
  badge: "PIPING",
  description: "适用于主工艺管道、辅助管线、介质输送管、公用工程管线及信号连线",
  fields: [
    {
      key: "nominal_diameter",
      label: "公称管径 (Size)",
      placeholder: "例如 DN50 或 2\"",
      description: "管道公称通径（标准 DN15 ~ DN500 或 1/4\" ~ 20\"）",
      presets: NOMINAL_DIAMETER_PRESETS,
    },
    {
      key: "medium",
      label: "流体介质代号 (Medium)",
      placeholder: "例如 CW (循环水) 或 ST (蒸汽)",
      description: "流体介质工程代码（PW, CW, ST, IA, N2, AR 等）",
      presets: MEDIUM_PRESETS,
    },
    {
      key: "pipe_material",
      label: "管道材质 (Material)",
      placeholder: "例如 20# 碳钢 或 304不锈钢",
      description: "管道材料牌号与标准规范",
      presets: PIPING_MATERIAL_PRESETS,
    },
    {
      key: "wall_thickness",
      label: "壁厚等级 / 表号 (Schedule)",
      placeholder: "例如 SCH 40 或 4.0 mm",
      description: "管道管壁厚度等级",
      presets: WALL_THICKNESS_PRESETS,
    },
    {
      key: "design_pressure",
      label: "设计压力等级",
      placeholder: "例如 PN16 或 1.0 MPa",
      description: "管道等级设计耐压",
      presets: PRESSURE_RATING_PRESETS,
    },
    {
      key: "insulation",
      label: "伴热 / 保温形式 (Tracing/Insulation)",
      placeholder: "例如 蒸汽外伴热 (ST) 或 无",
      description: "防冻伴热或保温防烫形式",
      presets: INSULATION_PRESETS,
    },
  ],
};

export const INSTRUMENT_SCHEMA: CategorySchema = {
  id: "instrument",
  name: "检测仪表 / 控制元件",
  badge: "INSTRUMENT",
  description: "适用于压力、温度、流量、液位、成分分析变送器、现场指示表、控制回路与安全联锁",
  fields: [
    {
      key: "measured_variable",
      label: "测量变量代码 (Variable)",
      placeholder: "例如 P (压力) 或 T (温度)",
      description: "ISA 5.1 首字母变量代号（P, T, F, L, A 等）",
      presets: MEASURED_VARIABLE_PRESETS,
    },
    {
      key: "instrument_function",
      label: "仪表功能类别 (Function)",
      placeholder: "例如 T (变送器) 或 C (控制器)",
      description: "后继字母功能代号（T 变送, I 指示, C 控制, A 报警, S 开关, V 控制阀）",
      presets: INSTRUMENT_FUNCTION_PRESETS,
    },
    {
      key: "range_span",
      label: "测量量程 / 标称范围 (Span)",
      placeholder: "例如 0 ~ 1.6 MPa 或 -20 ~ 200 ℃",
      description: "传感器标定工作量程与工程单位",
      presets: RANGE_SPAN_PRESETS,
    },
    {
      key: "signal_type",
      label: "输出信号 / 供电制式 (Signal)",
      placeholder: "例如 4-20mA DC + HART",
      description: "信号传输制式与现场总线类型",
      presets: SIGNAL_TYPE_PRESETS,
    },
    {
      key: "mount_location",
      label: "安装位置 / 安装形式 (Mounting)",
      placeholder: "例如 现场就地安装 (Field)",
      description: "一次元件及变送器的现场安装位置",
      presets: MOUNT_LOCATION_PRESETS,
    },
    {
      key: "protection_rating",
      label: "防爆等级 / 外壳防护 (Ex / IP)",
      placeholder: "例如 Ex d IIC T6 / IP66",
      description: "现场防爆区域认证及外壳防尘防水等级",
      presets: PROTECTION_RATING_PRESETS,
    },
    {
      key: "alarm_setpoints",
      label: "报警与联锁设定值 (Alarm Setpoints)",
      placeholder: "例如 高高联锁 (HHA) / 低低联锁 (LLA)",
      description: "控制系统内预置的工艺限值报警",
      presets: ALARM_SETPOINTS_PRESETS,
    },
  ],
};

export const NODE_FITTING_SCHEMA: CategorySchema = {
  id: "node_fitting",
  name: "管件 / 跨图连接符 / 边界",
  badge: "FITTING/OPC",
  description: "适用于跨图连接符 (OPC)、法兰、变径、盲通、排放管口与装置界区边界",
  fields: [
    {
      key: "nominal_diameter",
      label: "接口管径 / 规格 (Size)",
      placeholder: "例如 DN50 或 2\"",
      description: "连接端部管径规格",
      presets: NOMINAL_DIAMETER_PRESETS,
    },
    {
      key: "linked_drawing",
      label: "关联图纸号 / 目标区域 (Linked P&ID)",
      placeholder: "例如 PID-DWG-002 或 界区外",
      description: "跨图连接符对应的去向/来源图号",
      presets: LINKED_DRAWING_PRESETS,
    },
    {
      key: "target_pipe_tag",
      label: "目标管段号 / 来源去向说明",
      placeholder: "例如 PL-101-50 (去反应单元)",
      description: "跨图连接的对端管道编号及介质",
      presets: TARGET_PIPE_PRESETS,
    },
    {
      key: "direction",
      label: "介质流向说明",
      placeholder: "例如 进图 (Inlet) 或 出图 (Outlet)",
      description: "跨图进出方向",
      presets: DIRECTION_PRESETS,
    },
    {
      key: "pressure_rating",
      label: "压力等级 / 法兰等级",
      placeholder: "例如 PN16 或 Class 150",
      description: "接口法兰或界区法兰耐压等级",
      presets: PRESSURE_RATING_PRESETS,
    },
  ],
};

export const GENERIC_SCHEMA: CategorySchema = {
  id: "generic",
  name: "通用工程图元",
  badge: "GENERIC",
  description: "适用于通用基础图元及自定义工艺标注",
  fields: [
    {
      key: "nominal_diameter",
      label: "关联管径 / 尺寸 (Size)",
      placeholder: "例如 DN50",
      description: "可选关联管径",
      presets: NOMINAL_DIAMETER_PRESETS,
    },
    {
      key: "medium",
      label: "适用介质 (Medium)",
      placeholder: "例如 CW 或 ST",
      description: "可选工艺介质",
      presets: MEDIUM_PRESETS,
    },
    {
      key: "description",
      label: "工程说明 / 备注",
      placeholder: "输入设计要求或补充说明",
      description: "设计要求或工程注释",
      presets: [],
    },
  ],
};

// -------------------------------------------------------------
// Helper Functions
// -------------------------------------------------------------

export function getSymbolCategory(symbol?: SymbolDefinition | null): PropertyCategory {
  if (!symbol) return "generic";
  const cat = (symbol.category || "").toLowerCase();
  const key = (symbol.key || "").toLowerCase();
  const name = (symbol.name || "").toLowerCase();

  if (
    cat.includes("阀")
    || cat.includes("安全附件")
    || key.includes("valve")
    || name.includes("阀")
  ) {
    return "valve";
  }

  if (
    cat.includes("仪表")
    || key.includes("instrument")
    || key.includes("sensor")
    || key.includes("transmitter")
    || name.includes("仪表")
    || name.includes("变送器")
    || name.includes("温度计")
    || name.includes("压力表")
    || name.includes("流量计")
  ) {
    return "instrument";
  }

  if (
    cat.includes("管件")
    || cat.includes("管道附件")
    || cat.includes("边界")
    || cat.includes("排放")
    || key.includes("opc")
    || key.includes("flange")
    || key.includes("reducer")
    || name.includes("跨图")
    || name.includes("法兰")
    || name.includes("变径")
    || name.includes("盲板")
  ) {
    return "node_fitting";
  }

  if (
    cat.includes("泵")
    || cat.includes("风机")
    || cat.includes("换热")
    || cat.includes("容器")
    || cat.includes("过滤")
    || cat.includes("混合")
    || cat.includes("工艺设备")
    || cat.includes("设备")
    || key.includes("pump")
    || key.includes("tank")
    || key.includes("vessel")
    || key.includes("exchanger")
    || key.includes("column")
    || key.includes("reactor")
    || name.includes("泵")
    || name.includes("罐")
    || name.includes("换热器")
    || name.includes("塔")
    || name.includes("反应器")
  ) {
    return "equipment";
  }

  return "equipment";
}

export function isBasicShapeSymbol(symbol?: SymbolDefinition | null): boolean {
  if (!symbol) return false;
  if (symbol.category === "基础图元") return true;
  const basicKeys = new Set([
    "revision_cloud",
    "hexagon_tag",
    "octagon_box",
    "diamond_decision",
    "cylinder_vessel",
    "cube_cabinet",
    "trapezoid_hopper",
    "parallelogram_io",
    "callout_bubble",
    "block_arrow_right",
  ]);
  return basicKeys.has(symbol.key);
}

export function getElementCategory(element: Element, symbol?: SymbolDefinition | null): PropertyCategory {
  if (element.type === "connector") return "connector";
  if (element.type === "symbol") return getSymbolCategory(symbol);
  if (element.type === "junction") return "node_fitting";
  return "generic";
}

export function getCategorySchema(category: PropertyCategory): CategorySchema {
  switch (category) {
    case "valve": return VALVE_SCHEMA;
    case "equipment": return EQUIPMENT_SCHEMA;
    case "connector": return CONNECTOR_SCHEMA;
    case "instrument": return INSTRUMENT_SCHEMA;
    case "node_fitting": return NODE_FITTING_SCHEMA;
    default: return GENERIC_SCHEMA;
  }
}

export function readElementProperty(element: Element, key: string): string {
  if (element.type === "symbol") {
    const propVal = element.properties?.[key];
    if (typeof propVal === "string" && propVal) return propVal;
    if (typeof propVal === "number") return String(propVal);
  }
  if (element.type === "connector") {
    if (key === "nominal_diameter" && element.nominal_diameter) return element.nominal_diameter;
    if (key === "medium" && element.medium) return element.medium;
    if (key === "process_tag" && element.process_tag) return element.process_tag;
    if (key === "flow_direction" && element.flow_direction) return element.flow_direction;
  }
  const metaVal = element.metadata?.[key];
  if (typeof metaVal === "string") return metaVal;
  if (typeof metaVal === "number") return String(metaVal);
  return "";
}

export function buildPropertyPatch(
  element: Element,
  category: PropertyCategory,
  properties: Record<string, string>,
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  const schema = getCategorySchema(category);
  const metadataPatch: Record<string, unknown> = { ...(element.metadata || {}) };

  for (const field of schema.fields) {
    const val = properties[field.key]?.trim() ?? "";
    metadataPatch[field.key] = val || undefined;
  }

  if (element.type === "symbol") {
    const nextProperties = { ...(element.properties || {}) };
    for (const field of schema.fields) {
      const val = properties[field.key]?.trim() ?? "";
      if (val) nextProperties[field.key] = val;
      else delete nextProperties[field.key];
    }
    patch.properties = nextProperties;
  }

  if (element.type === "connector") {
    if ("nominal_diameter" in properties) patch.nominal_diameter = properties.nominal_diameter.trim();
    if ("medium" in properties) patch.medium = properties.medium.trim();
    if ("process_tag" in properties) patch.process_tag = properties.process_tag.trim();
  }

  patch.metadata = metadataPatch;
  return patch;
}
