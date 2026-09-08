chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "ne-trace",
    title: "Trace wallet with NearestExchange",
    contexts: ["selection"],
  });
});

chrome.contextMenus.onClicked.addListener((info) => {
  if (info.menuItemId !== "ne-trace") return;
  const text = (info.selectionText || "").trim();
  chrome.storage.sync.set({ lastAddress: text });
  chrome.action.openPopup().catch(() => {});
});
