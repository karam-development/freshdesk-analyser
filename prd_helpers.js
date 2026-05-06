/**
 * Silverfin PRD Analysis — Shared docx helpers
 *
 * This module provides all the reusable building blocks for generating
 * Silverfin bug fix / small feature analysis documents in .docx format.
 *
 * Usage:
 *   const h = require("./prd_helpers");
 *   // then use h.empty(), h.bodyText([...]), h.headerCell("Col", width), etc.
 *   // and h.buildDocument(sections) to create the final Document object.
 */

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
  AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType,
  VerticalAlign, LevelFormat
} = require("docx");

// ─── Brand constants ───────────────────────────────────────────────
const NAVY       = "002d44";
const CYAN       = "13c5e2";
const BODY_COLOR = "434343";
const FONT_BODY  = "Open Sans Light";
const FONT_BOLD  = "Open Sans";
const FONT_TITLE = "Open Sans ExtraBold";

// ─── Paragraph helpers ─────────────────────────────────────────────

function hr() {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "A0A0A0", space: 1 } },
    spacing: { before: 120, after: 120 }, children: []
  });
}

function empty() {
  return new Paragraph({ children: [] });
}

/**
 * Body text paragraph. `runs` is an array of strings or TextRun option objects.
 * Example: bodyText(["Hello ", { text: "world", bold: true }])
 */
function bodyText(runs, opts = {}) {
  const children = runs.map(r => typeof r === "string"
    ? new TextRun({ text: r, font: FONT_BODY, size: 22, color: BODY_COLOR })
    : new TextRun({ font: FONT_BODY, size: 22, color: BODY_COLOR, ...r }));
  return new Paragraph({ spacing: { after: 120 }, ...opts, children });
}

function italicText(text) {
  return new Paragraph({ spacing: { after: 80 }, children: [
    new TextRun({ text, font: FONT_BODY, size: 22, color: BODY_COLOR, italics: true })
  ] });
}

function pageTitle(text) {
  return new Paragraph({ spacing: { after: 0, before: 0 }, children: [
    new TextRun({ text, font: FONT_TITLE, size: 56, color: NAVY, bold: false })
  ] });
}

function subtitle(text) {
  return new Paragraph({ spacing: { before: 240, after: 240 }, children: [
    new TextRun({ text, font: FONT_BOLD, size: 24, color: NAVY })
  ] });
}

function bullet(runs, ref = "bullets") {
  const children = runs.map(r => typeof r === "string"
    ? new TextRun({ text: r, font: FONT_BODY, size: 22, color: BODY_COLOR })
    : new TextRun({ font: FONT_BODY, size: 22, color: BODY_COLOR, ...r }));
  return new Paragraph({ numbering: { reference: ref, level: 0 }, children });
}

function heading1(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [
    new TextRun({ text, font: FONT_BOLD })
  ] });
}

function heading2(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [
    new TextRun({ text, font: FONT_BOLD })
  ] });
}

function heading3(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_3, children: [
    new TextRun({ text, font: FONT_BOLD })
  ] });
}

// ─── Table helpers ─────────────────────────────────────────────────

const thinBorder  = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders     = { top: thinBorder, bottom: thinBorder, left: thinBorder, right: thinBorder };
const cellMargins = { top: 60, bottom: 60, left: 100, right: 100 };

function headerCell(text, width) {
  return new TableCell({
    borders, width: { size: width, type: WidthType.DXA },
    shading: { fill: NAVY, type: ShadingType.CLEAR }, margins: cellMargins,
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
      new TextRun({ text, bold: true, color: "FFFFFF", font: FONT_BOLD, size: 20 })
    ] })]
  });
}

/**
 * Standard data cell. `lines` is an array of strings or TextRun option objects.
 */
function dataCell(lines, width, opts = {}) {
  const paras = lines.map((line, i) => {
    if (typeof line === "string") {
      return new Paragraph({ spacing: { before: i > 0 ? 30 : 0, after: 0 }, children: [
        new TextRun({ text: line, font: FONT_BODY, size: 18, color: BODY_COLOR, ...opts })
      ] });
    }
    return new Paragraph({ spacing: { before: i > 0 ? 30 : 0, after: 0 }, children: [
      new TextRun({ font: FONT_BODY, size: 18, color: BODY_COLOR, ...line })
    ] });
  });
  return new TableCell({ borders, width: { size: width, type: WidthType.DXA },
    margins: cellMargins, verticalAlign: VerticalAlign.TOP, children: paras });
}

/**
 * Shaded (colored background) cell — used for status indicators.
 * Common fills: "E8F5E9" (green/fixed), "FDE8E8" (red/bug), "FFF3CD" (yellow/pending).
 */
function shadedCell(lines, width, fill) {
  const paras = lines.map((line, i) => {
    if (typeof line === "string") {
      return new Paragraph({ spacing: { before: i > 0 ? 30 : 0, after: 0 }, children: [
        new TextRun({ text: line, font: FONT_BODY, size: 18, color: BODY_COLOR })
      ] });
    }
    return new Paragraph({ spacing: { before: i > 0 ? 30 : 0, after: 0 }, children: [
      new TextRun({ font: FONT_BODY, size: 18, color: BODY_COLOR, ...line })
    ] });
  });
  return new TableCell({ borders, width: { size: width, type: WidthType.DXA },
    margins: cellMargins, verticalAlign: VerticalAlign.TOP,
    shading: fill ? { fill, type: ShadingType.CLEAR } : undefined,
    children: paras });
}

/**
 * Color-coded status cell (centered, bold). Pass the status label and width.
 * Recognises: "Fixed in dev", "Blocked", "To do", "To test".
 */
function statusCell(status, width) {
  const colorMap = {
    "Fixed in dev": { fill: "E8F5E9", color: "006600" },
    "Fixed":        { fill: "E8F5E9", color: "006600" },
    "Blocked":      { fill: "FDE8E8", color: "CC0000" },
    "To do":        { fill: "FFF3CD", color: "856404" },
    "To test":      { fill: "F5F5F5", color: BODY_COLOR },
  };
  const s = colorMap[status] || { fill: "F5F5F5", color: BODY_COLOR };
  return new TableCell({
    borders, width: { size: width, type: WidthType.DXA },
    margins: cellMargins, verticalAlign: VerticalAlign.CENTER,
    shading: { fill: s.fill, type: ShadingType.CLEAR },
    children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
      new TextRun({ text: status, font: FONT_BOLD, size: 18, color: s.color, bold: true })
    ] })]
  });
}

// ─── Image helper ──────────────────────────────────────────────────

function screenshotParagraph(imgBuffer, w, h, altTitle) {
  return new Paragraph({
    children: [new ImageRun({
      type: "png", data: imgBuffer,
      transformation: { width: w, height: h },
      altText: { title: altTitle, description: altTitle, name: altTitle }
    })]
  });
}

// ─── Quick table builder ───────────────────────────────────────────

/**
 * Build a table from header array and rows array.
 * colWidths: array of DXA widths.
 * headers: array of header strings.
 * rows: array of arrays — each inner array is one row of cell content arrays.
 *   e.g. [[["A"], ["Description"]], [["B"], ["Other"]]]
 */
function buildTable(colWidths, headers, rows) {
  const totalW = colWidths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: totalW, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: [
      new TableRow({ tableHeader: true, children:
        headers.map((h, i) => headerCell(h, colWidths[i]))
      }),
      ...rows.map(row =>
        new TableRow({ children:
          row.map((cellLines, i) => dataCell(cellLines, colWidths[i]))
        })
      )
    ]
  });
}

// ─── Document builder ──────────────────────────────────────────────

const sectionProps = {
  page: { size: { width: 11909, height: 16834 },
    margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } }
};

/**
 * Build the standard 4-tab PRD document.
 *
 * @param {Object} opts
 * @param {Paragraph[]} opts.tab1Content - Array of paragraphs for the "Bug fix / small feature" tab
 * @param {string}      opts.introText   - Italic intro sentence under the title
 * @param {Object}      opts.quickLinks  - { freshdesk: "url or <<<ADD>>>", jira: "url or <<<ADD>>>" }
 * @param {Object}      opts.templateInfo - { name, workflow, type?, linkedTemplate? }
 * @param {Object}      opts.bulletChecks - { periodLogic: "No"/"Yes", linkedTemplates: "No"/"Yes – ..." }
 * @param {Paragraph[]} opts.issueContent - Main analysis content (current behaviour, new behaviour, etc.)
 * @param {Paragraph[]} opts.testPlan     - Test plan content (usually a table)
 * @param {string[]}    opts.poChecklist  - Optional extra PO checklist items beyond the default 3
 */
function buildDocument(opts) {
  const {
    introText, quickLinks = {}, templateInfo = {}, bulletChecks = {},
    issueContent = [], testPlan = [], poChecklist = []
  } = opts;

  // Tab 1 content
  const tab1Children = [
    pageTitle("Bug fix \uD83D\uDC1B / small feature \uD83D\uDCAA"),
    italicText(introText),
    new Paragraph({ spacing: { after: 80 }, children: [
      new TextRun({ text: "The goal is to make sure a ", font: FONT_BODY, size: 22, color: BODY_COLOR, italics: true }),
      new TextRun({ text: "proper investigation", font: FONT_BOLD, size: 22, color: BODY_COLOR, italics: true, bold: true }),
      new TextRun({ text: " is done, and that this template serves as the ", font: FONT_BODY, size: 22, color: BODY_COLOR, italics: true }),
      new TextRun({ text: "single source of truth", font: FONT_BOLD, size: 22, color: BODY_COLOR, italics: true, bold: true }),
      new TextRun({ text: ".", font: FONT_BODY, size: 22, color: BODY_COLOR, italics: true }),
    ] }),
    hr(), empty(),

    // Quick links
    heading1("Quick links \uD83D\uDD17"),
    bodyText([`Freshdesk ticket: ${quickLinks.freshdesk || "<<<ADD>>>"}`]),
    bodyText([`Jira ticket: ${quickLinks.jira || "<<<ADD>>>"}`]),
    empty(),

    // Info impacted template(s)
    heading1("Info impacted template(s) \u2139\uFE0F"),
  ];

  if (templateInfo.name) tab1Children.push(bodyText([`Name template: ${templateInfo.name}`]));
  if (templateInfo.note) tab1Children.push(bodyText([`Name note: ${templateInfo.note}`]));
  if (templateInfo.table) tab1Children.push(bodyText([`Table: ${templateInfo.table}`]));
  if (templateInfo.workflow) tab1Children.push(bodyText([`Name workflow: ${templateInfo.workflow}`]));
  if (templateInfo.type) tab1Children.push(bodyText([`Template type: ${templateInfo.type}`]));
  if (templateInfo.entity) tab1Children.push(bodyText([`Entity: ${templateInfo.entity}`]));
  if (templateInfo.linkedTemplate) tab1Children.push(bodyText([`Linked template: ${templateInfo.linkedTemplate}`]));
  tab1Children.push(empty());

  // Bullet items to check
  tab1Children.push(heading1("Bullet items to check before analysing \uD83E\uDD14"));
  tab1Children.push(bullet(["Does the fix / feature require period logic? ", { text: bulletChecks.periodLogic || "<<<ADD>>>", bold: true }]));
  tab1Children.push(bullet(["Is the fix / feature linked to other templates (impact!)? ", { text: bulletChecks.linkedTemplates || "<<<ADD>>>", bold: true }]));
  tab1Children.push(empty(), empty(), hr(), empty());

  // Main issue content
  tab1Children.push(heading1("Current issue / feature"));
  tab1Children.push(italicText("Explain how the template works currently, and what is needed to be implemented as a fix / feature"));
  tab1Children.push(...issueContent);

  // Test plan
  if (testPlan.length > 0) {
    tab1Children.push(heading1("Test plan \uD83E\uDDEA"));
    tab1Children.push(empty());
    tab1Children.push(...testPlan);
  }
  tab1Children.push(empty(), empty(), empty());

  // Default PO checklist
  const defaultPO = [
    "Tested in all languages",
    "Tested in several periods",
    "PDF / export tested",
  ];
  const allPO = [...defaultPO, ...poChecklist];

  return new Document({
    styles: {
      default: { document: {
        run: { font: FONT_BODY, size: 22, color: BODY_COLOR },
        paragraph: { spacing: { line: 276 }, alignment: AlignmentType.JUSTIFIED }
      } },
      paragraphStyles: [
        { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 36, bold: true, font: FONT_BOLD, color: CYAN },
          paragraph: { spacing: { before: 200, after: 200 }, outlineLevel: 0 } },
        { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 28, bold: true, font: FONT_BOLD, color: CYAN },
          paragraph: { spacing: { before: 200, after: 200 }, outlineLevel: 1 } },
        { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 22, bold: true, font: FONT_BOLD, color: CYAN },
          paragraph: { spacing: { before: 120, after: 120 }, outlineLevel: 2 } },
      ]
    },
    numbering: { config: [{ reference: "bullets", levels: [{
      level: 0, format: LevelFormat.BULLET, text: "\u2022",
      alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 720, hanging: 360 } } }
    }] }] },
    sections: [
      // TAB 1 - Bug fix / small feature
      { properties: sectionProps, children: tab1Children },

      // TAB 2 - DEV analysis
      { properties: sectionProps, children: [
        pageTitle("DEV analysis"),
        italicText("An overview of things to know before a DEV review can be held; try to describe in brief words / sentences what the fix needs to be (what it fixes and how it will be fixed)"),
        hr(), empty(),
      ] },

      // TAB 3 - DEV review
      { properties: sectionProps, children: [
        pageTitle("DEV review"), empty(), hr(),
        subtitle("Functional review"), empty(), empty(), hr(),
        subtitle("Code review"),
        bodyText(["Link Gitlab-ticket: <<<ADD>>>"]),
      ] },

      // TAB 4 - PO review
      { properties: sectionProps, children: [
        pageTitle("PO review"), empty(), hr(), empty(),
        heading1("Checklist"),
        ...allPO.map(item => bullet([item])),
        empty(), hr(),
      ] },
    ]
  });
}

// ─── Exports ───────────────────────────────────────────────────────

module.exports = {
  // Constants
  NAVY, CYAN, BODY_COLOR, FONT_BODY, FONT_BOLD, FONT_TITLE,
  sectionProps,
  // Paragraph helpers
  hr, empty, bodyText, italicText, pageTitle, subtitle, bullet,
  heading1, heading2, heading3,
  // Table helpers
  headerCell, dataCell, shadedCell, statusCell, buildTable,
  // Image helper
  screenshotParagraph,
  // Document builder
  buildDocument,
  // Re-exports from docx
  Table, TableRow, TableCell, ImageRun, Packer,
  AlignmentType, HeadingLevel, WidthType, ShadingType,
};
