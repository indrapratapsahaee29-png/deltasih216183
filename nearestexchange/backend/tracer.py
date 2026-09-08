"""Hop-following engine for Bitcoin (Blockstream Esplora) and Ethereum (Blockscout)."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

import requests

from attribution import attach_attribution
from binance_desk import attach_binance_desk
from exchanges import lookup, validate_address

BLOCKSTREAM_BASE = "https://blockstream.info/api"
BLOCKSCOUT_BASE = "https://eth.blockscout.com/api/v2"
USER_AGENT = "NearestExchange/1.0 (SIH26183 investigator prototype)"
REQUEST_TIMEOUT = 25
HOP_DELAY_SECONDS = 0.45
MAX_HOPS = 3
MAX_RETRIES = 3

FetchOutgoing = Callable[[str, str], list[dict[str, Any]]]


class TraceError(Exception):
    """Raised when a chain API call fails after retries."""


def _http_get(url: str) -> Any:
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 429:
                time.sleep(1.2 * (attempt + 1))
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            if not resp.content:
                return None
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(0.6 * (attempt + 1))
    raise TraceError(f"Chain API request failed: {last_exc}")


def _btc_time(tx: dict[str, Any]) -> str | None:
    status = tx.get("status") or {}
    block_time = status.get("block_time")
    if not block_time:
        return None
    try:
        return datetime.fromtimestamp(int(block_time), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def get_btc_outgoing(address: str) -> list[dict[str, Any]]:
    """Return normalized outgoing transfers from a Bitcoin address."""
    data = _http_get(f"{BLOCKSTREAM_BASE}/address/{address}/txs")
    if not data:
        return []
    outgoing: list[dict[str, Any]] = []
    addr_lc = address.lower() if address.lower().startswith("bc1") else address
    for tx in data:
        spent_from_here = False
        for vin in tx.get("vin") or []:
            prev = vin.get("prevout") or {}
            vin_addr = prev.get("scriptpubkey_address")
            if vin_addr and vin_addr == addr_lc:
                spent_from_here = True
                break
            if vin_addr and address.lower().startswith("bc1") and vin_addr.lower() == addr_lc:
                spent_from_here = True
                break
        if not spent_from_here:
            continue
        txid = tx.get("txid") or ""
        when = _btc_time(tx)
        for vout in tx.get("vout") or []:
            dest = vout.get("scriptpubkey_address")
            if not dest:
                continue
            dest_norm = dest.lower() if dest.lower().startswith("bc1") else dest
            if dest_norm == addr_lc:
                continue  # change back to self
            sats = int(vout.get("value") or 0)
            if sats <= 0:
                continue
            outgoing.append(
                {
                    "to": dest_norm,
                    "amount": sats / 1e8,
                    "amount_raw": sats,
                    "unit": "BTC",
                    "txid": txid,
                    "time": when,
                }
            )
    return outgoing


def _addr_hash(node: Any) -> str | None:
    if not node:
        return None
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        return node.get("hash")
    return None


def get_eth_outgoing(address: str) -> list[dict[str, Any]]:
    """Return normalized outgoing native-ETH transfers from an address."""
    data = _http_get(
        f"{BLOCKSCOUT_BASE}/addresses/{address}/transactions?filter=from"
    )
    if not data:
        return []
    items = data.get("items") if isinstance(data, dict) else data
    if not items:
        return []
    src = address.lower()
    outgoing: list[dict[str, Any]] = []
    for tx in items:
        dest = _addr_hash(tx.get("to"))
        if not dest:
            continue
        dest = dest.lower()
        if dest == src:
            continue
        try:
            wei = int(str(tx.get("value") or "0"))
        except (TypeError, ValueError):
            wei = 0
        if wei <= 0:
            continue
        outgoing.append(
            {
                "to": dest,
                "amount": wei / 1e18,
                "amount_raw": wei,
                "unit": "ETH",
                "txid": tx.get("hash") or "",
                "time": tx.get("timestamp"),
            }
        )
    return outgoing


def get_outgoing(address: str, chain: str) -> list[dict[str, Any]]:
    if chain == "btc":
        return get_btc_outgoing(address)
    if chain == "eth":
        return get_eth_outgoing(address)
    raise ValueError("Unsupported chain.")


def risk_for_hops(found: bool, hops: int | None) -> str:
    """Rule-based risk: High (≤1 hop), Medium (2–3), Low/Unknown (not found)."""
    if not found or hops is None:
        return "low"
    if hops <= 1:
        return "high"
    return "medium"


def recommendation_for(result: dict[str, Any]) -> str:
    if result.get("queried_is_exchange"):
        name = (result.get("exchange") or {}).get("exchange") or "the labeled VASP"
        return (
            f"The queried wallet is itself a labeled {name} wallet. "
            f"Send a preservation / KYC request to {name} immediately, citing this "
            f"address. Confirm the label on a block explorer before filing process."
        )
    if result.get("found"):
        name = (result.get("exchange") or {}).get("exchange") or "the matched VASP"
        hops = result.get("hops")
        speed = (
            "Funds appear to have landed directly."
            if hops == 1
            else f"Funds reached {name} in {hops} hops."
        )
        return (
            f"{speed} Contact {name} compliance / law-enforcement liaison now with "
            f"the matched deposit address, the txids on the path, and the victim "
            f"complaint reference. Request a freeze/preservation letter and KYC "
            f"on the depositing account. Speed matters — remaining funds can move."
        )
    return (
        "No labeled exchange wallet was reached within 3 hops of the largest "
        "outflow path. This is not a finding of 'untraceable' — try a longer "
        "manual review on a block explorer, check token (USDT/USDC) flows, and "
        "consider that funds may still sit in an unlabeled intermediary. Do not "
        "guess a VASP."
    )


def _sleep(seconds: float, sleeper: Callable[[float], None] | None) -> None:
    (sleeper or time.sleep)(seconds)


def trace_wallet(
    address: str,
    chain: str,
    *,
    max_hops: int = MAX_HOPS,
    fetch_outgoing: FetchOutgoing | None = None,
    sleeper: Callable[[float], None] | None = None,
    hop_delay: float = HOP_DELAY_SECONDS,
) -> dict[str, Any]:
    """Follow the largest outgoing transfer up to `max_hops` looking for a VASP."""
    chain = chain.lower().strip()
    if chain in ("bitcoin", "btc"):
        chain = "btc"
    elif chain in ("ethereum", "eth"):
        chain = "eth"
    else:
        raise ValueError("Chain must be 'btc' or 'eth'.")

    normalized = validate_address(address, chain)
    fetcher = fetch_outgoing or get_outgoing
    now = datetime.now(timezone.utc).isoformat()

    start_hit = lookup(normalized, chain)
    path: list[dict[str, Any]] = [
        {
            "hop": 0,
            "from": None,
            "to": normalized,
            "amount": None,
            "unit": "BTC" if chain == "btc" else "ETH",
            "txid": None,
            "time": None,
            "is_exchange": bool(start_hit),
            "exchange": start_hit["exchange"] if start_hit else None,
        }
    ]

    if start_hit:
        result = {
            "address": normalized,
            "chain": chain,
            "found": True,
            "queried_is_exchange": True,
            "hops": 0,
            "risk": "high",
            "exchange": start_hit,
            "path": path,
            "note": "Queried wallet is a labeled exchange/VASP address.",
            "traced_at": now,
            "cached": False,
        }
        result["recommendation"] = recommendation_for(result)
        attach_binance_desk(result)
        attach_attribution(result)
        return result

    current = normalized
    visited = {normalized}
    found_hit: dict[str, Any] | None = None
    hops_used = 0
    no_outgoing = False

    for hop in range(1, max_hops + 1):
        if hop > 1:
            _sleep(hop_delay, sleeper)
        outgoing = fetcher(current, chain)
        candidates = [o for o in outgoing if o.get("to") and o["to"] not in visited]
        if not candidates:
            if hop == 1 and not outgoing:
                no_outgoing = True
            break
        largest = max(candidates, key=lambda o: float(o.get("amount") or 0))
        dest = largest["to"]
        dest_hit = lookup(dest, chain)
        step = {
            "hop": hop,
            "from": current,
            "to": dest,
            "amount": largest.get("amount"),
            "unit": largest.get("unit"),
            "txid": largest.get("txid"),
            "time": largest.get("time"),
            "is_exchange": bool(dest_hit),
            "exchange": dest_hit["exchange"] if dest_hit else None,
        }
        path.append(step)
        hops_used = hop
        visited.add(dest)
        if dest_hit:
            found_hit = dest_hit
            break
        current = dest

    found = found_hit is not None
    hops = hops_used if found else None
    risk = risk_for_hops(found, hops if found else None)
    if no_outgoing:
        note = "No outgoing transactions found for this wallet."
    elif not found:
        note = f"No labeled exchange reached within {max_hops} hops."
    else:
        note = f"Matched {found_hit['exchange']} at hop {hops_used}."

    result = {
        "address": normalized,
        "chain": chain,
        "found": found,
        "queried_is_exchange": False,
        "hops": hops if found else hops_used,
        "risk": risk,
        "exchange": found_hit,
        "path": path,
        "note": note,
        "traced_at": now,
        "cached": False,
    }
    if not found:
        result["hops"] = None
        result["hops_traced"] = hops_used
    else:
        result["hops_traced"] = hops_used
    result["recommendation"] = recommendation_for(result)
    attach_binance_desk(result)
    attach_attribution(result)
    return result


def format_amount(amount: float | None, unit: str | None) -> str:
    if amount is None:
        return "—"
    unit = unit or ""
    if unit == "BTC":
        return f"{amount:.8f} BTC"
    if unit == "ETH":
        return f"{amount:.6f} ETH"
    return f"{amount} {unit}".strip()


def render_report(result: dict[str, Any]) -> str:
    chain_name = "Bitcoin" if result.get("chain") == "btc" else "Ethereum"
    exch = result.get("exchange") or {}
    lines = [
        "NEAREST EXCHANGE — INVESTIGATOR REPORT",
        "======================================",
        f"Generated (UTC): {result.get('traced_at') or datetime.now(timezone.utc).isoformat()}",
        "Tool: NearestExchange (SIH26183 core tracer)",
        "Scope: native BTC/ETH, max 3 hops, largest-outflow heuristic",
        "",
        "SUBJECT",
        "-------",
        f"Wallet:  {result.get('address')}",
        f"Chain:   {chain_name} ({result.get('chain')})",
        "",
        "RESULT",
        "------",
    ]
    if result.get("found") and exch:
        lines.extend(
            [
                f"Nearest VASP:      {exch.get('exchange')}",
                f"Matched address:   {exch.get('address')}",
                f"Hops to VASP:      {result.get('hops')}",
                f"Risk:              {str(result.get('risk') or '').upper()}",
                f"Label confidence:  {exch.get('confidence')}",
                f"Label source:      {exch.get('source')}",
                f"Source URL:        {exch.get('source_url')}",
                f"Label:             {exch.get('label') or '—'}",
            ]
        )
    else:
        lines.extend(
            [
                "Nearest VASP:      NOT FOUND",
                f"Hops traced:       {result.get('hops_traced', 0)}",
                "Risk:              LOW / UNKNOWN",
                f"Note:              {result.get('note')}",
            ]
        )

    lines.extend(["", "PATH", "----"])
    for step in result.get("path") or []:
        hop = step.get("hop")
        tag = ""
        if step.get("is_exchange"):
            tag = f"  [EXCHANGE: {step.get('exchange')}]"
        if hop == 0:
            lines.append(f"Hop 0  SUBJECT     {step.get('to')}{tag}")
            if step.get("role_label"):
                lines.append(f"         role:   {step.get('role_label')}")
        else:
            lines.append(
                f"Hop {hop}  {step.get('from')}  →  {step.get('to')}{tag}"
            )
            lines.append(
                f"         amount: {format_amount(step.get('amount'), step.get('unit'))}"
            )
            lines.append(f"         txid:   {step.get('txid') or '—'}")
            lines.append(f"         time:   {step.get('time') or '—'}")
            if step.get("role_label"):
                lines.append(f"         role:   {step.get('role_label')}")

    lines.extend(
        [
            "",
            "RISK INTERPRETATION",
            "-------------------",
            "HIGH     — queried wallet is a VASP, or funds moved in 1 hop to a labeled exchange.",
            "MEDIUM   — labeled exchange reached in 2–3 hops (layering likely).",
            "LOW      — no labeled exchange within 3 hops. Do not invent a destination.",
            "",
            "RECOMMENDATION",
            "--------------",
            result.get("recommendation") or "",
            "",
            "ATTRIBUTION (SIH26183)",
            "----------------------",
        ]
    )
    attr = result.get("attribution") or {}
    if attr:
        alert = attr.get("alert") or {}
        lines.extend(
            [
                f"Complaint ID:      {attr.get('complaint_id') or '—'}",
                f"Crime type:        {attr.get('crime_label') or '—'}",
                f"Pattern:           {attr.get('pattern_label') or '—'}",
                f"Pattern meaning:   {attr.get('pattern_meaning') or '—'}",
                f"Alert:             {alert.get('label') or '—'}",
                f"Advisory:          {attr.get('crime_advisory') or '—'}",
                f"Intermediaries:    {', '.join(attr.get('intermediaries') or []) or 'none'}",
                f"Method:            {attr.get('method') or '—'}",
            ]
        )
    else:
        lines.append("(no attribution packet)")
    lines.extend(
        [
            "",
            "BINANCE / VASP DESK",
            "-------------------",
        ]
    )
    desk = result.get("binance") or {}
    if desk:
        lines.extend(
            [
                f"Action:            {desk.get('action')}",
                f"Lands at Binance:  {desk.get('lands_at_binance')}",
                f"Urgency:           {desk.get('urgency')}",
                f"Scenario:          {desk.get('scenario_label') or desk.get('scenario')}",
                f"Title:             {desk.get('title')}",
            ]
        )
        for i, step in enumerate(desk.get("steps") or [], 1):
            lines.append(f"  {i}. {step}")
    else:
        lines.append("(no desk packet)")
    lines.extend(
        [
            "",
            "LIMITATIONS",
            "-----------",
            "This prototype follows only the largest native outflow per hop, on BTC or",
            "ETH, to a depth of 3. It does not trace cross-chain bridges, mixers,",
            "CoinJoin, or token (USDT/USDC) transfers. A NOT FOUND result is not a",
            "conclusion that funds are unrecoverable.",
            "",
            "DISCLAIMER",
            "----------",
            "Exchange labels are compiled from public sources (proof-of-reserves",
            "disclosures, community-maintained lists, explorer name tags) and may be",
            "incomplete or outdated. Verify the matched address on a block explorer",
            "before filing legal process. Not a substitute for a licensed chain-analysis",
            "product or a formal forensic report.",
            "",
        ]
    )
    return "\n".join(lines)
