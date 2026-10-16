const $ = id => document.getElementById(id);
let examples = [], data = null, selected = -1, timer = null, busy = false;
function stop() { clearInterval(timer); timer = null; $("play").textContent = "Play"; }
function reset() {
  clearTranslation();
  $("detected-language").textContent = "Language will be detected when you analyze.";
  stop(); data = null; selected = -1;
  $("tokens").replaceChildren();
  const row = document.createElement("tr"), cell = document.createElement("td");
  cell.colSpan = 5; cell.className = "empty-table"; cell.textContent = "Your tokens will appear here.";
  row.append(cell); $("tokens").append(row);
  $("token-count").textContent = "0 tokens";
  $("source-preview").hidden = true; $("raw-output").hidden = true;
  $("status-pill").textContent = "READY"; $("status-pill").className = "pill";
  $("lex-status").textContent = $("syntax-status").textContent = "Waiting";
  $("result").className = ""; $("result").replaceChildren();
  const title = document.createElement("h3"); title.textContent = "Ready when you are.";
  const note = document.createElement("p"); note.textContent = "Run an analysis to check your program against the grammar.";
  $("result").append(title,note); $("notice").textContent = "";
  $("step-info").textContent = "Analyze a program to explore how Lex recognizes each token.";
  ["previous","next","play"].forEach(id => $(id).disabled = true);
  $("length").textContent = $("source").value.length + " characters";
}
function choose(index) {
  if (!data) return;
  selected = Math.max(0, Math.min(index, data.tokens.length - 1));
  const token = data.tokens[selected];
  document.querySelectorAll("tr[data-index]").forEach(row => row.classList.toggle("active", Number(row.dataset.index) === selected));
  const preview = $("source-preview"); preview.hidden = false; preview.replaceChildren();
  const start = Math.min(token.start, data.source.length), end = Math.min(token.end, data.source.length);
  preview.append(document.createTextNode(data.source.slice(0,start)));
  const mark = document.createElement("mark"); mark.textContent = token.type === "EOF" ? " ⟨EOF⟩" : data.source.slice(start,end);
  preview.append(mark, document.createTextNode(data.source.slice(end)));
  $("step-info").textContent = "Token " + (selected+1) + " / " + data.tokens.length + ": " +
    (token.lexeme || "end of input") + " → " + token.type + " · line " + token.line + ", column " + token.column +
    ". Highlighting refers to the original source; comments are skipped.";
  $("previous").disabled = selected === 0; $("next").disabled = selected === data.tokens.length - 1;
}
async function analyze() {
  if (busy) return;
  busy = true; reset(); $("analyze").disabled = true; $("source").readOnly = true; $("examples").disabled = true;
  $("analyze").textContent = "Analyzing…"; $("language").disabled = true;
  try {
    const response = await fetch("/api/analyze", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({source:$("source").value, language:$("language").value || "auto"})});
    const body = await response.json();
    if (!response.ok) throw new Error(Array.isArray(body.detail) ? body.detail.map(item => item.msg).join("; ") : body.detail || "Analysis failed.");
    data = body; $("tokens").replaceChildren();
    const detected = data.language;
    $("detected-language").textContent = detected.name + (detected.ambiguous ? " · ambiguous: " + detected.candidates.join(", ") : "") + ". " + detected.reason;
    data.tokens.forEach((token,index) => {
      const row = document.createElement("tr"); row.dataset.index = index;
      [token.index,token.type,token.lexeme || "⟨EOF⟩",token.line,token.column].forEach((value,i) => {
        const cell = document.createElement("td"); cell.textContent = value;
        if (i === 1) cell.className = "type"; row.append(cell);
      });
      row.addEventListener("click", () => {stop();choose(index);}); $("tokens").append(row);
    });
    $("token-count").textContent = data.tokens.length + " tokens";
    $("lex-status").textContent = data.lexical === "success" ? "Passed" : "Error";
    $("syntax-status").textContent = {success:"Passed",error:"Error",skipped:"Skipped"}[data.syntax];
    const good = data.syntax === "success";
    $("status-pill").textContent = good ? "VALID" : "ERROR";
    $("status-pill").className = "pill " + (good ? "success" : "error");
    $("result").className = good ? "" : "error"; $("result").replaceChildren();
    const icon = document.createElement("div"); icon.className = "empty-icon"; icon.textContent = good ? "✓" : "!";
    const title = document.createElement("h3"); title.textContent = good ? "Your syntax checks out." : data.diagnostic.stage === "lexical" ? "Unrecognized character." : "A syntax issue was found.";
    const note = document.createElement("p"); note.textContent = good ? "The source passes syntax checking. This does not check types or run the code." :
      "Line " + data.diagnostic.line + ", column " + data.diagnostic.column + ": " + data.diagnostic.message;
    $("result").append(icon,title,note);
    renderTranslation();
    $("terminal").textContent = data.output; $("raw-output").hidden = false;
    $("play").disabled = false;
    let index = 0;
    if (data.diagnostic) {
      index = data.tokens.findIndex(t => t.line === data.diagnostic.line && t.column === data.diagnostic.column);
      if (index < 0) index = data.tokens.length - 1;
    }
    choose(index);
  } catch(error) { $("notice").textContent = error.message; }
  finally { busy = false; $("analyze").disabled = false; $("source").readOnly = false; $("examples").disabled = false; $("language").disabled = false; $("analyze").textContent = "Analyze code →"; }
}
$("analyze").addEventListener("click", analyze);
$("source").addEventListener("input", reset);
$("language").addEventListener("change", reset);
$("source").addEventListener("keydown", event => {if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {event.preventDefault();analyze();}});
$("previous").addEventListener("click", () => {stop();choose(selected-1);});
$("next").addEventListener("click", () => {stop();choose(selected+1);});
$("play").addEventListener("click", () => {
  if (timer) {stop();return;}
  if (selected === data.tokens.length - 1) choose(0);
  $("play").textContent = "Pause";
  timer = setInterval(() => {if (selected >= data.tokens.length - 1) stop();else choose(selected+1);},650);
});
$("examples").addEventListener("change", () => {
  const example = examples.find(item => item.id === $("examples").value);
  if (example) {$("source").value = example.source;$("language").value = "auto";reset();}
});
async function initialize() {
  try {
    const response = await fetch("/api/examples");
    if (!response.ok) throw new Error("Could not load examples.");
    examples = await response.json();
    examples.forEach(example => {const option = document.createElement("option"); option.value = example.id;option.textContent = example.name;$("examples").append(option);});
    $("source").value = examples.find(item => item.id === "branches").source;
    $("examples").value = "branches";reset();
  } catch(error) {$("notice").textContent = error.message;}
}

/* These panels display IR and semantic actions produced by C, not by JS. */
let patchesApplied = 0;
function emptyRow(id, columns, message) {
  const row = document.createElement("tr"), cell = document.createElement("td");
  cell.colSpan = columns; cell.textContent = message; cell.className = "empty-table";
  row.append(cell); $(id).replaceChildren(row);
}
function clearTranslation() {
  patchesApplied = 0;
  $("normalized-panel").hidden = true; $("normalized-code").textContent = "";
  $("translation-status").textContent = "WAITING"; $("translation-status").className = "pill";
  $("translation-steps").replaceChildren();
  const item = document.createElement("li"); item.textContent = "Analyze a valid program to see the semantic actions.";
  $("translation-steps").append(item);
  $("patch-operations").replaceChildren();
  emptyRow("patch-code",2,"Waiting for valid input.");
  emptyRow("tac-code",3,"Waiting for valid input.");
  $("patch-info").textContent = "Pending jump targets start as _. Apply patches to resolve each destination.";
  $("tac-info").textContent = "Final code appears only after the entire input passes syntax checking.";
  $("tac-count").textContent = "0 instructions";
  ["patch-next","patch-reset","download-tac"].forEach(id => $(id).disabled = true);
}
function drawPatches() {
  const resolved = new Map(data.backpatches.slice(0,patchesApplied).map(p => [p.instruction,p.target]));
  $("patch-code").replaceChildren();
  for (const instruction of data.tac) {
    const row = document.createElement("tr"), label = document.createElement("td"), code = document.createElement("td");
    label.textContent = instruction.id;
    code.textContent = resolved.has(instruction.id) ? instruction.text : instruction.unpatched_text;
    if (resolved.has(instruction.id)) row.className = "patched";
    row.append(label,code); $("patch-code").append(row);
  }
  const total = data.backpatches.length;
  $("patch-info").textContent = total ? patchesApplied + " / " + total + " jump targets resolved." : "No jumps need patching in this program.";
  if (patchesApplied) {
    const last = data.backpatches[patchesApplied-1];
    $("patch-info").textContent += " Last action: backpatch({" + last.instruction + "}, " + last.target + ").";
  }
  $("patch-next").disabled = patchesApplied === total;
  $("patch-reset").disabled = patchesApplied === 0;
}
function renderTranslation() {
  const valid = data.translation === "success";
  $("translation-status").textContent = valid ? "GENERATED" : "SKIPPED";
  $("translation-status").className = "pill " + (valid ? "success" : "error");
  $("translation-steps").replaceChildren();
  if (!valid) {
    const item = document.createElement("li"); item.textContent = data.translation_reason || "Translation was discarded because the source has an error.";
    $("translation-steps").append(item);
    emptyRow("patch-code",2,"Backpatching skipped.");
    emptyRow("tac-code",3,data.syntax === "success" ? "Syntax is valid, but this construct is outside TAC support." : "No TAC generated for invalid input.");
    $("patch-info").textContent = "Backpatching skipped.";
    $("tac-info").textContent = data.translation_reason || "Fix the lexical or syntax error and analyze again.";
    return;
  }
  if (data.normalized_source !== null) {
    $("normalized-panel").hidden = false; $("normalized-code").textContent = data.normalized_source;
  }
  for (const step of data.translation_steps) {
    const item = document.createElement("li"), rule = document.createElement("strong");
    rule.textContent = step.rule; item.append(rule,document.createElement("br"),document.createTextNode(step.detail));
    $("translation-steps").append(item);
  }
  $("patch-operations").replaceChildren();
  for (const patch of data.backpatches) {
    const item = document.createElement("li");
    item.textContent = "backpatch({" + patch.instruction + "}, " + patch.target + ")";
    $("patch-operations").append(item);
  }
  if (!data.backpatches.length) {
    const item = document.createElement("li");item.textContent = "No pending jumps.";$("patch-operations").append(item);
  }
  $("tac-code").replaceChildren();
  for (const instruction of data.tac) {
    const row = document.createElement("tr");
    for (const value of [instruction.id,instruction.text,instruction.target ?? "—"]) {
      const cell = document.createElement("td");cell.textContent = value;row.append(cell);
    }
    $("tac-code").append(row);
  }
  $("tac-count").textContent = data.tac.length + " instructions";
  $("tac-info").textContent = "All jumps reference instruction labels. $t temporaries are compiler-generated; halt marks the program exit.";
  $("download-tac").disabled = false; patchesApplied = 0;drawPatches();
}
$("patch-next").addEventListener("click", () => {
  if (data && patchesApplied < data.backpatches.length) {patchesApplied++;drawPatches();}
});
$("patch-reset").addEventListener("click", () => {patchesApplied = 0;drawPatches();});
$("download-tac").addEventListener("click", () => {
  if (!data || data.translation !== "success") return;
  const blob = new Blob([data.tac.map(i => i.id + ": " + i.text).join("\n") + "\n"], {type:"text/plain"});
  const url = URL.createObjectURL(blob), link = document.createElement("a");
  link.href = url;link.download = "program.tac";link.click();setTimeout(() => URL.revokeObjectURL(url),1000);
});

initialize();

