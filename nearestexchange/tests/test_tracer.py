"""Unit tests for hop logic, risk scoring, and address validation.

HTTP is mocked — these tests never touch Blockstream or Blockscout.
"""

from __future__ import annotations

import pytest

from exchanges import lookup, validate_address
from tracer import recommendation_for, render_report, risk_for_hops, trace_wallet


def _out(to: str, amount: float, txid: str = "tx", unit: str = "ETH") -> dict:
    return {
        "to": to,
        "amount": amount,
        "amount_raw": int(amount * 1e18) if unit == "ETH" else int(amount * 1e8),
        "unit": unit,
        "txid": txid,
        "time": "2026-01-01T00:00:00+00:00",
    }


# A labeled Binance ETH wallet from the real dataset (Binance 14 / PoR).
BINANCE_ETH = "0x28c6c06298d514db089934071355e5743bf21d60"
# Unlabeled placeholders used only inside mocked graphs.
A = "0x1111111111111111111111111111111111111111"
B = "0x2222222222222222222222222222222222222222"
C = "0x3333333333333333333333333333333333333333"
D = "0x4444444444444444444444444444444444444444"


class TestAddressValidation:
    def test_eth_ok(self):
        assert (
            validate_address("0x28C6c06298d514Db089934071355E5743bf21d60", "eth")
            == BINANCE_ETH
        )

    def test_eth_rejects_short(self):
        with pytest.raises(ValueError, match="Ethereum"):
            validate_address("0xabc", "eth")

    def test_eth_rejects_empty(self):
        with pytest.raises(ValueError, match="required"):
            validate_address("   ", "eth")

    def test_btc_legacy(self):
        addr = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
        assert validate_address(addr, "btc") == addr

    def test_btc_bech32_lowercased(self):
        addr = "bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97"
        assert validate_address(addr.upper(), "btc") == addr

    def test_btc_rejects_garbage(self):
        with pytest.raises(ValueError, match="Bitcoin"):
            validate_address("not-an-address", "btc")

    def test_unsupported_chain(self):
        with pytest.raises(ValueError, match="Unsupported"):
            validate_address("0x28C6c06298d514Db089934071355E5743bf21d60", "sol")


class TestRiskScoring:
    def test_high_direct(self):
        assert risk_for_hops(True, 1) == "high"

    def test_high_self(self):
        assert risk_for_hops(True, 0) == "high"

    def test_medium_two(self):
        assert risk_for_hops(True, 2) == "medium"

    def test_medium_three(self):
        assert risk_for_hops(True, 3) == "medium"

    def test_low_not_found(self):
        assert risk_for_hops(False, None) == "low"


class TestTraceLogic:
    def test_direct_hop_match(self):
        graph = {A: [_out(BINANCE_ETH, 1.5, "tx-direct")]}

        def fetch(addr, chain):
            return graph.get(addr, [])

        result = trace_wallet(A, "eth", fetch_outgoing=fetch, hop_delay=0, sleeper=lambda s: None)
        assert result["found"] is True
        assert result["hops"] == 1
        assert result["risk"] == "high"
        assert result["exchange"]["exchange"] == "Binance"
        assert result["path"][-1]["txid"] == "tx-direct"
        assert "Binance" in result["recommendation"]

    def test_multi_hop_match(self):
        graph = {
            A: [_out(B, 4.0, "tx1"), _out(D, 0.1, "dust")],
            B: [_out(C, 3.5, "tx2")],
            C: [_out(BINANCE_ETH, 3.2, "tx3")],
        }

        def fetch(addr, chain):
            return graph.get(addr, [])

        result = trace_wallet(A, "eth", fetch_outgoing=fetch, hop_delay=0, sleeper=lambda s: None)
        assert result["found"] is True
        assert result["hops"] == 3
        assert result["risk"] == "medium"
        assert [s["to"] for s in result["path"] if s["hop"] > 0] == [
            B,
            C,
            BINANCE_ETH,
        ]

    def test_follows_largest_outflow_not_dust(self):
        # Dust to Binance, bulk to unlabeled — spec says follow largest.
        graph = {A: [_out(BINANCE_ETH, 0.01, "dust"), _out(B, 9.0, "bulk")]}

        def fetch(addr, chain):
            return graph.get(addr, [])

        result = trace_wallet(A, "eth", fetch_outgoing=fetch, hop_delay=0, sleeper=lambda s: None)
        assert result["path"][1]["to"] == B
        assert result["found"] is False

    def test_no_match_within_depth(self):
        graph = {
            A: [_out(B, 1.0, "t1")],
            B: [_out(C, 0.9, "t2")],
            C: [_out(D, 0.8, "t3")],
        }

        def fetch(addr, chain):
            return graph.get(addr, [])

        result = trace_wallet(A, "eth", fetch_outgoing=fetch, hop_delay=0, sleeper=lambda s: None)
        assert result["found"] is False
        assert result["risk"] == "low"
        assert result["hops"] is None
        assert result["hops_traced"] == 3
        assert result["exchange"] is None
        assert "NOT" in render_report(result) or "not found" in render_report(result).lower()

    def test_address_with_no_transactions(self):
        def fetch(addr, chain):
            return []

        result = trace_wallet(A, "eth", fetch_outgoing=fetch, hop_delay=0, sleeper=lambda s: None)
        assert result["found"] is False
        assert result["hops_traced"] == 0
        assert "No outgoing" in result["note"]

    def test_malformed_address_raises(self):
        with pytest.raises(ValueError):
            trace_wallet("zzz", "eth", fetch_outgoing=lambda a, c: [], hop_delay=0)

    def test_invalid_chain_raises(self):
        with pytest.raises(ValueError, match="Chain"):
            trace_wallet(A, "solana", fetch_outgoing=lambda a, c: [], hop_delay=0)

    def test_queried_wallet_is_itself_exchange(self):
        result = trace_wallet(
            BINANCE_ETH,
            "eth",
            fetch_outgoing=lambda a, c: [_out(A, 1.0)],
            hop_delay=0,
            sleeper=lambda s: None,
        )
        assert result["found"] is True
        assert result["queried_is_exchange"] is True
        assert result["hops"] == 0
        assert result["risk"] == "high"
        # Must not follow outgoing hops once the subject is a VASP.
        assert len(result["path"]) == 1

    def test_stops_at_first_match_before_max_hops(self):
        graph = {
            A: [_out(B, 2.0, "t1")],
            B: [_out(BINANCE_ETH, 1.5, "t2")],
            BINANCE_ETH: [_out(C, 1.0, "should-not-run")],
        }
        calls = []

        def fetch(addr, chain):
            calls.append(addr)
            return graph.get(addr, [])

        result = trace_wallet(A, "eth", fetch_outgoing=fetch, hop_delay=0, sleeper=lambda s: None)
        assert result["hops"] == 2
        assert BINANCE_ETH not in calls


class TestDataset:
    def test_binance_eth_labeled(self):
        hit = lookup(BINANCE_ETH, "eth")
        assert hit is not None
        assert hit["exchange"] == "Binance"
        assert hit["source_url"]

    def test_unknown_not_labeled(self):
        assert lookup(A, "eth") is None


class TestReport:
    def test_report_contains_core_fields(self):
        graph = {A: [_out(BINANCE_ETH, 1.0, "abc")]}
        result = trace_wallet(
            A, "eth", fetch_outgoing=lambda a, c: graph.get(a, []), hop_delay=0, sleeper=lambda s: None
        )
        text = render_report(result)
        assert "INVESTIGATOR REPORT" in text
        assert BINANCE_ETH in text
        assert "Binance" in text
        assert "HIGH" in text
        assert recommendation_for(result)


COINBASE_ETH = "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43"


class TestBinanceDesk:
    def test_direct_to_binance_is_internal_freeze(self):
        graph = {A: [_out(BINANCE_ETH, 1.0, "abc")]}
        result = trace_wallet(
            A, "eth", fetch_outgoing=lambda a, c: graph.get(a, []), hop_delay=0, sleeper=lambda s: None
        )
        desk = result["binance"]
        assert desk["lands_at_binance"] is True
        assert desk["action"] == "freeze_internal"
        assert desk["urgency"] == "immediate"
        assert "BINANCE / VASP DESK" in render_report(result)

    def test_two_hop_binance_is_same_day_freeze(self):
        graph = {A: [_out(B, 2.0)], B: [_out(BINANCE_ETH, 1.5)]}
        result = trace_wallet(
            A, "eth", fetch_outgoing=lambda a, c: graph.get(a, []), hop_delay=0, sleeper=lambda s: None
        )
        assert result["hops"] == 2
        assert result["binance"]["action"] == "freeze_internal"
        assert result["binance"]["urgency"] == "same_day"

    def test_other_vasp_is_referral(self):
        graph = {A: [_out(COINBASE_ETH, 1.0)]}
        result = trace_wallet(
            A, "eth", fetch_outgoing=lambda a, c: graph.get(a, []), hop_delay=0, sleeper=lambda s: None
        )
        desk = result["binance"]
        assert desk["lands_at_binance"] is False
        assert desk["action"] == "refer_vasp"
        assert "Coinbase" in desk["title"]

    def test_not_found_is_no_vasp(self):
        result = trace_wallet(
            A, "eth", fetch_outgoing=lambda a, c: [], hop_delay=0, sleeper=lambda s: None
        )
        assert result["binance"]["action"] == "no_vasp"
        assert result["binance"]["lands_at_binance"] is False


class TestAttribution:
    def test_direct_deposit_roles(self):
        graph = {A: [_out(BINANCE_ETH, 1.0, "abc")]}
        result = trace_wallet(
            A, "eth", fetch_outgoing=lambda a, c: graph.get(a, []), hop_delay=0, sleeper=lambda s: None
        )
        attr = result["attribution"]
        assert attr["pattern"] == "direct_deposit"
        assert result["path"][0]["role"] == "reported_noncustodial"
        assert result["path"][1]["role"] == "labeled_vasp"
        assert attr["alert"]["code"] == "preservation"
        assert "ATTRIBUTION" in render_report(result)

    def test_layering_marks_intermediary(self):
        graph = {A: [_out(B, 2.0)], B: [_out(BINANCE_ETH, 1.5)]}
        result = trace_wallet(
            A, "eth", fetch_outgoing=lambda a, c: graph.get(a, []), hop_delay=0, sleeper=lambda s: None
        )
        assert result["attribution"]["pattern"] == "layering"
        assert B in result["attribution"]["intermediaries"]
        assert result["path"][1]["role"] == "intermediary"
        assert result["attribution"]["alert"]["code"] == "coordination"

    def test_no_outgoing_is_burner(self):
        result = trace_wallet(
            A, "eth", fetch_outgoing=lambda a, c: [], hop_delay=0, sleeper=lambda s: None
        )
        assert result["attribution"]["pattern"] == "no_outgoing"
        assert result["path"][0]["role"] == "burner_or_holding"
        assert result["attribution"]["alert"]["code"] == "manual_review"

