#!/usr/bin/env node
/**
 * Generate a Silverfin PRD functional analysis Word document.
 *
 * Follows the team's 4-tab PRD structure exactly:
 *   Section 1: Bug fix / small feature (full analysis)
 *   Section 2: DEV analysis (boilerplate)
 *   Section 3: DEV review (boilerplate)
 *   Section 4: PO review (checklist)
 *
 * Section 1 internal order:
 *   1. Page title + intro + boilerplate
 *   2. Quick links
 *   3. Info impacted template(s)
 *   4. Bullet items to check
 *   5. Current issue / feature:
 *      - Context (H2)
 *      - Problem statement (H2)
 *      - Current behaviour (H2)
 *      - New behaviour after fix (H2) with H3 subsections
 *      - Visibility rules summary (H2) — always a table
 *      - Reference implementation (H2)
 *   6. Test plan — always a table
 *
 * Usage: node generate_analysis.js <input.json> <output.docx>
 */

const fs = require("fs");
const path = require("path");
const h = require(path.join(__dirname, "prd_helpers"));

const inputPath = process.argv[2];
const outputPath = process.argv[3];

if (!inputPath || !outputPath) {
  console.error("Usage: node generate_analysis.js <input.json> <output.docx>");
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(inputPath, "utf8"));

/**
 * Convert a multiline string into body-text paragraphs.
 * Handles bullet points (* or -) and bold FR:/EN: prefixes.
 */
function textToParas(text) {
  if (!text) return [];
  const lines = text.split("\n").filter(l => l.trim() !== "");
  const result = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("* ") || trimmed.startsWith("- ")) {
      // Bullet point
      const bulletText = trimmed.replace(/^[*\-]\s+/, "");
      // Check for bold lead-in (Step X — or Label:)
      const boldMatch = bulletText.match(/^(Step \d+\s*[—–-]\s*[^.]+?)\s+(.*)/);
      if (boldMatch) {
        result.push(h.bullet([{ text: boldMatch[1] + " ", bold: true }, boldMatch[2]]));
      } else {
        result.push(h.bullet([bulletText]));
      }
    } else if (trimmed.startsWith("FR:") || trimmed.startsWith("EN:")) {
      // Bilingual line with bold label
      const label = trimmed.substring(0, 3);
      const rest = trimmed.substring(3).trim();
      result.push(h.bodyText([{ text: label + " ", bold: true }, rest]));
    } else {
      result.push(h.bodyText([trimmed]));
    }
  }
  return result;
}

/**
 * Parse a table from the special format:
 * TABLE_TYPE:\nCol1|Col2|Col3\nRow1C1|Row1C2|Row1C3\n...
 * Returns { headers: [...], rows: [[...], ...] } or null
 */
function parseInlineTable(text) {
  if (!text) return null;
  const tableTypes = ["DROPDOWN_TABLE:", "COMBINATION_TABLE:", "OUTPUT_TABLE:", "VISIBILITY_TABLE:"];
  const tableStart = tableTypes.find(t => text.includes(t));
  if (!tableStart) return null;

  const idx = text.indexOf(tableStart);
  const afterType = text.substring(idx + tableStart.length).trim();
  const lines = afterType.split("\n").filter(l => l.trim() && l.includes("|"));
  if (lines.length < 2) return null;

  const headers = lines[0].split("|").map(c => c.trim());
  const rows = lines.slice(1).map(line => line.split("|").map(c => [c.trim()]));

  // Calculate column widths proportionally
  const totalWidth = 9029; // standard page width in twips
  const colWidths = headers.map(() => Math.floor(totalWidth / headers.length));

  return { headers, rows, colWidths };
}

/**
 * Render a subsection's content, extracting inline tables if present.
 */
function renderSubsectionContent(content) {
  if (!content) return [];
  const result = [];
  const tableTypes = ["DROPDOWN_TABLE:", "COMBINATION_TABLE:", "OUTPUT_TABLE:", "VISIBILITY_TABLE:"];
  const hasTable = tableTypes.some(t => content.includes(t));

  if (hasTable) {
    // Split content into before-table, table, and after-table
    let tableTypeFound = tableTypes.find(t => content.includes(t));
    const parts = content.split(tableTypeFound);
    const beforeTable = parts[0].trim();
    const tableAndAfter = (tableTypeFound + (parts[1] || "")).trim();

    // Render text before table
    if (beforeTable) {
      result.push(...textToParas(beforeTable));
      result.push(h.empty());
    }

    // Parse and render the table
    const table = parseInlineTable(tableAndAfter);
    if (table) {
      result.push(h.buildTable(table.colWidths, table.headers, table.rows));
      result.push(h.empty());
    }

    // Check for text after the table (after last row with |)
    const allLines = tableAndAfter.split("\n");
    let lastPipeLine = -1;
    for (let i = 0; i < allLines.length; i++) {
      if (allLines[i].includes("|")) lastPipeLine = i;
    }
    if (lastPipeLine >= 0 && lastPipeLine < allLines.length - 1) {
      const afterTable = allLines.slice(lastPipeLine + 1).join("\n").trim();
      if (afterTable) {
        result.push(...textToParas(afterTable));
      }
    }
  } else {
    result.push(...textToParas(content));
  }

  return result;
}


/**
 * Load screenshots from disk and create embedded image paragraphs.
 * Returns an array of paragraph objects ready to insert into the document.
 */
function loadScreenshots(screenshotsList) {
  const result = [];
  if (!screenshotsList || !Array.isArray(screenshotsList) || screenshotsList.length === 0) {
    return result;
  }

  for (const ss of screenshotsList) {
    const filePath = ss.path;
    if (!filePath || !fs.existsSync(filePath)) continue;

    try {
      const imgBuffer = fs.readFileSync(filePath);
      if (imgBuffer.length < 100) continue; // skip tiny/corrupt files

      // Default dimensions (will be scaled in the document)
      // Use reasonable defaults — the document width is ~6 inches (576pt)
      const maxWidth = 550;
      const maxHeight = 400;

      const label = ss.source || "Screenshot";
      const filename = ss.filename || path.basename(filePath);

      // Add a label paragraph
      result.push(h.bodyText([{ text: `${label}: `, bold: true }, filename]));
      // Add the actual image
      result.push(h.screenshotParagraph(imgBuffer, maxWidth, maxHeight, filename));
      result.push(h.empty());
    } catch (err) {
      // Skip failed screenshots silently
      console.error(`Failed to load screenshot ${filePath}: ${err.message}`);
    }
  }
  return result;
}


async function generate() {
  const lang = data.language || "fr";
  const ticket = data.ticket || {};
  const prd = data.prd_analysis || {};
  const screenshots = data.screenshots || [];

  // ── Template info ──
  const templateName = prd.template_name || ticket.subject || "<<<ADD>>>";
  const workflow = prd.workflow || "<<<ADD>>>";
  const periodLogic = prd.period_logic || "<<<ADD>>>";
  const linkedTemplates = prd.linked_templates || "<<<ADD>>>";

  // ── Intro sentence ──
  const introText = prd.intro_sentence
    || (lang === "fr"
      ? `Cette analyse couvre le problème signalé concernant le template "${templateName}" dans le workflow ${workflow}.`
      : `This analysis covers the issue reported for the "${templateName}" template in the ${workflow} workflow.`);

  // ══════════════════════════════════════════════════════════════
  // ISSUE CONTENT — follows the exact section order from the prompt
  // ══════════════════════════════════════════════════════════════
  const issueContent = [];

  // ─── CONTEXT (Heading 2) ───
  issueContent.push(h.heading2("Context"));
  if (prd.context) {
    issueContent.push(...textToParas(prd.context));
  } else if (prd.current_behaviour_context) {
    // Fallback for old format
    issueContent.push(...textToParas(prd.current_behaviour_context));
  } else {
    issueContent.push(h.bodyText(["<<<ADD>>> — Describe what this template/note does and its role in the workflow."]));
  }
  issueContent.push(h.empty());

  // ─── PROBLEM STATEMENT (Heading 2) ───
  issueContent.push(h.heading2(lang === "fr" ? "Problème identifié" : "Problem statement"));
  if (prd.problem_statement) {
    issueContent.push(...textToParas(prd.problem_statement));
  } else if (prd.current_behaviour_problems) {
    // Fallback for old format
    issueContent.push(...textToParas(prd.current_behaviour_problems));
  } else if (ticket.analysis) {
    issueContent.push(...textToParas(ticket.analysis));
  } else {
    issueContent.push(h.bodyText(["<<<ADD>>> — Describe what is wrong or missing."]));
  }
  issueContent.push(h.empty());

  // ─── SCREENSHOTS (embedded after problem statement, before current behaviour) ───
  const screenshotParas = loadScreenshots(screenshots);
  if (screenshotParas.length > 0) {
    issueContent.push(h.heading2(lang === "fr" ? "Captures d'écran" : "Screenshots"));
    issueContent.push(...screenshotParas);
    issueContent.push(h.empty());
  }

  // ─── CURRENT BEHAVIOUR (Heading 2) ───
  issueContent.push(h.heading2(lang === "fr" ? "Comportement actuel" : "Current behaviour"));
  if (prd.current_behaviour) {
    issueContent.push(...textToParas(prd.current_behaviour));
  } else {
    issueContent.push(h.bodyText(["<<<ADD>>> — Describe what happens currently when the section is active. Include FR and EN sentences."]));
  }
  issueContent.push(h.empty());

  // ─── NEW BEHAVIOUR AFTER FIX (Heading 2) ───
  issueContent.push(h.heading2(lang === "fr" ? "Nouveau comportement après correction" : "New behaviour after fix"));

  // Summary sentence
  if (prd.new_behaviour_summary) {
    issueContent.push(...textToParas(prd.new_behaviour_summary));
    issueContent.push(h.empty());
  } else if (prd.requested_functional_change) {
    // Fallback for previous format
    issueContent.push(...textToParas(prd.requested_functional_change));
    issueContent.push(h.empty());
  } else if (prd.new_behaviour) {
    // Fallback for oldest format
    issueContent.push(...textToParas(prd.new_behaviour));
    issueContent.push(h.empty());
  }

  // Heading 3 subsections (the detailed spec)
  const subsections = prd.new_behaviour_subsections || [];
  for (const sub of subsections) {
    if (!sub.heading || !sub.content) continue;
    issueContent.push(h.heading3(sub.heading));
    issueContent.push(...renderSubsectionContent(sub.content));
    issueContent.push(h.empty());
  }

  // If no subsections but we have the old format fields, render them
  if (subsections.length === 0 && !prd.new_behaviour_summary && !prd.requested_functional_change && !prd.new_behaviour) {
    issueContent.push(h.bodyText(["<<<ADD>>> — Describe the exact functional change needed."]));
    issueContent.push(h.empty());
  }

  // ─── VISIBILITY RULES SUMMARY (Heading 2) — always a table when present ───
  if (prd.visibility_rules && prd.visibility_rules !== "N/A" && prd.visibility_rules.trim()) {
    issueContent.push(h.heading2(lang === "fr" ? "Résumé des règles de visibilité" : "Visibility rules summary"));
    const visTable = parseInlineTable(prd.visibility_rules);
    if (visTable) {
      issueContent.push(h.buildTable(visTable.colWidths, visTable.headers, visTable.rows));
    } else {
      // Fallback: render as text with bullets
      issueContent.push(...textToParas(prd.visibility_rules));
    }
    issueContent.push(h.empty());
  }

  // ─── REFERENCE IMPLEMENTATION (Heading 2) ───
  if (prd.reference_implementation && prd.reference_implementation !== "N/A") {
    issueContent.push(h.heading2(lang === "fr" ? "Implémentation de référence" : "Reference implementation"));
    issueContent.push(...textToParas(prd.reference_implementation));
    issueContent.push(h.empty());
  } else if (prd.reference_pattern && prd.reference_pattern !== "N/A") {
    // Fallback for previous format
    issueContent.push(h.heading2(lang === "fr" ? "Implémentation de référence" : "Reference implementation"));
    issueContent.push(...textToParas(prd.reference_pattern));
    issueContent.push(h.empty());
  }

  // ─── PROPOSED WORDING (if separate from subsections) ───
  const hasWording = ["proposed_wording_current_fr", "proposed_wording_new_fr"].some(
    k => prd[k] && prd[k] !== "N/A"
  );
  if (hasWording) {
    issueContent.push(h.heading2("Proposed wording"));
    for (const [key, label] of [
      ["proposed_wording_current_fr", "Current FR"],
      ["proposed_wording_current_en", "Current EN"],
      ["proposed_wording_new_fr", "New FR"],
      ["proposed_wording_new_en", "New EN"],
    ]) {
      if (prd[key] && prd[key] !== "N/A") {
        issueContent.push(h.heading3(label));
        issueContent.push(...textToParas(prd[key]));
        issueContent.push(h.empty());
      }
    }
  }

  // ── TEST PLAN ──
  const testPlanContent = [];
  const scenarios = prd.test_scenarios || [];

  if (scenarios.length > 0) {
    const rows = scenarios.map((s, i) => [
      [`${i + 1}`],
      [s.scenario || "<<<ADD>>>"],
      [s.input || "<<<ADD>>>"],
      [s.expected || "<<<ADD>>>"],
      ["To test"],
    ]);
    testPlanContent.push(
      h.buildTable(
        [400, 2200, 2600, 3200, 629],
        ["#", "Scenario", "Input", lang === "fr" ? "Résultat attendu" : "Expected result", "Status"],
        rows
      )
    );
  } else {
    testPlanContent.push(
      h.buildTable(
        [400, 2200, 2600, 3200, 629],
        ["#", "Scenario", "Input", lang === "fr" ? "Résultat attendu" : "Expected result", "Status"],
        [
          [["1"], ["Section inactive"], ["Checkbox = unchecked"], [lang === "fr" ? "Aucun texte affiché" : "No text printed"], ["To test"]],
          [["2"], [lang === "fr" ? "Actif, aucune saisie" : "Active, no input"], [lang === "fr" ? "Checkbox coché, champs vides" : "Checkbox checked, fields empty"], [lang === "fr" ? "Aucun texte dans la sortie publiée" : "No text in published output"], ["To test"]],
          [["3"], [lang === "fr" ? "Tester FR / EN" : "Test FR / EN"], [lang === "fr" ? "Changer la langue" : "Switch language"], [lang === "fr" ? "Correct dans toutes les langues" : "Correct in all languages"], ["To test"]],
          [["4"], [lang === "fr" ? "Tester périodes" : "Test periods"], ["N, N-1, N-2"], [lang === "fr" ? "Correct quelle que soit la période" : "Correct regardless of period"], ["To test"]],
          [["5"], [lang === "fr" ? "Export PDF" : "PDF export"], ["PDF"], [lang === "fr" ? "PDF correct" : "PDF is correct"], ["To test"]],
        ]
      )
    );
  }

  // ── PO CHECKLIST EXTRA ITEMS ──
  const poChecklist = prd.po_checklist_extra || [];

  // ── BUILD THE 4-TAB DOCUMENT ──
  const doc = h.buildDocument({
    introText,
    quickLinks: {
      freshdesk: ticket.ticket_url || `https://silverfin.freshdesk.com/a/tickets/${ticket.ticket_id}`,
      jira: "<<<ADD>>>",
    },
    templateInfo: {
      name: templateName,
      workflow: workflow,
    },
    bulletChecks: {
      periodLogic: periodLogic,
      linkedTemplates: linkedTemplates,
    },
    issueContent,
    testPlan: testPlanContent,
    poChecklist: poChecklist,
  });

  const buffer = await h.Packer.toBuffer(doc);
  fs.writeFileSync(outputPath, buffer);
  console.log(`Generated: ${outputPath}`);
}

generate().catch(err => {
  console.error("Error:", err.message);
  process.exit(1);
});
