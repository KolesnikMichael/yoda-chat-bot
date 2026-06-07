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
  "## Options",
  "",
  "### Option 1: Name",
  "",
  "Description.",
  "",
  "**Pros:**",
  "- ...",
  "",
  "**Cons:**",
  "- ...",
  "",
  "---",
  "",
  "### Option 2: Name",
  "",
  "Description.",
  "",
  "**Pros:**",
  "- ...",
  "",
  "**Cons:**",
  "- ...",
  "",
  "## Decision",
  "",
  "**Option N chosen.**",
  "",
  "Rationale: why this option in this context.",
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
  "<!-- Tasks, designs, or other ADRs this decision relates to -->",
  "- [[]]"
].join("\n");
%>
