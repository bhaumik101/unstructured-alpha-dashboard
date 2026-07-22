"""Regression tests for the live PDF export workflow."""

import ast
from pathlib import Path

import numpy as np


EXPORT = Path(__file__).resolve().parents[1] / "pages" / "28_Export.py"


def _export_functions():
    source = EXPORT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {"_fmt_shares", "_pdf_safe_text", "build_pdf"}
    nodes = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted
    ]
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "np": np,
        "STATUS_RGB": {
            "bullish": (0, 120, 60), "bearish": (180, 30, 30),
            "neutral": (80, 90, 140), "insufficient_data": (130, 130, 130),
        },
        "STATUS_LABEL": {
            "bullish": "BULLISH", "bearish": "BEARISH",
            "neutral": "NEUTRAL", "insufficient_data": "NO DATA",
        },
        "count_unavailable_signals": lambda signals: (0, len(signals)),
    }
    exec(compile(module, str(EXPORT), "exec"), namespace)
    return namespace


def test_pdf_accepts_unicode_provider_names():
    functions = _export_functions()
    pdf = functions["build_pdf"](
        ticker="TEST",
        company_name="D’Angelo — Holdings",
        score=67,
        score_status="bullish",
        all_signals={
            "demand": {
                "config": {"name": "S&P 500 → Demand", "category": "macro", "pcs": 6},
                "score": 70,
                "status": "bullish",
            }
        },
        price_metrics={},
        generated_at="2026-07-22 12:00 UTC",
        insider_tx=[{"insider_name": "O’Neil", "title": "Chief—Officer", "shares": 10}],
        thirteenf_fund_rows=[{"fund_name": "Müller → Capital", "shares": 20}],
    )
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1_000


def test_export_keeps_generated_bytes_for_download_rerun():
    source = EXPORT.read_text(encoding="utf-8")
    assert 'st.session_state["pdf_payload"]' in source
    assert '_pdf_payload.get("ticker") == ticker_input' in source
    assert 'st.session_state["export_ticker_input"] = _requested_export_ticker' in source


def test_export_normalizes_canonical_score_cases():
    source = EXPORT.read_text(encoding="utf-8")
    assert '"bull": "bullish"' in source
    assert '"bear": "bearish"' in source
