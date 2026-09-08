# NearestExchange

SIH 2026 · Problem **26183** · I4C — real-time crypto fraud attribution
(nearest exchange / VASP for a victim-reported wallet).

Paste a wallet from an investment scam, task fraud, sextortion, ransomware,
phishing, darknet, or organized-crime complaint. The desk follows the largest
native outflow up to **three hops** on Bitcoin or Ethereum, matches a labeled
VASP, tags non-custodial / intermediary / burner wallets, and emits a freeze
or refer packet. Mixers, bridges, DeFi, and live NCRP/SAHYOG are **out of
scope** — a miss is returned instead of a guessed destination.


## Run (Mac / Linux)

From a fresh checkout, one command:

```bash
cd nearestexchange/backend
chmod +x run.sh
./run.sh
```

That creates a Python virtualenv (so `pip` never hits `externally-managed-environment`), installs dependencies, and starts the server on `http://127.0.0.1:8000`.

Override host/port if you need to:

```bash
PORT=8080 HOST=0.0.0.0 ./run.sh
```

## Run (Windows)

```bat
cd nearestexchange\backend
run.bat
```

## Tests

No network required. From `nearestexchange/`:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cd ..
python -m pytest tests/ -q
```

Covered: direct-hop match, multi-hop match, no-match-within-depth, address with no transactions, malformed address, queried-wallet-is-itself-an-exchange, risk scoring.

## What it does

1. Accepts a wallet + chain (`btc` or `eth`).
2. If the wallet itself is a labeled exchange address, that is the finding (hop 0, risk **High**).
3. Otherwise it pulls outgoing transactions from:
   - Bitcoin: [Blockstream Esplora](https://blockstream.info/api) (`/address/{addr}/txs`)
   - Ethereum: [Blockscout API v2](https://eth.blockscout.com/api/v2) (`/addresses/{addr}/transactions?filter=from`)
4. Follows the **largest native outflow** each hop (skips change-to-self and zero-value contract calls).
5. At each destination, looks the address up in a sourced VASP label set.
6. Stops at the first match, or after 3 hops.
7. Scores risk: **High** (0–1 hop), **Medium** (2–3 hops), **Low / unknown** (not found).
8. Draws the path and offers a plain-text investigator report.

Repeat queries for the same address+chain are served from a local SQLite cache for one hour so we do not hammer the public APIs.

## API

| Method | Path | Body | Result |
| --- | --- | --- | --- |
| `GET` | `/api/health` | — | Service + dataset stats |
| `POST` | `/api/trace` | `{ "address": "...", "chain": "eth" \| "btc" }` | JSON finding |
| `POST` | `/api/report` | same | `text/plain` investigator report |

`chain` also accepts `ethereum` / `bitcoin`. Empty or malformed addresses return HTTP 400. Upstream explorer failures return HTTP 502.

## Architecture

```
frontend/index.html     vanilla dashboard (vis-network via CDN)
backend/main.py        FastAPI: health, trace, report, static UI
backend/tracer.py      hop loop + Blockstream/Blockscout adapters
backend/exchanges.py   sourced VASP lookup
backend/data/exchanges.json
backend/cache.py       SQLite TTL cache
```

CORS is `allow_origins=["*"]` for local demo use. Tighten this before any public deployment.

## Label dataset

**997 addresses** across Bitcoin and Ethereum, **786 high-confidence**, covering **40+ VASPs**. Every row records `address`, `exchange`, `chain`, `confidence`, `source`, and `source_url`. Unverifiable addresses were not included.

| Source | What | Confidence |
| --- | --- | --- |
| [DefiLlama CEX adapters](https://github.com/DefiLlama/DefiLlama-Adapters) via [wallet-attribution](https://github.com/prettydeath/wallet-attribution) | Official proof-of-reserves / disclosed hot+cold wallets (BTC + ETH) | high |
| [Binance PoR blog, Nov 2022](https://www.binance.com/en/blog/community/2895840147147652626) | Self-disclosed BTC and ETH wallets | high |
| [Etherscan nametag docs](https://docs.etherscan.io/api-reference/endpoint/getaddresstag) | Coinbase 10 | high |
| [tradezon/cex-list](https://github.com/tradezon/cex-list) | Curated Ethereum CEX hot wallets | medium (unless already high from PoR) |
| [MerkleScience samples](https://github.com/merklescience/ethereum-exchange-addresses) | Published hot-wallet CSV | medium |
| Public rich-list labels (Arkham / CoinCarp) | Widely tagged BTC cold wallets (Binance, Bitfinex, Robinhood, OKX) | high |

This is a **starter set** aimed at the 200–500 address target. It is not a complete cluster of every deposit address those exchanges have ever used.

## Risk scoring (rule-based, no ML)

| Finding | Risk | Why it matters |
| --- | --- | --- |
| Queried wallet is a labeled VASP, or 1 hop to one | **High** | Freeze request can still work if you move now |
| Labeled VASP at hop 2 or 3 | **Medium** | Layering; still a named entity to compel |
| No match within 3 hops | **Low / unknown** | Do not invent a destination |

## Binance P2P desk (what you can sell)

This is **not** a Binance login and it does not freeze funds by itself. It is a
vendor desk Binance CS / P2P-dispute / compliance can sit *next to* a ticket:

- If the largest outflow **lands at Binance** → `freeze_internal` packet (UID
  clustering + withdrawal hold stay on Binance systems).
- If it lands at **another VASP** → `refer_vasp` packet (do not promise a
  Binance recovery).
- If nothing matches in 3 hops → `no_vasp` (do not guess).

**P2P patterns the desk names:** off-platform wallet after a P2P trade, inbound
laundering to Binance, fake P2P merchant, withdrawal to a reported wallet.

| How Binance would use it | Endpoint |
| --- | --- |
| Ticket sidebar / internal tool | `POST /api/p2p/case` + `GET /embed.js` (`NearestExchange.mount`) |
| Chrome overlay on binance.com/p2p, Etherscan, Telegram | `GET /extension.zip` (load unpacked) |
| Investigator report attached to the dispute | `POST /api/report` |

The JSON freeze/refer packet is what you copy into a Binance ticket. The actual
asset freeze, KYC, and UID map are Binance-owned and out of scope on purpose.


There is no public API for NCRP or SAHYOG that a prototype can legally call. The intended join is:

- NCRP case id + reported wallet + chain land in this tool as `POST /api/trace`.
- The JSON finding (VASP name, matched address, txids, risk, report text) is the payload that would go back onto the SAHYOG request to that VASP.
- Do not stand up fake NCRP endpoints; they teach judges the wrong lesson.

## What's left (honest)

**Working and verified in this environment**

- Health / trace / report endpoints, including 400s for empty and malformed input
- Hop engine + risk scoring against mocked graphs (`pytest`, no network)
- Live Blockstream and Blockscout reachability (the APIs responded from this host)
- Live traces against labeled wallets (a Binance ETH hot wallet returns hop 0; genesis BTC reports not found rather than crashing)
- SQLite cache, sourced 997-address label set, dashboard + graph + report download

**Placeholders / out of scope on purpose**

- Cross-chain / bridge tracing — open research, not a weekend feature
- Mixer / CoinJoin de-anonymization
- USDT/USDC token flows (native BTC and ETH only today; most Indian fraud is stablecoins — this is the highest-value next slice)
- Following more than the single largest outflow per hop
- Real-time NCRP/SAHYOG ingestion
- ML risk models
- Investigator accounts, auth, audit trails
- Expanding the label set from 997 toward a full deposit-address cluster (thousands)

**Not claimed**

- Completeness of exchange coverage. An unlabeled deposit address will produce **not found** even if a commercial tool would cluster it.

## Pitfalls this repo already avoids

- `run.sh` / `run.bat` always use a venv. Do not `pip install` into system Python.
- A short delay is inserted between hop requests. Do not loop the public APIs.
- The zip you hand to judges should not contain `venv/`, `__pycache__/`, or `trace_cache.db` (see `.gitignore`).
