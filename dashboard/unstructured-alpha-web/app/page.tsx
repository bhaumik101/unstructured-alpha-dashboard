'use client';

import { useState } from 'react';
import Link from 'next/link';
import './landing.css';
import LiveMovers from './LiveMovers';
import LiveStats from './LiveStats';
import HeroXray from './HeroXray';
import DailyChallenge from './DailyChallenge';

const APP_URL = "https://app.unstructuredalpha.com";
const PILOT_EMAIL = "support@unstructuredalpha.com";

type AppOpenAction =
  | "nav"
  | "mobile_nav"
  | "hero_sample"
  | "hero_own"
  | "report_sample"
  | "free_plan"
  | "pro_plan"
  | "advisor_pilot"
  | "closing"
  | "footer";

function appUrl(path: string, action: AppOpenAction, params: Record<string, string> = {}): string {
  const url = new URL(`${APP_URL}${path}`);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  url.searchParams.set("utm_source", "marketing_landing");
  url.searchParams.set("utm_medium", "owned");
  url.searchParams.set("utm_campaign", "exposure_report");
  url.searchParams.set("utm_content", action);
  return url.toString();
}

function recordAppOpen(action: AppOpenAction) {
  const internal = (window as unknown as { __uaInternal?: boolean }).__uaInternal || undefined;
  const body = JSON.stringify({ event: "app_opened", page: "Landing", action, internal });
  try {
    if (navigator.sendBeacon) {
      navigator.sendBeacon("/api/track", new Blob([body], { type: "application/json" }));
    } else {
      void fetch("/api/track", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        keepalive: true,
      });
    }
  } catch {
    // Measurement must never block the visitor from entering the product.
  }
}

// ─── Data ─────────────────────────────────────────────────────────────────────

type FactorKey = "rates" | "inflation" | "dollar" | "oil" | "credit" | "growth";
type Evidence = "Clear" | "Tentative" | "Not distinguishable from zero" | "Not enough data";

// The economic series the exposure report measures against, mirroring
// FACTORS + GROWTH_FACTOR in dashboard/utils/exposure.py. A test asserts this
// list matches the engine, so the page cannot advertise a series it doesn't use.
const DATA_SERIES: { id: string; label: string; key: FactorKey; name: string }[] = [
  { id: "DGS10", label: "10-year Treasury yield", key: "rates", name: "Interest rates" },
  { id: "T10YIE", label: "10-year inflation expectations", key: "inflation", name: "Inflation expectations" },
  { id: "DTWEXBGS", label: "Trade-weighted U.S. dollar", key: "dollar", name: "U.S. dollar" },
  { id: "DCOILWTICO", label: "WTI crude oil price", key: "oil", name: "Oil and energy" },
  { id: "BAA10Y", label: "Baa corporate bond spread", key: "credit", name: "Credit spreads" },
  { id: "INDPRO", label: "Industrial production (monthly)", key: "growth", name: "Economic growth" },
];

// A real report: the app's "balanced" sample, computed by the same engine on
// data through 2026-11-13 (156 weeks from 2023-11-24), copied from the stored
// report rather than typed in. Kept as a dated example, not a live number, so
// the page never shows something stale as current; the date is on screen.
// `holders`: each holding's share of that exposure (report "contributions"),
// the ones adding to it; a holding pushing the other way is left out.
const SAMPLE = {
  name: "Balanced ETF portfolio",
  holdings: [["VTI", 40], ["BND", 30], ["VXUS", 20], ["GLD", 5], ["TIP", 5]] as [string, number][],
  asOf: "Nov 13, 2026",
  window: "156 weeks, Nov 2023 to Nov 2026",
  rows: [
    { key: "dollar" as FactorKey, label: "U.S. dollar", shock: "the dollar rose 2%", unit: "dollar +2%", impact: -0.71, low: -0.83, high: -0.58, evidence: "Clear" as Evidence,
      holders: [["VXUS", 78], ["GLD", 23], ["BND", 1]] as [string, number][] },
    { key: "rates" as FactorKey, label: "Interest rates", shock: "the 10-year yield rose 0.25 points", unit: "yield +0.25 pt", impact: -0.62, low: -0.70, high: -0.54, evidence: "Clear" as Evidence,
      holders: [["BND", 74], ["TIP", 12], ["VTI", 12], ["GLD", 3]] as [string, number][] },
    { key: "inflation" as FactorKey, label: "Inflation expectations", shock: "inflation expectations rose 0.25 points", unit: "breakeven +0.25 pt", impact: 0.32, low: 0.08, high: 0.56, evidence: "Tentative" as Evidence,
      holders: [["VTI", 41], ["VXUS", 33], ["TIP", 23], ["BND", 13]] as [string, number][] },
    { key: "credit" as FactorKey, label: "Credit spreads", shock: "credit spreads widened 0.25 points", unit: "Baa spread +0.25 pt", impact: -0.17, low: -0.37, high: 0.04, evidence: "Not distinguishable from zero" as Evidence,
      holders: [] as [string, number][] },
    { key: "oil" as FactorKey, label: "Oil and energy", shock: "oil rose 10%", unit: "oil +10%", impact: -0.10, low: -0.17, high: -0.03, evidence: "Tentative" as Evidence,
      holders: [["VXUS", 97], ["VTI", 18]] as [string, number][] },
  ],
};

const EVIDENCE: { label: Evidence; body: string }[] = [
  { label: "Clear", body: "Strong enough to hold up even after allowing for testing five factors at once." },
  { label: "Tentative", body: "Suggestive, but could plausibly be noise. Worth watching, not relying on." },
  { label: "Not distinguishable from zero", body: "The measured relationship is within the range of random noise. Not the same as no exposure." },
  { label: "Not enough data", body: "Too little price history to measure reliably, so nothing is shown." },
];

const FAQ_ITEMS = [
  {
    q: "Is this a forecast?",
    a: "No. Every number describes how a portfolio has moved alongside an economic force over the past three years. Relationships change, so it is a description of exposure, not a prediction of returns. We tested whether this kind of data could predict markets and found it could not; those results are published on the research page.",
  },
  {
    q: "How is exposure calculated?",
    a: "We compare three years of weekly portfolio returns with weekly changes in interest rates, inflation expectations, the dollar, oil and credit spreads, while accounting for the overall stock market. Each result comes with a 90% range, the number of weeks used, and an evidence label. Growth is measured separately on monthly data and is always marked as limited evidence.",
  },
  {
    q: "Why account for the stock market?",
    a: "Rates, oil and the dollar often move on the same days stocks do. Without separating that out, almost every stock portfolio would look sensitive to everything. The report shows what is left after the market's own movement is removed.",
  },
  {
    q: "What does \"Not distinguishable from zero\" mean?",
    a: "It means the measured relationship is small enough that it could be random noise. We show it rather than hide it, because knowing a portfolio is not meaningfully exposed to something is useful too.",
  },
  {
    q: "Do I need an account?",
    a: "Not for your first report. A free account lets you save a portfolio and come back to it.",
  },
  {
    q: "Can advisers use this with clients?",
    a: "That is who we are building it for. We are running a small pilot with independent advisers to learn what a client-ready report needs. If you are an adviser, get in touch below.",
  },
  {
    q: "Is this investment advice?",
    a: "No. Unstructured Alpha is an educational and informational tool. It does not know your circumstances and does not recommend buying or selling anything.",
  },
  {
    q: "Where does the data come from?",
    a: "Economic series come from the Federal Reserve Bank of St. Louis (FRED). Prices come from Yahoo Finance and include dividends. If a series or price history is unavailable, it is left out and named in the report, never filled in.",
  },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function pct(v: number): string {
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}%`;
}

function evClass(label: string): string {
  if (label === "Clear") return "lp-ev lp-ev-clear";
  if (label === "Tentative") return "lp-ev lp-ev-tent";
  if (label === "Not enough data") return "lp-ev lp-ev-nodata";
  return "lp-ev lp-ev-zero";
}

// Shorter label in the dense panel; the full wording is the title and the
// accessible name, so "uncertain" is never shown as "zero".
function evShort(label: Evidence): string {
  return label === "Not distinguishable from zero" ? "Not distinguishable" : label;
}

function EvidenceChip({ label, short = false }: { label: Evidence; short?: boolean }) {
  return (
    <span className={evClass(label)} title={label} aria-label={`Evidence: ${label}`}>
      <i aria-hidden="true" />{short ? evShort(label) : label}
    </span>
  );
}

// ─── Graphics ─────────────────────────────────────────────────────────────────

const SCALE = 1.0;   // percent at each end of the panel's axis; every row shares it

/**
 * One row's diverging bar on a shared axis: the estimate as a bar from zero,
 * the 90% range as a thin line with end caps. Direction is position plus the
 * sign printed beside it; the fill says how strong the evidence is (solid,
 * lighter, outline), so neither colour nor shape carries meaning alone.
 */
function DivergingBar({ impact, low, high, evidence }: { impact: number; low: number; high: number; evidence: Evidence }) {
  const pos = (v: number) => 50 + (Math.max(-SCALE, Math.min(SCALE, v)) / SCALE) * 50;
  const left = Math.min(pos(0), pos(impact));
  const width = Math.abs(pos(impact) - pos(0));
  const tone = evidence === "Clear" ? "is-clear" : evidence === "Tentative" ? "is-tent" : "is-zero";
  return (
    <div className="lp-dbar" aria-hidden="true">
      <span className="lp-dbar-zero" />
      <span className={`lp-dbar-fill ${tone} ${impact < 0 ? "is-neg" : "is-pos"}`} style={{ left: `${left}%`, width: `${width}%` }} />
      <span className="lp-dbar-range" style={{ left: `${pos(low)}%`, width: `${pos(high) - pos(low)}%` }} />
    </div>
  );
}

/** The sample report as the product draws it: the hero's centrepiece. */
function SamplePanel() {
  return (
    <figure className="lp-panel" aria-labelledby="lp-panel-title">
      <div className="lp-panel-top">
        <div>
          <p className="lp-panel-kicker">Sample report · data through {SAMPLE.asOf}</p>
          <h2 id="lp-panel-title" className="lp-panel-title">{SAMPLE.name}</h2>
        </div>
        <ul className="lp-panel-holdings" aria-label="Holdings and weights">
          {SAMPLE.holdings.map(([t, w]) => <li key={t}><b>{t}</b>{w}%</li>)}
        </ul>
      </div>
      <p className="lp-panel-take">
        Clearly sensitive to the <b>U.S. dollar</b> and <b>interest rates</b>. VXUS carries most of the dollar
        exposure; BND most of the rate exposure.
      </p>
      <div className="lp-ptable" role="table" aria-label="Exposure to each economic force">
        <div className="lp-prow lp-prow-head" role="row">
          <span role="columnheader">Force</span>
          <span role="columnheader" className="lp-paxis"><span>−1%</span><span>0</span><span>+1%</span></span>
          <span role="columnheader" className="lp-num">Estimate</span>
          <span role="columnheader">Evidence</span>
        </div>
        {SAMPLE.rows.map((r) => (
          <div key={r.key} className="lp-prow" role="row">
            <span role="cell" className="lp-pforce">
              <i className={`lp-fdot f-${r.key}`} aria-hidden="true" />
              <span><b>{r.label}</b><small title={`In weeks when ${r.shock}`}>per {r.unit}</small></span>
            </span>
            <span role="cell" className="lp-pbar"><DivergingBar {...r} /></span>
            <span role="cell" className="lp-num lp-pest"><b>{pct(r.impact)}</b><small>{pct(r.low)} to {pct(r.high)}</small></span>
            <span role="cell"><EvidenceChip label={r.evidence} short /></span>
          </div>
        ))}
      </div>
      <figcaption className="lp-panel-foot">
        Typical same-week move beyond the stock market when each force moved by the stated amount, with its 90%
        range. {SAMPLE.window}. The past, not a forecast.
      </figcaption>
    </figure>
  );
}

/** Who carries each exposure: one 100% strip per force, from the sample's contributions. */
function Holders() {
  const shown = SAMPLE.rows.filter((r) => r.holders.length);
  const tone: Record<string, string> = { VTI: "h1", BND: "h2", VXUS: "h3", GLD: "h4", TIP: "h5" };
  return (
    <div className="lp-holders">
      <ul className="lp-holders-key" aria-label="Holdings">
        {SAMPLE.holdings.map(([t, w]) => <li key={t}><i className={`lp-h ${tone[t]}`} aria-hidden="true" />{t} <span>{w}%</span></li>)}
      </ul>
      {shown.map((r) => {
        return (
          <div key={r.key} className="lp-hrow">
            <div className="lp-hrow-name">
              <i className={`lp-fdot f-${r.key}`} aria-hidden="true" /><b>{r.label}</b>
              <span className="lp-num">{pct(r.impact)}</span><EvidenceChip label={r.evidence} short />
            </div>
            <div className="lp-hstrip" role="img"
                 aria-label={`${r.label}: ${r.holders.map(([t, s]) => `${t} ${s}%`).join(", ")} of the exposure`}>
              {r.holders.map(([t, s]) => (
                <span key={t} className={`lp-h ${tone[t]}`} style={{ flexGrow: s }}><b>{t}</b> {s}%</span>
              ))}
            </div>
          </div>
        );
      })}
      <p className="lp-small">
        Each holding&rsquo;s share of the exposure. A holding that pushes the other way is not drawn, so the
        shares shown can add to more than 100%. Credit spreads are left out: that reading is not
        distinguishable from zero.
      </p>
    </div>
  );
}

function Mini({ kind }: { kind: "report" | "scenario" | "drivers" | "evidence" }) {
  if (kind === "report") {
    return (
      <div className="lp-mini lp-mini-report" aria-hidden="true">
        {SAMPLE.rows.slice(0, 3).map((r) => (
          <div key={r.key}><i className={`lp-fdot f-${r.key}`} /><DivergingBar {...r} /><b className="lp-num">{pct(r.impact)}</b></div>
        ))}
      </div>
    );
  }
  if (kind === "scenario") {
    return (
      <div className="lp-mini lp-mini-scenario" aria-hidden="true">
        {["Market", "Interest rates", "U.S. dollar"].map((l, i) => (
          <div key={l}><span>{l}</span><span className="lp-mini-track"><i style={{ left: `${[62, 70, 38][i]}%` }} /></span></div>
        ))}
      </div>
    );
  }
  if (kind === "drivers") {
    // Shape only: a waterfall's anatomy, with no figures, so it cannot be read as a result.
    return (
      <svg className="lp-mini lp-mini-drivers" viewBox="0 0 200 72" aria-hidden="true">
        <line x1="0" y1="40" x2="200" y2="40" className="lp-mini-axis" />
        {[[8, 14, 26], [44, 14, 10], [80, 24, 8], [116, 32, 10], [152, 14, 26]].map(([x, y, h], i) => (
          <rect key={i} x={x} y={y} width="30" height={h} rx="3" className={i === 4 ? "lp-mini-total" : "lp-mini-step"} />
        ))}
      </svg>
    );
  }
  return (
    <div className="lp-mini lp-mini-ev" aria-hidden="true">
      <EvidenceChip label="Clear" /><EvidenceChip label="Tentative" /><EvidenceChip label="Not distinguishable from zero" short />
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

// The public tools, mirroring utils/tools_page.py (same hrefs and icons).
const FREE_TOOLS: { href: string; title: string; blurb: string; icon: React.ReactNode }[] = [
  { href: "/xray", title: "Portfolio X-ray", blurb: "Click the stocks and funds you own. See in seconds how the mix moves with the economy, and what drives it.",
    icon: <><rect x="4" y="4" width="16" height="16" rx="3" /><path d="M8 15l3-4 2 2 3-5" /></> },
  { href: "/exposure", title: "Stocks", blurb: "Every stock against rates, inflation, the dollar, oil and credit. Filter by sector or by what held up.",
    icon: <path d="M4 6h16M4 12h16M4 18h10" /> },
  { href: "/etfs", title: "ETFs", blurb: "Bond, sector, dividend and commodity funds: how each moved with rates, inflation, the dollar, oil and credit.",
    icon: <><circle cx="12" cy="12" r="8" /><path d="M12 4v8l6 4" /></> },
  { href: "/sectors", title: "Sector heatmap", blurb: "How each sector moved with each force. Click a cell for the stocks behind it.",
    icon: <><rect x="4" y="4" width="7" height="7" rx="1" /><rect x="13" y="4" width="7" height="7" rx="1" /><rect x="4" y="13" width="7" height="7" rx="1" /><rect x="13" y="13" width="7" height="7" rx="1" /></> },
  { href: "/map", title: "Stock map", blurb: "Every stock on any two forces at once. Light up a sector, find a ticker.",
    icon: <><circle cx="8" cy="15" r="2" /><circle cx="15" cy="8" r="2" /><circle cx="17" cy="16" r="2" /><path d="M4 4v16h16" /></> },
  { href: "/scenario", title: "Build a scenario", blurb: "Move all five forces at once, or pick one like an inflation scare.",
    icon: <><path d="M5 6h14M5 12h14M5 18h14" /><circle cx="9" cy="6" r="2" /><circle cx="15" cy="12" r="2" /><circle cx="11" cy="18" r="2" /></> },
  { href: "/compare", title: "Compare two stocks", blurb: "Two stocks on one scale, and where they clearly differ.",
    icon: <><path d="M8 4v16M16 4v16" /><circle cx="8" cy="9" r="2" /><circle cx="16" cy="15" r="2" /></> },
  { href: "/heatmap", title: "Market heatmap", blurb: "Every stock as a tile, coloured by how it moved with oil, rates or any force.",
    icon: <><rect x="3" y="4" width="10" height="7" rx="1" /><rect x="15" y="4" width="6" height="7" rx="1" /><rect x="3" y="13" width="6" height="7" rx="1" /><rect x="11" y="13" width="10" height="7" rx="1" /></> },
];

export default function Home() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const toggleTheme = () => {
    const current = document.documentElement.dataset.theme === "light" ? "light" : "dark";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem("ua-theme", next);
  };

  const sampleUrl = (action: AppOpenAction) => appUrl("/", action, { sample: "balanced" });

  return (
    <div className="lp">
      <a href="#main" className="sr-only">Skip to content</a>

      {/* ── Hero: the one dark, dramatic surface ─────────────────────────── */}
      <div className="lp-hero-band">
        <nav className="lp-nav" aria-label="Main">
          <div className="lp-wrap lp-nav-inner">
            <Link href="/" className="lp-brand" aria-label="Unstructured Alpha home">
              UNSTRUCTURED <span>ALPHA</span>
            </Link>
            <div className="lp-nav-links">
              <a href="#how-it-works">How it works</a>
              <a href="/tools">Free tools</a>
              <a href={`${APP_URL}/methodology`}>Methodology</a>
              <a href={`${APP_URL}/research`}>Research</a>
              <a href="#pricing">Pricing</a>
              {/* The app's own toggle: it names the theme you would switch TO.
                  Both labels render and CSS shows the right one, so the server
                  HTML and the stored theme can never disagree at hydration. */}
              <button type="button" className="lp-theme" onClick={toggleTheme}
                      aria-label="Switch between light and dark theme">
                <span className="lp-theme-to-dark"><span aria-hidden="true">&#9789;</span>DARK</span>
                <span className="lp-theme-to-light"><span aria-hidden="true">&#9788;</span>LIGHT</span>
              </button>
              <a href={sampleUrl("nav")} onClick={() => recordAppOpen("nav")}
                 className="lp-btn lp-btn-primary lp-btn-sm">Try a sample report</a>
            </div>
            <button type="button" className="lp-menu-btn" aria-expanded={mobileOpen}
                    aria-controls="lp-mobile" onClick={() => setMobileOpen(!mobileOpen)}>
              <span aria-hidden="true" className="lp-menu-icon" />Menu
            </button>
          </div>
          <div id="lp-mobile" className={`lp-mobile${mobileOpen ? " open" : ""}`}>
            <a href="#how-it-works" onClick={() => setMobileOpen(false)}>How it works</a>
            <a href="/tools">Free tools</a>
            <a href={`${APP_URL}/methodology`}>Methodology</a>
            <a href={`${APP_URL}/research`}>Research</a>
            <a href="#pricing" onClick={() => setMobileOpen(false)}>Pricing</a>
            <a href="#faq" onClick={() => setMobileOpen(false)}>FAQ</a>
            <button type="button" onClick={toggleTheme}>Switch light / dark theme</button>
            <a href={sampleUrl("mobile_nav")} onClick={() => recordAppOpen("mobile_nav")}>Try a sample report</a>
          </div>
        </nav>

        <header className="lp-wrap lp-hero">
          <div className="lp-hero-copy">
            <p className="lp-kicker">Portfolio exposure · measured weekly</p>
            <h1 className="lp-h1">See the forces inside your portfolio.</h1>
            <p className="lp-lead">
              Measure how your holdings have moved with rates, inflation, the dollar, oil and credit&mdash;with
              the uncertainty shown.
            </p>
            <div className="lp-cta-row">
              <a href={sampleUrl("hero_sample")} onClick={() => recordAppOpen("hero_sample")}
                 className="lp-btn lp-btn-primary">Try a sample portfolio</a>
              <a href={appUrl("/", "hero_own")} onClick={() => recordAppOpen("hero_own")}
                 className="lp-textlink">Use my own holdings <span aria-hidden="true">→</span></a>
            </div>
            <form className="lp-lookup" action="/go" method="get" role="search">
              <label htmlFor="lp-lookup-t">Or look up one stock</label>
              <div className="lp-lookup-row">
                <input id="lp-lookup-t" name="t" placeholder="AAPL" autoComplete="off"
                       spellCheck={false} maxLength={15} />
                <button type="submit" aria-label="See its exposure"><span aria-hidden="true">→</span></button>
              </div>
            </form>
            <p className="lp-hero-facts">Free · No account for your first report · Not a forecast, not investment advice</p>
          </div>
          <div className="lp-hero-art">
            <SamplePanel />
          </div>
        </header>
        <LiveStats />
      </div>

      <main id="main">
        {/* ── Inside the sample: who carries each exposure ───────────────── */}
        <section className="lp-section" aria-labelledby="sample-title">
          <div className="lp-wrap lp-split">
            <div>
              <p className="lp-kicker">Inside the report</p>
              <h2 id="sample-title" className="lp-h2">Every exposure, traced to the holdings behind it.</h2>
              <p className="lp-body">
                In the sample, BND carries 74% of the measured rate exposure and VXUS 78% of the dollar
                exposure. The report shows this for every force, with the evidence for each holding, so you can
                see what to look at before you change anything.
              </p>
              <a href={sampleUrl("report_sample")} onClick={() => recordAppOpen("report_sample")}
                 className="lp-btn lp-btn-secondary">Open the full sample report</a>
            </div>
            <Holders />
          </div>
        </section>

        {/* ── Try it live ──────────────────────────────────────────────────── */}
        <section className="lp-section lp-tone" aria-labelledby="try-title">
          <div className="lp-wrap lp-split lp-split-try">
            <div>
              <p className="lp-kicker">Try it now</p>
              <h2 id="try-title" className="lp-h2">Click a mix. See its fingerprint.</h2>
              <p className="lp-body">
                Pick a starter mix or add the tickers you hold. Equal weight, readings from this week&rsquo;s
                data. For weights, balancing and the holdings behind each force, open the full X-ray or the report.
              </p>
            </div>
            <HeroXray fallback={<p className="lp-body">The live X-ray could not load. <a className="lp-textlink" href="/xray">Open the Portfolio X-ray →</a></p>} />
          </div>
        </section>

        {/* ── How it works ──────────────────────────────────────────────── */}
        <section id="how-it-works" className="lp-section">
          <div className="lp-wrap">
            <p className="lp-kicker">How it works</p>
            <h2 className="lp-h2">From holdings to a plain-English report in about a minute.</h2>
            <ol className="lp-steps">
              <li>
                <span className="lp-step-n">01</span>
                <h3 className="lp-h3">Enter holdings</h3>
                <p className="lp-body">Paste tickers with weights, upload a CSV, or start from a sample. Stocks and ETFs both work.</p>
              </li>
              <li>
                <span className="lp-step-n">02</span>
                <h3 className="lp-h3">We measure</h3>
                <p className="lp-body">Three years of weekly returns are compared with weekly changes in five core economic series from the Federal Reserve, and 14 more forces measured beyond them, with the stock market accounted for.</p>
              </li>
              <li>
                <span className="lp-step-n">03</span>
                <h3 className="lp-h3">You read it plainly</h3>
                <p className="lp-body">Each exposure shows its size, a 90% range, the weeks of data used, the holdings behind it, and how strong the evidence is.</p>
              </li>
            </ol>
          </div>
        </section>

        {/* ── Capabilities ──────────────────────────────────────────────── */}
        <section id="tools" className="lp-section lp-section-tight">
          <div className="lp-wrap">
            <p className="lp-kicker">What you can do with it</p>
            <h2 className="lp-h2">One measurement, four ways to use it.</h2>
            <div className="lp-caps">
              <a className="lp-cap" href={`${APP_URL}/`}>
                <Mini kind="report" />
                <h3 className="lp-h3">Exposure report</h3>
                <p className="lp-body">What a portfolio has moved with, force by force, with a range, an evidence label and the holdings behind each one.</p>
                <span className="lp-textlink">Open the report →</span>
              </a>
              <a className="lp-cap" href={`${APP_URL}/scenarios`}>
                <Mini kind="scenario" />
                <h3 className="lp-h3">Scenario lab</h3>
                <p className="lp-body">Move the stock market and any of 19 forces, and see the estimated move with its range, what each force contributed, and which holdings carry it.</p>
                <span className="lp-textlink">Run a stress test →</span>
              </a>
              <a className="lp-cap" href={`${APP_URL}/`}>
                <Mini kind="drivers" />
                <h3 className="lp-h3">What drove returns</h3>
                <p className="lp-body">The last 4 to 52 weeks broken into the market, each force, and what none of them explains, adding up to the total.</p>
                <span className="lp-textlink">See it in the report →</span>
              </a>
              <a className="lp-cap" href="/evidence">
                <Mini kind="evidence" />
                <h3 className="lp-h3">Does it hold up?</h3>
                <p className="lp-body">How readings measured this way held up over the following year, out of sample, across the S&amp;P 500 — published whatever it shows.</p>
                <span className="lp-textlink">Read the track record →</span>
              </a>
            </div>
          </div>
        </section>

        {/* ── The library: free tools, the live demo, the daily games ─────── */}
        <section className="lp-section lp-tone" aria-labelledby="free-title">
          <div className="lp-wrap">
            <p className="lp-kicker">Free, no account</p>
            <h2 id="free-title" className="lp-h2">The same measurement, one stock at a time.</h2>
            <p className="lp-body lp-narrow">
              S&amp;P 500 companies and popular funds, measured weekly with the same engine. Look one up, try a
              move, or test what you think you know &mdash; then measure your own portfolio the same way.
            </p>
            <ul className="lp-library">
              {FREE_TOOLS.map((t) => (
                <li key={t.href}>
                  <a href={t.href}>
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth={1.6}
                         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{t.icon}</svg>
                    <b>{t.title}</b>
                    <span>{t.blurb}</span>
                  </a>
                </li>
              ))}
            </ul>
            <a className="lp-textlink" href="/tools">All free tools →</a>
          </div>
        </section>
        <LiveMovers />
        <DailyChallenge />

        {/* ── Evidence and method ──────────────────────────────────────── */}
        <section className="lp-section" aria-labelledby="evidence-title">
          <div className="lp-wrap lp-split lp-split-even">
            <div>
              <p className="lp-kicker">Every number is labelled</p>
              <h2 id="evidence-title" className="lp-h2">We tell you how much to trust each result.</h2>
              <p className="lp-body">
                Statistics can make noise look meaningful. Each exposure carries one of four labels, and the bar
                for &ldquo;Clear&rdquo; is raised because five factors are tested at once.
              </p>
              <a className="lp-textlink" href="/learn">How to read a result, with a playground →</a>
            </div>
            <dl className="lp-evlist">
              {EVIDENCE.map((e) => (
                <div key={e.label}>
                  <dt><EvidenceChip label={e.label} /></dt>
                  <dd>{e.body}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="lp-wrap lp-split lp-split-even lp-not">
            <div>
              <p className="lp-kicker">What this is not</p>
              <h3 className="lp-h3 lp-h3-lg">Not a forecast. Not a stock pick.</h3>
              <p className="lp-body">
                We spent months testing whether macro data could predict markets. It could not do so
                reliably, and we publish those failed tests rather than hide them. So this product measures
                what a portfolio is exposed to today and says nothing about what happens next.
              </p>
              <p className="lp-links">
                <a className="lp-textlink" href={`${APP_URL}/research`}>Read the research record →</a>
                <a className="lp-textlink" href={`${APP_URL}/methodology`}>Read the methodology →</a>
              </p>
            </div>
            <div>
              <p className="lp-kicker">Who it is for</p>
              <h3 className="lp-h3 lp-h3-lg">Advisers first.</h3>
              <p className="lp-body">
                <strong>Independent advisers and small RIAs:</strong> show a client, on one page, why their
                portfolio moves when rates or oil move and which holdings cause it.
              </p>
              <p className="lp-body">
                <strong>Self-directed investors:</strong> check whether a portfolio that looks diversified
                is quietly concentrated in one economic force.
              </p>
            </div>
          </div>
        </section>

        {/* ── Data: a reference layout, not six cards ─────────────────────── */}
        <section className="lp-section lp-tone" aria-labelledby="data-title">
          <div className="lp-wrap lp-split lp-split-even">
            <div>
              <p className="lp-kicker">Data</p>
              <h2 id="data-title" className="lp-h2">19 economic forces, from public sources</h2>
              <p className="lp-body">
                Prices from Yahoo Finance, adjusted for dividends. Economic series from the Federal Reserve Bank
                of St. Louis (FRED). The five core forces and economic growth are listed here; 14 more are measured
                beyond the core five: short-term rates, market volatility, mortgage rates, gold, copper, natural
                gas, bitcoin, small vs large companies, value vs growth, momentum, the euro, the yen, emerging
                markets and China.
              </p>
            </div>
            <table className="lp-series">
              <caption className="sr-only">Core economic series</caption>
              <thead><tr><th scope="col">Force</th><th scope="col">Series</th><th scope="col">FRED code</th></tr></thead>
              <tbody>
                {DATA_SERIES.map((s) => (
                  <tr key={s.id}>
                    <th scope="row"><i className={`lp-fdot f-${s.key}`} aria-hidden="true" />{s.name}</th>
                    <td>{s.label}</td>
                    <td><code>{s.id}</code></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* ── Pricing ───────────────────────────────────────────────────── */}
        <section id="pricing" className="lp-section">
          <div className="lp-wrap">
            <p className="lp-kicker">Pricing</p>
            <h2 className="lp-h2">Early-access pricing</h2>
            <p className="lp-body lp-narrow">These prices are being tested with early users and may change.</p>
            <div className="lp-prices">
              <div className="lp-price">
                <div className="lp-price-name">Free</div>
                <div className="lp-price-amount">$0</div>
                <div className="lp-small">No card, no account for your first report</div>
                <a href={appUrl("/", "free_plan")} onClick={() => recordAppOpen("free_plan")}
                   className="lp-btn lp-btn-secondary">Start free</a>
                <ul>
                  <li>Exposure report for one portfolio, up to 15 holdings</li>
                  <li>Holdings behind each exposure</li>
                  <li>Range and evidence label on every number</li>
                  <li>Save one portfolio with a free account</li>
                  <li>A weekly email when its exposures change</li>
                  <li>Public methodology and research record</li>
                </ul>
              </div>
              <div className="lp-price">
                <div className="lp-price-name">Investor Pro</div>
                <div className="lp-price-amount">$20<span className="lp-small"> / month</span></div>
                <div className="lp-small">Cancel anytime</div>
                <a href={appUrl("/pricing", "pro_plan")} onClick={() => recordAppOpen("pro_plan")}
                   className="lp-btn lp-btn-secondary">See Investor Pro</a>
                <ul>
                  <li>Measure up to 60 holdings per portfolio, instead of 15</li>
                  <li>Save up to 3 portfolios and switch between them</li>
                  <li>A one-page client summary, ready to print or save as a PDF</li>
                  <li>Download the report&rsquo;s numbers as a CSV</li>
                  <li>Alerts when an exposure crosses a line you set</li>
                  <li>Everything in Free</li>
                </ul>
              </div>
              <div className="lp-price lp-price-feature">
                <div className="lp-price-name">Advisor pilot <span className="lp-price-tag">For advisers</span></div>
                <div className="lp-price-amount">$149<span className="lp-small"> / month</span></div>
                <div className="lp-small">Small pilot · first month free</div>
                <a href={`mailto:${PILOT_EMAIL}?subject=Advisor%20pilot`} onClick={() => recordAppOpen("advisor_pilot")}
                   className="lp-btn lp-btn-secondary">Ask about the pilot</a>
                <ul>
                  <li>Unlimited client portfolios, saved and switched from the report</li>
                  <li>Client-ready explanations for review meetings</li>
                  <li>Built with you: tell us what your clients ask</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* ── FAQ ───────────────────────────────────────────────────────── */}
        <section id="faq" className="lp-section lp-tone">
          <div className="lp-wrap lp-split lp-split-faq">
            <div>
              <p className="lp-kicker">FAQ</p>
              <h2 className="lp-h2">Questions</h2>
            </div>
            <div className="lp-faq">
              {FAQ_ITEMS.map((item) => (
                <details key={item.q}>
                  <summary>{item.q}</summary>
                  <p>{item.a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        {/* ── Closing ───────────────────────────────────────────────────── */}
        <section className="lp-closing">
          <div className="lp-wrap lp-closing-inner">
            <h2 className="lp-h2">See what a portfolio is exposed to.</h2>
            <p className="lp-body">Start with a sample, or paste your own holdings. It takes about a minute.</p>
            <div className="lp-cta-row">
              <a href={sampleUrl("closing")} onClick={() => recordAppOpen("closing")}
                 className="lp-btn lp-btn-primary">Try a sample portfolio</a>
            </div>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-wrap">
          <div className="lp-footer-brand">UNSTRUCTURED <span>ALPHA</span></div>
          <div className="lp-footer-links">
            <a href={appUrl("/", "footer")} onClick={() => recordAppOpen("footer")}>Exposure report</a>
            <a href={`${APP_URL}/methodology`}>Methodology</a>
            <a href={`${APP_URL}/research`}>Research</a>
            <a href="#pricing">Pricing</a>
            <a href="#faq">FAQ</a>
            <a href={`${APP_URL}/privacy-terms`}>Privacy &amp; Terms</a>
          </div>
          <p>
            Unstructured Alpha is an educational and informational tool. Nothing on this site is personalized
            financial, investment, tax or legal advice, or a recommendation to buy, sell or hold any security.
            Exposure figures describe how portfolios have moved in the past; relationships change and past
            behaviour does not guarantee future results.
          </p>
          <p>© {new Date().getFullYear()} Unstructured Alpha</p>
        </div>
      </footer>
    </div>
  );
}
