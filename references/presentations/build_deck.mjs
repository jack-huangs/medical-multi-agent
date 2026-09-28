import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const workspaceDir = "C:/Users/Administrator/Documents/ChatGPT/multi-agent医疗项目";
const SKILL_DIR = "C:/Users/Administrator/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.12148/skills/presentations";
const RUNTIME_PYTHON = "C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe";
const TMP_DIR = path.join(workspaceDir, "references/presentations/build");
const FINAL_PPTX = path.join(workspaceDir, "references/presentations/versions/多智能体医疗论文分享_连线修正版_v2.pptx");
const FONT = "Microsoft YaHei";

const C = {
  navy: "#102A43",
  navy2: "#183B56",
  teal: "#0E7C86",
  cyan: "#3FB8C6",
  blue: "#2F6BFF",
  ink: "#1C2733",
  muted: "#607080",
  pale: "#EAF4F6",
  paleBlue: "#EDF3FF",
  line: "#C8D6E2",
  white: "#FFFFFF",
  warm: "#F6F2EB",
  green: "#2B8A66",
  orange: "#E28A3B",
  red: "#C95757",
};

await fs.mkdir(TMP_DIR, { recursive: true });
await fs.mkdir(path.dirname(FINAL_PPTX), { recursive: true });

const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });

function addText(slide, text, x, y, w, h, opts = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = {
    typeface: FONT,
    fontSize: opts.size ?? 22,
    color: opts.color ?? C.ink,
    bold: opts.bold ?? false,
    alignment: opts.align ?? "left",
    verticalAlignment: opts.valign ?? "top",
    autoFit: opts.autoFit ?? "shrinkText",
    wrap: "square",
    lineSpacing: opts.lineSpacing ?? 1.08,
    insets: opts.insets ?? { left: 0, right: 0, top: 0, bottom: 0 },
  };
  return shape;
}

function addBox(slide, text, x, y, w, h, opts = {}) {
  const shape = slide.shapes.add({
    geometry: opts.geometry ?? "roundRect",
    position: { left: x, top: y, width: w, height: h },
    fill: opts.fill ?? C.white,
    line: { fill: opts.line ?? C.line, width: opts.lineWidth ?? 1.5 },
  });
  shape.text = text;
  shape.text.style = {
    typeface: FONT,
    fontSize: opts.size ?? 21,
    color: opts.color ?? C.ink,
    bold: opts.bold ?? false,
    alignment: opts.align ?? "center",
    verticalAlignment: "middle",
    autoFit: "shrinkText",
    wrap: "square",
    lineSpacing: opts.lineSpacing ?? 1.05,
    insets: opts.insets ?? { left: 12, right: 12, top: 8, bottom: 8 },
  };
  shape.__pos = { x, y, w, h };
  return shape;
}

function addTitle(slide, title, number) {
  addText(slide, title, 64, 36, 1070, 54, { size: 34, bold: true, color: C.navy });
  addText(slide, String(number).padStart(2, "0"), 1160, 42, 56, 32, { size: 16, bold: true, color: C.teal, align: "right" });
  const line = slide.shapes.add({
    geometry: "line",
    position: { left: 64, top: 104, width: 1152, height: 0 },
    fill: "none",
    line: { fill: C.line, width: 1 },
  });
  return line;
}

function addFooter(slide, text = "多智能体医疗论文分享") {
  addText(slide, text, 64, 680, 480, 20, { size: 11, color: "#8191A1" });
}

function anchor(shape, side) {
  const p = shape.__pos;
  if (side === "left") return { x: p.x, y: p.y + p.h / 2 };
  if (side === "right") return { x: p.x + p.w, y: p.y + p.h / 2 };
  if (side === "top") return { x: p.x + p.w / 2, y: p.y };
  return { x: p.x + p.w / 2, y: p.y + p.h };
}

function lineSegment(slide, a, b, color, width = 2.2) {
  if (Math.abs(a.x - b.x) < 0.5 && Math.abs(a.y - b.y) < 0.5) return;
  const left = Math.min(a.x, b.x);
  const top = Math.min(a.y, b.y);
  const w = Math.abs(b.x - a.x);
  const h = Math.abs(b.y - a.y);
  slide.shapes.add({
    geometry: "line",
    position: {
      left,
      top,
      width: w,
      height: h,
      horizontalFlip: b.x < a.x,
      verticalFlip: b.y < a.y,
    },
    fill: "none",
    line: { style: "solid", fill: color, width },
  });
}

function arrowHead(slide, p, targetSide, color) {
  const rot = targetSide === "left" ? 90 : targetSide === "right" ? 270 : targetSide === "top" ? 180 : 0;
  slide.shapes.add({
    geometry: "triangle",
    position: { left: p.x - 6, top: p.y - 6, width: 12, height: 12, rotation: rot },
    fill: color,
    line: { fill: color, width: 0 },
  });
}

function connect(slide, from, to, sides = {}) {
  const fromSide = sides.from ?? "right";
  const toSide = sides.to ?? "left";
  const a = anchor(from, fromSide);
  const b = anchor(to, toSide);
  const color = sides.color ?? C.teal;
  const width = sides.width ?? 2.2;
  const kind = sides.kind ?? "straight";
  if (kind === "straight") {
    lineSegment(slide, a, b, color, width);
  } else if ((fromSide === "right" && toSide === "left") || (fromSide === "left" && toSide === "right")) {
    const mx = (a.x + b.x) / 2;
    lineSegment(slide, a, { x: mx, y: a.y }, color, width);
    lineSegment(slide, { x: mx, y: a.y }, { x: mx, y: b.y }, color, width);
    lineSegment(slide, { x: mx, y: b.y }, b, color, width);
  } else if (fromSide === "bottom" && toSide === "bottom") {
    const routeY = Math.max(a.y, b.y) + 24;
    lineSegment(slide, a, { x: a.x, y: routeY }, color, width);
    lineSegment(slide, { x: a.x, y: routeY }, { x: b.x, y: routeY }, color, width);
    lineSegment(slide, { x: b.x, y: routeY }, b, color, width);
  } else if (fromSide === "left" && toSide === "left") {
    const routeX = Math.min(a.x, b.x) - 24;
    lineSegment(slide, a, { x: routeX, y: a.y }, color, width);
    lineSegment(slide, { x: routeX, y: a.y }, { x: routeX, y: b.y }, color, width);
    lineSegment(slide, { x: routeX, y: b.y }, b, color, width);
  } else if ((fromSide === "bottom" && toSide === "top") || (fromSide === "top" && toSide === "bottom")) {
    const my = (a.y + b.y) / 2;
    lineSegment(slide, a, { x: a.x, y: my }, color, width);
    lineSegment(slide, { x: a.x, y: my }, { x: b.x, y: my }, color, width);
    lineSegment(slide, { x: b.x, y: my }, b, color, width);
  } else if (fromSide === "top" && toSide === "right") {
    const routeY = a.y - 24;
    lineSegment(slide, a, { x: a.x, y: routeY }, color, width);
    lineSegment(slide, { x: a.x, y: routeY }, { x: b.x + 24, y: routeY }, color, width);
    lineSegment(slide, { x: b.x + 24, y: routeY }, { x: b.x + 24, y: b.y }, color, width);
    lineSegment(slide, { x: b.x + 24, y: b.y }, b, color, width);
  } else {
    lineSegment(slide, a, b, color, width);
  }
  arrowHead(slide, b, toSide, color);
}

function connectBoth(slide, leftShape, rightShape, color = C.teal) {
  const a = anchor(leftShape, "right");
  const b = anchor(rightShape, "left");
  lineSegment(slide, a, b, color, 2.2);
  arrowHead(slide, a, "right", color);
  arrowHead(slide, b, "left", color);
}

function note(slide, source, talkingPoints = "") {
  slide.speakerNotes.textFrame.setText(`资料来源：${source}\n${talkingPoints}`);
}

// Slide 1
{
  const slide = presentation.slides.add();
  slide.background.fill = C.navy;
  addText(slide, "多智能体大语言模型", 78, 142, 760, 70, { size: 48, bold: true, color: C.white });
  addText(slide, "在医疗决策中的应用与发展", 78, 218, 900, 70, { size: 48, bold: true, color: C.white });
  addText(slide, "论文分享", 80, 318, 220, 34, { size: 20, bold: true, color: C.cyan });
  const accent = slide.shapes.add({ geometry: "line", position: { left: 80, top: 375, width: 220, height: 0 }, fill: "none", line: { fill: C.cyan, width: 4 } });
  addText(slide, "黄锦佳", 80, 432, 220, 34, { size: 22, color: C.white, bold: true });
  addText(slide, "2026 年 9 月 17 日", 80, 474, 300, 30, { size: 18, color: "#BCD0DE" });
  addText(slide, "MDAgents · KAMAC · DeepRare · MedLA · DoctorAgent-RL", 80, 632, 860, 26, { size: 16, color: "#BCD0DE" });
  addText(slide, "AI × MEDICINE", 930, 165, 260, 180, { size: 34, bold: true, color: "#5DA7B0", align: "right", valign: "middle" });
  note(slide, "用户提供的论文与内容规划文档。", "开场说明本次分享关注多智能体医疗系统的协作机制。 ");
}

// Slide 2
{
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addTitle(slide, "为什么医疗需要多智能体系统", 2);
  const center = addBox(slide, "复杂医疗决策", 485, 265, 310, 120, { fill: C.navy, line: C.navy, color: C.white, size: 30, bold: true });
  const b1 = addBox(slide, "多专科知识\n需要共同参与", 92, 150, 260, 112, { fill: C.paleBlue, line: "#AFC4F5", size: 22, bold: true });
  const b2 = addBox(slide, "数据形式复杂\n病历、影像、基因", 928, 150, 260, 112, { fill: C.pale, line: "#9DD4D9", size: 22, bold: true });
  const b3 = addBox(slide, "单模型可能遗漏信息\n也可能产生幻觉", 92, 440, 260, 112, { fill: "#FFF2E8", line: "#EFC397", size: 22, bold: true });
  const b4 = addBox(slide, "真实医疗本身依赖\n团队分工与协作", 928, 440, 260, 112, { fill: "#EDF7F2", line: "#A8D6C3", size: 22, bold: true });
  connect(slide, b1, center, { from: "right", to: "left" });
  connect(slide, b2, center, { from: "left", to: "right" });
  connect(slide, b3, center, { from: "right", to: "left" });
  connect(slide, b4, center, { from: "left", to: "right" });
  addText(slide, "多个 AI 分别处理擅长的任务，再共同完成医疗决策", 270, 600, 740, 38, { size: 24, color: C.teal, bold: true, align: "center" });
  addFooter(slide);
  note(slide, "综合用户提供的五篇论文。", "强调多智能体的动机来自医学知识跨度、数据复杂性和临床协作结构。 ");
}

// Slide 3
{
  const slide = presentation.slides.add();
  slide.background.fill = "#F8FBFC";
  addTitle(slide, "多智能体医疗系统的基本协作模式", 3);
  const patient = addBox(slide, "患者临床数据", 60, 285, 190, 92, { fill: C.navy, line: C.navy, color: C.white, bold: true, size: 23 });
  const a1 = addBox(slide, "全科与专科 AI", 340, 142, 220, 80, { fill: C.paleBlue, line: "#AFC4F5", bold: true, size: 20 });
  const a2 = addBox(slide, "影像分析 AI", 340, 244, 220, 80, { fill: C.pale, line: "#9DD4D9", bold: true, size: 20 });
  const a3 = addBox(slide, "基因分析 AI", 340, 346, 220, 80, { fill: "#EDF7F2", line: "#A8D6C3", bold: true, size: 20 });
  const a4 = addBox(slide, "医学知识检索 AI", 340, 448, 220, 80, { fill: "#FFF2E8", line: "#EFC397", bold: true, size: 20 });
  const discuss = addBox(slide, "讨论与相互验证", 665, 250, 220, 110, { fill: C.teal, line: C.teal, color: C.white, bold: true, size: 24 });
  const synth = addBox(slide, "综合分析结果", 965, 196, 220, 82, { fill: C.white, line: C.teal, bold: true, size: 22 });
  const output = addBox(slide, "诊断或医疗建议", 965, 376, 220, 82, { fill: C.navy, line: C.navy, color: C.white, bold: true, size: 22 });
  [a1, a2, a3, a4].forEach((a) => connect(slide, patient, a, { from: "right", to: "left", kind: "elbow" }));
  [a1, a2, a3, a4].forEach((a) => connect(slide, a, discuss, { from: "right", to: "left", kind: "elbow" }));
  connect(slide, discuss, synth, { from: "right", to: "left" });
  connect(slide, synth, output, { from: "bottom", to: "top" });
  addFooter(slide);
  note(slide, "用户提供的内容规划文档。", "本页只展示整体协作流程。 ");
}

// Slide 4
{
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addTitle(slide, "MDAgents：按问题难度选择协作规模", 4);
  addText(slide, "先判断复杂度，再分配协作资源", 64, 126, 560, 38, { size: 25, color: C.teal, bold: true });
  const q = addBox(slide, "医疗问题", 64, 272, 170, 88, { fill: C.navy, line: C.navy, color: C.white, bold: true, size: 24 });
  const checker = addBox(slide, "复杂度判断", 296, 272, 190, 88, { fill: C.pale, line: C.teal, bold: true, size: 23 });
  connect(slide, q, checker);
  const low = addBox(slide, "低复杂度\n单个基层医生 AI", 598, 150, 260, 106, { fill: C.paleBlue, line: "#AFC4F5", bold: true, size: 21 });
  const mid = addBox(slide, "中等复杂度\n多学科团队讨论", 598, 288, 260, 106, { fill: C.pale, line: "#9DD4D9", bold: true, size: 21 });
  const high = addBox(slide, "高复杂度\n多个专业小组分析", 598, 426, 260, 106, { fill: "#FFF2E8", line: "#EFC397", bold: true, size: 21 });
  connect(slide, checker, low, { from: "right", to: "left", kind: "elbow" });
  connect(slide, checker, mid, { from: "right", to: "left", kind: "elbow" });
  connect(slide, checker, high, { from: "right", to: "left", kind: "elbow" });
  const final = addBox(slide, "最终医疗决策", 976, 272, 220, 104, { fill: C.navy, line: C.navy, color: C.white, bold: true, size: 24 });
  [low, mid, high].forEach((b) => connect(slide, b, final, { from: "right", to: "left", kind: "elbow" }));
  addText(slide, "目标：在诊断准确率与调用成本之间取得平衡", 390, 600, 520, 34, { size: 22, bold: true, color: C.teal, align: "center" });
  addFooter(slide);
  note(slide, "MDAgents: An Adaptive Collaboration of LLMs for Medical Decision-Making, NeurIPS 2024。", "论文根据低、中、高复杂度选择不同协作结构。 ");
}

// Slide 5
{
  const slide = presentation.slides.add();
  slide.background.fill = "#F8FBFC";
  addTitle(slide, "KAMAC：根据知识缺口动态招募专家", 5);
  addText(slide, "专家团队在讨论过程中逐步扩展", 64, 126, 560, 38, { size: 25, color: C.teal, bold: true });
  const initial = addBox(slide, "初始专家\n独立分析病例", 88, 250, 220, 110, { fill: C.paleBlue, line: "#AFC4F5", bold: true, size: 22 });
  const discuss = addBox(slide, "多轮讨论\n交换与修正意见", 380, 250, 220, 110, { fill: C.pale, line: "#9DD4D9", bold: true, size: 22 });
  const gap = addBox(slide, "知识缺口检测\n现有专家是否足够", 672, 250, 220, 110, { fill: "#FFF2E8", line: "#EFC397", bold: true, size: 22 });
  const recruit = addBox(slide, "动态招募\n相关领域新专家", 964, 250, 220, 110, { fill: "#EDF7F2", line: "#A8D6C3", bold: true, size: 22 });
  connect(slide, initial, discuss);
  connect(slide, discuss, gap);
  connect(slide, gap, recruit);
  connect(slide, recruit, discuss, { from: "bottom", to: "bottom", kind: "elbow", color: C.orange });
  addText(slide, "继续讨论", 720, 445, 180, 28, { size: 17, color: C.orange, bold: true, align: "center" });
  const decision = addBox(slide, "主持者综合专家意见\n输出最终决策", 470, 525, 340, 92, { fill: C.navy, line: C.navy, color: C.white, bold: true, size: 23 });
  connect(slide, gap, decision, { from: "bottom", to: "top", kind: "elbow" });
  addText(slide, "没有知识缺口", 710, 478, 170, 24, { size: 16, color: C.teal, align: "center" });
  addFooter(slide);
  note(slide, "A Knowledge-driven Adaptive Collaboration of LLMs for Enhancing Medical Decision-making, EMNLP 2025。", "重点讲知识缺口检测和讨论中招募新专家。 ");
}

// Slide 6
{
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addTitle(slide, "DeepRare：工具增强的罕见病诊断", 6);
  const i1 = addBox(slide, "临床文本", 64, 152, 190, 64, { fill: C.paleBlue, line: "#AFC4F5", bold: true, size: 19 });
  const i2 = addBox(slide, "HPO 表型", 64, 238, 190, 64, { fill: C.pale, line: "#9DD4D9", bold: true, size: 19 });
  const i3 = addBox(slide, "基因检测与 VCF", 64, 324, 190, 64, { fill: "#EDF7F2", line: "#A8D6C3", bold: true, size: 19 });
  const core = addBox(slide, "DeepRare\n中央推理与工具调度", 340, 223, 260, 124, { fill: C.navy, line: C.navy, color: C.white, bold: true, size: 25 });
  [i1, i2, i3].forEach((i) => connect(slide, i, core, { from: "right", to: "left", kind: "elbow" }));
  const tool = addBox(slide, "40+ 专业工具与知识来源\n表型 · 基因 · 论文 · 病例", 340, 410, 260, 92, { fill: C.warm, line: "#D9C9AF", bold: true, size: 20 });
  connect(slide, tool, core, { from: "top", to: "bottom" });
  const h1 = addBox(slide, "生成初步诊断假设", 705, 144, 220, 70, { fill: C.paleBlue, line: "#AFC4F5", bold: true, size: 19 });
  const h2 = addBox(slide, "自我反思与重新检索", 705, 256, 220, 70, { fill: "#FFF2E8", line: "#EFC397", bold: true, size: 19 });
  const h3 = addBox(slide, "验证或否定假设", 705, 368, 220, 70, { fill: C.pale, line: "#9DD4D9", bold: true, size: 19 });
  connect(slide, core, h1);
  connect(slide, h1, h2, { from: "bottom", to: "top" });
  connect(slide, h2, h3, { from: "bottom", to: "top" });
  connect(slide, h3, h2, { from: "left", to: "left", kind: "elbow", color: C.orange });
  const output = addBox(slide, "候选疾病排名\n推理过程与证据链", 1010, 245, 210, 116, { fill: C.teal, line: C.teal, color: C.white, bold: true, size: 21 });
  connect(slide, h3, output);
  addText(slide, "模型、医学工具和外部证据共同参与诊断", 340, 575, 600, 34, { size: 23, bold: true, color: C.teal, align: "center" });
  addFooter(slide);
  note(slide, "An agentic system for rare disease diagnosis with traceable reasoning, Nature 2026。", "本页合并系统能力和诊断流程。 ");
}

// Slide 7
{
  const slide = presentation.slides.add();
  slide.background.fill = "#F8FBFC";
  addTitle(slide, "DeepRare 的实验表现", 7);
  addText(slide, "9", 66, 145, 110, 68, { size: 52, bold: true, color: C.teal });
  addText(slide, "个数据集", 66, 211, 150, 28, { size: 18, color: C.muted });
  addText(slide, "14", 236, 145, 130, 68, { size: 52, bold: true, color: C.blue });
  addText(slide, "个医学专科", 236, 211, 150, 28, { size: 18, color: C.muted });
  addText(slide, "2,919", 410, 145, 180, 68, { size: 52, bold: true, color: C.navy });
  addText(slide, "种罕见病", 410, 211, 150, 28, { size: 18, color: C.muted });
  addText(slide, "多模态病例 Recall@1", 680, 136, 390, 34, { size: 22, bold: true, color: C.navy });
  const chart = slide.charts.add("bar", {
    position: { left: 660, top: 180, width: 520, height: 210 },
    categories: ["DeepRare", "Exomiser"],
    series: [{ name: "Recall@1", values: [69.1, 55.9], fill: C.teal }],
    barOptions: { direction: "bar", grouping: "clustered", gapWidth: 48 },
    hasLegend: false,
    xAxis: { visible: false, majorGridlines: null, minimumScale: 0, maximumScale: 80 },
    yAxis: { textStyle: { fill: C.ink, fontSize: 16, typeface: FONT }, line: { style: "solid", fill: C.line, width: 1 } },
    dataLabels: { showValue: true, position: "outEnd", numberFormatCode: "0.0\"%\"", textStyle: { fill: C.ink, fontSize: 15, bold: true, typeface: FONT } },
  });
  const { applyPresentationChartFont } = await import(pathToFileURL(path.join(SKILL_DIR, "container_tools/artifact_tool_utils.mjs")).href);
  applyPresentationChartFont(chart, { fontFamily: FONT });
  addText(slide, "57.18%", 90, 370, 240, 70, { size: 48, bold: true, color: C.teal, align: "center" });
  addText(slide, "HPO 任务平均 Recall@1", 60, 438, 300, 32, { size: 18, color: C.muted, align: "center" });
  addText(slide, "95.4%", 390, 370, 240, 70, { size: 48, bold: true, color: C.blue, align: "center" });
  addText(slide, "专家认可推理链", 360, 438, 300, 32, { size: 18, color: C.muted, align: "center" });
  addText(slide, "外部工具与证据链提升了罕见病诊断的可用性，但临床使用仍需医生监督", 110, 570, 1060, 48, { size: 22, bold: true, color: C.navy, align: "center" });
  addFooter(slide);
  note(slide, "An agentic system for rare disease diagnosis with traceable reasoning, Nature 2026。", "图表比较 168 个多模态病例中的 Recall@1。 ");
}

// Slide 8
{
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addTitle(slide, "MedLA：用逻辑树定位推理错误", 8);
  addText(slide, "最小逻辑单元", 64, 132, 300, 36, { size: 24, bold: true, color: C.teal });
  const major = addBox(slide, "大前提\n细菌感染常伴随白细胞升高", 64, 218, 240, 92, { fill: C.paleBlue, line: "#AFC4F5", bold: true, size: 18 });
  const minor = addBox(slide, "小前提\n患者白细胞明显升高", 340, 218, 240, 92, { fill: C.pale, line: "#9DD4D9", bold: true, size: 18 });
  const merge = addBox(slide, "共同支持", 272, 352, 100, 58, { geometry: "ellipse", fill: C.warm, line: "#D9C9AF", bold: true, size: 16 });
  const conclusion = addBox(slide, "结论\n患者可能存在细菌感染", 122, 474, 390, 92, { fill: C.navy, line: C.navy, color: C.white, bold: true, size: 20 });
  connect(slide, major, merge, { from: "bottom", to: "top" });
  connect(slide, minor, merge, { from: "bottom", to: "top" });
  connect(slide, merge, conclusion, { from: "bottom", to: "top" });
  addText(slide, "多个智能体的逻辑树", 494, 132, 330, 36, { size: 24, bold: true, color: C.teal });
  const root = addBox(slide, "最终判断", 850, 250, 170, 72, { fill: C.navy, line: C.navy, color: C.white, bold: true, size: 21 });
  const n1 = addBox(slide, "医学规律", 500, 208, 170, 68, { fill: C.paleBlue, line: "#AFC4F5", bold: true, size: 18 });
  const n2 = addBox(slide, "患者事实", 500, 315, 170, 68, { fill: C.pale, line: "#9DD4D9", bold: true, size: 18 });
  const n3 = addBox(slide, "中间推断", 730, 208, 170, 68, { fill: "#FFF2E8", line: "#EFC397", bold: true, size: 18 });
  const n4 = addBox(slide, "冲突节点", 730, 390, 170, 68, { fill: "#FBECEC", line: "#E3A9A9", color: C.red, bold: true, size: 18 });
  connect(slide, n1, n3);
  connect(slide, n2, n3, { kind: "elbow" });
  connect(slide, n3, root);
  const revise = addBox(slide, "可信度评估与多轮讨论\n修正前提、遗漏和冲突", 970, 390, 230, 104, { fill: "#EDF7F2", line: "#A8D6C3", bold: true, size: 19 });
  connect(slide, n4, revise, { color: C.red });
  connect(slide, revise, root, { from: "top", to: "right", kind: "elbow", color: C.green });
  addText(slide, "比较推理步骤，而不只比较最终答案", 530, 580, 610, 38, { size: 24, bold: true, color: C.teal, align: "center" });
  addFooter(slide);
  note(slide, "MedLA: A Logic-Driven Multi-Agent Framework for Complex Medical Reasoning with Large Language Models, AAAI 2026。", "重点讲大前提、小前提、结论和前提级冲突定位。 ");
}

// Slide 9
{
  const slide = presentation.slides.add();
  slide.background.fill = "#F8FBFC";
  addTitle(slide, "DoctorAgent-RL：通过强化学习实现主动问诊", 9);
  addText(slide, "传统系统的问题", 64, 132, 280, 34, { size: 24, bold: true, color: C.teal });
  addText(slide, "患者难以一次说清所有症状\n单轮问答容易缺少关键信息\n传统多轮模型主要模仿既有对话", 64, 188, 350, 158, { size: 21, color: C.ink, lineSpacing: 1.24 });
  const patient = addBox(slide, "患者智能体\n模拟真实表达", 485, 258, 210, 96, { fill: C.paleBlue, line: "#AFC4F5", bold: true, size: 21 });
  const doctor = addBox(slide, "医生智能体\n选择下一步问题", 765, 258, 210, 96, { fill: C.navy, line: C.navy, color: C.white, bold: true, size: 21 });
  const evalr = addBox(slide, "问诊评估器\n提供多维奖励", 1040, 258, 190, 96, { fill: C.pale, line: "#9DD4D9", bold: true, size: 20 });
  connectBoth(slide, patient, doctor, C.teal);
  connect(slide, doctor, evalr, { from: "right", to: "left" });
  connect(slide, evalr, doctor, { from: "bottom", to: "bottom", kind: "elbow", color: C.orange });
  addText(slide, "提问与回答", 690, 215, 145, 24, { size: 16, color: C.teal, bold: true, align: "center" });
  addText(slide, "奖励反馈", 950, 402, 180, 24, { size: 16, color: C.orange, bold: true, align: "center" });
  addText(slide, "学习重点：如何通过提问逐步找到答案", 278, 566, 724, 44, { size: 28, bold: true, color: C.navy, align: "center" });
  addText(slide, "论文报告完全诊断匹配率约 70%", 410, 625, 460, 28, { size: 18, color: C.teal, bold: true, align: "center" });
  addFooter(slide);
  note(slide, "Real-World Doctor Agent with Proactive Consultation through Multi-Agent Reinforcement Learning, arXiv:2505.19630v4。", "介绍患者智能体、医生智能体和问诊评估器的互动。 ");
}

const requirements = {
  explicitTotalSlideCount: 9,
  requiredNativeTableOwnerSlides: [],
  requiredNativeChartOwnerSlides: [7],
  materializeLiteralChartWorkbooks: true,
};
const fontPolicy = { basis: "design", families: [FONT], scriptFonts: { ea: FONT } };
const expectedSlideSizeEmu = "12192000,6858000";
const { finalizePresentation } = await import(pathToFileURL(path.join(SKILL_DIR, "container_tools/artifact_tool_utils.mjs")).href);
const stagingDir = path.join(workspaceDir, ".codex-finalizer");
await fs.mkdir(stagingDir, { recursive: true });
const candidatePath = path.join(stagingDir, "multiagent_medical_candidate.pptx");
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
const result = await finalizePresentation({
  ...requirements,
  workspaceDir,
  candidatePath,
  finalPath: FINAL_PPTX,
  pythonExecutable: RUNTIME_PYTHON,
  integrityValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: [
    "--expected-slide-size-emu", expectedSlideSizeEmu,
    "--validate-bullet-geometry",
    "--validate-heading-fit",
  ],
  requiredNativeTableOwnerSlides: [],
  requiredNativeChartOwnerSlides: [7],
  fontPolicy,
  verifyArtifactToolImport: true,
  receiptPath: path.join(stagingDir, "multiagent_medical_lines_fixed_v2.validation.json"),
});
console.log(JSON.stringify({ finalPath: FINAL_PPTX, result }, null, 2));
