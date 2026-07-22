"""Regression coverage for watchlist intelligence emails and live-data integrity."""

import pandas as pd


class _FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None


def test_signal_pulse_excludes_unavailable_sources(monkeypatch):
    from cron import send_digest
    from utils import analysis, fetchers

    monkeypatch.setattr(
        send_digest,
        "SIGNALS",
        {
            "live_bull": {"name": "Live Bull", "inverse": False},
            "live_neutral": {"name": "Live Neutral", "inverse": False},
            "missing": {"name": "Missing", "inverse": False},
        },
    )

    def _fetch(cfg, _start, _end):
        if cfg["name"] == "Missing":
            return pd.Series(dtype=float)
        return pd.Series([1.0, 2.0, 3.0])

    def _score(series, inverse=False):
        if series.iloc[-1] == 3.0 and not inverse:
            # Return two distinct statuses across the two live configs.
            name = getattr(series, "name", None)
            return {"score": 75 if name != "neutral" else 50,
                    "status": "bullish" if name != "neutral" else "neutral"}
        return {"score": 50, "status": "neutral"}

    calls = iter(("bull", "neutral"))

    def _named_fetch(cfg, start, end):
        series = _fetch(cfg, start, end)
        if not series.empty:
            series.name = next(calls)
        return series

    monkeypatch.setattr(fetchers, "fetch_signal_series", _named_fetch)
    monkeypatch.setattr(analysis, "score_signal", _score)

    scores, bull, bear, neutral, unavailable, bias = send_digest._compute_signal_pulse()

    assert set(scores) == {"live_bull", "live_neutral"}
    assert (bull, bear, neutral, unavailable, bias) == (1, 0, 1, 1, "Bullish")


def test_digest_email_has_coverage_deep_links_tags_and_idempotency(monkeypatch):
    from utils import email

    captured = {}

    def _post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return _FakeResponse()

    monkeypatch.setattr(email, "_get_resend_config", lambda: ("re_test", "UA <mail@example.com>"))
    monkeypatch.setattr(email.requests, "post", _post)

    email.send_digest_email(
        to_email="reader@example.com",
        signal_flips=[],
        score_movers=[],
        overall_bias="Mixed",
        bull_n=2,
        bear_n=1,
        neut_n=1,
        unavailable_n=2,
        watchlist_items=[{
            "ticker": "AAPL",
            "name": "Apple <Research>",
            "score": 61.0,
            "case": "BULL",
            "delta": 2.0,
            "aligned": 4,
            "total_relevant": 6,
        }],
        watchlist_narrative="Evidence < script, not markup.",
    )

    payload = captured["json"]
    assert payload["tags"] == [{"name": "email_type", "value": "morning_digest"}]
    assert captured["headers"]["Idempotency-Key"].startswith("morning-digest/")
    assert "4/6 live sources loaded" in payload["html"]
    assert "2 unavailable excluded" in payload["html"]
    assert "Evidence &lt; script" in payload["html"]
    assert "/ticker-deep-dive?ticker=AAPL" in payload["html"]
    assert "/today-s-brief" in payload["html"]
    assert "unstructuredalpha.com/Watchlist" not in payload["html"]


def test_watchlist_alert_email_escapes_content_and_links_research(monkeypatch):
    from utils import email

    captured = {}

    def _post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return _FakeResponse()

    monkeypatch.setattr(email, "_get_resend_config", lambda: ("re_test", "UA <mail@example.com>"))
    monkeypatch.setattr(email.requests, "post", _post)

    email.send_watchlist_alert_email(
        "reader@example.com",
        [{
            "ticker": "MSFT",
            "alert_type": "price_move",
            "direction": "bullish",
            "message": "Moved > 5% <review>",
        }],
    )

    payload = captured["json"]
    assert payload["subject"] == "1 Watchlist Alert: MSFT"
    assert payload["tags"] == [{"name": "email_type", "value": "watchlist_alert"}]
    assert captured["headers"]["Idempotency-Key"].startswith("watchlist-alert/")
    assert "Moved &gt; 5% &lt;review&gt;" in payload["html"]
    assert "/ticker-deep-dive?ticker=MSFT" in payload["html"]
    assert "/my-watchlist" in payload["html"]
    assert "linear-gradient" not in payload["html"]
