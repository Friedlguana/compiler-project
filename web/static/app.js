const $ = id => document.getElementById(id);
let examples = [], data = null, selected = -1, timer = null, busy = false;
function stop() { clearInterval(timer); timer = null; $("play").textContent = "Play"; }
function reset() {
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
    ". Whitespace and // comments are skipped.";
  $("previous").disabled = selected === 0; $("next").disabled = selected === data.tokens.length - 1;
}
async function analyze() {
  if (busy) return;
  busy = true; reset(); $("analyze").disabled = true; $("source").readOnly = true; $("examples").disabled = true;
  $("analyze").textContent = "Analyzing…";
  try {
    const response = await fetch("/api/analyze", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({source:$("source").value})});
    const body = await response.json();
    if (!response.ok) throw new Error(Array.isArray(body.detail) ? body.detail.map(item => item.msg).join("; ") : body.detail || "Analysis failed.");
    data = body; $("tokens").replaceChildren();
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
    const note = document.createElement("p"); note.textContent = good ? "Every token follows the language grammar. Explore the token sequence below." :
      "Line " + data.diagnostic.line + ", column " + data.diagnostic.column + ": " + data.diagnostic.message;
    $("result").append(icon,title,note);
    $("terminal").textContent = data.output; $("raw-output").hidden = false;
    $("play").disabled = false;
    let index = 0;
    if (data.diagnostic) {
      index = data.tokens.findIndex(t => t.line === data.diagnostic.line && t.column === data.diagnostic.column);
      if (index < 0) index = data.tokens.length - 1;
    }
    choose(index);
  } catch(error) { $("notice").textContent = error.message; }
  finally { busy = false; $("analyze").disabled = false; $("source").readOnly = false; $("examples").disabled = false; $("analyze").textContent = "Analyze code →"; }
}
$("analyze").addEventListener("click", analyze);
$("source").addEventListener("input", reset);
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
  if (example) {$("source").value = example.source;reset();}
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
initialize();

