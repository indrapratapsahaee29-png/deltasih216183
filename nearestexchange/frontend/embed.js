/* NearestExchange embed — drop into an internal Binance CS / P2P ticket view.
 *
 *   <div id="ne-desk"></div>
 *   <script src="https://YOUR-HOST/embed.js"></script>
 *   <script>
 *     NearestExchange.mount("#ne-desk", { apiBase: "" });
 *     NearestExchange.trace({ address, chain: "eth", scenario: "off_platform", order_id: "P2P123" })
 *       .then((r) => NearestExchange.render("#ne-desk", r));
 *   </script>
 *
 * Does not authenticate to Binance. The host page supplies the wallet from the ticket.
 */
(function (root) {
  var apiBase = "";

  function join(path) {
    return (apiBase || "").replace(/\/$/, "") + path;
  }

  function trace(opts) {
    opts = opts || {};
    var path = opts.scenario ? "/api/p2p/case" : "/api/trace";
    return fetch(join(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        address: opts.address,
        chain: opts.chain || "eth",
        scenario: opts.scenario || "unknown",
        order_id: opts.order_id || "",
        notes: opts.notes || "",
      }),
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) throw new Error(data.detail || "Trace failed");
        return data;
      });
    });
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&")
      .replace(/</g, "<")
      .replace(/>/g, ">");
  }

  function render(target, data) {
    var el = typeof target === "string" ? document.querySelector(target) : target;
    if (!el) return;
    var desk = data.binance || {};
    var exch = data.exchange || {};
    var hops = data.found ? data.hops : "—";
    el.innerHTML =
      '<div class="ne-card" style="font-family:system-ui,sans-serif;background:#141518;color:#ecece8;border:1px solid rgba(236,236,232,.12);border-radius:16px;padding:16px;max-width:420px">' +
      '<div style="font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#9a9a94">NearestExchange desk</div>' +
      '<div style="margin-top:8px;font-weight:600">' + escapeHtml(desk.title || "Trace") + "</div>" +
      '<div style="margin-top:8px;font-size:13px;color:#9a9a94">VASP ' +
      escapeHtml(data.found ? exch.exchange || "—" : "not found") +
      " · hop " + escapeHtml(hops) +
      " · " + escapeHtml((desk.action || "").replace(/_/g, " ")) +
      "</div>" +
      '<ol style="margin:12px 0 0;padding-left:18px;font-size:13px;color:#c8c8c2;line-height:1.45">' +
      (desk.steps || []).map(function (s) { return "<li>" + escapeHtml(s) + "</li>"; }).join("") +
      "</ol></div>";
  }

  function mount(target, opts) {
    opts = opts || {};
    if (opts.apiBase != null) apiBase = opts.apiBase;
    var el = typeof target === "string" ? document.querySelector(target) : target;
    if (el && !el.innerHTML.trim()) {
      el.innerHTML = '<div style="font-family:system-ui;color:#9a9a94;font-size:13px">NearestExchange ready. Call NearestExchange.trace then render.</div>';
    }
    return { trace: trace, render: function (data) { render(el, data); } };
  }

  root.NearestExchange = { trace: trace, render: render, mount: mount, setApiBase: function (b) { apiBase = b; } };
})(typeof window !== "undefined" ? window : this);
