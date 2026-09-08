"""SIH26183 / I4C attribution overlay.

Maps a hop-trace onto the problem-statement variables: crime typology,
wallet role (non-custodial / intermediary / labeled VASP), fund-movement
pattern, investigator alert, and an honest coverage matrix.

No mixers, bridges, or NCRP live calls. Pattern recognition is rule-based
(hop heuristic), not a trained model.
"""

from __future__ import annotations

from typing import Any

CRIME_TYPES = {
    "investment": {
        "label": "Investment scam",
        "advisory": (
            "Typical collection wallet for fake trading/ROI schemes. "
            "Speed of VASP freeze matters — victims keep sending."
        ),
    },
    "task": {
        "label": "Task-based fraud",
        "advisory": (
            "Task/app-job scams often use a burner that forwards once to an exchange. "
            "A 1-hop hit is a freeze candidate."
        ),
    },
    "sextortion": {
        "label": "Sextortion",
        "advisory": (
            "Payment wallets are usually short-lived. Preserve the first VASP hit "
            "and the complaint chat as a package."
        ),
    },
    "ransomware": {
        "label": "Ransomware",
        "advisory": (
            "Ransom wallets may hop through intermediaries. A labeled VASP on the "
            "path is still the compelable entity — do not wait for a mixer analysis this tool does not do."
        ),
    },
    "phishing": {
        "label": "Phishing",
        "advisory": (
            "Drainer/phishing proceeds often land at an exchange quickly. "
            "Treat hop 1 as a preservation request."
        ),
    },
    "darknet": {
        "label": "Darknet transaction",
        "advisory": (
            "Darknet cash-out still needs a VASP off-ramp. This tracer only follows "
            "native BTC/ETH — it will miss CoinJoin and mixers."
        ),
    },
    "organized": {
        "label": "Organized cyber-enabled crime",
        "advisory": (
            "Expect layering (2–3 hops). Match the last labeled VASP and keep "
            "intermediaries in the case file for cluster work."
        ),
    },
    "p2p": {
        "label": "P2P / off-platform",
        "advisory": (
            "Victim may have used an exchange P2P channel then sent off-platform. "
            "If the path returns to a labeled VASP, that VASP can still freeze."
        ),
    },
    "unspecified": {
        "label": "Unspecified cyber fraud",
        "advisory": "Apply the hop result as-is. Do not infer a crime type from the chain path.",
    },
}

PATTERNS = {
    "labeled_vasp": {
        "label": "Reported wallet is a labeled VASP",
        "meaning": "Custodial / exchange address — preservation letter goes here, now.",
    },
    "direct_deposit": {
        "label": "Direct deposit to a VASP",
        "meaning": "Non-custodial or burner collection wallet sent its largest outflow straight to a labeled exchange.",
    },
    "layering": {
        "label": "Intermediary layering then VASP",
        "meaning": "Unlabeled hop(s) sit between the reported wallet and the exchange — classic layering, still compelable at the last hop.",
    },
    "no_outgoing": {
        "label": "No native outflow",
        "meaning": "Burner holding, unused address, or funds already moved as tokens/other chain — this tracer cannot see that.",
    },
    "unlabeled_path": {
        "label": "No labeled VASP in 3 hops",
        "meaning": "Not a finding of untraceable. Manual explorer review, tokens, and other chains remain open.",
    },
}

# Problem-statement coverage. in = shipped, partial = heuristic/stub, out = refused.
COVERAGE = [
    {
        "need": "Ingest victim-reported wallet from a complaint",
        "status": "in",
        "how": "POST /api/complaint with optional NCRP-style complaint ID.",
    },
    {
        "need": "Automatic blockchain tracing",
        "status": "in",
        "how": "Largest native outflow, BTC + ETH, max 3 hops, live explorers.",
    },
    {
        "need": "Identify nearest exchange / VASP (direct deposits)",
        "status": "in",
        "how": "Match against 100 labeled VASP addresses with public sources.",
    },
    {
        "need": "Detect intermediary / layering wallets",
        "status": "in",
        "how": "Unlabeled hops 1–2 on the path are tagged intermediary.",
    },
    {
        "need": "Fund-flow visualization",
        "status": "in",
        "how": "Hop graph + investigator report with txids.",
    },
    {
        "need": "Risk categorization",
        "status": "in",
        "how": "High ≤1 hop, Medium 2–3, Low if not found. Rule-based, not ML.",
    },
    {
        "need": "Automated investigative recommendations",
        "status": "in",
        "how": "Freeze / refer / keep-investigating packet plus LEA advisory.",
    },
    {
        "need": "Standardized investigation report",
        "status": "in",
        "how": "POST /api/report — text file with path, VASP, sources, desk packet.",
    },
    {
        "need": "API for LEA systems",
        "status": "in",
        "how": "JSON APIs: /api/trace, /api/complaint, /api/p2p/case, /embed.js.",
    },
    {
        "need": "Coordination with VASPs (freeze / KYC)",
        "status": "in",
        "how": "Named VASP + freeze/refer packet. Binance desk as the first VASP module.",
    },
    {
        "need": "Fraud typology recognition",
        "status": "partial",
        "how": "Investigator selects crime type; hop pattern is classified. No trained model.",
    },
    {
        "need": "Exchange-wallet clustering",
        "status": "partial",
        "how": "Public labels / PoR, not deposit-address clustering. Binance UID map stays with the VASP.",
    },
    {
        "need": "LEA analytics dashboard",
        "status": "partial",
        "how": "In-session case register with risk counts. No long-term case DB.",
    },
    {
        "need": "NCRP / SAHYOG live integration",
        "status": "partial",
        "how": "Complaint ID field + JSON shape. No live NCRP/SAHYOG credentials in this prototype.",
    },
    {
        "need": "Multiple blockchain ecosystems",
        "status": "partial",
        "how": "Bitcoin and Ethereum only. Tron/BSC/Polygon are not traced.",
    },
    {
        "need": "Cross-chain / bridges / DeFi",
        "status": "out",
        "how": "Out of scope. A miss is returned instead of a guessed destination.",
    },
    {
        "need": "Mixers / tumblers / CoinJoin / privacy coins",
        "status": "out",
        "how": "Out of scope. The report states this limitation.",
    },
    {
        "need": "AI/ML risk model",
        "status": "out",
        "how": "Deliberately rule-based so an investigator can recap the logic.",
    },
    {
        "need": "Scalable self-hosted blockchain indexer",
        "status": "out",
        "how": "Uses Blockstream + Blockscout. Swap-in for an agency indexer later.",
    },
]


def pattern_for(result: dict[str, Any]) -> str:
    if result.get("queried_is_exchange"):
        return "labeled_vasp"
    note = result.get("note") or ""
    if "No outgoing" in note:
        return "no_outgoing"
    if result.get("found") and result.get("hops") == 1:
        return "direct_deposit"
    if result.get("found") and result.get("hops") in (2, 3):
        return "layering"
    return "unlabeled_path"


def role_for_step(step: dict[str, Any], result: dict[str, Any]) -> str:
    if step.get("is_exchange"):
        return "labeled_vasp"
    if step.get("hop") == 0:
        if "No outgoing" in (result.get("note") or ""):
            return "burner_or_holding"
        return "reported_noncustodial"
    return "intermediary"


ROLE_LABELS = {
    "labeled_vasp": "Labeled VASP (custodial)",
    "reported_noncustodial": "Reported wallet (non-custodial / unknown)",
    "burner_or_holding": "Burner or holding (no native outflow)",
    "intermediary": "Intermediary / layering wallet",
}


def alert_for(result: dict[str, Any]) -> dict[str, str]:
    if result.get("found") and result.get("risk") == "high":
        return {
            "code": "preservation",
            "label": "Preservation alert",
            "text": "Nearest VASP is compelable now. Send a freeze / KYC request with the matched address and txids.",
        }
    if result.get("found"):
        return {
            "code": "coordination",
            "label": "VASP coordination",
            "text": "Layered path still ends at a labeled VASP. Coordinate freeze on the last hop; keep intermediaries in the file.",
        }
    return {
        "code": "manual_review",
        "label": "Manual review",
        "text": "No labeled VASP in 3 hops. Do not guess. Check tokens, other chains, and the explorer by hand.",
    }


def attach_attribution(
    result: dict[str, Any],
    *,
    crime_type: str | None = None,
    complaint_id: str | None = None,
) -> dict[str, Any]:
    key = (crime_type or "unspecified").strip().lower()
    if key not in CRIME_TYPES:
        key = "unspecified"
    crime = CRIME_TYPES[key]
    pat = pattern_for(result)
    meta = PATTERNS[pat]
    alert = alert_for(result)

    for step in result.get("path") or []:
        role = role_for_step(step, result)
        step["role"] = role
        step["role_label"] = ROLE_LABELS[role]

    intermediaries = [
        s["to"] for s in (result.get("path") or []) if s.get("role") == "intermediary"
    ]
    result["attribution"] = {
        "crime_type": key,
        "crime_label": crime["label"],
        "crime_advisory": crime["advisory"],
        "complaint_id": (complaint_id or "").strip() or None,
        "pattern": pat,
        "pattern_label": meta["label"],
        "pattern_meaning": meta["meaning"],
        "alert": alert,
        "intermediaries": intermediaries,
        "method": "largest-native-outflow, 3 hops, labeled VASP match — not ML, not clustering",
    }
    return result
