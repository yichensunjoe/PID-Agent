// P&ID-Agent 青创大赛路演 PPT 生成脚本
// 运行: node deck.js  →  输出 P&ID-Agent-路演.pptx
"use strict";
const pptxgen = require("pptxgenjs");
const {
  imageSizingContain,
  warnIfSlideHasOverlaps,
  warnIfSlideElementsOutOfBounds,
} = require("./helpers");

const pptx = new pptxgen();
pptx.defineLayout({ name: "WIDE", width: 13.333, height: 7.5 });
pptx.layout = "WIDE";
pptx.author = "P&ID-Agent Team";
pptx.company = "国家电投集团钍基能源科技有限公司";
pptx.title = "P&ID-Agent 路演";
pptx.theme = { headFontFace: "Microsoft YaHei", bodyFontFace: "Microsoft YaHei", lang: "zh-CN" };

// ---------- 设计系统 ----------
const W = 13.333, H = 7.5;
const BG = "0B1220";
const PANEL_FILL = { color: "FFFFFF", transparency: 95 };
const PANEL_FILL_2 = { color: "FFFFFF", transparency: 92 };
const BORDER = { color: "2A3B55", width: 0.75 };
const BORDER_ACCENT = { color: "22D3EE", width: 1.2 };
const CYAN = "22D3EE", BLUE = "3B82F6", GREEN = "34D399", AMBER = "FBBF24", RED = "F87171";
const TXT = "F1F5F9", SUB = "A8B6C8", FAINT = "66788F";
const FONT = "Microsoft YaHei";

let slideNo = 0;

// CJK 感知的换行：中文=1 单位，ASCII≈0.55，空格 0.3
function units(s) {
  let u = 0;
  for (const ch of s) {
    const c = ch.codePointAt(0);
    if (ch === " ") u += 0.35;
    else if (c < 128) u += 0.62;
    else u += 1.0;
  }
  return u;
}
function wrapUnits(s, maxUnits) {
  const lines = [];
  let cur = "";
  for (const ch of s) {
    if (units(cur + ch) <= maxUnits) cur += ch;
    else { lines.push(cur.trim()); cur = ch === " " ? "" : ch; }
  }
  if (cur.trim()) lines.push(cur.trim());
  return lines;
}
function textFit(slide, s, x, y, w, fontSize, opts = {}) {
  const { color = TXT, bold = false, align = "left", valign = "top", maxUnitsPerLine = null,
    lineSpacing = null, paraSpace = 0, fontFace = FONT } = opts;
  const charW = fontSize / 72;
  const maxU = maxUnitsPerLine || Math.floor((w - 0.06) / charW * 1.02);
  const lines = wrapUnits(String(s), maxU);
  return slide.addText(
    lines.map((ln, i) => ({
      text: ln,
      options: {
        breakLine: i < lines.length - 1,
        paraSpaceAfterPt: paraSpace,
        ...(lineSpacing ? { lineSpacingMultiple: lineSpacing } : {}),
      },
    })),
    { x, y, w, h: lines.length * charW * 1.32 + 0.1, fontSize, fontFace, color, bold, align, valign }
  );
}
function bulletLines(items, w, fontSize) {
  const charW = fontSize / 72;
  const maxU = Math.floor((w - 0.28) / charW * 1.02);
  const out = [];
  for (const it of items) {
    for (const ln of wrapUnits(it, maxU)) out.push(ln);
  }
  return out;
}
function base(slide, grid = false) {
  slide.background = { color: BG };
  if (grid) {
    for (let i = 0; i <= 26; i++) {
      slide.addShape(pptx.ShapeType.line, {
        x: (i * W) / 26, y: 0, w: 0, h: H,
        line: { color: "1E2C42", width: 0.5 },
      });
    }
    for (let j = 0; j <= 15; j++) {
      slide.addShape(pptx.ShapeType.line, {
        x: 0, y: (j * H) / 15, w: W, h: 0,
        line: { color: "1E2C42", width: 0.5 },
      });
    }
  }
}
function header(slide, kick, title, sub) {
  slide.addText(kick.toUpperCase(), {
    x: 0.75, y: 0.4, w: 6, h: 0.3, fontSize: 12, fontFace: FONT, color: CYAN, bold: true, charSpacing: 2,
  });
  slide.addShape(pptx.ShapeType.rect, { x: 0.75, y: 0.72, w: 0.42, h: 0.045, fill: { color: CYAN } });
  slide.addText(title, {
    x: 0.75, y: 0.82, w: 11.9, h: 0.62, fontSize: 26, fontFace: FONT, color: TXT, bold: true,
  });
  if (sub) {
    slide.addText(sub, {
      x: 0.75, y: 1.44, w: 11.9, h: 0.3, fontSize: 12.5, fontFace: FONT, color: SUB,
    });
  }
  slide.addShape(pptx.ShapeType.line, {
    x: 0.75, y: 1.82, w: W - 1.5, h: 0, line: { color: "1E2C42", width: 0.75 },
  });
}
function footer(slide) {
  slideNo += 1;
  slide.addText("P&ID-Agent · 人机协同智能工艺流程图设计平台", {
    x: 0.75, y: 7.14, w: 6, h: 0.25, fontSize: 8.5, fontFace: FONT, color: FAINT,
  });
  slide.addText("青创大赛路演 · 2026", {
    x: W - 3.0, y: 7.14, w: 1.6, h: 0.25, fontSize: 8.5, fontFace: FONT, color: FAINT, align: "right",
  });
  slide.addText(String(slideNo).padStart(2, "0"), {
    x: W - 1.15, y: 7.12, w: 0.4, h: 0.25, fontSize: 9, fontFace: FONT, color: CYAN, bold: true, align: "right",
  });
}
function panel(slide, x, y, w, h, opts = {}) {
  const { fill = PANEL_FILL, line = BORDER, radius = 0.07, shadow = true } = opts;
  return slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h, fill, line, rectRadius: radius,
    ...(shadow ? { shadow: { type: "outer", color: "000000", opacity: 0.3, blur: 6, angle: 90, offset: 3 } } : {}),
  });
}
function cardTitle(slide, text, x, y, w, opts = {}) {
  return slide.addText(text, {
    x, y, w, h: 0.34, fontSize: opts.fontSize || 15.5, fontFace: FONT, color: TXT, bold: true,
    ...opts,
  });
}
function chip(slide, text, x, y, opts = {}) {
  const fs = opts.fontSize || 10.5;
  const w = Math.max(0.55, units(text) * fs / 72 + 0.42);
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h: 0.32, fill: { color: "FFFFFF", transparency: 95 },
    line: opts.line || BORDER, rectRadius: 0.16,
  });
  slide.addText(text, {
    x: x + 0.08, y: y + 0.045, w: w - 0.16, h: 0.23, fontSize: fs, fontFace: FONT,
    color: opts.color || SUB, align: "center",
  });
  return w;
}
function imgCard(slide, path, x, y, w, h, opts = {}) {
  const { caption, captionY = h, frameFill = "FFFFFF", radius = 0.07, captionW = w, captionX = x } = opts;
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h, fill: { color: frameFill }, line: { color: "2C3E5C", width: 1 }, rectRadius: radius,
    shadow: { type: "outer", color: "000000", opacity: 0.35, blur: 7, angle: 90, offset: 3 },
  });
  const pad = 0.13;
  slide.addImage({ path, ...imageSizingContain(path, x + pad, y + pad, w - pad * 2, h - pad * 2) });
  if (caption) {
    slide.addText(caption, {
      x: captionX, y: y + captionY + 0.08, w: captionW, h: 0.26, fontSize: 10, fontFace: FONT, color: SUB, align: "center",
    });
  }
}
function arrow(slide, x1, y1, x2, y2, color = CYAN) {
  slide.addShape(pptx.ShapeType.line, { x: x1, y: y1, w: 0, h: 0, line: { color, width: 1.6, endArrowType: "triangle" } });
  slide.addShape(pptx.ShapeType.line, {
    x: Math.min(x1, x2), y: Math.min(y1, y2),
    w: Math.abs(x2 - x1), h: Math.abs(y2 - y1),
    line: { color, width: 1.6, endArrowType: "triangle" },
  });
}
// 水平箭头（从左到右）
function harrow(slide, x1, x2, y, color = "2A3B55") {
  slide.addShape(pptx.ShapeType.line, {
    x: x1, y, w: x2 - x1, h: 0, line: { color, width: 1.4, endArrowType: "triangle" },
  });
}
function check(slide, cb, last = false) {
  slide.addShape(pptx.ShapeType.line, { x: cb.x1, y: cb.y1, w: 0, h: 0, line: { color: cb.c, width: 1.4, endArrowType: last ? "triangle" : "none" } });
}

// ================= 第 1 页 · 封面 =================
(function () {
  const s = pptx.addSlide();
  base(s, true);
  // 右下角光晕
  // 有意装饰：右上角光晕（先绘制、位于所有内容之下；与图框角部轻微重叠为设计意图）
  s.addShape(pptx.ShapeType.ellipse, {
    x: 11.55, y: 0.1, w: 1.75, h: 1.75, fill: { color: CYAN, transparency: 90 }, line: { color: BG, width: 0.5 },
  });
  s.addShape(pptx.ShapeType.ellipse, {
    x: 12.15, y: 0.7, w: 1.1, h: 1.1, fill: { color: BLUE, transparency: 86 }, line: { color: BG, width: 0.5 },
  });
  // 左上品牌
  s.addShape(pptx.ShapeType.roundRect, {
    x: 0.75, y: 0.6, w: 1.05, h: 0.42, fill: { color: CYAN }, rectRadius: 0.1,
  });
  s.addText("P&ID", { x: 0.75, y: 0.665, w: 1.05, h: 0.3, fontSize: 13, fontFace: FONT, color: "062027", bold: true, align: "center" });
  s.addText("A G E N T", { x: 1.92, y: 0.68, w: 2.4, h: 0.28, fontSize: 11, fontFace: FONT, color: SUB, bold: true, charSpacing: 3 });
  s.addText("青创大赛 · 项目路演 · 2026", { x: 0.78, y: 1.85, w: 5, h: 0.3, fontSize: 12, fontFace: FONT, color: CYAN, bold: true, charSpacing: 2 });
  s.addText("P&ID-Agent", { x: 0.72, y: 2.25, w: 5.7, h: 1.0, fontSize: 48, fontFace: FONT, color: TXT, bold: true });
  s.addText("人机协同的智能工艺流程图设计平台", { x: 0.78, y: 3.28, w: 5.7, h: 0.55, fontSize: 21, fontFace: FONT, color: "BDE9F5", bold: true });
  s.addShape(pptx.ShapeType.rect, { x: 0.78, y: 3.92, w: 1.5, h: 0.05, fill: { color: CYAN } });
  s.addText("让工程师与 AI 共用一张图、同一种语言、同一套规则", {
    x: 0.78, y: 4.15, w: 5.5, h: 0.6, fontSize: 13.5, fontFace: FONT, color: SUB,
  });
  let cc = 0.78;
  cc += chip(s, "浏览器原生", cc, 5.0) + 0.25;
  cc += chip(s, "AI 原生", cc, 5.0) + 0.25;
  cc += chip(s, "开源 MIT", cc, 5.0) + 0.25;
  chip(s, "MCP 协议", cc, 5.0);
  s.addText("国家电投集团钍基能源科技有限公司", { x: 0.78, y: 6.55, w: 5.5, h: 0.35, fontSize: 12.5, fontFace: FONT, color: "D5DEEA", bold: true });
  s.addText("GitHub 开源 · v2.1.0-alpha.1", { x: 0.78, y: 6.92, w: 5.5, h: 0.3, fontSize: 10.5, fontFace: FONT, color: FAINT });
  // 右侧主图
  imgCard(s, "assets/argon_pid_final.png", 6.75, 1.0, 5.85, 4.95, {
    caption: "氩气供气与循环系统 P&ID（闭式循环）· 444 图元 · 由 P&ID-Agent 绘制",
    captionY: 4.95,
  });
  s.addText("▸ 结构化图纸：全元素可选中 · 可修改 · 可导出 PDF / DXF / CSV", {
    x: 6.75, y: 6.35, w: 5.85, h: 0.3, fontSize: 10.5, fontFace: FONT, color: CYAN, align: "center",
  });
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

// ================= 第 2 页 · 目录 =================
(function () {
  const s = pptx.addSlide();
  base(s);
  s.addText("CONTENTS", { x: 0.75, y: 1.0, w: 4, h: 0.9, fontSize: 40, fontFace: FONT, color: "23334C", bold: true });
  s.addText("目录", { x: 0.75, y: 1.95, w: 4, h: 0.6, fontSize: 26, fontFace: FONT, color: TXT, bold: true });
  s.addShape(pptx.ShapeType.rect, { x: 0.75, y: 2.7, w: 0.42, h: 0.045, fill: { color: CYAN } });
  const items = [
    ["01", "为什么做", "行业痛点与机会窗口"],
    ["02", "做什么", "产品定位与核心能力"],
    ["03", "凭什么", "四层可靠性架构与验收证据"],
    ["04", "卖给谁", "市场、竞争与商业模式"],
    ["05", "怎么走", "团队、实施计划与经济效益"],
  ];
  items.forEach((it, i) => {
    const y = 1.45 + i * 0.95;
    s.addText(it[0], { x: 5.1, y, w: 0.9, h: 0.5, fontSize: 26, fontFace: FONT, color: CYAN, bold: true });
    s.addText(it[1], { x: 6.15, y: y + 0.03, w: 2.4, h: 0.45, fontSize: 19, fontFace: FONT, color: TXT, bold: true });
    s.addText(it[2], { x: 8.55, y: y + 0.11, w: 4.0, h: 0.35, fontSize: 12.5, fontFace: FONT, color: SUB });
    s.addShape(pptx.ShapeType.line, { x: 6.15, y: y + 0.62, w: 6.4, h: 0, line: { color: "1E2C42", width: 0.75 } });
  });
  panel(s, 5.1, 6.15, 7.45, 0.8, { fill: PANEL_FILL_2 });
  s.addText("当前状态", { x: 5.35, y: 6.25, w: 1.4, h: 0.3, fontSize: 11, fontFace: FONT, color: CYAN, bold: true });
  s.addText("v2.1.0-alpha.1 已开源（MIT）· 原型 / Alpha / Beta 三个里程碑已按期完成 · CI 全绿", {
    x: 5.35, y: 6.56, w: 7.0, h: 0.35, fontSize: 12, fontFace: FONT, color: TXT,
  });
  footer(s);
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

// ================= 第 3 页 · 痛点 =================
(function () {
  const s = pptx.addSlide();
  base(s);
  header(s, "01 · 为什么做", "一张 P&ID 贯穿工程全生命周期，工具却还停在十年前");
  const cards = [
    ["上手门槛高", "通用 CAD 体量大、命令多；画出一张规范的 P&ID，依赖工程师多年的经验与规范积累。"],
    ["图纸没有语义", "设备、管线、连接关系只是图形元素，机器读不懂，无法自动检查、统计、复用。"],
    ["AI 介入不足", "工程行业对 AI 辅助设计需求迫切，却一直没有一款为流程设计而生的轻量工具。"],
    ["人机两张图", "人工修改与 AI 自动生成互相脱节，版本冲突、返工是常态，效率被内耗掉。"],
  ];
  cards.forEach((c, i) => {
    const x = 0.75 + (i % 2) * 6.05;
    const y = 2.0 + Math.floor(i / 2) * 1.85;
    panel(s, x, y, 5.8, 1.6);
    s.addShape(pptx.ShapeType.rect, { x: x + 0.18, y: y + 0.28, w: 0.06, h: 0.42, fill: { color: i % 2 === 0 ? CYAN : BLUE } });
    cardTitle(s, c[0], x + 0.42, y + 0.18, 5.2);
    textFit(s, c[1], x + 0.42, y + 0.6, 5.15, 12, { color: SUB, lineSpacing: 1.15 });
  });
  panel(s, 0.75, 5.85, 11.83, 0.95, { fill: { color: CYAN, transparency: 93 }, line: { color: "155E75", width: 0.75 } });
  s.addText("P&ID 是最核心的系统设计文件", { x: 1.0, y: 6.0, w: 4.2, h: 0.3, fontSize: 13, fontFace: FONT, color: CYAN, bold: true });
  s.addText("概念设计 → 初步设计 → 施工设计 → 建安运维，全程依赖；而核能、化工、电力正处于数字化与 AI 应用的窗口期。", {
    x: 1.0, y: 6.32, w: 11.3, h: 0.35, fontSize: 12, fontFace: FONT, color: TXT,
  });
  footer(s);
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

// ================= 第 4 页 · 产品定位 =================
(function () {
  const s = pptx.addSlide();
  base(s);
  header(s, "02 · 做什么", "只做 P&ID 这一件事，把它做到轻、准、通");
  s.addText("P&ID-Agent —— 浏览器端、人机共编的工艺流程图专用工具", {
    x: 0.75, y: 2.0, w: 11.83, h: 0.5, fontSize: 17, fontFace: FONT, color: "BDE9F5", bold: true, align: "center",
  });
  const pillars = [
    ["轻", "浏览器即用", "打开网页就能画，零安装、零运维；拖放即绘图，几分钟上手。"],
    ["准", "图纸有语义", "端口、管线、节点全部结构化，AI 读得懂、查得出问题、一键出报表。"],
    ["通", "人机共编", "人工与 AI 操作同一份文档、同一套图例，revision 并发控制，互不覆盖。"],
  ];
  pillars.forEach((p, i) => {
    const x = 0.75 + i * 4.08;
    panel(s, x, 2.75, 3.83, 2.6);
    s.addShape(pptx.ShapeType.ellipse, { x: x + 0.3, y: 3.0, w: 0.72, h: 0.72, fill: { color: CYAN, transparency: 82 }, line: { color: CYAN, width: 1 } });
    s.addText(p[0], { x: x + 0.3, y: 3.1, w: 0.72, h: 0.55, fontSize: 24, fontFace: FONT, color: CYAN, bold: true, align: "center" });
    s.addText(p[1], { x: x + 1.2, y: 3.13, w: 2.5, h: 0.45, fontSize: 17, fontFace: FONT, color: TXT, bold: true });
    textFit(s, p[2], x + 0.3, 3.7, 3.23, 12.5, { color: SUB, lineSpacing: 1.25 });
  });
  panel(s, 0.75, 5.7, 11.83, 0.95, { fill: PANEL_FILL_2 });
  s.addText("明确的边界", { x: 1.0, y: 5.84, w: 1.6, h: 0.3, fontSize: 13, fontFace: FONT, color: AMBER, bold: true });
  s.addText("不造第二个 AutoCAD：不做三维、BIM、机械零件与通用命令堆砌——把力气全部花在“画好一张流程图”上。", {
    x: 1.0, y: 6.16, w: 11.3, h: 0.35, fontSize: 12, fontFace: FONT, color: TXT,
  });
  footer(s);
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

// ================= 第 5 页 · 编辑器能力 =================
(function () {
  const s = pptx.addSlide();
  base(s);
  header(s, "02 · 做什么", "工程师熟悉的画图体验，一样都不少");
  const items = [
    "设备图形拖放 + 端口吸附，管线只连真实端口",
    "正交管线、折点调整、跨线桥，相交≠连接",
    "连接节点：主管线原子拆分，真实分支/汇合拓扑",
    "多选 / 框选 / 复制粘贴 / 撤销重做，全流程快捷键",
    "图层、锁定、批量属性、大图 minimap 导航",
    "中键平移 · 滚轮缩放 · 网格吸附，操作零学习成本",
  ];
  const b = bulletLines(items, 5.1, 12.5);
  s.addText(b.map((ln, i) => ({ text: ln, options: { bullet: { code: "25AA", indent: 14, color: CYAN }, breakLine: i < b.length - 1, paraSpaceAfterPt: 10 } })), {
    x: 0.75, y: 2.05, w: 5.5, h: 2.3, fontSize: 12.5, fontFace: FONT, color: "C9D4E3", valign: "top",
  });
  panel(s, 0.75, 6.35, 5.5, 0.55, { fill: PANEL_FILL_2, shadow: false });
  s.addText("92 项前端单元测试 · 37 项浏览器端到端验收 · 视觉快照回归", {
    x: 0.95, y: 6.46, w: 5.2, h: 0.3, fontSize: 10.5, fontFace: FONT, color: CYAN,
  });
  imgCard(s, "assets/engineering-drawing.png", 6.55, 2.0, 6.0, 4.0, {
    caption: "浏览器编辑器实拍：主管线 + 支路 + 仪表，全元素可选中、可修改",
    captionY: 4.0,
  });
  chip(s, "SVG 实时渲染", 6.55, 6.45);
  chip(s, "深浅双主题", 7.85, 6.45);
  chip(s, "命令面板", 9.15, 6.45);
  footer(s);
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

// ================= 第 6 页 · 真实图纸 =================
(function () {
  const s = pptx.addSlide();
  base(s);
  header(s, "02 · 做什么", "不是 Demo 玩具：一张真实工程的氩气系统 P&ID");
  imgCard(s, "assets/argon_pid_final.png", 0.75, 2.05, 7.6, 4.75, {
    caption: "氩气供气与循环系统（闭式循环）· 444 图元 · 可继续编辑",
    captionY: 4.75,
  });
  const facts = [
    ["三回路按介质着色", "供气（蓝）→ 尾气冷凝（绿）→ 循环（红），工程逻辑一目了然。"],
    ["全谱设备图例", "供气柜、盐循环泵、溢流罐、过滤器、换热器 + 20 余个止回阀、24 块压力表。"],
    ["交付级导出", "PDF / PNG / DXF / JSON 一键导出，设备表、管线表、仪表索引自动生成。"],
  ];
  facts.forEach((f, i) => {
    const y = 2.05 + i * 1.6;
    panel(s, 8.6, y, 4.0, 1.42);
    s.addText(f[0], { x: 8.85, y: y + 0.15, w: 3.55, h: 0.35, fontSize: 13.5, fontFace: FONT, color: CYAN, bold: true });
    textFit(s, f[1], 8.85, y + 0.55, 3.5, 11, { color: SUB, lineSpacing: 1.15 });
  });
  panel(s, 8.6, 6.9, 4.0, 0.0, { shadow: false });
  s.addText("结构化数据 → 可查询、可检查、可导入导出，不只是像素。", {
    x: 8.6, y: 6.78, w: 4.0, h: 0.3, fontSize: 10.5, fontFace: FONT, color: FAINT, align: "center",
  });
  footer(s);
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

// ================= 第 7 页 · AI 生成架构 =================
(function () {
  const s = pptx.addSlide();
  base(s);
  header(s, "03 · 凭什么", "AI 画图靠不靠谱？四层确定性边界把风险关在门外");
  const steps = [
    ["① 模型只出拓扑计划", "输出图例 key、真实端口与连接关系，不直接决定像素路径。", BLUE],
    ["② 语义编译器校验", "JSON Schema、图例、端口、介质、流向逐项验证，错误即拒绝。", CYAN],
    ["③ 确定性路由器", "按端口外法线走最短正交路径，自动避障，相交管线画跨线桥。", GREEN],
    ["④ 质量门禁 ≥95 分", "正交性、重叠、穿设备、重复标签逐项打分；不合格带 issue code 回炉重规划。", AMBER],
  ];
  steps.forEach((st, i) => {
    const x = 0.75 + i * 3.05;
    panel(s, x, 2.0, 2.83, 2.55, { line: { color: st[2], width: 1.1 } });
    s.addText(st[0], { x: x + 0.2, y: 2.2, w: 2.45, h: 0.75, fontSize: 14, fontFace: FONT, color: TXT, bold: true });
    textFit(s, st[1], x + 0.2, 3.0, 2.45, 11, { color: SUB, lineSpacing: 1.2 });
    if (i < 3) harrow(s, x + 2.83, x + 3.05, 3.27);
  });
  panel(s, 0.75, 4.95, 11.83, 1.15, { fill: { color: CYAN, transparency: 92 }, line: BORDER_ACCENT });
  s.addText("原子事务落库", { x: 1.05, y: 5.12, w: 2.2, h: 0.35, fontSize: 14.5, fontFace: FONT, color: CYAN, bold: true });
  s.addText("全部操作一次成功、或完全不写入 · revision 乐观并发，AI 盖不掉人工修改 · 全程可撤销、可重做、可追踪", {
    x: 1.05, y: 5.5, w: 11.2, h: 0.4, fontSize: 12.5, fontFace: FONT, color: TXT,
  });
  s.addText("同一计划 → 同一张图（确定性）；错误计划 → 干净的拒绝 + 稳定错误码（可修复）。模型只被允许“出错”，不被允许“写坏”。", {
    x: 0.75, y: 6.4, w: 11.83, h: 0.4, fontSize: 11.5, fontFace: FONT, color: FAINT, align: "center",
  });
  footer(s);
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

// ================= 第 8 页 · 可靠性证据 =================
(function () {
  const s = pptx.addSlide();
  base(s);
  header(s, "03 · 凭什么", "可靠性不是口号：可复现的模型验收矩阵");
  // 表头
  panel(s, 0.75, 2.0, 7.4, 0.5, { fill: { color: CYAN, transparency: 88 }, shadow: false });
  s.addText("模型", { x: 1.0, y: 2.08, w: 3.0, h: 0.32, fontSize: 12, fontFace: FONT, color: CYAN, bold: true });
  s.addText("15 场景 × 3 次", { x: 4.15, y: 2.08, w: 2.3, h: 0.32, fontSize: 12, fontFace: FONT, color: CYAN, bold: true, align: "center" });
  s.addText("结论", { x: 6.45, y: 2.08, w: 1.5, h: 0.32, fontSize: 12, fontFace: FONT, color: CYAN, bold: true, align: "center" });
  const rows = [
    ["DeepSeek-V4-Flash", "15 / 15 · 100%", "验收通过", GREEN],
    ["Qwen3.6-35B（本地 Ollama）", "15 / 15 · 100%", "验收通过", GREEN],
    ["第三方通用模型（试跑）", "11 / 15 · 78.6%", "判为不可用", RED],
  ];
  rows.forEach((r, i) => {
    const y = 2.5 + i * 0.72;
    panel(s, 0.75, y, 7.4, 0.64, { fill: PANEL_FILL, shadow: false });
    s.addText(r[0], { x: 1.0, y: y + 0.14, w: 3.0, h: 0.35, fontSize: 12, fontFace: FONT, color: TXT, bold: true });
    s.addText(r[1], { x: 4.15, y: y + 0.14, w: 2.3, h: 0.35, fontSize: 12, fontFace: FONT, color: SUB, align: "center" });
    s.addText(r[2], { x: 6.45, y: y + 0.14, w: 1.5, h: 0.35, fontSize: 12, fontFace: FONT, color: r[3], bold: true, align: "center" });
  });
  textFit(s, "方法：拓扑断言 + 图面质量双验收；不达标的模型被系统明确拒收——我们不宣称“什么模型都能画”。",
    0.75, 4.78, 7.4, 10.5, { color: FAINT });
  panel(s, 8.45, 2.0, 4.13, 3.42, { line: BORDER_ACCENT });
  s.addText("如果 AI 画错了？", { x: 8.72, y: 2.2, w: 3.6, h: 0.4, fontSize: 16, fontFace: FONT, color: TXT, bold: true });
  const lines = [
    "它没有机会“画错”：任何修改必须通过 Schema 与语义校验才允许写入",
    "事务原子性：失败不会留下半张图",
    "稳定 issue code 反馈模型自动重规划（≤3 轮）",
    "271 项后端测试 + 92 项前端测试 + 37 项浏览器验收 + CI 全绿",
  ];
  s.addText(lines.map((ln, i) => ({ text: ln, options: { bullet: { code: "25AA", indent: 14, color: CYAN }, breakLine: i < lines.length - 1, paraSpaceAfterPt: 8 } })), {
    x: 8.72, y: 2.7, w: 3.65, h: 2.5, fontSize: 11.5, fontFace: FONT, color: "C9D4E3", valign: "top",
  });
  panel(s, 8.45, 5.62, 4.13, 0.8, { fill: PANEL_FILL_2, shadow: false });
  s.addText("公开仓库可复现：pid-agent model-matrix", {
    x: 8.7, y: 5.86, w: 3.7, h: 0.3, fontSize: 10.5, fontFace: FONT, color: CYAN, align: "center",
  });
  footer(s);
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

// ================= 第 9 页 · 三种工作方式 =================
(function () {
  const s = pptx.addSlide();
  base(s);
  header(s, "02 · 做什么", "三种工作方式，覆盖从草图到交付全流程");
  const modes = [
    ["1", "人工自由绘图", "拖放设备、连接管线、标注位号；设计习惯完全不变，几分钟上手。", BLUE],
    ["2", "AI 语义生成", "输入一段系统描述，AI 自动布置设备、连接管线、标注位号，一次成图。", CYAN],
    ["3", "人机协同修改", "AI 出草图、人来调整；人画草图、AI 补全优化。先预览、后应用。", GREEN],
  ];
  modes.forEach((m, i) => {
    const x = 0.75 + i * 4.08;
    panel(s, x, 2.0, 3.83, 2.5);
    s.addShape(pptx.ShapeType.ellipse, { x: x + 0.28, y: 2.25, w: 0.6, h: 0.6, fill: { color: m[3], transparency: 82 }, line: { color: m[3], width: 1 } });
    s.addText(m[0], { x: x + 0.28, y: 2.33, w: 0.6, h: 0.45, fontSize: 20, fontFace: FONT, color: m[3], bold: true, align: "center" });
    s.addText(m[1], { x: x + 1.0, y: 2.33, w: 2.7, h: 0.45, fontSize: 16.5, fontFace: FONT, color: TXT, bold: true });
    textFit(s, m[2], x + 0.28, 2.95, 3.3, 12, { color: SUB, lineSpacing: 1.3 });
  });
  imgCard(s, "assets/agent-ghost-preview.png", 2.45, 4.82, 8.4, 1.9, {
    caption: "AI 修改先以“幽灵预览”展示，工程师确认后才写入——人始终是最终拍板人",
    captionY: 1.9,
  });
  footer(s);
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

// ================= 第 10 页 · 技术架构 =================
(function () {
  const s = pptx.addSlide();
  base(s);
  header(s, "03 · 凭什么", "一条事务总线，四个接入面，一个真相源");
  const clients = ["React 浏览器编辑器", "REST API", "Python Client", "MCP Server（stdin）"];
  clients.forEach((c, i) => {
    const x = 0.75 + i * 2.2;
    s.addShape(pptx.ShapeType.roundRect, {
      x, y: 2.0, w: 1.98, h: 0.55, fill: { color: BLUE, transparency: 80 }, line: { color: BLUE, width: 1 }, rectRadius: 0.08,
    });
    s.addText(c, { x: x + 0.06, y: 2.12, w: 1.86, h: 0.32, fontSize: 10.5, fontFace: FONT, color: TXT, bold: true, align: "center" });
    if (i < 3) harrow(s, x + 1.98, x + 2.2, 2.27, "2A3B55");
  });
  s.addShape(pptx.ShapeType.roundRect, {
    x: 0.75, y: 2.85, w: 8.77, h: 0.6, fill: { color: CYAN, transparency: 85 }, line: BORDER_ACCENT, rectRadius: 0.08,
  });
  s.addText("TransactionRequest · 原子事务总线 —— 人工与 AI 走同一个入口，谁也不能绕过验证", {
    x: 0.95, y: 2.97, w: 8.4, h: 0.35, fontSize: 12, fontFace: FONT, color: "BDE9F5", bold: true,
  });
  // 右侧 LLM 规划器
  s.addShape(pptx.ShapeType.roundRect, {
    x: 9.9, y: 2.0, w: 2.68, h: 1.45, fill: PANEL_FILL, line: BORDER, rectRadius: 0.08,
  });
  s.addText("LLM 规划器", { x: 10.1, y: 2.15, w: 2.3, h: 0.35, fontSize: 13, fontFace: FONT, color: TXT, bold: true, align: "center" });
  s.addText("只生成结构化事务\\n不接触数据库、不执行代码\\n标准兼容协议 / 本地开源模型", {
    x: 10.1, y: 2.55, w: 2.3, h: 0.85, fontSize: 9.5, fontFace: FONT, color: SUB, align: "center",
  });
  s.addShape(pptx.ShapeType.line, { x: 9.53, y: 3.15, w: 0.37, h: 0, line: { color: "2A3B55", width: 1.4, startArrowType: "triangle" } });
  // 服务层
  s.addShape(pptx.ShapeType.roundRect, {
    x: 0.75, y: 3.75, w: 8.77, h: 0.55, fill: PANEL_FILL, line: BORDER, rectRadius: 0.08,
  });
  s.addText("FastAPI 服务层 · 参数转换 · 身份与安全边界 · 请求限流", {
    x: 0.95, y: 3.87, w: 8.4, h: 0.32, fontSize: 11.5, fontFace: FONT, color: "C9D4E3",
  });
  // 核心
  s.addShape(pptx.ShapeType.roundRect, {
    x: 0.75, y: 4.6, w: 8.77, h: 1.0, fill: { color: "FFFFFF", transparency: 92 }, line: { color: CYAN, width: 1.2 }, rectRadius: 0.08,
  });
  s.addText("DocumentService · 单一文档真相源", { x: 0.95, y: 4.74, w: 4.6, h: 0.35, fontSize: 13.5, fontFace: FONT, color: TXT, bold: true });
  s.addText("原子事务 · revision 乐观并发 · 撤销/重做 · 拓扑与场景摘要 · 质量门禁", {
    x: 0.95, y: 5.12, w: 8.4, h: 0.35, fontSize: 10.5, fontFace: FONT, color: SUB,
  });
  // 存储
  const stores = [
    ["SQLiteDocumentStore", "文档 / 图层 / 图元 / 管线\\n快照历史 · 备份恢复"],
    ["SymbolRegistry 单位图例", "符号 + 端口 + 介质\\n企业图例可覆盖"],
  ];
  stores.forEach((st, i) => {
    const x = 0.75 + i * 4.55;
    s.addShape(pptx.ShapeType.roundRect, {
      x, y: 5.8, w: 4.3, h: 0.72, fill: PANEL_FILL, line: BORDER, rectRadius: 0.08,
    });
    s.addText(st[0], { x: x + 0.18, y: 5.9, w: 3.9, h: 0.28, fontSize: 11.5, fontFace: FONT, color: TXT, bold: true, align: "center" });
    s.addText(st[1], { x: x + 0.18, y: 6.18, w: 3.9, h: 0.3, fontSize: 9, fontFace: FONT, color: FAINT, align: "center" });
  });
  // 技术栈 chips
  const techs = ["Python 3.11+ · FastAPI · Pydantic · SQLite · CairoSVG", "React 19 · TypeScript · Vite · Zustand · SVG", "导出 JSON/SVG/PNG/PDF/DXF/CSV"];
  let tx = 0.75;
  techs.forEach((t) => {
    tx += chip(s, t, tx, 6.75) + 0.25;
  });
  footer(s);
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

// ================= 第 11 页 · 图例库 =================
(function () {
  const s = pptx.addSlide();
  base(s);
  header(s, "03 · 凭什么", "单位图例库：人与 AI 共用的同一套工程语言");
  const items = [
    "55+ 标准符号 · 12 大分类：泵 / 风机 / 换热 / 容器 / 过滤 / 阀门 / 安全附件 / 管件 / 仪表…",
    "声明式 JSON：符号 key、端口、介质、位号规则、使用约束全部内建，人和 AI 读同一份定义",
    "覆盖 GB/T 国标阀门符号（闸阀、截止阀、止回阀、调节阀、蝶阀…），不拿通用球阀糊弄",
    "图例一致性离线校验：坏图例进不了库；企业图例可覆盖、可版本化",
  ];
  const b = bulletLines(items, 5.1, 12);
  s.addText(b.map((ln, i) => ({ text: ln, options: { bullet: { code: "25AA", indent: 14, color: CYAN }, breakLine: i < b.length - 1, paraSpaceAfterPt: 9 } })), {
    x: 0.75, y: 2.05, w: 5.4, h: 2.4, fontSize: 12, fontFace: FONT, color: "C9D4E3", valign: "top",
  });
  panel(s, 0.75, 6.35, 5.4, 0.55, { fill: PANEL_FILL_2, shadow: false });
  s.addText("pid-agent quality-harness · 图例完整性 / 拓扑事务 / 质量门禁 四层离线验收", {
    x: 0.95, y: 6.46, w: 5.0, h: 0.3, fontSize: 10.5, fontFace: FONT, color: CYAN,
  });
  imgCard(s, "assets/valves_gbt.png", 6.5, 2.0, 5.1, 2.6, {
    caption: "内置图例库 · GB/T 阀门符号（部分）", captionY: 2.6, captionW: 4.9,
  });
  imgCard(s, "assets/valves_gbt_vs_standard.png", 11.85, 2.0, 0.75, 2.6, { caption: "", captionY: 2.6 });
  s.addText("国标 vs 内置对照", { x: 11.55, y: 4.63, w: 1.35, h: 0.26, fontSize: 10, fontFace: FONT, color: FAINT, align: "center" });
  panel(s, 6.5, 4.95, 6.1, 1.3, { fill: PANEL_FILL_2, shadow: false });
  s.addText("为什么这构成壁垒", { x: 6.75, y: 5.1, w: 2.6, h: 0.3, fontSize: 12, fontFace: FONT, color: AMBER, bold: true });
  textFit(s, "符号库是“共同语言”：换一家单位，换一份图例即可，编辑器内核与 Agent 能力不变——行业经验沉淀成可复用资产。",
    6.75, 5.45, 5.6, 11, { color: SUB, lineSpacing: 1.2 });
  footer(s);
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

// ================= 第 12 页 · 市场 =================
(function () {
  const s = pptx.addSlide();
  base(s);
  header(s, "04 · 卖给谁", "数万设计人员 · 数亿元市场 · 三层真实客户");
  s.addText("目标客户", { x: 0.75, y: 2.0, w: 2, h: 0.35, fontSize: 14, fontFace: FONT, color: CYAN, bold: true });
  const tiers = [
    ["③", "核电 · 国防", "自主可控刚性要求，国产开源工具拥有天然信任优势——进口竞品无法逾越的定位壁垒。"],
    ["②", "大型设计院 · 基层科室", "需要高效的系统流程设计与图纸编辑，追求快速上手与团队协同。"],
    ["①", "中小型工程公司 / 设计院", "成本敏感，轻量、浏览器即用、免费基础版是真实刚需。"],
  ];
  // 有意设计：以下卡片文字均绘制在所属面板之上
  tiers.forEach((t, i) => {
    const y = 2.45 + i * 1.05;
    const w = 5.6 - i * 0.35;
    const x = 0.75 + (5.6 - w) / 2;
    panel(s, x, y, w, 0.92, { line: i === 0 ? BORDER_ACCENT : BORDER });
    s.addText(t[0], { x: x + 0.2, y: y + 0.16, w: 0.5, h: 0.6, fontSize: 20, fontFace: FONT, color: i === 0 ? CYAN : FAINT, bold: true });
    s.addText(t[1], { x: x + 0.72, y: y + 0.13, w: 2.4, h: 0.32, fontSize: 13.5, fontFace: FONT, color: TXT, bold: true });
    textFit(s, t[2], x + 0.72, y + 0.5, w - 0.95, 10.5, { color: SUB });
  });
  panel(s, 0.75, 5.75, 5.6, 0.95, { fill: { color: CYAN, transparency: 93 }, line: { color: "155E75", width: 0.75 } });
  s.addText("市场规模（保守估计）", { x: 1.0, y: 5.9, w: 2.6, h: 0.3, fontSize: 11.5, fontFace: FONT, color: CYAN, bold: true });
  s.addText("国内 P&ID 相关设计人员数万人 · 市场空间可达数亿元", {
    x: 1.0, y: 6.2, w: 5.1, h: 0.4, fontSize: 13.5, fontFace: FONT, color: TXT, bold: true,
  });
  s.addText("竞争格局", { x: 6.85, y: 2.0, w: 2, h: 0.35, fontSize: 14, fontFace: FONT, color: CYAN, bold: true });
  const comps = [
    ["通用 CAD（AutoCAD / 中望）", "大而全，但体量大、价格不低，P&ID 只是众多功能之一", false],
    ["专业 P&ID（SmartPlant 等）", "功能专业，但价格高、部署重、需专门学习，没有 AI 嵌入", false],
    ["P&ID-Agent", "只做 P&ID · 轻 · 快 · AI 原生 · 开源国产 · 自主可控", true],
  ];
  comps.forEach((c, i) => {
    const y = 2.45 + i * 1.05;
    panel(s, 6.85, y, 5.73, 0.92, {
      fill: c[2] ? { color: CYAN, transparency: 90 } : PANEL_FILL,
      line: c[2] ? BORDER_ACCENT : BORDER,
    });
    s.addText(c[0], { x: 7.1, y: y + 0.12, w: 3.6, h: 0.32, fontSize: 12.5, fontFace: FONT, color: c[2] ? "BDE9F5" : TXT, bold: true });
    textFit(s, c[1], 7.1, y + 0.5, 5.25, 10.5, { color: c[2] ? "C9D4E3" : SUB });
  });
  panel(s, 6.85, 5.75, 5.73, 0.95, { fill: PANEL_FILL_2 });
  s.addText("差异化切入", { x: 7.1, y: 5.9, w: 1.8, h: 0.3, fontSize: 11.5, fontFace: FONT, color: AMBER, bold: true });
  textFit(s, "从架构第一天就为 AI 设计，不是事后打补丁——这个起点差异会随时间拉大。",
    7.1, 6.2, 5.25, 11.5, { color: TXT });
  footer(s);
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

// ================= 第 13 页 · 商业模式 =================
(function () {
  const s = pptx.addSlide();
  base(s);
  header(s, "04 · 卖给谁", "三步走：开源攒口碑 → 企业版上量 → SaaS 并行");
  const tiers = [
    ["基础版 · 免费", "MIT 开源", "编辑器、AI 接入、标准导出全部免费——先攒用户与口碑，让社区把产品滚起来。"],
    ["企业版 · 年订阅", "5–30 万元 / 年", "私有化部署、SSO、审批流、知识库对接、单位符号库定制与技术支持。"],
    ["SaaS 云 · 月付", "面向中小团队", "托管式协同编辑与项目管理，按月付费，降低中小团队使用门槛。"],
  ];
  tiers.forEach((t, i) => {
    const x = 0.75 + i * 4.08;
    panel(s, x, 2.0, 3.83, 1.9, { line: i === 1 ? BORDER_ACCENT : BORDER });
    s.addText(t[0], { x: x + 0.25, y: 2.18, w: 2.2, h: 0.35, fontSize: 14, fontFace: FONT, color: TXT, bold: true });
    s.addText(t[1], { x: x + 2.45, y: 2.2, w: 1.2, h: 0.32, fontSize: 10, fontFace: FONT, color: i === 1 ? CYAN : SUB, align: "right" });
    textFit(s, t[2], x + 0.25, 2.62, 3.33, 11, { color: SUB, lineSpacing: 1.25 });
  });
  // 收入预期图表
  s.addText("收入预期（万元 / 年）", { x: 0.75, y: 4.15, w: 3.5, h: 0.35, fontSize: 13, fontFace: FONT, color: CYAN, bold: true });
  const chartData = [
    { name: "保守", labels: ["第一年", "第二年", "第三年"], values: [0, 100, 500] },
    { name: "乐观", labels: ["第一年", "第二年", "第三年"], values: [20, 300, 1000] },
  ];
  s.addChart(pptx.ChartType.bar, chartData, {
    x: 0.75, y: 4.55, w: 6.1, h: 2.35,
    barDir: "col",
    barGrouping: "clustered",
    chartColors: [BLUE, CYAN],
    chartColorsOpacity: 80,
    showLegend: true, legendPos: "b", legendColor: SUB, legendFontSize: 9,
    showValue: true, dataLabelColor: SUB, dataLabelFontSize: 9, dataLabelPosition: "outEnd",
    catAxisLabelColor: SUB, catAxisLabelFontSize: 10,
    valAxisLabelColor: FAINT, valAxisLabelFontSize: 9,
    valGridLine: { style: "none" }, catGridLine: { style: "none" },
    valAxisLineColor: "2A3B55", catAxisLineColor: "2A3B55",
    chartArea: { fill: { color: "0B1220" } },
    plotArea: { fill: { color: "0B1220" } },
  });
  const notes = [
    "第一年社区优先，收入 0–20 万（企业定制零散收入）",
    "第二年企业版成熟上量，100–300 万",
    "第三年企业版 + SaaS 双线并行，500–1000 万",
  ];
  s.addText(notes.map((n, i) => ({ text: n, options: { bullet: { code: "25AA", indent: 14, color: CYAN }, breakLine: i < notes.length - 1, paraSpaceAfterPt: 8 } })), {
    x: 7.15, y: 4.55, w: 5.45, h: 1.6, fontSize: 11.5, fontFace: FONT, color: "C9D4E3", valign: "top",
  });
  panel(s, 7.15, 6.25, 5.43, 0.65, { fill: PANEL_FILL_2, shadow: false });
  s.addText("企业版订阅价仅为商业软件的 1/5–1/10 · 浏览器架构，客户 IT 运维成本趋近于零", {
    x: 7.4, y: 6.4, w: 5.0, h: 0.35, fontSize: 11, fontFace: FONT, color: AMBER,
  });
  footer(s);
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

// ================= 第 14 页 · 竞争优势 =================
(function () {
  const s = pptx.addSlide();
  base(s);
  header(s, "04 · 卖给谁", "五个壁垒，都是时间与行业背景换不来的");
  const advs = [
    ["AI 原生架构", "先想清楚 AI 怎么用，再设计整个系统；不是传统 CAD 事后打补丁。"],
    ["图纸语义化", "设备、端口、管线、节点都有明确定义——AI 读得懂、查得出问题、自动出报表。"],
    ["原子事务", "任何修改先验证后写入，人工也好 AI 也好，都改不乱数据。工程图纸的底线。"],
    ["成本优势", "基础版免费开源，企业版仅为商业软件 1/5–1/10；浏览器架构零运维。"],
    ["核工业背景", "团队设计一线出身，每个功能都来自真实画图痛点，通用工具团队难以复制。"],
    ["先发优势", "P&ID 原生 AI 协同的开源工具，国内最早一批；开源社区就是流量入口。"],
  ];
  advs.forEach((a, i) => {
    const x = 0.75 + (i % 3) * 4.08;
    const y = 2.0 + Math.floor(i / 3) * 2.28;
    panel(s, x, y, 3.83, 2.05);
    s.addShape(pptx.ShapeType.rect, { x: x + 0.22, y: y + 0.25, w: 0.06, h: 0.5, fill: { color: i % 3 === 0 ? CYAN : i % 3 === 1 ? BLUE : GREEN } });
    cardTitle(s, a[0], x + 0.44, y + 0.2, 3.2, { fontSize: 14.5 });
    textFit(s, a[1], x + 0.44, y + 0.68, 3.15, 11.5, { color: SUB, lineSpacing: 1.3 });
  });
  footer(s);
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

// ================= 第 15 页 · 实施计划 =================
(function () {
  const s = pptx.addSlide();
  base(s);
  header(s, "05 · 怎么走", "18 个月：从原型到 1.0 商业化发布");
  const stages = [
    ["M1", "原型与核心引擎", "技术选型 · 文档模型 · 原型", true],
    ["M2", "Alpha 发布", "文档内核 · 持久化 · 编辑器基础", true],
    ["M3", "Beta 发布", "属性编辑 · 管线功能 · 图层显隐", true],
    ["M4", "RC 发布候选", "AI 自然语言局部修改 · 自动布局 · 大图性能", false],
    ["M5", "1.0 正式版", "企业级功能 · 工程交付验收", false],
  ];
  const yLine = 3.55;
  s.addShape(pptx.ShapeType.line, { x: 1.0, y: yLine, w: 11.3, h: 0, line: { color: "2A3B55", width: 2 } });
  stages.forEach((st, i) => {
    const cx = 1.55 + i * 2.6;
    s.addShape(pptx.ShapeType.ellipse, {
      x: cx - 0.17, y: yLine - 0.17, w: 0.34, h: 0.34,
      fill: { color: st[3] ? CYAN : "0B1220" }, line: { color: st[3] ? CYAN : "3B5C82", width: 1.5 },
    });
    // 有意设计：✓ 号绘制在里程碑圆点之上
    if (st[3]) s.addText("✓", { x: cx - 0.17, y: yLine - 0.19, w: 0.34, h: 0.34, fontSize: 12, fontFace: FONT, color: "062027", bold: true, align: "center" });
    s.addText(st[0], { x: cx - 1.2, y: yLine - 0.62, w: 2.4, h: 0.3, fontSize: 12, fontFace: FONT, color: st[3] ? CYAN : FAINT, bold: true, align: "center" });
    s.addText(st[1], { x: cx - 1.2, y: yLine + 0.28, w: 2.4, h: 0.35, fontSize: 13, fontFace: FONT, color: TXT, bold: true, align: "center" });
    textFit(s, st[2], cx - 1.2, yLine + 0.68, 2.4, 10, { color: SUB, align: "center" });
  });
  panel(s, 0.75, 5.1, 11.83, 0.85, { fill: { color: CYAN, transparency: 93 }, line: { color: "155E75", width: 0.75 } });
  s.addText("当前进度", { x: 1.0, y: 5.24, w: 1.4, h: 0.3, fontSize: 12, fontFace: FONT, color: CYAN, bold: true });
  s.addText("v2.1.0-alpha.1 已开源（MIT）· 原型 / Alpha / Beta 三个里程碑按期完成 · 质量门槛全部通过", {
    x: 1.0, y: 5.55, w: 11.3, h: 0.35, fontSize: 12.5, fontFace: FONT, color: TXT,
  });
  s.addText("如获支持，12–18 个月内完成 1.0 正式版并启动商业化", {
    x: 0.75, y: 6.35, w: 11.83, h: 0.4, fontSize: 13.5, fontFace: FONT, color: "BDE9F5", bold: true, align: "center",
  });
  footer(s);
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

// ================= 第 16 页 · 经济效益 =================
(function () {
  const s = pptx.addSlide();
  base(s);
  header(s, "05 · 怎么走", "轻资产起步，三重收益清晰可见");
  const stats = [
    ["30–50%", "设计出图效率提升", "AI 生成草图 + 自动规则检查 + 设备表/管线表一键生成，工程师从重复劳动中解放。"],
    ["1/5–1/10", "软件采购成本", "中型设计院 20 人用 AutoCAD 年费 10–30 万，专业 P&ID 软件更高；企业版年费仅为零头。"],
    ["0", "外部授权与资金链风险", "技术栈全开源、零授权费；轻资产模式，人力时间成本为主，不存在资金链断裂风险。"],
  ];
  stats.forEach((st, i) => {
    const x = 0.75 + i * 4.08;
    panel(s, x, 2.0, 3.83, 2.9, { line: i === 0 ? BORDER_ACCENT : BORDER });
    s.addText(st[0], { x: x + 0.25, y: 2.25, w: 3.3, h: 0.85, fontSize: 38, fontFace: FONT, color: i === 2 ? GREEN : CYAN, bold: true });
    s.addText(st[1], { x: x + 0.25, y: 3.2, w: 3.3, h: 0.4, fontSize: 14.5, fontFace: FONT, color: TXT, bold: true });
    textFit(s, st[2], x + 0.25, 3.72, 3.33, 11, { color: SUB, lineSpacing: 1.25 });
  });
  const lines = [
    "效率收益：科室工艺设计出图效率提升 30–50%",
    "能力收益：沉淀数字化技术与 AI 应用能力",
    "安全收益：降低对外部商业软件依赖，自主可控",
  ];
  s.addText(lines.map((ln, i) => ({ text: ln, options: { bullet: { code: "25AA", indent: 14, color: CYAN }, breakLine: i < lines.length - 1, paraSpaceAfterPt: 7 } })), {
    x: 0.75, y: 5.2, w: 5.9, h: 1.3, fontSize: 12, fontFace: FONT, color: "C9D4E3", valign: "top",
  });
  panel(s, 6.85, 5.2, 5.73, 1.55, { fill: PANEL_FILL_2 });
  s.addText("资金结构", { x: 7.1, y: 5.35, w: 1.6, h: 0.3, fontSize: 12.5, fontFace: FONT, color: AMBER, bold: true });
  textFit(s, "公司内部自发创新：无外部融资、无股权稀释、无对赌压力；当前不追求盈利，核心是为公司创造效率、能力与安全三重内部收益。",
    7.1, 5.7, 5.25, 11.5, { color: SUB, lineSpacing: 1.25 });
  footer(s);
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

// ================= 第 17 页 · 团队 =================
(function () {
  const s = pptx.addSlide();
  base(s);
  header(s, "05 · 怎么走", "核工业一线出身 · 工程 × 软件 × AI 复合团队");
  const cards = [
    ["硕博团队 · 核工业设计一线", "对 P&ID 工程语义、行业标准、设计流程有深入理解——功能全部来自真实画图痛点。"],
    ["全栈技术覆盖", "Python / React / SVG / SQLite / MCP 多栈贯通，能独立完成从设计到交付的全链条开发。"],
    ["AI 智能体实战", "大模型应用与 Agent 架构一线经验，支撑 AI 原生产品持续演进。"],
  ];
  cards.forEach((c, i) => {
    const x = 0.75 + i * 4.08;
    panel(s, x, 2.0, 3.83, 1.75);
    s.addText(c[0], { x: x + 0.25, y: 2.18, w: 3.35, h: 0.4, fontSize: 13.5, fontFace: FONT, color: TXT, bold: true });
    textFit(s, c[1], x + 0.25, 2.68, 3.33, 11, { color: SUB, lineSpacing: 1.3 });
  });
  s.addText("分工矩阵", { x: 0.75, y: 4.1, w: 2, h: 0.35, fontSize: 13, fontFace: FONT, color: CYAN, bold: true });
  const roles = [
    ["产品架构与总体设计", "系统架构 · 文档模型 · 技术路线决策"],
    ["后端开发", "FastAPI 服务 · SQLite 持久化 · MCP 接入 · 导出引擎"],
    ["前端开发", "React / TS 编辑器 · SVG 渲染 · 交互设计"],
    ["AI 模型集成", "Agent 规划器 · 工具链 · 模型接口适配"],
    ["测试与质量", "自动化测试 · 质量门禁 · 持续集成"],
  ];
  roles.forEach((r, i) => {
    const x = 0.75 + (i % 5) * 2.4;
    panel(s, x, 4.55, 2.2, 1.35, { shadow: false });
    s.addText(r[0], { x: x + 0.15, y: 4.7, w: 1.95, h: 0.6, fontSize: 11.5, fontFace: FONT, color: TXT, bold: true, align: "center" });
    textFit(s, r[1], x + 0.15, 5.3, 1.95, 9, { color: FAINT, align: "center" });
  });
  panel(s, 0.75, 6.15, 11.83, 0.75, { fill: PANEL_FILL_2 });
  s.addText("项目由个人发起，依托央企科室孵化，室领导方向把关与资源支持；持续吸纳青年工程师，形成「工程设计 + 软件开发 + AI 应用」复合型团队。", {
    x: 1.0, y: 6.33, w: 11.35, h: 0.4, fontSize: 11.5, fontFace: FONT, color: "C9D4E3",
  });
  footer(s);
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

// ================= 第 18 页 · 愿景结尾 =================
(function () {
  const s = pptx.addSlide();
  base(s, true);
  // 有意装饰：右上/右下角光晕（位于无文字区域）
  s.addShape(pptx.ShapeType.ellipse, { x: 11.55, y: 0.1, w: 1.75, h: 1.75, fill: { color: BLUE, transparency: 88 }, line: { color: BG, width: 0.5 } });
  s.addShape(pptx.ShapeType.ellipse, { x: 11.55, y: 5.75, w: 1.75, h: 1.75, fill: { color: CYAN, transparency: 90 }, line: { color: BG, width: 0.5 } });
  s.addText("让 AI 增强工程师，而不是替代工程师", {
    x: 1.87, y: 1.15, w: 9.6, h: 0.8, fontSize: 30, fontFace: FONT, color: TXT, bold: true, align: "center",
  });
  s.addShape(pptx.ShapeType.rect, { x: 5.97, y: 2.1, w: 1.4, h: 0.05, fill: { color: CYAN } });
  textFit(s, "未来的工程设计，不是用更复杂的软件替代工程师，而是让工程师专注于创造性的工艺设计决策，把重复的画图、标注与检查工作交给智能工具。",
    2.17, 2.5, 9.0, 15, { color: "C9D4E3", align: "center", lineSpacing: 1.45 });
  s.addText("成为流程工业领域最广泛使用的开源 P&ID 工具", {
    x: 0.75, y: 4.35, w: 11.83, h: 0.5, fontSize: 17, fontFace: FONT, color: "BDE9F5", bold: true, align: "center",
  });
  const c1 = chip(s, "开源 MIT · GitHub", 4.6, 5.25, { color: TXT, fontSize: 11 });
  const c2 = chip(s, "欢迎试用 · 欢迎共建", 4.6 + c1 + 0.3, 5.25, { color: TXT, fontSize: 11 });
  s.addText("国家电投集团钍基能源科技有限公司", { x: 2.67, y: 6.3, w: 8.0, h: 0.4, fontSize: 13, fontFace: FONT, color: "D5DEEA", bold: true, align: "center" });
  s.addText("谢谢观看 · THANKS", { x: 3.67, y: 6.7, w: 6.0, h: 0.4, fontSize: 11, fontFace: FONT, color: FAINT, align: "center" });
  warnIfSlideHasOverlaps(s, pptx);
  warnIfSlideElementsOutOfBounds(s, pptx);
})();

pptx.writeFile({ fileName: "P&ID-Agent-路演.pptx" }).then(() => {
  console.log("DONE: P&ID-Agent-路演.pptx");
});
