NearestExchange Chrome extension (Manifest V3)

This is a compliance overlay, not an official Binance app.

1. Download nearestexchange-extension.zip from the desk and unzip.
2. Chrome → Extensions → Developer mode → Load unpacked → select the extension/ folder.
3. In the popup, set API base to the desk host (the same origin that serves /api/p2p/case).
4. On Binance P2P, Etherscan, Blockstream, or Telegram Web, addresses are outlined.
   Click one, then open the popup and Trace.

Binance would ship this internally by pinning API base to their private desk URL
and restricting host_permissions to binance.com + explorers.
