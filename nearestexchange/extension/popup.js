const $ = (id) => document.getElementById(id);

chrome.storage.sync.get(["apiBase", "lastAddress"], (st) => {
  if (st.apiBase) $("api").value = st.apiBase;
  if (st.lastAddress) $("address").value = st.lastAddress;
});

$("f").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const apiBase = $("api").value.trim().replace(/\/$/, "");
  const address = $("address").value.trim();
  const chain = $("chain").value;
  const scenario = $("scenario").value;
  chrome.storage.sync.set({ apiBase, lastAddress: address });
  const out = $("out");
  out.className = "out on";
  out.textContent = "Tracing…";
  try {
    const res = await fetch(apiBase + "/api/p2p/case", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address, chain, scenario }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed");
    const desk = data.binance || {};
    const exch = data.exchange || {};
    out.innerHTML =
      `<div class="title">${desk.title || "Result"}</div>` +
      `<div>${data.found ? (exch.exchange || "VASP") : "Not found"} · hop ${data.found ? data.hops : "—"} · ${desk.action || ""}</div>` +
      `<ol>${(desk.steps || []).map((s) => `<li>${s}</li>`).join("")}</ol>`;
  } catch (err) {
    out.innerHTML = `<div class="err">${err.message}. Set API base to the desk host.</div>`;
  }
});
