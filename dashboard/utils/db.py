# utils/db.py
# Unstructured Alpha — Database Engine + Schema
#
# Single source of truth for the SQL backend, built on SQLAlchemy Core
# (not the ORM -- this app's data model is simple enough that explicit
# Table objects + hand-written queries are easier to reason about than an
# ORM's session/identity-map machinery, and easier for a reviewer to audit
# against the actual SQL that runs).
#
# Why SQLAlchemy at all, instead of raw sqlite3/psycopg2: this app needs to
# run against TWO different databases depending on environment --
# Postgres in production (chosen explicitly: Streamlit Community Cloud has
# no persistent disk, so account/watchlist data has to live in a real
# hosted database, not a local file) and SQLite for local development and
# tests (no Postgres server needed to run `streamlit run app.py` or pytest
# on a laptop). Hand-writing raw SQL for both dialects (AUTOINCREMENT vs
# SERIAL, different upsert syntax, etc.) is a real source of bugs that
# would only surface in production against a database I can't directly
# test against here. SQLAlchemy's Core layer abstracts those dialect
# differences so the same Python code runs correctly against either.
#
# Connection string resolution:
#   1. UNSTRUCTURED_ALPHA_DATABASE_URL environment variable -- checked
#      FIRST, deliberately, ahead of everything else. This is what
#      tests/conftest.py sets to a throwaway SQLite file before any test
#      runs. Caught live, not assumed: with secrets checked first, running
#      pytest on a machine that has a real .streamlit/secrets.toml
#      configured (i.e. any developer's actual laptop, not just a sandbox
#      without network access) would silently connect to and write fake
#      test users/alerts into the REAL production Neon database instead of
#      the intended test DB -- the only reason this didn't already happen
#      unnoticed is that it was run somewhere with no network route to
#      Neon, which surfaced it as a connection error instead of silent data
#      pollution. An explicit, narrowly-named override beats anything else
#      configured, so it must win.
#   2. A plain DATABASE_URL environment variable -- the de facto standard
#      name on every host that ISN'T Streamlit Cloud (Render, Railway,
#      Heroku-style platforms all use exactly this). Checked before
#      st.secrets so the same code works unmodified after a hosting
#      migration, not just on Streamlit Cloud.
#   3. st.secrets["DATABASE_URL"] if running under Streamlit Cloud with
#      that secret configured (a Postgres URL from Neon/Supabase, set in
#      Streamlit Cloud's app settings, never committed to the repo).
#      Neither env var above is ever set there, so this remains the real
#      Streamlit Cloud production path.
#   4. A local SQLite file at ~/.unstructured_alpha/data/app.db (the
#      existing local-dev default -- and the same reasoning as before for
#      WHY it lives outside the project folder: a cloud-synced project
#      directory causes real SQLite disk I/O errors, confirmed live).

import os
from datetime import datetime, timezone

import streamlit as st
from sqlalchemy import (
    create_engine, inspect, text, MetaData, Table, Column, Integer, String, Float, Text, Boolean,
    ForeignKey, UniqueConstraint, select, insert, update, delete, func,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

_LOCAL_DB_DIR = os.path.join(os.path.expanduser("~"), ".unstructured_alpha", "data")
_LOCAL_DB_PATH = os.path.join(_LOCAL_DB_DIR, "app.db")


def _resolve_database_url() -> str:
    env_url = os.environ.get("UNSTRUCTURED_ALPHA_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if env_url:
        return env_url

    try:
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass  # st.secrets raises if no secrets.toml exists at all -- fine, fall through

    os.makedirs(_LOCAL_DB_DIR, exist_ok=True)
    return f"sqlite:///{_LOCAL_DB_PATH}"


DATABASE_URL = _resolve_database_url()
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# SQLite: single-file, no pool — just enable multi-thread access.
# PostgreSQL: production-grade pool tuned for a Render free/starter instance.
#   pool_size=5      — keep 5 idle connections ready (PaaS instances spin down
#                      idle workers, so pre-warmed connections survive restarts)
#   max_overflow=10  — allow up to 10 additional connections under burst load
#   pool_recycle=300 — recycle connections every 5 min to avoid stale/timed-out
#                      connections that PaaS NATs typically drop after ~4 min
#   pool_pre_ping    — execute a lightweight SELECT 1 before handing a connection
#                      to the caller, ensuring stale connections fail fast
if IS_SQLITE:
    _engine_kwargs: dict = {"connect_args": {"check_same_thread": False}}
else:
    _engine_kwargs = {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 300,
    }
engine = create_engine(DATABASE_URL, **_engine_kwargs)

metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String(255), nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    # Email verification (added 2026-06-21, after accounts already existed
    # in the running local DB -- see _migrate_users_table() below for why
    # this needs an explicit ALTER TABLE step, not just create_all()).
    Column("email_verified", Boolean, nullable=False, server_default="false"),
    Column("verification_code_hash", Text),
    Column("verification_code_expires_at", String(64)),
    # Morning digest opt-in (added 2026-06-23). False by default — users
    # must explicitly opt in via the Watchlist page settings section. The
    # cron/send_digest.py script queries this column to decide who to email.
    Column("digest_opted_in", Boolean, nullable=False, server_default="false"),
    # Stripe subscription columns (added 2026-06-30). subscription_tier is
    # "free" | "pro" — checked on every gated page via billing.get_user_tier().
    # stripe_customer_id and stripe_subscription_id are stored after a
    # successful Checkout Session so the Customer Portal and re-verification
    # can reference them without an extra Stripe API lookup.
    Column("subscription_tier", String(16), nullable=False, server_default="'free'"),
    Column("stripe_customer_id", String(64)),
    Column("stripe_subscription_id", String(64)),
    # ISO-8601 UTC datetime string of when the Stripe trial ends (populated on
    # checkout success). Used by cron/send_trial_reminder.py to fire the
    # day-6 "trial ends tomorrow" email.
    Column("trial_end_at", String(64)),
    # Discord / Slack / generic webhook URL for push alert delivery (added
    # 2026-07-01). Pro-gated — only shown in the Watchlist settings UI when
    # the user's subscription_tier == "pro". NULL means no webhook configured.
    # Migrated automatically by _migrate_users_table() via the generic TEXT path.
    Column("webhook_url", String(512)),
    # Referral code (added 2026-07-04). Unique 8-char alphanumeric code used to
    # build shareable referral links. Generated lazily on first request via
    # utils/referral.get_or_create_referral_code(). Migrated automatically via
    # the generic TEXT path in _migrate_users_table() below.
    Column("referral_code", String(16), unique=True),
    # Display name (added 2026-07-04). Optional friendly name shown in the profile
    # page and the top-right account widget. NULL = user hasn't set one yet;
    # UI falls back to the email prefix. Migrated via the generic TEXT path.
    Column("display_name", String(64)),
    # Login rate limiting (added 2026-07-04). Tracks consecutive failed password
    # attempts per account. After _MAX_FAILED_LOGINS failures the account is
    # temporarily locked for _LOCKOUT_MINUTES minutes. Both columns are reset to
    # 0/NULL on every successful login so a real user is never permanently locked
    # out — only a sustained brute-force run is affected. Migrated via the
    # INTEGER path in _migrate_users_table() below.
    Column("login_attempt_count", Integer, nullable=False, server_default="0"),
    Column("login_locked_until", String(64)),   # ISO-8601 UTC, NULL = not locked
    # OTP attempt counter. After _MAX_OTP_ATTEMPTS wrong codes the pending code
    # is invalidated and the user must request a fresh one. Reset on success.
    Column("verification_attempt_count", Integer, nullable=False, server_default="0"),
    # Password reset (added 2026-07-04). Same hash+expiry pattern as email
    # verification codes. Both cleared on successful reset.
    Column("password_reset_code_hash", Text),
    Column("password_reset_expires_at", String(64)),
    # Last login timestamp (added 2026-07-05). ISO-8601 UTC string set on every
    # successful login() call in utils/auth.py. Used by cron/send_reengagement.py
    # to identify users who haven't been active in the last N days.
    # NULL = user has never logged in after initial email verification (or column
    # was added after their last login — both treated as inactive by the cron).
    Column("last_login_at", String(64)),
    # Last re-engagement email timestamp (added 2026-07-05). Set after the
    # re-engagement cron sends to this user. Prevents re-sending within 7 days.
    # NULL = user has never received a re-engagement email.
    Column("last_reengagement_at", String(64)),
    # Day-3 onboarding email flag (added 2026-07-05). Set to "true" after
    # cron/send_onboarding_day3.py sends the feature-spotlight email. NULL or ""
    # = not yet sent. Using TEXT rather than Boolean to stay consistent with
    # other flag columns and the generic TEXT migration path.
    Column("day3_email_sent", String(8)),
    # Public shareable watchlist slug (added 2026-07-05). A 12-char random
    # alphanumeric string that identifies a user's read-only public watchlist
    # view at /Share_Watchlist?id=SLUG. Generated lazily on first "Share"
    # button click via utils/share_watchlist.get_or_create_slug(). NULL means
    # the user has never activated sharing. Migrated via the generic TEXT path.
    Column("watchlist_share_slug", String(20), unique=True),
    # Day-7 retention email flag (added 2026-07-05). Set to "true" after
    # cron/send_onboarding_day7.py sends the "unlock more signal power" email.
    # Mirrors the day3_email_sent pattern — TEXT flag, NULL/"" = not yet sent.
    Column("day7_email_sent", String(8)),
    # Risk profile (added 2026-07-17). JSON blob:
    #   {"tolerance":"conservative|balanced|aggressive",
    #    "horizon":"short|medium|long|all",
    #    "emphasis":"macro|balanced|full"}
    # Drives the personalized "Your Score" on Ticker Deep Dive (see
    # utils/risk_profile.py). NULL = user has never set one → defaults apply.
    # Deliberately does NOT affect the canonical Confluence Score. Migrated via
    # the generic TEXT path in _migrate_users_table().
    Column("risk_profile", Text),
    # Focused account setup (added 2026-07-22). Existing accounts are
    # grandfathered as complete by _migrate_users_table(); newly created
    # accounts remain NULL until they finish or explicitly skip setup.
    Column("onboarding_completed_at", String(64)),
    # The user's preferred briefing channel. This is kept separate from
    # digest_opted_in because morning email is Pro-only, while a Free user can
    # still express that preference during setup and activate it on upgrade.
    Column("digest_preference", String(24)),
)

watchlist = Table(
    "watchlist", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("ticker", String(16), nullable=False),
    Column("score_bull_threshold", Float, nullable=False, server_default="65.0"),
    Column("score_bear_threshold", Float, nullable=False, server_default="35.0"),
    Column("price_move_pct_threshold", Float, nullable=False, server_default="5.0"),
    Column("added_at", String(64), nullable=False),
    UniqueConstraint("user_id", "ticker", name="uq_watchlist_user_ticker"),
)

# User-scoped Stock Recommender presets. Only the bounded filter definition is
# stored here — never result frames or provider responses — so reopening a
# screen is instant without turning the database into a second analytics cache.
saved_recommender_screens = Table(
    "saved_recommender_screens", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("name", String(64), nullable=False),
    Column("config_json", Text, nullable=False),
    # Monitoring is opt-in per screen. The first enabled evaluation writes a
    # baseline without notifying; later runs alert only on genuinely new names.
    Column("alerts_enabled", Integer, nullable=False, server_default="0"),
    Column("result_state_json", Text),
    Column("last_checked_at", String(64)),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    UniqueConstraint("user_id", "name", name="uq_recommender_screen_user_name"),
)

# Persistent portfolio workspace. Watchlists answer "what do I monitor?";
# portfolios answer "what do I actually own, and in what proportion?" Keeping
# those concepts separate lets Portfolio Intelligence calculate weighted
# exposure without treating every watched idea as an equal-sized position.
portfolios = Table(
    "portfolios", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("name", String(96), nullable=False, server_default="'My Portfolio'"),
    Column("is_default", Integer, nullable=False, server_default="1"),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    UniqueConstraint("user_id", "name", name="uq_portfolio_user_name"),
)

portfolio_holdings = Table(
    "portfolio_holdings", metadata,
    Column("id", Integer, primary_key=True),
    Column("portfolio_id", Integer, ForeignKey("portfolios.id"), nullable=False),
    Column("ticker", String(16), nullable=False),
    Column("weight_pct", Float, nullable=False),
    Column("shares", Float),
    Column("cost_basis", Float),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    UniqueConstraint("portfolio_id", "ticker", name="uq_portfolio_holding_ticker"),
)

# One cached executive review per user/input fingerprint. The fingerprint is
# built from persisted holdings, score evidence, and risk profile, so repeated
# opens are database reads rather than repeated model calls.
portfolio_reviews = Table(
    "portfolio_reviews", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False, unique=True),
    Column("input_hash", String(64), nullable=False),
    Column("review_json", Text, nullable=False),
    Column("model", String(64), nullable=False),
    Column("input_tokens", Integer),
    Column("output_tokens", Integer),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
)

# One evolving investment thesis per user/security. This is deliberately
# user-scoped: unlike the canonical Confluence Score, thesis language, horizon,
# risk conditions, and outcome notes are private decision-journal data.
investment_theses = Table(
    "investment_theses", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("ticker", String(16), nullable=False),
    Column("stance", String(16), nullable=False),
    Column("status", String(16), nullable=False, server_default="active"),
    Column("horizon_weeks", Integer, nullable=False, server_default="12"),
    Column("entry_price", Float),
    Column("entry_score", Float),
    Column("thesis", Text, nullable=False),
    Column("catalysts", Text),
    Column("risks", Text),
    Column("invalidation", Text),
    Column("outcome_notes", Text),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    UniqueConstraint("user_id", "ticker", name="uq_thesis_user_ticker"),
)

alert_state = Table(
    "alert_state", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("ticker", String(16), nullable=False),
    Column("last_score", Float),
    # Identifies whether last_score was canonical or produced by a specific
    # research profile. A basis change re-establishes the baseline instead of
    # manufacturing a threshold crossing from two different score definitions.
    Column("last_score_basis", String(96)),
    Column("last_price", Float),
    Column("last_52w_high", Float),
    Column("last_52w_low", Float),
    Column("last_insider_status", String(32)),
    Column("last_short_interest_status", String(32)),
    Column("last_13f_status", String(32)),
    Column("last_checked_at", String(64)),
    # Score baseline for the score-moved email cron (added 2026-07-04).
    # Tracks the last confluence score AT THE TIME a score-moved email was sent
    # (or when the ticker was first checked by that cron). Kept separate from
    # last_score (which the hourly threshold-crossing cron refreshes on every
    # run) so the daily score-moved cron can see true multi-day deltas rather
    # than always comparing against a score that was just updated an hour ago.
    # NULL = ticker has never been checked by the score-moved cron yet.
    Column("last_score_emailed", Float),
    # ISO-8601 timestamp of the last velocity-alert email sent for this
    # (user, ticker) pair. Used by send_velocity_alerts cron to avoid
    # re-alerting within MIN_DAYS_BETWEEN_ALERTS days. NULL = never alerted.
    Column("last_velocity_alert_at", String(64)),
    UniqueConstraint("user_id", "ticker", name="uq_alert_state_user_ticker"),
)

alerts = Table(
    "alerts", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("ticker", String(16), nullable=False),
    Column("alert_type", String(32), nullable=False),
    Column("direction", String(16)),
    Column("message", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("is_read", Integer, nullable=False, server_default="0"),
)

# "Remember me" persistent login (added 2026-06-21, per explicit user
# request). Only the SHA-256 HASH of the token lives here -- same
# reasoning as verification_code_hash above: the raw token is the actual
# bearer secret (it lives in the user's browser cookie), so a database
# leak alone must not be enough to forge a session. A brand-new table, so
# plain create_all() is sufficient -- no ALTER TABLE migration needed
# the way users.email_verified needed one.
remember_tokens = Table(
    "remember_tokens", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("created_at", String(64), nullable=False),
    Column("expires_at", String(64), nullable=False),
)


# Historical score snapshots (added 2026-06-22, per the agreed roadmap:
# search bar -> score history -> sector percentile). Deliberately NOT
# user-scoped -- a ticker's Confluence Score at a given moment is the
# same number for every visitor, so one row per (ticker, day) is correct,
# not one per user. Upserted on (ticker, snapshot_date) every time
# anyone views that ticker's Deep Dive page (utils/score_history.py),
# which means history only accumulates for tickers people actually look
# at -- there is no background scheduler in this Streamlit app to sweep
# the whole universe daily, so coverage is organic/traffic-driven by
# design, not a guaranteed daily record for every tracked ticker.
score_snapshots = Table(
    "score_snapshots", metadata,
    Column("id", Integer, primary_key=True),
    Column("ticker", String(16), nullable=False),
    Column("snapshot_date", String(10), nullable=False),  # YYYY-MM-DD, local calendar date of the snapshot
    Column("score", Float, nullable=False),
    Column("case", String(16)),         # "BULL" / "BEAR" / "NEUTRAL"
    Column("conviction", String(32)),
    Column("created_at", String(64), nullable=False),
    # WHICH score this row holds (added 2026-07-18). Two different metrics can
    # legitimately exist for a ticker and they must never be conflated:
    #   "full"            — the Confluence Score shown on Ticker Deep Dive:
    #                       macro (correlation-weighted) + momentum + the four
    #                       optional differentiator signals. Expensive (~sec/ticker,
    #                       4 network calls), so only the core tier gets it.
    #   "macro_momentum"  — macro + momentum only, no differentiator data. This is
    #                       the same blend the Screener labels "Macro + Momentum
    #                       Rank". Cheap enough to precompute across ~5k tickers.
    # They produce DIFFERENT numbers for the same ticker (measured: AAPL 45.6 full
    # vs 56.3 macro-only), so a reader must filter on this column rather than
    # assume. NULL = legacy row, which was always the full score.
    Column("score_kind", String(20)),
    UniqueConstraint("ticker", "snapshot_date", name="uq_score_snapshot_ticker_date"),
)


# Daily signal status snapshots (added 2026-06-23). Parallel to
# score_snapshots but for individual signals rather than per-ticker
# confluence scores. Keyed by (signal_id, snapshot_date). Upserted by
# Today's Brief (pages/2_Today_Digest.py) on each visit — same organic,
# traffic-driven coverage model as score_snapshots. Powers the "X signals
# flipped since yesterday" feed in Today's Brief.
signal_snapshots = Table(
    "signal_snapshots", metadata,
    Column("id", Integer, primary_key=True),
    Column("signal_id", String(64), nullable=False),
    Column("snapshot_date", String(10), nullable=False),  # YYYY-MM-DD
    Column("score", Float, nullable=False),
    Column("status", String(16), nullable=False),         # bullish / neutral / bearish
    Column("created_at", String(64), nullable=False),
    UniqueConstraint("signal_id", "snapshot_date", name="uq_signal_snapshot_sig_date"),
)

# Confluence Score COMPONENT snapshots (added 2026-07-14). Powers "Explain the
# Move": stores the full reconciling breakdown (per-signal contribution/weight/
# factor + momentum + positioning + coverage) that produced a ticker's score on a
# given day, plus the model version it was computed under. Keyed by (ticker,
# snapshot_date) like score_snapshots, same organic traffic-driven coverage
# model, upserted at Ticker Deep Dive view time. `components_json` is the JSON
# blob from utils.score_components.build_components — a Text column so the schema
# stays dialect-portable (SQLite + Postgres) and the breakdown can evolve without
# an ALTER TABLE. Brand-new table — plain create_all() is sufficient.
score_components = Table(
    "score_components", metadata,
    Column("id", Integer, primary_key=True),
    Column("ticker", String(16), nullable=False),
    Column("snapshot_date", String(10), nullable=False),   # YYYY-MM-DD
    Column("model_version", String(32)),
    Column("signal_registry_version", String(32)),
    Column("final_score", Float),
    Column("components_json", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    UniqueConstraint("ticker", "snapshot_date", name="uq_score_components_ticker_date"),
)

# Signal Flip Alert Log (added 2026-07-07). One row per (signal_id, flip_date)
# — deduplicates the signal_flip_alerts cron so users receive at most one email
# per signal flip per calendar day, even if the cron runs every 2 hours.
# from_status/to_status are stored for debugging; alerted_at is the UTC ISO
# timestamp of when the alert emails were dispatched.
signal_flip_log = Table(
    "signal_flip_log", metadata,
    Column("id", Integer, primary_key=True),
    Column("signal_id", String(64), nullable=False),
    Column("flip_date", String(10), nullable=False),    # YYYY-MM-DD
    Column("from_status", String(16), nullable=False),  # bullish / neutral / bearish
    Column("to_status", String(16), nullable=False),
    Column("n_users_alerted", Integer, nullable=False, server_default="0"),
    Column("alerted_at", String(64), nullable=False),   # ISO timestamp
    UniqueConstraint("signal_id", "flip_date", name="uq_flip_log_sig_date"),
)


# Prediction Log (added 2026-06-25). Every time the machine fires a
# convergence event or a ticker's confluence score crosses 70+ / 35-,
# we log the prediction with the entry price. When the forward windows
# expire (4w / 8w / 12w), we resolve the return automatically on the
# next page load that calls resolve_pending_predictions(). This creates
# an auditable, public track record — something no free tool offers.
# event_type: "convergence" | "score_cross_bull" | "score_cross_bear"
prediction_log = Table(
    "prediction_log", metadata,
    Column("id", Integer, primary_key=True),
    Column("ticker", String(16), nullable=False),
    Column("event_type", String(32), nullable=False),
    Column("direction", String(8), nullable=False),     # "bull" | "bear"
    Column("score_at_event", Float),
    Column("signal_count", Integer),
    Column("price_at_event", Float),
    Column("event_date", String(10), nullable=False),   # YYYY-MM-DD
    Column("status", String(16), nullable=False, server_default="'pending'"),  # pending | resolved
    Column("price_4w",   Float),
    Column("price_8w",   Float),
    Column("price_12w",  Float),
    Column("return_4w",  Float),   # pct
    Column("return_8w",  Float),
    Column("return_12w", Float),
    Column("correct_4w",  Integer),  # 1 / 0 / NULL
    Column("correct_8w",  Integer),
    Column("correct_12w", Integer),
    Column("signals_triggered", Text),   # comma-separated signal IDs, e.g. "crude_inventories,gas_storage"
    Column("created_at", String(64), nullable=False),
    UniqueConstraint("ticker", "event_date", "event_type", name="uq_pred_ticker_date_type"),
)

# System notifications — global, not user-scoped.
# Stores convergence events, regime changes, near-threshold warnings.
# Logged once per event; the header bell icon reads unread count from here.
# Users see all system notifications (no per-user filtering for now —
# per-watchlist filtering is a future personalisation step).
system_notifications = Table(
    "system_notifications", metadata,
    Column("id", Integer, primary_key=True),
    Column("notif_type", String(32), nullable=False),   # "convergence" | "regime_change" | "near_flip" | "prediction_resolved"
    Column("title", String(255), nullable=False),
    Column("body", Text, nullable=False),
    Column("ticker", String(16)),                       # NULL for regime-level events
    Column("direction", String(8)),                     # "bull" | "bear" | NULL
    Column("created_at", String(64), nullable=False),
)

# Machine-generated macro research notes (added 2026-06-25).
# Generated weekly by utils/narrative_engine.py via Anthropic API.
# One row per note_date (YYYY-MM-DD). The body is the full markdown note;
# headline and regime are extracted fields for fast home-page teaser display
# without parsing the full body on every load.
macro_narratives = Table(
    "macro_narratives", metadata,
    Column("id", Integer, primary_key=True),
    Column("note_date", String(10), nullable=False, unique=True),  # YYYY-MM-DD
    Column("regime", String(32), nullable=False),                  # RISK-ON / RISK-OFF / MIXED etc.
    Column("headline", String(255), nullable=False),
    Column("body", Text, nullable=False),                          # full markdown note
    Column("bull_count", Integer),
    Column("bear_count", Integer),
    Column("model", String(64)),                                   # model string used
    Column("input_tokens", Integer),
    Column("output_tokens", Integer),
    Column("created_at", String(64), nullable=False),
)

# Dynamic ticker universe (added 2026-07-13). The static config.TICKERS list is
# code and cannot grow at runtime; this table lets the tracked universe expand.
# Every ticker a user adds to their watchlist is recorded here, and a daily cron
# (cron/grow_universe.py) seeds big-cap names across the covered industries so
# their data is pre-warmed and loads instantly. Merged with the static universe
# by utils/universe.get_full_universe(). Brand-new table — plain create_all()
# creates it, no ALTER TABLE migration needed.
dynamic_universe = Table(
    "dynamic_universe", metadata,
    Column("id", Integer, primary_key=True),
    Column("ticker", String(16), nullable=False, unique=True),
    Column("name", String(255)),
    Column("sector", String(64)),
    Column("source", String(32), nullable=False, server_default="'watchlist'"),  # watchlist | daily | manual
    Column("added_at", String(64), nullable=False),
)

# Per-user read receipts for system notifications
notification_reads = Table(
    "notification_reads", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("notification_id", Integer, ForeignKey("system_notifications.id"), nullable=False),
    Column("read_at", String(64), nullable=False),
    UniqueConstraint("user_id", "notification_id", name="uq_notif_read"),
)

# Per-user notification-feed clear cursor. Clearing the tray records the newest
# global notification visible at that moment; it never deletes the underlying
# event or affects another user, and any later event appears normally.
notification_clear_state = Table(
    "notification_clear_state", metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("cleared_through_id", Integer, nullable=False, server_default="0"),
    Column("cleared_at", String(64), nullable=False),
)


# Referral Program (added 2026-07-04). Tracks referral relationships from
# signup through conversion to reward. One row per referee email — a user
# can only be referred once. Status lifecycle: pending → converted → rewarded.
#   pending   — referee signed up via referral link but hasn't subscribed yet
#   converted — referee started a paid Pro subscription
#   rewarded  — referrer received their 1-month free coupon via Stripe
# Brand-new table, so plain create_all() is sufficient (no ALTER needed).
referrals = Table(
    "referrals", metadata,
    Column("id", Integer, primary_key=True),
    Column("referrer_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("referee_email", String(255), nullable=False, unique=True),
    Column("referee_id", Integer, ForeignKey("users.id")),   # filled in on conversion
    Column("status", String(16), nullable=False, server_default="'pending'"),
    Column("created_at", String(64), nullable=False),
    Column("converted_at", String(64)),
    Column("rewarded_at", String(64)),
)


# Analytics event log (added 2026-07-08). Keyed by event_name + user_id + ts.
# user_id is nullable — anonymous page views before login are still tracked.
# properties is a JSON string for arbitrary per-event context.
# No unique constraint — duplicate events are legitimate (two page views = two rows).
# Brand-new table, create_all() handles it — no ALTER TABLE migration needed.
analytics_events = Table(
    "analytics_events", metadata,
    Column("id",         Integer, primary_key=True),
    Column("event_name", String(64), nullable=False),
    Column("user_id",    Integer),              # nullable — anonymous events
    Column("session_id", String(64)),           # Streamlit session ID for anon stitching
    Column("properties", Text),                 # JSON string
    Column("created_at", String(64), nullable=False),
)

# User onboarding progress (added 2026-07-08). Tracks which of the 3 "Start Here"
# steps each new user has completed: view_signals, search_ticker, add_to_watchlist.
# Unique on (user_id, step_id) — a step can only be marked done once per user.
# Brand-new table, create_all() handles it — no ALTER TABLE migration needed.
onboarding_progress = Table(
    "onboarding_progress", metadata,
    Column("id",           Integer, primary_key=True),
    Column("user_id",      Integer, ForeignKey("users.id"), nullable=False),
    Column("step_id",      String(64), nullable=False),
    Column("completed_at", String(64), nullable=False),
    UniqueConstraint("user_id", "step_id", name="uq_onboarding_user_step"),
)


def _migrate_users_table() -> None:
    """
    metadata.create_all() only creates tables that don't exist yet -- it
    does NOT add new columns to a table that's already there. The
    email_verified / verification_code_* columns were added to the `users`
    Table definition above AFTER real accounts already existed in the
    running local database (and will exist in production once real users
    sign up there too), so a plain create_all() would silently leave those
    columns missing on every already-deployed database, and every
    is_verified check would then KeyError instead of working.

    This runs a one-time, idempotent ALTER TABLE for any column present in
    the Python Table definition but missing from the real database, then
    backfills existing rows: any account that existed BEFORE email
    verification was added is grandfathered in as already verified --
    locking out every pre-existing account the next time they log in,
    just because a feature was added after they signed up, would be a
    real, self-inflicted regression.
    """
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return  # brand new database -- create_all() already created this table with every column

    existing_cols = {c["name"] for c in inspector.get_columns("users")}
    new_cols = [c for c in users.columns if c.name not in existing_cols]
    if not new_cols:
        return

    bool_type = "BOOLEAN" if not IS_SQLITE else "INTEGER"
    # PostgreSQL requires TRUE/FALSE literals for BOOLEAN defaults; SQLite accepts 0/1.
    false_literal = "0" if IS_SQLITE else "FALSE"
    with engine.begin() as conn:
        for col in new_cols:
            if col.name in ("email_verified", "digest_opted_in"):
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col.name} {bool_type} DEFAULT {false_literal}"))
            elif col.name == "subscription_tier":
                # VARCHAR with default 'free' — existing users are all free tier.
                conn.execute(text(f"ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(16) DEFAULT 'free'"))
            elif col.name in ("login_attempt_count", "verification_attempt_count"):
                # INTEGER counters — default 0, no backfill needed.
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col.name} INTEGER DEFAULT 0"))
            else:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col.name} TEXT"))
        if any(c.name == "email_verified" for c in new_cols):
            # Grandfather in every account that existed before this column did.
            conn.execute(update(users).values(email_verified=True))
        if any(c.name == "onboarding_completed_at" for c in new_cols):
            # Do not interrupt existing members with a newly introduced setup
            # flow. New signups created after this migration retain NULL.
            conn.execute(update(users).values(
                onboarding_completed_at=datetime.now(timezone.utc).isoformat()
            ))
        # digest_opted_in: new accounts default False, no backfill needed.
        # subscription_tier: existing accounts default 'free' — already handled by column DEFAULT above.


def _migrate_prediction_log_table() -> None:
    """
    Idempotent ALTER TABLE for any column present in the prediction_log
    Table definition but missing from the real database.  Same inspect()
    pattern as _migrate_users_table() above.

    Currently handles:
      signals_triggered TEXT  — added 2026-07 to enable per-signal accuracy.
                                Existing rows get NULL (unknown signals).
    """
    inspector = inspect(engine)
    if "prediction_log" not in inspector.get_table_names():
        return  # brand new database — create_all() already made the table with every column

    existing_cols = {c["name"] for c in inspector.get_columns("prediction_log")}
    new_cols = [c for c in prediction_log.columns if c.name not in existing_cols]
    if not new_cols:
        return

    with engine.begin() as conn:
        for col in new_cols:
            # All additive columns are nullable TEXT — no backfill needed.
            conn.execute(text(f"ALTER TABLE prediction_log ADD COLUMN {col.name} TEXT"))


def _migrate_alert_state_table() -> None:
    """
    Idempotent ALTER TABLE for any column present in the alert_state Table
    definition but missing from the real database.

    Currently handles:
      last_score_emailed FLOAT      — added 2026-07-04 for the score-moved cron
      last_velocity_alert_at TEXT   — added 2026-07-04 for velocity-alert cron
      last_score_basis TEXT         — added 2026-07-22 to prevent profile-change alerts
    """
    inspector = inspect(engine)
    if "alert_state" not in inspector.get_table_names():
        return  # brand new database — create_all() already made the table with every column

    existing_cols = {c["name"] for c in inspector.get_columns("alert_state")}
    new_cols = [c for c in alert_state.columns if c.name not in existing_cols]
    if not new_cols:
        return

    with engine.begin() as conn:
        for col in new_cols:
            # Detect column type: String → TEXT, everything else → FLOAT
            col_sql_type = "TEXT" if isinstance(col.type, String) else "FLOAT"
            conn.execute(text(f"ALTER TABLE alert_state ADD COLUMN {col.name} {col_sql_type}"))


def _migrate_score_snapshots_table() -> None:
    """
    Idempotent ALTER TABLE for score_snapshots. Same inspect() pattern as the
    other migrations.

    Currently handles:
      score_kind TEXT — added 2026-07-18 so a "full" Confluence Score and a
                        cheaper "macro_momentum" bulk score can coexist without
                        being mistaken for each other. Existing rows are left
                        NULL and read as "full", which is what they were.
    """
    inspector = inspect(engine)
    if "score_snapshots" not in inspector.get_table_names():
        return  # brand new database — create_all() already made it with every column

    existing_cols = {c["name"] for c in inspector.get_columns("score_snapshots")}
    new_cols = [c for c in score_snapshots.columns if c.name not in existing_cols]
    if not new_cols:
        return

    with engine.begin() as conn:
        for col in new_cols:
            col_sql_type = "TEXT" if isinstance(col.type, String) else "FLOAT"
            conn.execute(text(
                f"ALTER TABLE score_snapshots ADD COLUMN {col.name} {col_sql_type}"))


def _migrate_saved_recommender_screens_table() -> None:
    """Add monitoring state to screen tables created before alert support."""
    inspector = inspect(engine)
    if "saved_recommender_screens" not in inspector.get_table_names():
        return
    existing_cols = {c["name"] for c in inspector.get_columns("saved_recommender_screens")}
    new_cols = [c for c in saved_recommender_screens.columns if c.name not in existing_cols]
    if not new_cols:
        return
    with engine.begin() as conn:
        for col in new_cols:
            if col.name == "alerts_enabled":
                conn.execute(text(
                    "ALTER TABLE saved_recommender_screens "
                    "ADD COLUMN alerts_enabled INTEGER DEFAULT 0"
                ))
            else:
                conn.execute(text(
                    f"ALTER TABLE saved_recommender_screens ADD COLUMN {col.name} TEXT"
                ))


def init_db() -> None:
    """Create every table if it doesn't already exist, then apply any
    pending column migrations. Safe to call on every page load."""
    metadata.create_all(engine)
    _migrate_users_table()
    _migrate_prediction_log_table()
    _migrate_alert_state_table()
    _migrate_score_snapshots_table()
    _migrate_saved_recommender_screens_table()


# Probability that any single page load triggers run_periodic_maintenance()
# below. This app has no background scheduler/cron -- it's a Streamlit app,
# driven entirely by page loads -- so periodic cleanup has to piggyback on
# a request somehow. Running it on every single load would mean every user
# pays for 2 DELETE statements on every page view, for the sake of a
# low-urgency hygiene task (expired remember-tokens, old read alerts) that
# doesn't need second-by-second freshness. A ~1-in-200 chance means it
# still runs many times a day under any real traffic, without adding
# measurable overhead to the typical request.
_MAINTENANCE_PROBABILITY = 0.005


def run_periodic_maintenance(force: bool = False) -> dict:
    """
    Probabilistically purge rows that exist only because nothing has ever
    deleted them: expired "remember me" tokens (utils.auth) and old, ALREADY
    -READ alerts (utils.alerts_db). Neither is urgent at this app's current
    scale -- both are real, unbounded-growth gaps that were flagged in a
    2026-06-22 UI/usage audit and are cheap to fix now rather than as an
    emergency later.

    `force=True` bypasses the probability gate -- used by tests and by a
    caller that wants a guaranteed run (e.g. a manual admin trigger), never
    by the normal per-page-load call site.

    Returns {"ran": bool, "remember_tokens_deleted": int, "alerts_deleted": int}
    so a caller/test can confirm this did something real, not just that it
    didn't raise. Deliberately swallows any single cleanup's exception
    rather than letting a maintenance hiccup take down a page load --
    this is hygiene, not a page requirement.
    """
    import random

    if not force and random.random() >= _MAINTENANCE_PROBABILITY:
        return {"ran": False, "remember_tokens_deleted": 0, "alerts_deleted": 0}

    from utils.auth import cleanup_expired_remember_tokens
    from utils.alerts_db import cleanup_old_read_alerts

    tokens_deleted, alerts_deleted = 0, 0
    try:
        tokens_deleted = cleanup_expired_remember_tokens()
    except Exception:
        pass
    try:
        alerts_deleted = cleanup_old_read_alerts()
    except Exception:
        pass

    return {"ran": True, "remember_tokens_deleted": tokens_deleted, "alerts_deleted": alerts_deleted}


def upsert_stmt(table: Table, index_elements: list):
    """
    Return the dialect-correct "INSERT ... ON CONFLICT DO UPDATE" statement
    builder for the current engine. Postgres and SQLite both support this
    upsert syntax but via different SQLAlchemy constructs -- this is
    exactly the kind of dialect difference this module exists to hide from
    every caller.
    """
    return pg_insert(table) if not IS_SQLITE else sqlite_insert(table)
