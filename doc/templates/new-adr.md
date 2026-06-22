<%*
const num  = await tp.system.prompt("ADR number (e.g. 2)");
const name = await tp.system.prompt("Hyphenated name (e.g. ui-language)");

if (!num || !name) { new Notice("ADR creation cancelled."); return; }

const id     = "ADR-" + num.padStart(3, "0");
const path   = "design/decisions/" + id + "-" + name;
const title  = name.replace(/-/g, " ");
const today  = tp.date.now("YYYY-MM-DD");

await tp.file.move(path);

tR += [
  "---",
  "id: " + id,
  'title: "' + title + '"',
  "date: " + today,
  "created: " + today,
  "tags: []",
  "---",
  "",
  "# " + id + ": " + title,
  "",
  "## Context",
  "",
  "The situation or problem that made this decision necessary.",
  "What forces are at play, what constraints exist, how the trade-offs line up.",
  "",
  "## Decision",
  "",
  "The chosen approach and its rationale.",
  "",
  "<!-- Optional: ### Affected subsystems — maximum detail allowed in an ADR.",
  "     One line per subsystem: what the decision requires, not how to implement it.",
  "     Skip tables, field names, and design mechanics; those belong in epic/task design. -->",
  "",
  "## Rejected options",
  "",
  "- **Option name** — why it was rejected.",
  "- **Option name** — why it was rejected.",
  "",
  "## Consequences",
  "",
  "**Positive:**",
  "- ...",
  "",
  "**Negative / accepted trade-offs:**",
  "- ...",
  "",
  "**Neutral:**",
  "- ...",
  "",
  "## Related documents",
  "",
  "<!-- Same level or higher only: ADR, Policy, Strategies, etc. Not epic/task design.md -->",
  "- [[]]"
].join("\n");
%>
