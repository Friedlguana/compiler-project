/* DOM-level integration check against a running FastAPI server.
 * No browser packages required. Run: node tests/test_frontend.cjs [base URL]
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const base = process.argv[2] || "http://127.0.0.1:8016";
class Element {
  constructor() {
    this.children = []; this.dataset = {}; this.listeners = {}; this.value = "";
    this._text = ""; this.disabled = false;
    this.classList = {toggle() {}};
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(""); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) {this._text = ""; this.children = children;}
  addEventListener(name, fn) { this.listeners[name] = fn; }
}
const html = fs.readFileSync(path.join(__dirname, "../web/static/index.html"),"utf8");
const elements = new Map([...html.matchAll(/id="([^"]+)"/g)].map(m => [m[1],new Element()]));
const document = {
  getElementById(id) { assert(elements.has(id), "Unknown UI element: "+id); return elements.get(id); },
  createElement() { return new Element(); },
  createTextNode(text) {const node=new Element();node.textContent=text;return node;},
  querySelectorAll() {return elements.get("tokens").children;},
};
const context = vm.createContext({
  document, setInterval, clearInterval, setTimeout, URL, Blob,
  fetch: (url,options) => fetch(base+url,options),
});
vm.runInContext(fs.readFileSync(path.join(__dirname,"../web/static/app.js"),"utf8"),context);
const element = id => document.getElementById(id);
const invoke = (id,event) => element(id).listeners[event]();
async function main() {
  for(let i=0;i<100 && !element("source").value;i++)
    await new Promise(resolve => setTimeout(resolve,20));
  assert(element("examples").children.length >= 9, "Examples must load");
  await invoke("analyze","click");
  assert.equal(element("translation-status").textContent,"GENERATED");
  assert(element("tac-code").textContent.includes("halt"));
  assert(element("translation-steps").textContent.includes("truelist"));
  assert(element("patch-code").textContent.includes("goto _"));
  const original = element("patch-code").textContent;
  let count=0;
  while(!element("patch-next").disabled && count++ < 100) invoke("patch-next","click");
  assert(count > 0 && count < 100);
  assert(!element("patch-code").textContent.includes("goto _"));
  invoke("patch-reset","click");
  assert.equal(element("patch-code").textContent,original);
  element("source").value = "a=1; if(a<2){b=3;";
  invoke("source","input");
  assert(element("download-tac").disabled);
  await invoke("analyze","click");
  assert.equal(element("translation-status").textContent,"SKIPPED");
  assert(element("tac-code").textContent.includes("No TAC"));
  element("examples").value = "empty-branches";invoke("examples","change");
  await invoke("analyze","click");
  assert.equal(element("translation-status").textContent,"GENERATED");
  assert.equal(element("notice").textContent,"");
  for (const [id,label] of [["python","Python"],["java","Java"],["c","C"],["cpp","C++"],["javascript","JavaScript"]]) {
    element("examples").value=id;invoke("examples","change");
    await invoke("analyze","click");
    assert.equal(element("translation-status").textContent,"GENERATED",id);
    assert(element("detected-language").textContent.includes(label));
    assert.equal(element("normalized-panel").hidden,false);
  }
  element("source").value = "const a = [1, 2];";invoke("source","input");
  await invoke("analyze","click");
  assert.equal(element("status-pill").textContent,"VALID");
  assert.equal(element("translation-status").textContent,"SKIPPED");
  assert(element("tac-code").textContent.includes("Syntax is valid"));
  assert(element("download-tac").disabled);
  element("source").value = "a = 1;";invoke("source","input");
  element("language").value = "javascript";invoke("language","change");
  await invoke("analyze","click");
  assert(element("detected-language").textContent.includes("selected by user"));
  assert.equal(element("translation-status").textContent,"GENERATED");
  console.log("Frontend integration passed: five-language auto-detection, examples, override, native source tokens, semantic actions, patch stepping/reset, unsupported-construct handling, and stale-state clearing.");
}
main().catch(error => {console.error(error);process.exitCode=1;});

