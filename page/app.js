const $ = id => document.getElementById(id);
let state = { instances: [], models: [] }, busy = false, editing = null, lastSubmit = 0;
let text;
const en = { subtitle: "Independent Codex homes, managed together.", refresh: "Refresh", add: "Add instance", defaultLabel: "Default Codex", defaultNote: "Keeps its own configuration", empty: "Add a CODEX_HOME directory to get started.", footer: "Selections apply when an instance starts again. Existing cxi commands keep working.", model: "Model", choose: "Choose a model…", managed: "Magpie on", original: "Original config", rename: "Rename", remove: "Remove", name: "Name", create: "Create the directory if it does not exist", cancel: "Cancel", save: "Save", working: "Updating…", timeout: "The backend has not answered yet. Refresh in a moment.", pending: "Another operation is still running.", removeAsk: "Remove this instance from MultiCodex? Its files and sessions will stay." };
const zh = { subtitle: "不同配置的 Codex，放在一起管理。", refresh: "刷新", add: "添加实例", defaultLabel: "主 Codex", defaultNote: "继续使用自己的配置", empty: "添加一个 CODEX_HOME 目录，即可开始管理。", footer: "重新启动实例后应用选择。原有的 cxi 命令也可以继续使用。", model: "模型", choose: "选择模型…", managed: "Magpie 接管", original: "使用原配置", rename: "重命名", remove: "移除", name: "名称", create: "目录不存在时创建", cancel: "取消", save: "保存", working: "正在更新…", timeout: "后台暂未返回，请稍后刷新。", pending: "另一个操作正在处理中。", removeAsk: "从 MultiCodex 中移除此实例？配置文件和会话仍会保留。" };

function element(tag, content, className) {
  const e = document.createElement(tag);
  if (content !== undefined) e.textContent = content;
  if (className) e.className = className;
  return e;
}
function status(message, error = false) { $("status").textContent = message; $("status").className = error ? "error" : ""; }
function render() {
  $("instances").replaceChildren();
  $("default-path").textContent = state.defaultHome || "~/.codex";
  $("empty").hidden = state.instances.length > 0;
  for (const item of state.instances) {
    const card = element("article", undefined, "instance"); card.dataset.instance = item.id;
    const top = element("div", undefined, "instance-top");
    const icon = element("span", "›_", "agent-icon"); icon.setAttribute("aria-hidden", "true");
    const identity = element("div", undefined, "identity");
    identity.append(element("h2", item.name), element("code", item.home, "home"));
    top.append(icon, identity);
    const toggle = element("button", item.enabled ? text.managed : text.original, "switch");
    toggle.type = "button"; toggle.setAttribute("role", "switch"); toggle.setAttribute("aria-checked", String(item.enabled)); toggle.setAttribute("aria-label", item.name+" · "+text.managed);
    toggle.addEventListener("click", () => send("toggle", { id: item.id, enabled: !item.enabled }));
    const label = element("label", undefined, "model-field"), select = element("select");
    label.append(element("span", text.model));
    select.setAttribute("aria-label", item.name+" · "+text.model);
    const initial = element("option", text.choose); initial.value = ""; select.append(initial);
    const models = [...state.models];
    const current = item.model || item.lastModel;
    if (current && !models.some(m => m.id === current)) models.unshift({ id: current, name: current });
    for (const model of models) { const option = element("option", model.name); option.value = model.id; select.append(option); }
    select.value = current || "";
    select.addEventListener("change", () => { if (select.value) send("model", { id: item.id, model: select.value }); });
    label.append(select); top.append(label, toggle); card.append(top);
    const bottom = element("div", undefined, "bottom");
    bottom.append(element("code", item.launch, "launch"));
    const actions = element("div", undefined, "instance-actions");
    const rename = element("button", text.rename, "quiet"); rename.type = "button"; rename.addEventListener("click", () => edit(item));
    const remove = element("button", text.remove, "quiet"); remove.type = "button"; remove.addEventListener("click", () => send("remove", { id: item.id }));
    actions.append(rename, remove); bottom.append(actions); card.append(bottom); $("instances").append(card);
  }
  document.querySelectorAll("button,select").forEach(e => { e.disabled = busy; });
}
function edit(item = null) {
  editing = item;
  $("editor-title").textContent = item ? text.rename : text.add;
  $("instance-name").value = item?.name || "";
  $("instance-home").value = "";
  $("path-row").hidden = $("create-row").hidden = Boolean(item);
  $("instance-home").required = !item;
  $("instance-create").checked = false;
  $("editor").showModal(); $("instance-name").focus();
}
async function send(action, args = {}) {
  if (busy) return;
  busy = true; status(text.working); render();
  try {
    const latest = await magpie.options.get();
    if (latest.request) throw new Error(text.pending);
    const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, "0")).join("");
    const delay = Math.max(0, lastSubmit+1200-Date.now());
    if (delay) await new Promise(r => setTimeout(r, delay));
    lastSubmit = Date.now();
    await magpie.options.set({ schema: 1, request: { id, action, args } });
    for (let attempt = 0; attempt < 100; attempt++) {
      await new Promise(r => setTimeout(r, 500));
      const options = await magpie.options.get();
      if (options.result?.id === id) {
        if (options.state) state = options.state;
        status(options.result.message, !options.result.ok);
        return;
      }
    }
    throw new Error(text.timeout);
  } catch (error) { status(error.message, true); }
  finally { busy = false; render(); }
}
magpie.ready.then(async () => {
  text = magpie.theme?.lang?.startsWith("zh") ? zh : en;
  for (const [id, key] of Object.entries({ subtitle: "subtitle", refresh: "refresh", add: "add", "default-label": "defaultLabel", "default-note": "defaultNote", empty: "empty", footer: "footer", "name-label": "name", "create-label": "create", cancel: "cancel", save: "save" })) $(id).textContent = text[key];
  $("add").addEventListener("click", () => edit());
  $("refresh").addEventListener("click", () => send("refresh"));
  $("cancel").addEventListener("click", () => $("editor").close());
  $("save").addEventListener("click", () => {
    if (!$("instance-name").reportValidity() || (!editing && !$("instance-home").reportValidity())) return;
    const args = editing ? { id: editing.id, name: $("instance-name").value } : { name: $("instance-name").value, home: $("instance-home").value, create: $("instance-create").checked };
    const action = editing ? "rename" : "add";
    $("editor").close(); send(action, args);
  });
  $("instance-form").addEventListener("keydown", event => {
    if (event.key === "Enter") { event.preventDefault(); $("save").click(); }
  });
  const options = await magpie.options.get();
  if (options.state) state = options.state;
  render();
  if (!options.state) send("refresh");
}).catch(error => status(error.message, true));
