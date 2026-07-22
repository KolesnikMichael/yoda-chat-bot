<%*
// Next free ADR-NNN under design/decisions/ (file names only).
const _idScan = (prefix, roots) => {
  const re = new RegExp("^" + prefix + "-(\\d+)");
  const used = new Set();
  let max = -1;
  const visit = (folder) => {
    if (!folder || !folder.children) return;
    for (const child of folder.children) {
      const m = child.name.match(re);
      if (m) {
        const n = parseInt(m[1], 10);
        used.add(n);
        if (n > max) max = n;
      }
      if (child.children) visit(child);
    }
  };
  for (const root of roots) visit(app.vault.getAbstractFileByPath(root));
  return { max, used };
};

const _adrIds = _idScan("ADR", ["design/decisions"]);
const suggested = String(_adrIds.max + 1);
const num  = await tp.system.prompt("ADR number (next free: " + suggested + ")", suggested);
const name = await tp.system.prompt("Hyphenated name (e.g. ui-language)");

if (!num || !name) { new Notice("ADR creation cancelled."); return; }
if (!/^\d+$/.test(num.trim())) {
  new Notice("ADR number must be digits only."); return;
}
const numInt = parseInt(num.trim(), 10);
if (_adrIds.used.has(numInt)) {
  new Notice("ADR-" + String(numInt).padStart(3, "0") + " already exists.");
  return;
}

const id     = "ADR-" + String(numInt).padStart(3, "0");
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
