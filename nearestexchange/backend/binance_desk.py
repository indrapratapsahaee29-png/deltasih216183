"""Binance P2P / compliance desk overlay.

This does not call Binance internals. It turns a trace into an action packet
a Binance CS, compliance, or P2P-dispute agent can execute: freeze internally,
refer another VASP, or keep investigating.
"""

from __future__ import annotations

from typing import Any

SCENARIOS = {
    "off_platform": {
        "label": "Off-platform wallet after P2P",
        "blurb": (
            "Victim completed (or was told to complete) a Binance P2P trade, then "
            "sent extra crypto to an external wallet. Trace whether those coins "
            "bounced back into a Binance UID or left for another VASP."
        ),
    },
    "inbound_laundering": {
        "label": "Inbound to Binance",
        "blurb": (
            "Reported scam proceeds may be depositing into Binance. If the last "
            "hop is a Binance hot/deposit wallet, cluster it to a UID and freeze."
        ),
    },
    "fake_merchant": {
        "label": "Fake P2P merchant",
        "blurb": (
            "Ad or chat claimed to be Binance P2P, but the wallet is external. "
            "If it is not a labeled Binance address, do not treat it as escrow."
        ),
    },
    "withdrawal_to_scam": {
        "label": "Withdrawal to reported wallet",
        "blurb": (
            "User already withdrew from Binance to this address. Trace the "
            "onward path to the nearest VASP for a freeze or outbound referral."
        ),
    },
    "unknown": {
        "label": "Unspecified P2P case",
        "blurb": "Generic victim-reported wallet. Apply the hop result as-is.",
    },
}


def _is_binance(result: dict[str, Any]) -> bool:
    name = ((result.get("exchange") or {}).get("exchange") or "").strip().lower()
    return name == "binance"


def binance_desk(result: dict[str, Any], scenario: str | None = None) -> dict[str, Any]:
    """Return a Binance-action packet. Mutates nothing; caller may merge."""
    key = (scenario or "unknown").strip().lower()
    if key not in SCENARIOS:
        key = "unknown"
    scene = SCENARIOS[key]
    hops = result.get("hops")
    found = bool(result.get("found"))
    lands = found and _is_binance(result)
    other = ((result.get("exchange") or {}).get("exchange") if found else None)

    if lands:
        action = "freeze_internal"
        title = "Actionable on Binance — freeze path"
        if hops == 0:
            urgency = "immediate"
            steps = [
                "This address is itself a labeled Binance hot/deposit wallet.",
                "Do not treat it as a customer P2P escrow address until clustering confirms the UID.",
                "Run internal deposit clustering on this address + txids from the path.",
                "Place a withdrawal hold on the mapped UID and related P2P ads.",
                "Preserve KYC, device, and P2P chat logs for the dispute file.",
            ]
        elif hops == 1:
            urgency = "immediate"
            steps = [
                "Largest outflow went directly into a labeled Binance wallet (1 hop).",
                "Map the last-hop address to the depositing UID (internal clustering / deposit memo).",
                "Freeze that UID: withdrawals, P2P release, and remaining spot balance.",
                "Attach the txid from hop 1 to the P2P dispute / SAR draft.",
                "Notify the victim channel that Binance is the compelable entity — no outbound referral needed.",
            ]
        else:
            urgency = "same_day"
            steps = [
                f"Funds reached Binance in {hops} hops (layering). Still actionable internally.",
                "Cluster the last hop as a Binance deposit; hop-1/2 wallets are likely pass-throughs.",
                "Freeze the receiving UID and sibling accounts sharing device/KYC.",
                "Keep the full path in the case file — intermediaries may be reused across P2P scams.",
            ]
    elif found and other:
        action = "refer_vasp"
        title = f"Not Binance — refer {other}"
        urgency = "same_day"
        steps = [
            f"Nearest labeled VASP is {other}, not Binance. Binance cannot freeze these coins.",
            "Do not tell the user Binance will recover funds on-chain.",
            f"Package the investigator report + txids and send a VASP-to-VASP request to {other}.",
            "If the user still has a Binance UID involved (P2P chat, prior withdrawal), freeze that UID pending the referral.",
            "File the outbound SAR / law-enforcement packet with the hop path attached.",
        ]
    else:
        action = "no_vasp"
        title = "No labeled VASP within 3 hops"
        urgency = "investigate"
        steps = [
            "Do not guess a destination. A miss is not 'untraceable'.",
            "Check token (USDT/USDC) flows and whether the user sent from a Binance withdrawal.",
            "If this was a fake-P2P ad, treat the wallet as external — never as Binance escrow.",
            "Keep the case open; a later hop or a new label may land it at Binance.",
        ]

    packet = {
        "lands_at_binance": lands,
        "action": action,
        "title": title,
        "urgency": urgency,
        "scenario": key,
        "scenario_label": scene["label"],
        "scenario_blurb": scene["blurb"],
        "steps": steps,
        "sellable_to": "Binance P2P dispute, CS, and compliance (embed or extension)",
        "integration": {
            "rest": "POST /api/p2p/case",
            "trace": "POST /api/trace",
            "embed": "GET /embed.js",
            "extension": "GET /extension.zip",
        },
    }
    return packet


def attach_binance_desk(result: dict[str, Any], scenario: str | None = None) -> dict[str, Any]:
    result["binance"] = binance_desk(result, scenario)
    return result
