"use strict";
const themeButton = document.getElementById("theme");
try { if (localStorage.getItem("basinforge-theme") === "dark") document.body.classList.add("dark"); } catch (_) {}
themeButton?.addEventListener("click", () => { const dark = document.body.classList.toggle("dark"); try { localStorage.setItem("basinforge-theme", dark ? "dark" : "light"); } catch (_) {} });
const copyButton = document.getElementById("copy-install");
copyButton?.addEventListener("click", async () => { try { await navigator.clipboard.writeText(document.getElementById("install").textContent); copyButton.textContent = "Copied!"; } catch (_) { copyButton.textContent = "Select and copy the commands"; } });
const node = (tag, text, className) => { const element = document.createElement(tag); if (text !== undefined) element.textContent = text; if (className) element.className = className; return element; };
function modelEntry(model) {
  const details = node("details"), summary = node("summary");
  summary.append(node("strong", model.name), node("span", `${model.structure} · ${model.timestep} · ${model.calibrated_parameters.length} parameters · ${model.backend === "octave" ? "Octave + optim" : "Python"}${model.temperature_required ? " · temperature required" : ""}`, "model-meta"));
  details.append(summary, node("p", model.variant));
  const table = node("table"), caption = node("caption", "Parameter bounds and default initial configuration"), head = node("tr");
  for (const label of ["Parameter", "Supported range", "Default"]) head.append(node("th", label));
  const thead = node("thead"); thead.append(head); const tbody = node("tbody");
  for (const [parameter, value] of Object.entries(model.defaults)) { const row = node("tr"); row.append(node("td", parameter), node("td", model.bounds[parameter]?.join(" → ") ?? "fixed initial/configuration value"), node("td", String(value))); tbody.append(row); }
  table.append(caption, thead, tbody); details.append(table);
  if (model.stores !== null) details.append(node("p", `${model.stores} model stores. p01… follow source order; s01… are initial store values. Consult source comments for units and physical interpretation.`));
  const link = node("a", "Inspect the implementation →"); link.href = model.source; details.append(link);
  return details;
}
function renderResults(results) {
  const chart = document.getElementById("results-chart");
  for (const result of results) { const row = node("div", undefined, "chart-row"); const label = node("span", result.model.replace(" / hydromodel", "").replace(" / LuMod", "").replace("HYMOD structure / MARRMOT_29", "MARRMOT_29")); const track = node("div", undefined, "chart-track"), bar = node("span", undefined, "chart-bar");
    // Fixed domain [-0.5, 1.0]; zero is at one third. Do not imply all NSE
    // values are bounded below by -0.5; this chart uses these five results.
    const zero = 100 / 3, value = result.validation_nse;
    bar.style.left = `${value < 0 ? zero + value / 1.5 * 100 : zero}%`; bar.style.width = `${Math.abs(value) / 1.5 * 100}%`; if (value < 0) bar.classList.add("negative"); track.append(bar); row.append(label, track, node("span", value.toFixed(3), "chart-value")); chart.append(row);
  }
  chart.append(node("p", "Chart range: −0.5 to 1.0 · dashed line: NSE = 0", "fine"));
}
const modelList = document.getElementById("model-list");
if (modelList) fetch("data.json").then(response => { if (!response.ok) throw new Error("Registry unavailable"); return response.json(); }).then(data => {
  const search = document.getElementById("search"), backend = document.getElementById("backend"), timestep = document.getElementById("timestep");
  const render = () => { const query = search.value.toLowerCase().trim(); const entries = data.models.filter(model => (!backend.value || model.backend === backend.value) && (!timestep.value || model.timestep === timestep.value) && `${model.name} ${model.structure} ${model.variant}`.toLowerCase().includes(query)); modelList.replaceChildren(...entries.map(modelEntry)); if (!entries.length) modelList.append(node("p", "No models match these filters.")); document.getElementById("model-count").textContent = `${entries.length} of ${data.models.length} implementations · registry v${data.version}`; };
  search.addEventListener("input", render); backend.addEventListener("change", render); timestep.addEventListener("change", render); render(); renderResults(data.results);
}).catch(() => { document.getElementById("model-count").textContent = "Cannot load the interactive registry. Use the research catalog link below."; modelList.append(node("p", "Serve this site over HTTP rather than opening index.html directly.")); });
