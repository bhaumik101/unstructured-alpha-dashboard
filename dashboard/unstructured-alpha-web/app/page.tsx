'use client';

import { useState, useEffect, FormEvent } from 'react';

const APP_URL = "https://app.unstructuredalpha.com";

// ─── Data ─────────────────────────────────────────────────────────────────────

// Stats: specific, honest, and differentiated
const STATS = [
  { value: "47",     label: "Macro signals tracked" },
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
    body: "All 47 macro signals in one view — categorized by macro, credit, energy, sentiment, inflation, and growth. Spot regime shifts before they hit price.",
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
    icon: "🔔", title: "Continuous Monitoring", accent: "#7c3aed", pro: true,
    body: "We watch the macro backdrop around your holdings when you're not there. Get alerted the moment a Confluence Score materially moves or a signal flips — email, Discord, or Slack.",
    detail: "So you never miss when the macro around a holding turns.",
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


const FAQ_ITEMS = [
  {
    q: "Is this real data or simulated/backtested?",
    a: "Real, live data. Every signal pulls from active public APIs — FRED for macroeconomic series, SEC EDGAR for Form 4 insider filings, FINRA for short interest, EIA for weekly energy inventories, CBOE for volatility data. Scores update approximately every 2 hours. The signal dashboard clearly marks each source.",
  },
  {
    q: "How is this different from a Bloomberg Terminal?",
    a: "Different problem entirely. A terminal is built for professional desks that need real-time prices, news, and execution. Unstructured Alpha isn't competing with that — the real alternative is tracking the macro backdrop yourself across FRED, SEC EDGAR, FINRA, EIA and CBOE in a dozen tabs and a spreadsheet. We aggregate those public sources, score them against their own history, and explain what they mean for the stocks you hold. It's the interpretation layer, at $20/month.",
  },
  {
    q: "What is the Confluence Score and is it predictive?",
    a: "The Confluence Score is a 0–100 composite that weights the macro signals most relevant to a ticker's sector. Above 65 means multiple signals are in a historically bullish zone simultaneously. Below 35 means multiple headwinds are aligned. It is a measure of macro context, not a price prediction. We publish our validation results on the Model Validation page — no cherry-picking.",
  },
  {
    q: "What does 'free forever' mean in practice?",
    a: "The Signal Dashboard (all 47 signals), Today's Brief, and Ticker Deep Dive are free with an account. No time limits, no trial expiry. Pro ($20/mo) adds email alerts, score history, sector percentile rankings, and full digest history. You can stay on free indefinitely.",
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
  "Signal Dashboard — all 47 macro signals",
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
  "Continuous watchlist monitoring — we watch, so you don't have to",
  "Alerts when a Confluence Score materially moves — email, Discord, Slack",
  "Portfolio & sector macro-exposure shifts, flagged as they happen",
  "Personalized 7 AM macro digest on your holdings",
  "Score history & regime context (30/60/90 days)",
  "Full digest archive (90 days)",
  "Signal Backtester + factor-exposure dashboard",
  "Early access to new signals",
  "Everything in Free",
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
  const [email,      setEmail]      = useState("");
  const [subStatus,  setSubStatus]  = useState<"idle"|"loading"|"success"|"error">("idle");

  const handleSubscribe = async (e: FormEvent) => {
    e.preventDefault();
    if (!email) return;
    setSubStatus("loading");
    try {
      const res = await fetch("/api/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (res.ok) { setSubStatus("success"); setEmail(""); }
      else { setSubStatus("error"); }
    } catch { setSubStatus("error"); }
  };

  // Scroll-reveal: IntersectionObserver watches every [data-reveal] element
  // and adds .revealed once it enters the viewport. Unobserved after first trigger.
  //
  // FAIL-SAFE (added after the hero was found frozen invisible in production):
  // content must NEVER stay hidden. If the browser lacks IntersectionObserver,
  // reveal everything immediately. And regardless, a short safety timeout reveals
  // anything still hidden, so a mis-fired observer can't blank the page.
  useEffect(() => {
    const revealAll = () =>
      document.querySelectorAll('[data-reveal]:not(.revealed)')
        .forEach((el) => el.classList.add('revealed'));

    if (typeof IntersectionObserver === 'undefined') {
      revealAll();
      return;
    }

    const obs = new IntersectionObserver(
      (entries) =>
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add('revealed');
            obs.unobserve(e.target);
          }
        }),
      { threshold: 0.1, rootMargin: '0px 0px -40px 0px' }
    );
    document.querySelectorAll('[data-reveal]').forEach((el) => obs.observe(el));

    // Safety net: if anything above the fold hasn't revealed shortly after mount
    // (observer edge cases, layout races), force it visible.
    const t = setTimeout(revealAll, 1200);

    return () => { obs.disconnect(); clearTimeout(t); };
  }, []);

  const proPrice    = annual ? 16 : 20;
  const annualTotal = proPrice * 12;

  return (
    <div style={{ minHeight: "100vh", background: T.bg, color: T.bright,
                  fontFamily: "var(--font-geist), Inter, system-ui, sans-serif" }}>

      {/* ── Ambient background glows (fixed so they don't scroll) ── */}
      <div aria-hidden style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0, overflow: "hidden" }}>
        <div aria-hidden className="aurora-1" style={{ position: "absolute", top: -100, left: "50%", transform: "translateX(-50%)",
                                   width: 900, height: 600,
                                   background: "radial-gradient(ellipse at center, rgba(0,213,102,0.09) 0%, transparent 65%)",
                                   filter: "blur(40px)" }} />
        <div aria-hidden className="aurora-2" style={{ position: "absolute", top: 200, right: -100, width: 500, height: 400,
                                   background: "radial-gradient(ellipse at center, rgba(124,58,237,0.08) 0%, transparent 65%)",
                                   filter: "blur(60px)" }} />
        <div aria-hidden className="aurora-3" style={{ position: "absolute", bottom: "20%", left: -80, width: 400, height: 300,
                                   background: "radial-gradient(ellipse at center, rgba(0,200,224,0.07) 0%, transparent 65%)",
                                   filter: "blur(60px)" }} />
      </div>

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

        {/* Grid overlay — subtle depth layer */}
        <div className="hero-grid" aria-hidden />
        {/* Scanning sweep — subtle "live terminal" motion */}
        <div className="hero-scan" aria-hidden />

        {/* Trust pill — glass, glowing, with live signal bars */}
        <div data-reveal className="trust-pill"
             style={{ display: "inline-flex", alignItems: "center", gap: 10,
                      background: "rgba(0,213,102,0.08)", border: "1px solid rgba(0,213,102,0.25)",
                      borderRadius: 100, padding: "6px 16px", fontSize: 12, color: T.green,
                      fontWeight: 600, marginBottom: 28, letterSpacing: "0.04em" }}>
          <span className="sigbars" aria-hidden>
            <i /><i /><i /><i /><i /><i />
          </span>
          Live from FRED · SEC EDGAR · FINRA · EIA · CBOE
        </div>

        <h1 data-reveal data-delay="1"
            className="hero-h1"
            style={{ fontSize: "clamp(40px, 6vw, 72px)", fontWeight: 800,
                     lineHeight: 1.05, letterSpacing: "-0.045em", marginBottom: 22 }}>
          Know what the macro<br />
          <span className="grad">is doing to your stocks.</span>
        </h1>

        <p data-reveal data-delay="2"
           style={{ fontSize: 18, color: T.muted, maxWidth: 560, margin: "0 auto 16px", lineHeight: 1.75 }}>
          47 macro signals — credit spreads, insider flows, energy positioning, Fed indicators —
          scored daily from public data. Free dashboard for active investors.
        </p>

        {/* Positioning subline — lead with what it is; compliance stays secondary */}
        <p data-reveal data-delay="3"
           style={{ fontSize: 14, color: T.dimmer, marginBottom: 44 }}>
          Macro context for the stocks you already hold — educational intelligence, not personalized advice.
        </p>

        {/* CTA row */}
        <div data-reveal data-delay="3"
             className="hero-cta-row"
             style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap", marginBottom: 52 }}>
          <a href={APP_URL} className="btn-primary"
             style={{ background: T.green, color: "#000", padding: "14px 36px",
                      borderRadius: 10, fontSize: 15, fontWeight: 700, display: "inline-block" }}>
            Analyze my portfolio →
          </a>
          <a href="#how-it-works" className="btn-secondary"
             style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
                      color: T.bright, padding: "13px 28px", borderRadius: 10, fontSize: 15,
                      fontWeight: 600, display: "inline-block" }}>
            See How It Works
          </a>
        </div>

        {/* ── Email capture — below-hero ── */}
        <div data-reveal data-delay="4"
             style={{ maxWidth: 460, margin: "0 auto 48px", textAlign: "center" }}>
          <p style={{ fontSize: 12, color: T.dimmer, marginBottom: 10 }}>
            Or get the free weekly macro brief by email — no account needed
          </p>
          <form onSubmit={handleSubscribe}
                style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center" }}>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
              required
              disabled={subStatus === "success"}
              style={{ flex: "1 1 200px", padding: "10px 14px", borderRadius: 8, minWidth: 0,
                       background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.12)",
                       color: T.bright, fontSize: 14, outline: "none" }}
            />
            <button
              type="submit"
              disabled={subStatus === "loading" || subStatus === "success"}
              style={{ padding: "10px 18px", borderRadius: 8, cursor: "pointer",
                       background: "rgba(255,255,255,0.07)", border: "1px solid rgba(255,255,255,0.14)",
                       color: T.bright, fontSize: 14, fontWeight: 600, whiteSpace: "nowrap",
                       opacity: subStatus === "loading" ? 0.6 : 1 }}>
              {subStatus === "loading" ? "..." : subStatus === "success" ? "✓ You're in" : "Subscribe"}
            </button>
          </form>
          {subStatus === "success" && (
            <p style={{ fontSize: 12, color: T.green, marginTop: 8 }}>
              Done. First brief arrives Sunday.
            </p>
          )}
          {subStatus === "error" && (
            <p style={{ fontSize: 12, color: "#ff4444", marginTop: 8 }}>
              Something went wrong — try again.
            </p>
          )}
        </div>

        {/* Stat strip */}
        <div data-reveal data-delay="4"
             className="stat-strip"
             style={{ display: "flex", justifyContent: "center", flexWrap: "wrap",
                      borderTop: "1px solid rgba(255,255,255,0.06)",
                      borderBottom: "1px solid rgba(255,255,255,0.06)",
                      padding: "20px 0" }}>
          {STATS.map((s, i) => (
            <div key={s.label} className="stat-item"
                 style={{ display: "flex", alignItems: "center", padding: "0 28px",
                          borderRight: i < STATS.length - 1 ? "1px solid rgba(255,255,255,0.06)" : "none" }}>
              <div>
                <div style={{ fontSize: 24, fontWeight: 800, color: T.bright, letterSpacing: "-0.04em" }}>{s.value}</div>
                <div style={{ fontSize: 12, color: T.dimmer, marginTop: 3 }}>{s.label}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ─────────────── PRODUCT DEMO — a realistic portfolio change ─────────── */}
      {/* Lead with the ANSWER (what changed around your holdings), not an
          inventory of features. This is the product in one glance. */}
      <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", padding: "64px 24px" }}>
        <div style={{ maxWidth: 720, margin: "0 auto" }} data-reveal>
          <p className="eyebrow" style={{ textAlign: "center" }}>What you&apos;d see</p>
          <h2 className="section-title" data-reveal data-delay="1"
              style={{ textAlign: "center", maxWidth: "100%", marginBottom: 28 }}>
            2 things changed around your watchlist
          </h2>
          <div style={{ background: T.card, border: "1px solid rgba(255,255,255,0.08)",
                        borderRadius: 16, padding: "6px 22px" }}>
            <div style={{ padding: "18px 0", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
                <span style={{ fontSize: 18, fontWeight: 800, color: T.bright }}>NVDA</span>
                <span style={{ fontFamily: "monospace", color: T.muted }}>
                  71 &rarr; <span style={{ color: "#ff5a5a", fontWeight: 700 }}>54</span></span>
                <span style={{ fontSize: 14, color: "#ff8080", fontWeight: 600 }}>Macro support weakened</span>
              </div>
              <div style={{ fontSize: 13, color: T.dimmer, marginTop: 6 }}>
                Real yields &minus;8 &nbsp;·&nbsp; Liquidity &minus;5 &nbsp;·&nbsp; AI capex &minus;3</div>
            </div>
            <div style={{ padding: "18px 0" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
                <span style={{ fontSize: 18, fontWeight: 800, color: T.bright }}>JPM</span>
                <span style={{ fontFamily: "monospace", color: T.muted }}>
                  58 &rarr; <span style={{ color: T.green, fontWeight: 700 }}>67</span></span>
                <span style={{ fontSize: 14, color: T.green, fontWeight: 600 }}>Credit backdrop improved</span>
              </div>
              <div style={{ fontSize: 13, color: T.dimmer, marginTop: 6 }}>
                HY spreads +6 &nbsp;·&nbsp; Financial conditions +3</div>
            </div>
          </div>
          <p style={{ textAlign: "center", fontSize: 14, color: T.dimmer, marginTop: 16 }}>
            Everything else was noise.
          </p>
          <div style={{ textAlign: "center", marginTop: 22 }}>
            <a href={APP_URL} className="btn-primary"
               style={{ background: T.green, color: "#000", padding: "13px 30px",
                        borderRadius: 10, fontSize: 15, fontWeight: 700, display: "inline-block" }}>
              Analyze my watchlist
            </a>
          </div>
        </div>
      </div>

      {/* ─────────────────── SIGNAL PREVIEW ──────────────────────────────────── */}
      <div style={{ borderTop: "1px solid rgba(0,213,102,0.14)",
                    background: "linear-gradient(180deg, rgba(0,213,102,0.035) 0%, transparent 100%)",
                    padding: "60px 24px" }}>
        <div style={{ maxWidth: 860, margin: "0 auto" }} data-reveal>

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

            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {PREVIEW_SIGNALS.map((sig) => (
                <div key={sig.name}
                     className="sig-row"
                     style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px",
                              borderRadius: 8, background: "rgba(255,255,255,0.02)" }}>
                  <span style={{ fontSize: 10, fontWeight: 700, color: T.dimmer, letterSpacing: "0.08em",
                                 textTransform: "uppercase" as const, width: 76, flexShrink: 0 }}>
                    {sig.cat}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, color: T.mid, fontWeight: 500 }}>{sig.name}</div>
                    <div style={{ fontSize: 11, color: T.dimmer, marginTop: 2 }}>{sig.note}</div>
                  </div>
                  <div className="score-track" style={{ width: 110, height: 4, flexShrink: 0 }}>
                    <div className="score-fill"
                         style={{ width: `${sig.score}%`, height: "100%",
                                  background: sig.status === "bull"
                                    ? "linear-gradient(90deg, #00d566, #00c8e0)"
                                    : sig.status === "bear"
                                    ? "linear-gradient(90deg, #ff4444, #ff7777)"
                                    : T.muted }} />
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
          <p className="eyebrow" data-reveal>How it works</p>
          <h2 className="section-title" data-reveal data-delay="1">From public filings to macro context</h2>
          <p className="section-body" data-reveal data-delay="2" style={{ marginBottom: 56 }}>
            Three steps from raw government data to a clear read on whether the macro environment
            supports the stocks you hold.
          </p>

          <div className="grid-3" style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 20 }}>
            {[
              {
                n: "01", title: "47 signals scored daily",
                body: "We pull from FRED, SEC EDGAR, FINRA, EIA, and CBOE. Each signal gets a 0–100 percentile score against its trailing 1-year history. A score of 72 means the current reading is more bullish than 72% of the past year's readings — no arbitrary thresholds.",
                src: "Source: FRED, SEC EDGAR, FINRA, EIA, CBOE",
                delay: "3",
              },
              {
                n: "02", title: "Confluence Score per ticker",
                body: "For each stock in your watchlist, we weight the signals most relevant to its sector into a single Confluence Score. Energy stocks weight crude inventory and rig count differently than a semiconductor company weights hyperscaler capex. Sector-aware, not one-size-fits-all.",
                src: "Updated every ~2 hours",
                delay: "4",
              },
              {
                n: "03", title: "Plain-English regime summary",
                body: "Every day, Today's Brief tells you exactly which signals changed, by how much, and what it means for the macro backdrop — not raw numbers you have to interpret, but actual context. What changed. Why it matters. What to watch next.",
                src: "Available free · No account for Signal Dashboard",
                delay: "5",
              },
            ].map((step) => (
              <div key={step.n} className="hiw-card" data-reveal data-delay={step.delay}>
                <div className="step-num"
                     style={{ width: 38, height: 38, background: "rgba(0,213,102,0.1)",
                              border: "1px solid rgba(0,213,102,0.25)", borderRadius: 10,
                              display: "flex", alignItems: "center", justifyContent: "center",
                              fontSize: 13, fontWeight: 800, color: T.green, letterSpacing: "-0.03em",
                              flexShrink: 0 }}>
                  {step.n}
                </div>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 8, color: T.bright }}>{step.title}</div>
                  <div style={{ fontSize: 14, color: T.muted, lineHeight: 1.72, marginBottom: 10 }}>{step.body}</div>
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
        <div data-reveal
             style={{ maxWidth: 1100, margin: "0 auto", display: "flex", alignItems: "center",
                      gap: 10, flexWrap: "wrap", justifyContent: "center" }}>
          <span style={{ fontSize: 11, color: T.dimmer, fontWeight: 700, letterSpacing: "0.08em",
                         textTransform: "uppercase", flexShrink: 0 }}>Primary sources:</span>
          {SOURCES.map((src) => (
            <span key={src} className="source-chip"
                  style={{ fontSize: 12, fontWeight: 600, color: T.label,
                           background: "rgba(107,127,187,0.07)", border: "1px solid rgba(107,127,187,0.13)",
                           borderRadius: 6, padding: "3px 10px", letterSpacing: "0.02em",
                           display: "inline-block" }}>
              {src}
            </span>
          ))}
        </div>
      </div>

      {/* ─────────────────── FEATURES ────────────────────────────────────────── */}
      <div id="features" style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "80px 24px" }}>
          <p className="eyebrow" data-reveal>Features</p>
          <h2 className="section-title" data-reveal data-delay="1">The macro layer your portfolio is missing</h2>
          <p className="section-body" data-reveal data-delay="2" style={{ marginBottom: 56 }}>
            One dashboard. No Bloomberg required. Free for the core features.
          </p>
          <div className="grid-3" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))", gap: 20 }}>
            {FEATURES.map((f, idx) => (
              <div key={f.title}
                   className="feat-card card"
                   data-reveal
                   data-delay={String((idx % 3) + 1)}
                   style={{
                     background: T.card,
                     border: "1px solid rgba(255,255,255,0.07)",
                     borderRadius: 14,
                     padding: "28px",
                     position: "relative",
                     // CSS custom property for per-card accent glow
                     ["--feat-accent" as string]: `${f.accent}18`,
                     ["--feat-accent-border" as string]: `${f.accent}40`,
                   }}>
                {f.pro && (
                  <span className="badge badge-purple" style={{ position: "absolute", top: 16, right: 16 }}>
                    Pro ⚡
                  </span>
                )}
                {/* Icon with accent tint bg */}
                <div style={{ width: 48, height: 48, borderRadius: 12,
                              background: `${f.accent}12`,
                              border: `1px solid ${f.accent}28`,
                              display: "flex", alignItems: "center", justifyContent: "center",
                              fontSize: 22, marginBottom: 16 }}>
                  {f.icon}
                </div>
                <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8, letterSpacing: "-0.02em",
                              background: `linear-gradient(90deg, ${T.bright} 0%, ${f.accent} 100%)`,
                              WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
                              display: "inline-block" }}>
                  {f.title}
                </div>
                <div style={{ fontSize: 14, color: T.muted, lineHeight: 1.72, marginBottom: 12 }}>{f.body}</div>
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

            {/* Honest positioning — one confident line, not a wall of negatives. */}
            <div style={{ borderLeft: "1px solid rgba(255,255,255,0.06)", paddingLeft: 40,
                          display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <p className="eyebrow" style={{ color: T.label }}>What it is</p>
              <h2 className="section-title" style={{ marginBottom: 14, fontSize: "clamp(18px, 2vw, 24px)" }}>
                A macro context layer — not stock tips
              </h2>
              <p style={{ fontSize: 15, color: T.muted, lineHeight: 1.75 }}>
                Unstructured Alpha maps the economic environment around the stocks you hold and tells you
                when it materially changes. It&apos;s the interpretation layer between raw macro data and
                your own decisions &mdash; educational and informational, not personalized advice, price
                targets, or trade signals.
              </p>
            </div>

          </div>
        </div>
      </div>

      {/* ─────────────────── PRICING ─────────────────────────────────────────── */}
      <div id="pricing" style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", padding: "80px 24px" }}>
          <p className="eyebrow" style={{ textAlign: "center" }} data-reveal>Pricing</p>
          <h2 className="section-title" data-reveal data-delay="1"
              style={{ textAlign: "center", maxWidth: "100%", marginBottom: 12 }}>
            Start free. Go deeper with Pro.
          </h2>
          <p className="section-body" data-reveal data-delay="2"
             style={{ textAlign: "center", margin: "0 auto 36px" }}>
            Free tells you what the macro is doing now. Pro watches it for you — and tells you the moment the backdrop around one of your holdings materially changes.
          </p>

          {/* Billing toggle */}
          <div data-reveal data-delay="3"
               style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 12, marginBottom: 44 }}>
            <span style={{ fontSize: 14, color: annual ? T.dimmer : T.bright, fontWeight: annual ? 400 : 600 }}>
              Monthly
            </span>
            <button
              onClick={() => setAnnual(!annual)}
              aria-label="Toggle annual billing"
              className="billing-toggle"
              style={{ width: 44, height: 24, background: annual ? T.purple : "rgba(255,255,255,0.12)",
                       borderRadius: 100, border: "none", cursor: "pointer", position: "relative",
                       flexShrink: 0 }}
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
            <div className="price-card-free"
                 data-reveal data-delay="3"
                 style={{ background: T.card, border: "1px solid rgba(255,255,255,0.08)",
                          borderRadius: 16, padding: "32px" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.muted, letterSpacing: "0.1em",
                            textTransform: "uppercase" as const, marginBottom: 12 }}>
                Free
              </div>
              <div style={{ fontSize: 44, fontWeight: 800, letterSpacing: "-0.05em", marginBottom: 4 }}>$0</div>
              <div style={{ fontSize: 13, color: T.dimmer, marginBottom: 28 }}>Free forever · No card required</div>
              <ul className="checklist" style={{ marginBottom: 28 }}>
                {FREE_FEATURES.map((f) => (
                  <li key={f}><span className="check">✓</span><span>{f}</span></li>
                ))}
                {FREE_LOCKED.map((f) => (
                  <li key={f} style={{ opacity: 0.45 }}><span className="locked">—</span><span>{f}</span></li>
                ))}
              </ul>
              <a href={APP_URL} className="btn-secondary"
                 style={{ display: "block", textAlign: "center", padding: "13px", borderRadius: 10,
                          border: "1px solid rgba(255,255,255,0.12)", color: T.bright, fontSize: 14,
                          fontWeight: 600 }}>
                Start for free →
              </a>
            </div>

            {/* Pro — animated gradient border wrapper */}
            <div className="pro-card-wrap" data-reveal data-delay="4" style={{ position: "relative" }}>
              {/* "Most popular" pill floats above the gradient border */}
              <div style={{ position: "absolute", top: -12, left: "50%", transform: "translateX(-50%)",
                            background: T.purple, color: "#fff", fontSize: 11, fontWeight: 700,
                            padding: "3px 14px", borderRadius: 100, letterSpacing: "0.08em",
                            textTransform: "uppercase" as const, whiteSpace: "nowrap" as const, zIndex: 10 }}>
                Most popular
              </div>
              <div className="pro-card-inner" style={{ padding: "32px", position: "relative" }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: T.muted, letterSpacing: "0.1em",
                              textTransform: "uppercase" as const, marginBottom: 12 }}>
                  Pro
                </div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 4 }}>
                  <div style={{ fontSize: 44, fontWeight: 800, letterSpacing: "-0.05em" }}>${proPrice}</div>
                  <span style={{ fontSize: 14, color: T.dimmer }}>/ month</span>
                </div>
                <div style={{ fontSize: 13, color: T.dimmer, marginBottom: 16 }}>
                  {annual
                    ? `Billed $${annualTotal}/year · cancel anytime`
                    : "Per month · cancel anytime · 7-day free trial"}
                </div>
                <div style={{ fontSize: 13, color: T.bright, lineHeight: 1.6, marginBottom: 22,
                              paddingLeft: 12, borderLeft: "2px solid #7c3aed" }}>
                  Don&apos;t miss the moment the macro backdrop around one of your holdings materially changes.
                </div>
                <ul className="checklist" style={{ marginBottom: 28 }}>
                  {PRO_FEATURES.map((f) => (
                    <li key={f} style={{ color: "#c4c9e0" }}>
                      <span style={{ color: "#a78bfa", flexShrink: 0, marginTop: 1, fontSize: 13 }}>✓</span>
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
                <a href={`${APP_URL}/pages/29_Upgrade`}
                   style={{ display: "block", textAlign: "center", padding: "13px", borderRadius: 10,
                            background: T.purple, color: "#fff", fontSize: 14, fontWeight: 700,
                            transition: "all 0.2s ease", boxShadow: "0 4px 20px rgba(124,58,237,0.35)" }}>
                  Start 7-Day Free Trial ⚡
                </a>
                <p style={{ fontSize: 11, color: T.dimmer, textAlign: "center", marginTop: 10 }}>
                  No charge until trial ends · Cancel anytime
                </p>
              </div>
            </div>

          </div>

          {/* Real-competitor anchor: fragmented research, not a terminal */}
          <p data-reveal style={{ textAlign: "center", fontSize: 13, color: T.dimmer, marginTop: 28, maxWidth: 640, marginLeft: "auto", marginRight: "auto", lineHeight: 1.7 }}>
            You could track all of this yourself — across FRED, SEC EDGAR, FINRA, EIA and CBOE,
            in a dozen browser tabs and a spreadsheet. We built the interpretation layer, for $20/month.
          </p>
        </div>
      </div>

      {/* ─────────────────── FAQ ─────────────────────────────────────────────── */}
      <div id="faq" style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <div style={{ maxWidth: 720, margin: "0 auto", padding: "80px 24px" }}>
          <p className="eyebrow" style={{ textAlign: "center" }} data-reveal>FAQ</p>
          <h2 className="section-title" data-reveal data-delay="1"
              style={{ textAlign: "center", maxWidth: "100%", marginBottom: 48 }}>
            Questions we get asked
          </h2>
          <div data-reveal data-delay="2" style={{ display: "flex", flexDirection: "column" }}>
            {FAQ_ITEMS.map((item, i) => (
              <div key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  style={{ width: "100%", textAlign: "left", padding: "20px 0", background: "none",
                           border: "none", cursor: "pointer", display: "flex",
                           justifyContent: "space-between", alignItems: "center", gap: 16 }}
                >
                  <span style={{ fontSize: 15, fontWeight: 600, color: openFaq === i ? T.bright : T.mid,
                                 transition: "color 0.2s ease" }}>
                    {item.q}
                  </span>
                  <span style={{ color: openFaq === i ? T.green : T.dimmer,
                                 fontSize: 20, flexShrink: 0, lineHeight: 1,
                                 transform: openFaq === i ? "rotate(45deg)" : "none",
                                 transition: "transform 0.25s ease, color 0.2s ease",
                                 display: "inline-block", fontWeight: 300 }}>
                    +
                  </span>
                </button>
                {/* CSS-animated answer — always rendered, height animated via class */}
                <div className={`faq-answer${openFaq === i ? " open" : ""}`}
                     style={{ fontSize: 14, color: T.muted, lineHeight: 1.8 }}>
                  {item.a}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ─────────────────── CLOSING CTA ─────────────────────────────────────── */}
      <div style={{ background: "linear-gradient(180deg, rgba(0,213,102,0.04) 0%, transparent 60%)",
                    borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <div style={{ maxWidth: 680, margin: "0 auto", padding: "96px 24px", textAlign: "center" }}>
          <h2 data-reveal
              style={{ fontSize: "clamp(28px, 4vw, 48px)", fontWeight: 800,
                       letterSpacing: "-0.04em", marginBottom: 18, lineHeight: 1.08 }}>
            Start understanding<br />
            <span style={{ background: "linear-gradient(90deg, #00d566, #00c8e0, #7c3aed)",
                           WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              your macro environment.
            </span>
          </h2>
          <p data-reveal data-delay="1"
             style={{ fontSize: 17, color: T.muted, marginBottom: 40, lineHeight: 1.7,
                      maxWidth: 460, margin: "0 auto 40px" }}>
            Free to start. No credit card. 47 live signals, updated every ~2 hours,
            from the same public data sources institutional desks use.
          </p>
          <div data-reveal data-delay="2">
            <a href={APP_URL} className="btn-primary"
               style={{ background: T.green, color: "#000", padding: "16px 44px", borderRadius: 12,
                        fontSize: 16, fontWeight: 800, display: "inline-block", letterSpacing: "-0.01em" }}>
              Open the Dashboard — Free →
            </a>
            <div style={{ marginTop: 16, fontSize: 13, color: T.dimmer }}>
              Free · No card · 47 signals · Updated every ~2h · Cancel Pro anytime
            </div>
          </div>

          {/* ── Closing email capture ── */}
          <div data-reveal data-delay="3"
               style={{ marginTop: 40, padding: "24px 28px",
                        background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)",
                        borderRadius: 12, maxWidth: 480, margin: "40px auto 0" }}>
            <p style={{ fontSize: 14, fontWeight: 600, color: T.mid, marginBottom: 6 }}>
              Not ready to sign up? Get the weekly brief.
            </p>
            <p style={{ fontSize: 13, color: T.dimmer, marginBottom: 16, lineHeight: 1.6 }}>
              Sunday morning: which signals moved, what changed, what to watch.
              Free. No account. Unsubscribe anytime.
            </p>
            <form onSubmit={handleSubscribe}
                  style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="your@email.com"
                required
                disabled={subStatus === "success"}
                style={{ flex: "1 1 180px", padding: "10px 14px", borderRadius: 8, minWidth: 0,
                         background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.12)",
                         color: T.bright, fontSize: 14, outline: "none" }}
              />
              <button
                type="submit"
                disabled={subStatus === "loading" || subStatus === "success"}
                style={{ padding: "10px 18px", borderRadius: 8, cursor: "pointer",
                         background: T.purple, border: "none",
                         color: "#fff", fontSize: 14, fontWeight: 700,
                         opacity: subStatus === "loading" ? 0.6 : 1 }}>
                {subStatus === "loading" ? "..." : subStatus === "success" ? "✓ Subscribed" : "Get Brief"}
              </button>
            </form>
            {subStatus === "success" && (
              <p style={{ fontSize: 12, color: T.green, marginTop: 10 }}>
                You're subscribed. See you Sunday.
              </p>
            )}
          </div>

          {/* Disclaimer */}
          <div data-reveal data-delay="3"
               style={{ marginTop: 32, padding: "16px 20px", background: "rgba(255,255,255,0.02)",
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
                Macro signal intelligence for active investors. 47 signals scored daily
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
