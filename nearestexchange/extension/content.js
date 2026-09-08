(function () {
  const ETH = /\b0x[a-fA-F0-9]{40}\b/g;
  const BTC = /\b((?:bc1|[13])[a-zA-HJ-NP-Z0-9]{25,62})\b/g;

  function mark(node) {
    if (node.nodeType !== Node.TEXT_NODE) return;
    const parent = node.parentElement;
    if (!parent || parent.closest("a,script,style,textarea,input,.ne-addr")) return;
    const text = node.textContent;
    if (!ETH.test(text) && !BTC.test(text)) return;
    ETH.lastIndex = 0;
    BTC.lastIndex = 0;
    const wrap = document.createElement("span");
    wrap.innerHTML = text.replace(ETH, (m) => span(m, "eth")).replace(BTC, (m) => span(m, "btc"));
    if (wrap.childNodes.length) parent.replaceChild(wrap, node);
  }

  function span(addr, chain) {
    return `<span class="ne-addr" data-ne-chain="${chain}" title="NearestExchange: ${chain} address">${addr}</span>`;
  }

  function walk(el) {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(mark);
  }

  walk(document.body);
  document.addEventListener("click", (ev) => {
    const t = ev.target.closest && ev.target.closest(".ne-addr");
    if (!t) return;
    chrome.storage.sync.set({ lastAddress: t.textContent.trim() });
  });
})();
