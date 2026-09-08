"""Known VASP / exchange deposit and hot-wallet lookup.

Every record in data/exchanges.json was compiled from a public source
(see the `source` and `source_url` fields). Addresses that could not be
tied to a real source are not included.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parent / "data" / "exchanges.json"

_ETH_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
# Base58 legacy (1... / 3...) and Bech32 (bc1...).
_BTC_RE = re.compile(r"^(bc1[a-z0-9]{25,87}|[13][a-km-zA-HJ-NP-Z1-9]{25,39})$")


def normalize_address(address: str, chain: str) -> str:
    addr = (address or "").strip()
    if chain == "eth":
        return addr.lower()
    if chain == "btc":
        if addr.lower().startswith("bc1"):
            return addr.lower()
        return addr
    return addr


def validate_address(address: str, chain: str) -> str:
    addr = (address or "").strip()
    if not addr:
        raise ValueError("Address is required.")
    if chain == "eth":
        if not _ETH_RE.match(addr):
            raise ValueError("Not a valid Ethereum address (expected 0x + 40 hex).")
        return addr.lower()
    if chain == "btc":
        candidate = addr.lower() if addr.lower().startswith("bc1") else addr
        if not _BTC_RE.match(candidate):
            raise ValueError(
                "Not a valid Bitcoin address (expected 1..., 3..., or bc1...)."
            )
        return candidate
    raise ValueError("Unsupported chain.")


@lru_cache(maxsize=1)
def _load_records() -> tuple[dict[str, Any], ...]:
    with DATA_PATH.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return tuple(raw)


@lru_cache(maxsize=1)
def _index() -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for rec in _load_records():
        chain = rec["chain"]
        key = (chain, normalize_address(rec["address"], chain))
        out[key] = rec
    return out


def lookup(address: str, chain: str) -> dict[str, Any] | None:
    try:
        normalized = validate_address(address, chain)
    except ValueError:
        normalized = normalize_address(address, chain)
    return _index().get((chain, normalized))


def dataset_stats() -> dict[str, Any]:
    recs = _load_records()
    by_chain: dict[str, int] = {}
    by_exchange: dict[str, int] = {}
    by_confidence: dict[str, int] = {}
    for rec in recs:
        by_chain[rec["chain"]] = by_chain.get(rec["chain"], 0) + 1
        by_exchange[rec["exchange"]] = by_exchange.get(rec["exchange"], 0) + 1
        by_confidence[rec["confidence"]] = by_confidence.get(rec["confidence"], 0) + 1
    return {
        "total": len(recs),
        "by_chain": by_chain,
        "by_confidence": by_confidence,
        "exchanges": sorted(by_exchange.keys()),
        "exchange_count": len(by_exchange),
    }
