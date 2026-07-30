"""Provider-free ticker ranking and Home latency boundaries."""

from pathlib import Path

from utils.top_tickers import rank_top_tickers


DASHBOARD = Path(__file__).resolve().parents[1]


def test_rank_top_tickers_uses_only_supplied_real_scores(monkeypatch):
    """The pure ranker must never fall through to the live provider cache."""
    from utils import signals_cache

    monkeypatch.setattr(
        signals_cache,
        "get_all_signal_scores",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("provider cache must not be called")
        ),
    )
    scores = {
        "yield_curve": {"score": 82.0, "status": "bullish"},
        "hy_credit_spread": {"score": 74.0, "status": "bullish"},
        "jobless_claims": {"score": 71.0, "status": "bullish"},
        "put_call_ratio": {"score": 25.0, "status": "bearish"},
    }

    result = rank_top_tickers(scores)

    assert result["all"]
    assert all(row["signals"] > 0 for row in result["all"])


def test_rank_top_tickers_excludes_unavailable_and_errored_signals():
    scores = {
        "yield_curve": {"score": 82.0, "status": "bullish"},
        "hy_credit_spread": {
            "score": 50.0,
            "status": "insufficient_data",
            "error": True,
        },
    }

    result = rank_top_tickers(scores)

    assert result["all"]
    assert all(row["signals"] == 1 for row in result["all"])


def test_home_initial_render_has_no_live_signal_provider_sweep():
    source = (DASHBOARD / "pages" / "home_page.py").read_text(encoding="utf-8")

    assert "get_all_signal_scores" not in source
    assert "rank_top_tickers(_snap_rich)" in source
    assert "_score_tickers_from_cache(_pf_input, _snap_rich)" in source
