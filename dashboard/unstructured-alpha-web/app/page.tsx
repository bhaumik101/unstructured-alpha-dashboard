'use client';

import { useState } from 'react';

const APP_URL = "https://app.unstructuredalpha.com";

// ─── Data ─────────────────────────────────────────────────────────────────────

// Stats: specific, honest, and differentiated
const STATS = [
  { value: "43",     label: "Macro signals tracked" },
  { value: "7+",     label: "Trusted data sources" },
  { value: "4–16w",  label: "Typical signal lead time" },
  { value: "$0",     label: "To start — no card" },
];

// Trusted data sources — these are the actual ones used
const SOURCES = [
  "FRED (Federal Reserve)",
  "SEC EDGAR",
  "FINRA",
  "EIA",
  "CBOE",
  "Yahoo Finance",
  "Congressional Disclosures",
];

// Example signal preview — explicitly labeled as example, not live
const PREVIEW_SIGNALS = [
  { name: "Yield Curve (10Y–2Y)",    score: 72, status: "bull", cat: "Macro",     note: "Steepening — historically precedes risk-on" },
  { name: "HY Credit Spread",        score: 34, status: "bear", cat: "Credit",    note: "Wide spreads signal stress in risk appetite" },
  { name: "Insider Buy Ratio",       score: 78, status: "bull", cat: "Sentiment", note: "Elevated insider buying — cluster in 3+ names" },
  { name: "Short Interest",          score: 29, status: "bear", cat: "Sentiment", note: "High short interest / rising squeeze risk" },
  { name: "EIA Crude Inventory Δ",   score: 68, status: "bull", cat: "Energy",    note: "Weekly draw streak — bullish for energy names" },
  { name: "VIX Term Structure",      score: 55, status: "neut", cat: "Volatility",note: "Flat term structure — no near-term fear spike" },
  { name: "TIPS Breakeven (10Y)",    score: 61, status: "bull", cat: "Inflation", note: "Market pricing moderate inflation ahead" },
  { name: "ISM Manufacturing PMI",   score: 44, status: "neut", cat: "Growth",    note: "Borderline — watch for expansion/contraction" },
];

const FEATURES = [
  {
    icon: "⚡", title: "Signal Dashboard", accent: "#00d566", pro: false,
    body: "All 43 macro signals in one view — categorized by macro, credit, energy, sentiment, inflation, and growth. Spot regime shifts before they hit price.",
    detail: "Updated every ~2h from FRED, SEC, FINRA, EIA, CBOE.",
  },
  {
    icon: "🔍", title: "Ticker Deep Dive", accent: "#00c8e0", pro: false,
    body: "Enter any ticker: get a Confluence Score, the signals most relevant to its sector, insider activity, factor exposure, and a plain-English bull/bear case.",
    detail: "Works on any publicly-traded US stock or ETF.",
  },
  {
    icon: "📋", title: "Today's Brief", accent: "#7c3aed", pro: false,
    body: "A daily macro briefing that tells you which signals moved, by how much, and what it means. No charts to decode — just context you can act on.",
    detail: "Digestible in under 5 minutes. Delivered in-app and by email.",
  },
  {
    icon: "📈", title: "Score History", accent: "#00d566", pro: true,
    body: "Track how a ticker's Confluence Score has evolved over time. See which macro regimes preceded past moves, and where the current regime sits historically.",
    detail: "30, 60, 90-day charts with snapshot comparison.",
  },
  {
    icon: "🏭", title: "Sector Percentiles", accent: "#00c8e0", pro: true,
    body: "Rank every sector by its current macro tailwind strength. Instantly see which sectors are in the top quartile of macro support.",
    detail: "Relative ranking updated daily from snapshot history.",
  },
  {
    icon: "🔔", title: "Watchlist Alerts", accent: "#7c3aed", pro: true,
    body: "Set thresholds per ticker. Get emailed when a Confluence Score crosses your level — hourly checks, morning digest, or Discord/Slack webhooks.",
    detail: "No logging in required once configured.",
  },
];

const FOR_WHO = [
  {
    icon: "📊", title: "Active stock pickers",
    body: "You have a thesis. Unstructured Alpha tells you whether the macro backdrop supports it — before you size in. No more blind macro exposure.",
  },
  {
    icon: "🏦", title: "Macro-aware investors",
    body: "You follow Fed policy, credit spreads, and energy markets but track them in scattered tabs. We aggregate all of it into one scored view.",
  },
  {
    icon: "⚙️", title: "Systematic thinkers",
    body: "You want data and logic, not opinions. Every signal is pulled from primary public sources, scored against a rolling 1-year history, and explained.",
  },
];

// Not for everyone — builds trust through honesty
const NOT_FOR = [
  "Day traders who need sub-second data",
  "Purely technical chartists — we're macro-first",
  "Anyone looking for stock tips or guaranteed returns",
];

const FAQ_ITEMS = [
  {
    q: "Is this real data or simulated/backtested?",
    a: "Real, live data. Every signal pulls from active public APIs — FRED for macroeconomic series, SEC EDGAR for Form 4 insider filings, FINRA for short interest, EIA for weekly energy inventories, CBOE for volatility data. Scores update approximately every 2 hours. The signal dashboard clearly marks each source.",
  },
  {
    q: "How is this different from a Bloomberg Terminal?",
    a: "Bloomberg costs ~$27,000/year, requires institutional onboarding, and is designed for professional desks. Unstructured Alpha is $20/month, designed for individual active investors, and focuses specifically on the macro signal layer — not on real-time prices or news. Different audience, different purpose.",
  },
  {
    q: "What is the Confluence Score and is it predictive?",
    a: "The Confluence Score is a 0–100 composite that weights the macro signals most relevant to a ticker's sector. Above 65 means multiple signals are in a historically bullish zone simultaneously. Below 35 means multiple headwinds are aligned. It is a measure of macro context, not a price prediction. We publish our validation results on the Model Validation page — no cherry-picking.",
  },
  {
    q: "What does 'free forever' mean in practice?",
    a: "The Signal Dashboard (all 43 signals), Today's Brief, and Ticker Deep Dive are free with an account. No time limits, no trial expiry. Pro ($20/mo) adds email alerts, score history, sector percentile rankings, and full digest history. You can stay on free indefinitely.",
  },
  {
    q: "Do I need a finance or coding background?",
    a: "No. Scores are on a 0–100 scale. The daily brief explains what changed in plain English. The Ticker Deep Dive gives you a summary sentence for each signal — what it means and why it matters for that stock's sector.",
  },
  {
    q: "Can I cancel my Pro subscription at any time?",
    a: "Yes. Cancel from your account settings. You keep Pro access until the end of your billing period, then revert to free. No commitments, no cancellation fees.",
  },
];

const FREE_FEATURES = [
  "Signal Dashboard — all 43 macro signals",
  "Today's Brief — daily macro summary",
  "Ticker Deep Dive — Confluence Score + signal breakdown",
  "Market Overview — rates, commodities, sector performance",
  "Sector Map — macro tailwind by sector",
];
const FREE_LOCKED = [
  "Score history charts (30/60/90d)",
  "Sector percentile rankings",
  "Watchlist email + Discord alerts",
  "Full digest archive (90 days)",
];
const PRO_FEATURES = [
  "Everything in Free",
  "Score history charts (30/60/90 days)",
  "Sector percentile rankings",
  "Watchlist alerts — email + Discord + Slack",
  "Full digest archive (90 days)",
  "Morning email digest at 7 AM ET",
  "Signal Backtester — test strategy from 2010",
  "Factor exposure dashboard",
  "Early access to new signals",
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function ScoreCell({ score, status }: { score: number; status: string }) {
  const cls = status === "bull" ? "score-bull" : status === "bear" ? "score-bear" : "score-neutral";
  return (
    <span
      className={cls}
      style={{ borderRadius: 6, padding: "2px 10px", fontSize: 12, fontWeight: 700,
               flexShrink: 0, width: 40, textAlign: "center", display: "inline-block" }}
    >
      {score}
    </span>
  );
}

const T = {
  muted:   "#8892aa" as const,
  dimmer:  "#4a5280" as const,
  label:   "#6b7fbb" as const,
  bright:  "#e8eaf2" as const,
  mid:     "#b8c0d4" as const,
  green:   "#00d566" as const,
  cyan:    "#00c8e0" as const,
  purple:  "#7c3aed" as const,
  bg:      "#0b0d12" as const,
  card:    "#12151e" as const,
};

// ─── Component ────────────────────────────────────────────────────────────────

export default function Home() {
  const [annual,     setAnnual]     = useState(false);
  const [openFaq,    setOpenFaq]    = useState<number | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);

  const proPrice    = annual ? 16 : 20;
  const annualTotal = proPrice * 12;

  return (
    <div style={{ minHeight: "100vh", background: T.bg, color: T.bright,
                  fontFamily: "var(--font-geist), Inter, system-ui, sans-serif" }}>

      {/* ── Ambient glow ── */}
      <div aria-hidden style={{ position: "fixed", top: 0, left: "50%", transform: "translateX(-50%)",
                                 width: 900, height: 500, pointerEvents: "none", zIndex: 0,
                                 background: "radial-gradient(ellipse at top, rgba(0,213,102,0.06) 0%, transparent 70%)" }} />

      {/* ──────────────────────────── NAV ──────────────────────────────────── */}
      <nav style={{ borderBottom: "1px solid rgba(255,255,255,0.06)", position: "sticky", top: 0, zIndex: 50,
                    background: "rgba(11,13,18,0.92)", backdropFilter: "blur(12px)" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "0 24px", height: 60,
                      display: "flex", alignItems: "center", justifyContent: "space-between" }}>

          {/* Logo */}
          <a href="/" style={{ display: "flex", alignItems: "center", gap: 10, fontWeight: 700,
                               fontSize: 15, letterSpacing: "-0.02em", color: T.bright }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.svg" alt="UA logo" style={{ width: 28, height: 28, borderRadius: "50%" }} />
            Unstructured Alpha
          </a>

          {/* Desktop nav */}
          <div className="nav-desktop" style={{ display: "flex", gap: 24, alignItems: "center" }}>
            <a href="#how-it-works" className="nav-link">How it works</a>
            <a href="#features"     className="nav-link">Features</a>
            <a href="#pricing"      className="nav-link">Pricing</a>
            <a href="#faq"          className="nav-link">FAQ</a>
            <a href={`${APP_URL}`}
               style={{ background: T.green, color: "#000", padding: "8px 18px",
                        borderRadius: 8, fontSize: 14, fontWeight: 700 }}>
              Launch App →
            </a>
          </div>

          {/* Mobile hamburger */}
          <button
            className="hamburger"
            aria-label="Open menu"
            onClick={() => setMobileOpen(!mobileOpen)}
          >
            <span />
            <span />
            <span />
          </button>
        </div>

        {/* Mobile menu */}
        <div className={`mobile-menu${mobileOpen ? " open" : ""}`}>
          <a href="#how-it-works" onClick={() => setMobileOpen(false)}>How it works</a>
          <a href="#features"     onClick={() => setMobileOpen(false)}>Features</a>
          <a href="#pricing"      onClick={() => setMobileOpen(false)}>Pricing</a>
          <a href="#faq"          onClick={() => setMobileOpen(false)}>FAQ</a>
          <a href={APP_URL}       onClick={() => setMobileOpen(false)}>Launch App — Free →</a>
        </div>
      </nav>

      {/* ──────────────────────────── HERO ─────────────────────────────────── */}
      <section style={{ maxWidth: 1100, margin: "0 auto", padding: "96px 24px 52px",
                        textAlign: "center", position: "relative", zIndex: 1 }}>

        {/* Trust pill */}
        <div style={{ display: "inline-flex", alignItems: "center", gap: 7,
                      background: "rgba(0,213,102,0.08)", border: "1px solid rgba(0,213,102,0.25)",
                      borderRadius: 100, padding: "5px 14px", fontSize: 12, color: T.green,
                      fontWeight: 600, marginBottom: 28, letterSpacing: "0.04em" }}>
          <span className="live-dot" />
          Data from FRED · SEC EDGAR · FINRA · EIA · CBOE
        </div>

        <h1 className="hero-h1" style={{ fontSize: "clamp(38px, 5.5vw, 64px)", fontWeight: 800,
                                          lineHeight: 1.07, letterSpacing: "-0.04em", marginBottom: 22 }}>
          Know what the macro<br />
          <span style={{ background: "linear-gradient(90deg, #00d566 0%, #00c8e0 100%)",
                         WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            is doing to your stocks.
          </span>
        </h1>

        <p style={{ fontSize: 18, color: T.muted, maxWidth: 560, margin: "0 auto 16px", lineHeight: 1.75 }}>
          43 macro signals — credit spreads, insider flows, energy positioning, Fed indicators —
          scored daily from public data. Free dashboard for active investors.
        </p>

        {/* Objection-killer subline */}
        <p style={{ fontSize: 14, color: T.dimmer, marginBottom: 44 }}>
          Not financial advice. No trade signals. No guaranteed returns. Just context.
        </p>

        {/* CTA row */}
        <div className="hero-cta-row" style={{ display: "flex", gap: 12, justifyContent: "center",
                                               flexWrap: "wrap", marginBottom: 52 }}>
          <a href={APP_URL} className="btn-primary">
            Start Free — No Card Required
          </a>
          <a href="#how-it-works" className="btn-secondary">
            See How It Works
          </a>
        </div>

        {/* Stat strip */}
        <div className="stat-strip" style={{ display: "flex", justifyContent: "center", flexWrap: "wrap",
                                             borderTop: "1px solid rgba(255,255,255,0.06)",
                                             borderBottom: "1px solid rgba(255,255,255,0.06)",
                                             padding: "20px 0" }}>
          {STATS.map((s, i) => (
            <div key={s.label} className="stat-item"
                 style={{ display: "flex", alignItems: "center", padding: "0 28px",
                          borderRight: i < STATS.length - 1 ? "1px solid rgba(255,255,255,0.06)" : "none" }}>
              <div>
                <div style={{ fontSize: 22, fontWeight: 800, color: T.bright, letterSpacing: "-0.03em" }}>{s.value}</div>
                <div style={{ fontSize: 12, color: T.dimmer, marginTop: 2 }}>{s.label}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ─────────────────── SIGNAL PREVIEW ──────────────────────────────────── */}
      <div style={{ borderTop: "1px solid rgba(0,213,102,0.14)",
                    background: "linear-gradient(180deg, rgba(0,213,102,0.035) 0%, transparent 100%)",
                    padding: "60px 24px" }}>
        <div style={{ maxWidth: 860, margin: "0 auto" }}>

          {/* Section label with explicit "example" disclaimer */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                        flexWrap: "wrap", gap: 12, marginBottom: 20 }}>
            <p style={{ fontSize: 11, color: T.dimmer, fontWeight: 700, letterSpacing: "0.1em",
                        textTransform: "uppercase" }}>
              What the dashboard looks like
            </p>
            <span style={{ fontSize: 11, color: T.dimmer, background: "rgba(255,255,255,0.04)",
                           border: "1px solid rgba(255,255,255,0.07)", borderRadius: 6, padding: "3px 10px" }}>
              Example scores · Not your portfolio · Live scores update every ~2h
            </span>
          </div>

          <div style={{ background: T.card, border: "1px solid rgba(255,255,255,0.08)",
                        borderRadius: 16, padding: "24px", overflowX: "auto" }}>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                          marginBottom: 18, flexWrap: "wrap", gap: 12 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: T.bright }}>Macro Signal Scores</span>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span className="live-dot" />
                <span style={{ fontSize: 11, color: T.dimmer }}>Updates every ~2h from FRED, SEC, EIA, CBOE</span>
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {PREVIEW_SIGNALS.map((sig) => (
                <div key={sig.name}
                     style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px",
                              borderRadius: 8, background: "rgba(255,255,255,0.02)" }}>
                  <span style={{ fontSize: 10, fontWeight: 700, color: T.dimmer, letterSpacing: "0.08em",
                                 textTransform: "uppercase" as const, width: 76, flexShrink: 0 }}>
                    {sig.cat}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, color: T.mid }}>{sig.name}</div>
                    <div style={{ fontSize: 11, color: T.dimmer, marginTop: 2 }}>{sig.note}</div>
                  </div>
                  <div style={{ width: 120, height: 4, background: "rgba(255,255,255,0.06)",
                                borderRadius: 2, flexShrink: 0 }}>
                    <div style={{ width: `${sig.score}%`, height: "100%", borderRadius: 2,
                                  background: sig.status === "bull" ? T.green : sig.status === "bear" ? "#ff4444" : T.muted }} />
                  </div>
                  <ScoreCell score={sig.score} status={sig.status} />
                </div>
              ))}
            </div>

            {/* Legend + CTA */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                          marginTop: 20, paddingTop: 16, borderTop: "1px solid rgba(255,255,255,0.05)",
                          flexWrap: "wrap", gap: 12 }}>
              <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
                {[
                  { label: "≥65 Bullish macro", color: T.green },
                  { label: "36–64 Neutral", color: T.muted },
                  { label: "≤35 Bearish macro", color: "#ff4444" },
                ].map((l) => (
                  <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 6,
                                              fontSize: 11, color: T.dimmer }}>
                    <div style={{ width: 8, height: 8, borderRadius: 2, background: l.color }} />
                    {l.label}
                  </div>
                ))}
              </div>
              <a href={APP_URL} style={{ fontSize: 13, color: T.green, fontWeight: 600,
                                        display: "flex", alignItems: "center", gap: 4 }}>
                See live dashboard →
              </a>
            </div>
          </div>

          <p style={{ fontSize: 12, color: T.dimmer, textAlign: "center", marginTop: 14 }}>
            Scores are 0–100 percentile rankings vs. a rolling 1-year history.
            They measure macro context, not price direction.
          </p>
        </div>
      </div>

      {/* ─────────────────── HOW IT WORKS ───────────────────────────────────── */}
      <div id="how-it-works" style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "80px 24px" }}>
          <p className="eyebrow">How it works</p>
          <h2 className="section-title">From public filings to macro context</h2>
          <p className="section-body" style={{ marginBottom: 56 }}>
            Three steps from raw government data to a clear read on whether the macro environment
            supports the stocks you hold.
          </p>

          <div className="grid-3" style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 28 }}>
            {[
              {
                n: "01", title: "43 signals scored daily",
                body: "We pull from FRED, SEC EDGAR, FINRA, EIA, and CBOE. Each signal gets a 0–100 percentile score against its trailing 1-year history. A score of 72 means the current reading is more bullish than 72% of the past year's readings — no arbitrary thresholds.",
                src: "Source: FRED, SEC EDGAR, FINRA, EIA, CBOE",
              },
              {
                n: "02", title: "Confluence Score per ticker",
                body: "For each stock in your watchlist, we weight the signals most relevant to its sector into a single Confluence Score. Energy stocks weight crude inventory and rig count differently than a semiconductor company weights hyperscaler capex. Sector-aware, not one-size-fits-all.",
                src: "Updated every ~2 hours",
              },
              {
                n: "03", title: "Plain-English regime summary",
                body: "Every day, Today's Brief tells you exactly which signals changed, by how much, and what it means for the macro backdrop — not raw numbers you have to interpret, but actual context. What changed. Why it matters. What to watch next.",
                src: "Available free · No account for Signal Dashboard",
              },
            ].map((step) => (
              <div key={step.n} style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
                <div style={{ flexShrink: 0, width: 36, height: 36, background: "rgba(0,213,102,0.1)",
                              border: "1px solid rgba(0,213,102,0.25)", borderRadius: 10, display: "flex",
                              alignItems: "center", justifyContent: "center", fontSize: 13,
                              fontWeight: 700, color: T.green }}>
                  {step.n}
                </div>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 8, color: T.bright }}>{step.title}</div>
                  <div style={{ fontSize: 14, color: T.muted, lineHeight: 1.7, marginBottom: 8 }}>{step.body}</div>
                  <div style={{ fontSize: 11, color: T.dimmer, fontStyle: "italic" }}>{step.src}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ─────────────────── SOURCE STRIP ────────────────────────────────────── */}
      <div style={{ background: "rgba(255,255,255,0.015)", borderBottom: "1px solid rgba(255,255,255,0.04)",
                    padding: "18px 24px" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", display: "flex", alignItems: "center",
                      gap: 10, flexWrap: "wrap", justifyContent: "center" }}>
          <span style={{ fontSize: 11, color: T.dimmer, fontWeight: 700, letterSpacing: "0.08em",
                         textTransform: "uppercase", flexShrink: 0 }}>Primary sources:</span>
          {SOURCES.map((src) => (
            <span key={src}
                  style={{ fontSize: 12, fontWeight: 600, color: T.label,
                           background: "rgba(107,127,187,0.07)", border: "1px solid rgba(107,127,187,0.13)",
                           borderRadius: 6, padding: "3px 10px", letterSpacing: "0.02em" }}>
              {src}
            </span>
          ))}
        </div>
      </div>

      {/* ─────────────────── FEATURES ────────────────────────────────────────── */}
      <div id="features" style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "80px 24px" }}>
          <p className="eyebrow">Features</p>
          <h2 className="section-title">The macro layer your portfolio is missing</h2>
          <p className="section-body" style={{ marginBottom: 56 }}>
            One dashboard. No Bloomberg required. Free for the core features.
          </p>
          <div className="grid-3" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))", gap: 20 }}>
            {FEATURES.map((f) => (
              <div key={f.title} className="card"
                   style={{ background: T.card, border: "1px solid rgba(255,255,255,0.07)",
                            borderRadius: 14, padding: "28px", position: "relative" }}>
                {f.pro && (
                  <span className="badge badge-purple" style={{ position: "absolute", top: 16, right: 16 }}>
                    Pro
                  </span>
                )}
                <div style={{ fontSize: 28, marginBottom: 14 }}>{f.icon}</div>
                <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8, letterSpacing: "-0.02em",
                              background: `linear-gradient(90deg, ${T.bright}, ${f.accent})`,
                              WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
                              display: "inline-block" }}>
                  {f.title}
                </div>
                <div style={{ fontSize: 14, color: T.muted, lineHeight: 1.7, marginBottom: 10 }}>{f.body}</div>
                <div style={{ fontSize: 11, color: T.dimmer, borderTop: "1px solid rgba(255,255,255,0.05)",
                              paddingTop: 10, marginTop: 4 }}>
                  {f.detail}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ─────────────────── WHO IT'S FOR + NOT FOR ──────────────────────────── */}
      <div style={{ borderBottom: "1px solid rgba(255,255,255,0.05)", background: "rgba(255,255,255,0.01)" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "80px 24px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 40 }}>

            {/* Who it's for */}
            <div>
              <p className="eyebrow">Built for</p>
              <h2 className="section-title" style={{ marginBottom: 32 }}>Active investors, not finance PhDs</h2>
              <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                {FOR_WHO.map((w) => (
                  <div key={w.title} style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
                    <div style={{ fontSize: 26, flexShrink: 0, lineHeight: 1 }}>{w.icon}</div>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 5, color: T.bright }}>{w.title}</div>
                      <div style={{ fontSize: 14, color: T.muted, lineHeight: 1.65 }}>{w.body}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Honest "not for" section — builds trust */}
            <div style={{ borderLeft: "1px solid rgba(255,255,255,0.06)", paddingLeft: 40 }}>
              <p className="eyebrow" style={{ color: T.label }}>Honest disclaimer</p>
              <h2 className="section-title" style={{ marginBottom: 12, fontSize: "clamp(18px, 2vw, 24px)" }}>
                Not for everyone
              </h2>
              <p style={{ fontSize: 14, color: T.muted, lineHeight: 1.7, marginBottom: 24 }}>
                We'd rather you know upfront. Unstructured Alpha is <em>not</em> useful if you're looking for:
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {NOT_FOR.map((item) => (
                  <div key={item} style={{ display: "flex", alignItems: "flex-start", gap: 10,
                                          fontSize: 14, color: T.muted }}>
                    <span style={{ color: "#ff4444", flexShrink: 0, fontSize: 13, marginTop: 1 }}>✕</span>
                    <span>{item}</span>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 28, padding: "16px 18px", background: "rgba(255,255,255,0.02)",
                            border: "1px solid rgba(255,255,255,0.06)", borderRadius: 10 }}>
                <div style={{ fontSize: 12, color: T.dimmer, lineHeight: 1.7 }}>
                  <strong style={{ color: T.label, display: "block", marginBottom: 4 }}>
                    What we actually are:
                  </strong>
                  A macro signal layer for investors who want to understand the economic environment
                  around their portfolio. Educational and informational only.
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>

      {/* ─────────────────── PRICING ─────────────────────────────────────────── */}
      <div id="pricing" style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "80px 24px" }}>
          <p className="eyebrow" style={{ textAlign: "center" }}>Pricing</p>
          <h2 className="section-title" style={{ textAlign: "center", maxWidth: "100%", marginBottom: 12 }}>
            Start free. Go deeper with Pro.
          </h2>
          <p className="section-body" style={{ textAlign: "center", margin: "0 auto 36px" }}>
            The core signal dashboard is free with an account. Pro adds alerts, history, and delivery.
          </p>

          {/* Billing toggle */}
          <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 12, marginBottom: 44 }}>
            <span style={{ fontSize: 14, color: annual ? T.dimmer : T.bright, fontWeight: annual ? 400 : 600 }}>
              Monthly
            </span>
            <button
              onClick={() => setAnnual(!annual)}
              aria-label="Toggle annual billing"
              style={{ width: 44, height: 24, background: annual ? T.purple : "rgba(255,255,255,0.12)",
                       borderRadius: 100, border: "none", cursor: "pointer", position: "relative",
                       transition: "background 0.2s", flexShrink: 0 }}
            >
              <span style={{ position: "absolute", top: 2, left: annual ? 22 : 2, width: 20, height: 20,
                             background: "#fff", borderRadius: "50%", transition: "left 0.2s", display: "block" }} />
            </button>
            <span style={{ fontSize: 14, color: annual ? T.bright : T.dimmer, fontWeight: annual ? 600 : 400 }}>
              Annual
            </span>
            {annual && (
              <span className="badge badge-green">Save 20%</span>
            )}
          </div>

          <div className="pricing-grid"
               style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
                        gap: 20, maxWidth: 780, margin: "0 auto" }}>

            {/* Free */}
            <div style={{ background: T.card, border: "1px solid rgba(255,255,255,0.08)",
                          borderRadius: 16, padding: "32px" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.muted, letterSpacing: "0.1em",
                            textTransform: "uppercase" as const, marginBottom: 12 }}>
                Free
              </div>
              <div style={{ fontSize: 42, fontWeight: 800, letterSpacing: "-0.04em", marginBottom: 4 }}>$0</div>
              <div style={{ fontSize: 13, color: T.dimmer, marginBottom: 28 }}>Free forever · No card</div>
              <ul className="checklist" style={{ marginBottom: 28 }}>
                {FREE_FEATURES.map((f) => (
                  <li key={f}><span className="check">✓</span><span>{f}</span></li>
                ))}
                {FREE_LOCKED.map((f) => (
                  <li key={f} style={{ opacity: 0.55 }}><span className="locked">—</span><span>{f}</span></li>
                ))}
              </ul>
              <a href={APP_URL}
                 style={{ display: "block", textAlign: "center", padding: "12px", borderRadius: 10,
                          border: "1px solid rgba(255,255,255,0.12)", color: T.bright, fontSize: 14,
                          fontWeight: 600 }}>
                Start for free →
              </a>
            </div>

            {/* Pro */}
            <div style={{ background: "rgba(124,58,237,0.07)", border: "1px solid rgba(124,58,237,0.38)",
                          borderRadius: 16, padding: "32px", position: "relative" }}>
              <div style={{ position: "absolute", top: -12, left: "50%", transform: "translateX(-50%)",
                            background: T.purple, color: "#fff", fontSize: 11, fontWeight: 700,
                            padding: "3px 14px", borderRadius: 100, letterSpacing: "0.08em",
                            textTransform: "uppercase" as const, whiteSpace: "nowrap" as const }}>
                Most popular
              </div>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.muted, letterSpacing: "0.1em",
                            textTransform: "uppercase" as const, marginBottom: 12 }}>
                Pro
              </div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 4 }}>
                <div style={{ fontSize: 42, fontWeight: 800, letterSpacing: "-0.04em" }}>${proPrice}</div>
                <span style={{ fontSize: 14, color: T.dimmer }}>/ month</span>
              </div>
              <div style={{ fontSize: 13, color: T.dimmer, marginBottom: 28 }}>
                {annual
                  ? `Billed $${annualTotal}/year · cancel anytime`
                  : "Per month · cancel anytime · 7-day free trial"}
              </div>
              <ul className="checklist" style={{ marginBottom: 28 }}>
                {PRO_FEATURES.map((f) => (
                  <li key={f} style={{ color: "#c4c9e0" }}>
                    <span style={{ color: T.purple, flexShrink: 0, marginTop: 1, fontSize: 13 }}>✓</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <a href={`${APP_URL}/pages/29_Upgrade`}
                 style={{ display: "block", textAlign: "center", padding: "12px", borderRadius: 10,
                          background: T.purple, color: "#fff", fontSize: 14, fontWeight: 700 }}>
                Start 7-Day Free Trial ⚡
              </a>
              <p style={{ fontSize: 11, color: T.dimmer, textAlign: "center", marginTop: 10 }}>
                No charge until trial ends · Cancel anytime
              </p>
            </div>

          </div>

          {/* Bloomberg comparison anchor */}
          <p style={{ textAlign: "center", fontSize: 13, color: T.dimmer, marginTop: 28 }}>
            Bloomberg Terminal costs ~$27,000/year for similar raw data.
            Unstructured Alpha focuses it into what active investors actually need, at $20/month.
          </p>
        </div>
      </div>

      {/* ─────────────────── FAQ ─────────────────────────────────────────────── */}
      <div id="faq" style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <div style={{ maxWidth: 720, margin: "0 auto", padding: "80px 24px" }}>
          <p className="eyebrow" style={{ textAlign: "center" }}>FAQ</p>
          <h2 className="section-title" style={{ textAlign: "center", maxWidth: "100%", marginBottom: 48 }}>
            Questions we get asked
          </h2>
          <div style={{ display: "flex", flexDirection: "column" }}>
            {FAQ_ITEMS.map((item, i) => (
              <div key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  style={{ width: "100%", textAlign: "left", padding: "20px 0", background: "none",
                           border: "none", cursor: "pointer", display: "flex",
                           justifyContent: "space-between", alignItems: "center", gap: 16 }}
                >
                  <span style={{ fontSize: 15, fontWeight: 600, color: T.bright }}>{item.q}</span>
                  <span style={{ color: T.dimmer, fontSize: 20, flexShrink: 0, lineHeight: 1,
                                 transform: openFaq === i ? "rotate(45deg)" : "none",
                                 transition: "transform 0.2s", display: "inline-block" }}>
                    +
                  </span>
                </button>
                {openFaq === i && (
                  <div style={{ paddingBottom: 20, fontSize: 14, color: T.muted, lineHeight: 1.78 }}>
                    {item.a}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ─────────────────── CLOSING CTA ─────────────────────────────────────── */}
      <div style={{ background: "linear-gradient(180deg, rgba(0,213,102,0.04) 0%, transparent 60%)",
                    borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <div style={{ maxWidth: 680, margin: "0 auto", padding: "96px 24px", textAlign: "center" }}>
          <h2 style={{ fontSize: "clamp(28px, 4vw, 46px)", fontWeight: 800,
                       letterSpacing: "-0.04em", marginBottom: 18, lineHeight: 1.1 }}>
            Start understanding<br />
            <span style={{ background: "linear-gradient(90deg, #00d566, #00c8e0)",
                           WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              your macro environment.
            </span>
          </h2>
          <p style={{ fontSize: 17, color: T.muted, marginBottom: 40, lineHeight: 1.7,
                      maxWidth: 460, margin: "0 auto 40px" }}>
            Free to start. No credit card. 43 live signals, updated every ~2 hours,
            from the same public data sources institutional desks use.
          </p>
          <a href={APP_URL}
             style={{ background: T.green, color: "#000", padding: "16px 44px", borderRadius: 12,
                      fontSize: 16, fontWeight: 800, display: "inline-block", letterSpacing: "-0.01em" }}>
            Open the Dashboard — Free →
          </a>
          <div style={{ marginTop: 20, fontSize: 13, color: T.dimmer }}>
            Free · No card · 43 signals · Updated every ~2h · Cancel Pro anytime
          </div>

          {/* Disclaimer */}
          <div style={{ marginTop: 32, padding: "16px 20px", background: "rgba(255,255,255,0.02)",
                        border: "1px solid rgba(255,255,255,0.06)", borderRadius: 10, textAlign: "left" }}>
            <p style={{ fontSize: 11, color: T.dimmer, lineHeight: 1.7 }}>
              <strong style={{ color: T.label }}>Educational use only:</strong> Macro signal scores
              reflect historical percentile rankings of public economic data. They are not buy/sell
              recommendations, personalized investment advice, or predictions of future returns.
            </p>
          </div>
        </div>
      </div>

      {/* ─────────────────── FOOTER ──────────────────────────────────────────── */}
      <footer style={{ borderTop: "1px solid rgba(255,255,255,0.06)", padding: "48px 24px 32px" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto" }}>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start",
                        flexWrap: "wrap", gap: 36, marginBottom: 40 }}>

            {/* Brand */}
            <div style={{ maxWidth: 320 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, fontWeight: 700,
                            fontSize: 15, letterSpacing: "-0.02em", color: T.bright, marginBottom: 10 }}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/logo.svg" alt="Unstructured Alpha" style={{ width: 28, height: 28, borderRadius: "50%" }} />
                Unstructured Alpha
              </div>
              <div style={{ fontSize: 13, color: T.dimmer, lineHeight: 1.65, marginBottom: 14 }}>
                Macro signal intelligence for active investors. 43 signals scored daily
                from FRED, SEC EDGAR, FINRA, EIA, and CBOE.
              </div>
              <div style={{ fontSize: 11, color: T.dimmer }}>
                For educational and informational purposes only.
              </div>
            </div>

            {/* Links */}
            <div style={{ display: "flex", gap: 48, flexWrap: "wrap" }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: T.muted, letterSpacing: "0.1em",
                              textTransform: "uppercase" as const, marginBottom: 14 }}>
                  Product
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <a href="#how-it-works" style={{ color: T.dimmer, fontSize: 13 }}>How it works</a>
                  <a href="#features"     style={{ color: T.dimmer, fontSize: 13 }}>Features</a>
                  <a href="#pricing"      style={{ color: T.dimmer, fontSize: 13 }}>Pricing</a>
                  <a href={APP_URL}       style={{ color: T.dimmer, fontSize: 13 }}>Launch App</a>
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: T.muted, letterSpacing: "0.1em",
                              textTransform: "uppercase" as const, marginBottom: 14 }}>
                  Legal
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <a href={`${APP_URL}/pages/36_Privacy_Policy`}   style={{ color: T.dimmer, fontSize: 13 }}>Privacy Policy</a>
                  <a href={`${APP_URL}/pages/37_Terms_of_Service`} style={{ color: T.dimmer, fontSize: 13 }}>Terms of Service</a>
                  <a href={`${APP_URL}/pages/8_About`}             style={{ color: T.dimmer, fontSize: 13 }}>About</a>
                  <a href="#faq"                                    style={{ color: T.dimmer, fontSize: 13 }}>FAQ</a>
                </div>
              </div>
            </div>
          </div>

          {/* Disclaimer + copyright */}
          <div style={{ borderTop: "1px solid rgba(255,255,255,0.05)", paddingTop: 24 }}>
            <p style={{ fontSize: 11, color: T.dimmer, lineHeight: 1.75, maxWidth: 820, marginBottom: 16 }}>
              <strong style={{ color: T.label }}>Disclaimer:</strong> Unstructured Alpha is an educational
              and informational platform only. Nothing on this site constitutes personalized financial,
              investment, tax, or legal advice. Macro signal scores reflect historical percentile rankings
              of public data — they are not guarantees of future performance and should not be interpreted
              as recommendations to buy, sell, or hold any security. Always consult a licensed financial
              adviser before making investment decisions. Past signal behavior is not indicative of future results.
            </p>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                          flexWrap: "wrap", gap: 12 }}>
              <p style={{ fontSize: 12, color: T.dimmer }}>
                © {new Date().getFullYear()} Unstructured Alpha. All rights reserved.
              </p>
              <div style={{ display: "flex", gap: 20 }}>
                <a href={`${APP_URL}/pages/36_Privacy_Policy`}   style={{ color: T.dimmer, fontSize: 12 }}>Privacy</a>
                <a href={`${APP_URL}/pages/37_Terms_of_Service`} style={{ color: T.dimmer, fontSize: 12 }}>Terms</a>
              </div>
            </div>
          </div>
        </div>
      </footer>

    </div>
  );
}
