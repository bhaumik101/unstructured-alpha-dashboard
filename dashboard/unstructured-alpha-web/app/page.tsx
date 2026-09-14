'use client';

import { useState } from 'react';
import Link from 'next/link';
import './landing.css';

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
  const body = JSON.stringify({ event: "app_opened", page: "Landing", action });
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

// The economic series the exposure report measures against, mirroring
// FACTORS + GROWTH_FACTOR in dashboard/utils/exposure.py. A test asserts this
// list matches the engine, so the page cannot advertise a series it doesn't use.
const DATA_SERIES = [
  { id: "DGS10", label: "10-year Treasury yield" },
  { id: "T10YIE", label: "10-year inflation expectations" },
  { id: "DTWEXBGS", label: "Trade-weighted U.S. dollar" },
  { id: "DCOILWTICO", label: "WTI crude oil price" },
  { id: "BAA10Y", label: "Baa corporate bond spread" },
  { id: "INDPRO", label: "Industrial production (monthly)" },
];

// A real report, computed 2026-09-14 by the same engine on data through
// 2026-09-04. Kept as a dated example rather than a live number so the page
// never shows something stale as current.
const SAMPLE = {
  name: "Balanced ETF portfolio",
  holdings: "40% VTI · 20% VXUS · 30% BND · 5% TIP · 5% GLD",
  window: "156 weeks, Sept 2023 to Sept 2026",
  rows: [
    { label: "Interest rates", shock: "the 10-year yield rose 0.25 points", impact: -0.66, low: -0.73, high: -0.59, evidence: "Clear", driver: "Mostly BND (bonds)" },
    { label: "U.S. dollar", shock: "the dollar rose 2%", impact: -0.73, low: -0.86, high: -0.61, evidence: "Clear", driver: "Mostly VXUS (international stocks)" },
    { label: "Inflation expectations", shock: "inflation expectations rose 0.25 points", impact: 0.40, low: 0.18, high: 0.62, evidence: "Clear", driver: "Mostly VTI (U.S. stocks)" },
    { label: "Credit spreads", shock: "credit spreads widened 0.25 points", impact: -0.17, low: -0.38, high: 0.03, evidence: "Not distinguishable from zero", driver: "No measurable link" },
    { label: "Oil and energy", shock: "oil rose 10%", impact: -0.08, low: -0.16, high: 0.01, evidence: "Not distinguishable from zero", driver: "No measurable link" },
  ],
};

const EVIDENCE = [
  { label: "Clear", body: "Strong enough to hold up even after allowing for testing five factors at once." },
  { label: "Tentative", body: "Suggestive, but could plausibly be noise. Worth watching, not relying on." },
  { label: "Not distinguishable from zero", body: "The measured relationship is within the range of random noise." },
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

// ─── Components ───────────────────────────────────────────────────────────────

const SCALE = 1.0; // percent at each end of the bar

function ExposureBar({ impact, low, high }: { impact: number; low: number; high: number }) {
  const pos = (v: number) => 50 + (Math.max(-SCALE, Math.min(SCALE, v)) / SCALE) * 50;
  const left = Math.min(pos(0), pos(impact));
  const width = Math.abs(pos(impact) - pos(0));
  return (
    <div className="lp-bar" aria-hidden="true">
      <div className="lp-bar-axis" />
      <div className="lp-bar-fill"
           style={{ left: `${left}%`, width: `${width}%`,
                    background: impact >= 0 ? "var(--lp-pos)" : "var(--lp-neg)" }} />
      <div className="lp-bar-whisker" style={{ left: `${pos(low)}%`, width: `${pos(high) - pos(low)}%` }} />
    </div>
  );
}

function pct(v: number): string {
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}%`;
}

export default function Home() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const toggleTheme = () => {
    const current = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem("ua-theme", next);
  };

  const sampleUrl = (action: AppOpenAction) => appUrl("/", action, { sample: "balanced" });

  return (
    <div className="lp">
      <a href="#main" className="sr-only">Skip to content</a>

      {/* ── Nav ─────────────────────────────────────────────────────────── */}
      <nav className="lp-nav" aria-label="Main">
        <div className="lp-wrap lp-nav-inner">
          <Link href="/" className="lp-brand">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.svg" alt="" width={26} height={26} />
            Unstructured Alpha
          </Link>
          <div className="lp-nav-links">
            <a href="#how-it-works">How it works</a>
            <a href={`${APP_URL}/methodology`}>Methodology</a>
            <a href={`${APP_URL}/research`}>Research</a>
            <a href="#pricing">Pricing</a>
            <a href="#faq">FAQ</a>
            <button type="button" className="lp-theme" onClick={toggleTheme}
                    aria-label="Switch between light and dark theme">Theme</button>
            <a href={sampleUrl("nav")} onClick={() => recordAppOpen("nav")}
               className="lp-btn lp-btn-primary lp-btn-sm">Try a sample report</a>
          </div>
          <button type="button" className="lp-menu-btn" aria-expanded={mobileOpen}
                  aria-controls="lp-mobile" onClick={() => setMobileOpen(!mobileOpen)}>
            Menu
          </button>
        </div>
        <div id="lp-mobile" className={`lp-mobile${mobileOpen ? " open" : ""}`}>
          <a href="#how-it-works" onClick={() => setMobileOpen(false)}>How it works</a>
          <a href={`${APP_URL}/methodology`}>Methodology</a>
          <a href={`${APP_URL}/research`}>Research</a>
          <a href="#pricing" onClick={() => setMobileOpen(false)}>Pricing</a>
          <a href="#faq" onClick={() => setMobileOpen(false)}>FAQ</a>
          <button type="button" onClick={toggleTheme}>Switch light / dark theme</button>
          <a href={sampleUrl("mobile_nav")} onClick={() => recordAppOpen("mobile_nav")}>Try a sample report</a>
        </div>
      </nav>

      <main id="main">
        {/* ── Hero ──────────────────────────────────────────────────────── */}
        <section className="lp-wrap lp-hero">
          <p className="lp-eyebrow">Portfolio exposure, measured with the uncertainty shown</p>
          <h1 className="lp-h1">See which economic forces your portfolio is actually exposed to.</h1>
          <p className="lp-lead">
            Enter your holdings and see how the portfolio has moved with interest rates, inflation,
            the dollar, oil and credit spreads, which holdings cause it, and how sure we can be.
            Built for advisers who need to explain portfolio risk to clients.
          </p>
          <div className="lp-cta-row">
            <a href={sampleUrl("hero_sample")} onClick={() => recordAppOpen("hero_sample")}
               className="lp-btn lp-btn-primary">Try a sample portfolio</a>
            <a href={appUrl("/", "hero_own")} onClick={() => recordAppOpen("hero_own")}
               className="lp-btn lp-btn-secondary">Use my own holdings</a>
          </div>
          <p className="lp-small" style={{ marginTop: 14 }}>
            Free · No account needed for your first report · Not a forecast, not investment advice
          </p>
        </section>

        {/* ── Sample report ─────────────────────────────────────────────── */}
        <section className="lp-wrap" style={{ paddingBottom: 72 }} aria-labelledby="sample-title">
          <div className="lp-report">
            <div className="lp-report-head">
              <div>
                <div id="sample-title" className="lp-report-title">Example report: {SAMPLE.name}</div>
                <div className="lp-small">{SAMPLE.holdings}</div>
              </div>
              <div className="lp-legend">
                <span><span className="lp-swatch" style={{ background: "var(--lp-pos)" }} />Moves up with the factor</span>
                <span><span className="lp-swatch" style={{ background: "var(--lp-neg)" }} />Moves down with the factor</span>
                <span>Thin line: 90% range</span>
              </div>
            </div>
            {SAMPLE.rows.map((r) => (
              <div key={r.label} className="lp-row">
                <div>
                  <div className="lp-row-label">{r.label}</div>
                  <div className="lp-row-shock">In weeks when {r.shock}</div>
                </div>
                <ExposureBar impact={r.impact} low={r.low} high={r.high} />
                <div>
                  <div className="lp-row-value">{pct(r.impact)}</div>
                  <div className="lp-row-range">range {pct(r.low)} to {pct(r.high)}</div>
                </div>
                <div className="lp-row-driver">
                  <span className={`lp-chip${r.evidence === "Clear" ? " lp-chip-clear" : ""}`}>{r.evidence}</span>
                  <div className="lp-small" style={{ marginTop: 4 }}>{r.driver}</div>
                </div>
              </div>
            ))}
            <div className="lp-report-foot">
              Each figure is the portfolio&apos;s typical same-week move when that force moved by the stated
              amount, after accounting for the stock market. Measured over {SAMPLE.window}. It describes the
              past; it is not a forecast. Example computed September 14, 2026; not your portfolio.
            </div>
          </div>
          <div style={{ marginTop: 16 }}>
            <a href={sampleUrl("report_sample")} onClick={() => recordAppOpen("report_sample")}
               className="lp-btn lp-btn-secondary lp-btn-sm">Open the full sample report</a>
          </div>
        </section>

        {/* ── How it works ──────────────────────────────────────────────── */}
        <section id="how-it-works" className="lp-section">
          <div className="lp-wrap">
            <p className="lp-eyebrow">How it works</p>
            <h2 className="lp-h2">From holdings to a plain-English report in about a minute</h2>
            <div className="lp-grid-3">
              <div>
                <div className="lp-step-n">1</div>
                <h3 className="lp-h3">Enter holdings</h3>
                <p className="lp-body">Paste tickers with weights, upload a CSV, or start from a sample. Stocks and ETFs both work.</p>
              </div>
              <div>
                <div className="lp-step-n">2</div>
                <h3 className="lp-h3">We measure</h3>
                <p className="lp-body">Three years of weekly returns are compared with weekly changes in five economic series from the Federal Reserve, with the stock market accounted for.</p>
              </div>
              <div>
                <div className="lp-step-n">3</div>
                <h3 className="lp-h3">You read it plainly</h3>
                <p className="lp-body">Each exposure shows its size, a 90% range, the weeks of data used, the holdings behind it, and how strong the evidence is.</p>
              </div>
            </div>
          </div>
        </section>

        {/* ── Evidence labels ───────────────────────────────────────────── */}
        <section className="lp-section">
          <div className="lp-wrap">
            <p className="lp-eyebrow">Every number is labelled</p>
            <h2 className="lp-h2">We tell you how much to trust each result</h2>
            <p className="lp-body lp-narrow">
              Statistics can make noise look meaningful. Each exposure carries one of four labels, and the
              bar for &ldquo;Clear&rdquo; is raised because five factors are tested at once.
            </p>
            <div className="lp-evidence">
              {EVIDENCE.map((e) => (
                <div key={e.label}>
                  <span className={`lp-chip${e.label === "Clear" ? " lp-chip-clear" : e.label === "Tentative" ? " lp-chip-tentative" : ""}`}>{e.label}</span>
                  <p>{e.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── What it isn't + who it's for ──────────────────────────────── */}
        <section className="lp-section">
          <div className="lp-wrap lp-grid-2" style={{ marginTop: 0 }}>
            <div>
              <p className="lp-eyebrow">What this is not</p>
              <h2 className="lp-h2">Not a forecast. Not a stock pick.</h2>
              <p className="lp-body">
                We spent months testing whether macro data could predict markets. It could not do so
                reliably, and we publish those failed tests rather than hide them. So this product measures
                what a portfolio is exposed to today and says nothing about what happens next.
              </p>
              <p className="lp-body" style={{ marginTop: 14 }}>
                <a href={`${APP_URL}/research`} style={{ color: "var(--lp-accent)", fontWeight: 600 }}>Read the research record</a>
                {"  ·  "}
                <a href={`${APP_URL}/methodology`} style={{ color: "var(--lp-accent)", fontWeight: 600 }}>Read the methodology</a>
              </p>
            </div>
            <div>
              <p className="lp-eyebrow">Who it is for</p>
              <h2 className="lp-h2">Advisers first</h2>
              <p className="lp-body">
                <strong>Independent advisers and small RIAs:</strong> show a client, on one page, why their
                portfolio moves when rates or oil move and which holdings cause it.
              </p>
              <p className="lp-body" style={{ marginTop: 12 }}>
                <strong>Self-directed investors:</strong> check whether a portfolio that looks diversified
                is quietly concentrated in one economic force.
              </p>
            </div>
          </div>
        </section>

        {/* ── Data ──────────────────────────────────────────────────────── */}
        <section className="lp-section">
          <div className="lp-wrap">
            <p className="lp-eyebrow">Data</p>
            <h2 className="lp-h2">Public sources, named</h2>
            <p className="lp-body lp-narrow">
              Prices from Yahoo Finance, adjusted for dividends. Economic series from the Federal Reserve Bank
              of St. Louis (FRED):
            </p>
            <ul className="lp-body" style={{ marginTop: 12, paddingLeft: 20 }}>
              {DATA_SERIES.map((s) => (
                <li key={s.id}>{s.label} <span className="lp-small">({s.id})</span></li>
              ))}
            </ul>
          </div>
        </section>

        {/* ── Pricing ───────────────────────────────────────────────────── */}
        <section id="pricing" className="lp-section">
          <div className="lp-wrap">
            <p className="lp-eyebrow">Pricing</p>
            <h2 className="lp-h2">Early-access pricing</h2>
            <p className="lp-body lp-narrow">
              These prices are being tested with early users and may change. Features marked &ldquo;in
              development&rdquo; are not available yet.
            </p>
            <div className="lp-prices">
              <div className="lp-price">
                <div className="lp-price-name">Free</div>
                <div className="lp-price-amount">$0</div>
                <div className="lp-small">No card, no account for your first report</div>
                <ul>
                  <li>Exposure report for one portfolio, up to 15 holdings</li>
                  <li>Holdings behind each exposure</li>
                  <li>Range and evidence label on every number</li>
                  <li>Save one portfolio with a free account</li>
                  <li>Public methodology and research record</li>
                </ul>
                <a href={appUrl("/", "free_plan")} onClick={() => recordAppOpen("free_plan")}
                   className="lp-btn lp-btn-secondary">Start free</a>
              </div>
              <div className="lp-price">
                <div className="lp-price-name">Investor Pro</div>
                <div className="lp-price-amount">$20<span className="lp-small"> / month</span></div>
                <div className="lp-small">Cancel anytime</div>
                <ul>
                  <li>Measure up to 25 holdings per portfolio</li>
                  <li>Everything in Free</li>
                </ul>
                <div className="lp-price-sub">In development</div>
                <ul style={{ marginTop: 6 }}>
                  <li>Weekly &ldquo;what changed&rdquo; email</li>
                  <li>Exposure threshold alerts</li>
                  <li>PDF export and multiple portfolios</li>
                </ul>
                <a href={appUrl("/upgrade-to-pro", "pro_plan")} onClick={() => recordAppOpen("pro_plan")}
                   className="lp-btn lp-btn-secondary">See Investor Pro</a>
              </div>
              <div className="lp-price">
                <div className="lp-price-name">Advisor pilot</div>
                <div className="lp-price-amount">$149<span className="lp-small"> / month</span></div>
                <div className="lp-small">Small pilot · first month free</div>
                <ul>
                  <li>Reports for multiple client portfolios</li>
                  <li>Client-ready explanations for review meetings</li>
                  <li>Built with you: tell us what your clients ask</li>
                </ul>
                <a href={`mailto:${PILOT_EMAIL}?subject=Advisor%20pilot`} onClick={() => recordAppOpen("advisor_pilot")}
                   className="lp-btn lp-btn-primary">Ask about the pilot</a>
              </div>
            </div>
          </div>
        </section>

        {/* ── FAQ ───────────────────────────────────────────────────────── */}
        <section id="faq" className="lp-section">
          <div className="lp-wrap lp-narrow lp-faq">
            <p className="lp-eyebrow">FAQ</p>
            <h2 className="lp-h2">Questions</h2>
            {FAQ_ITEMS.map((item) => (
              <details key={item.q}>
                <summary>{item.q}</summary>
                <p>{item.a}</p>
              </details>
            ))}
          </div>
        </section>

        {/* ── Closing ───────────────────────────────────────────────────── */}
        <section className="lp-section">
          <div className="lp-wrap">
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
          <div style={{ fontWeight: 650, color: "var(--lp-ink)" }}>Unstructured Alpha</div>
          <div className="lp-footer-links">
            <a href={appUrl("/", "footer")} onClick={() => recordAppOpen("footer")}>Exposure report</a>
            <a href={`${APP_URL}/methodology`}>Methodology</a>
            <a href={`${APP_URL}/research`}>Research</a>
            <a href="#pricing">Pricing</a>
            <a href={`${APP_URL}/privacy-terms`}>Privacy &amp; Terms</a>
          </div>
          <p style={{ maxWidth: 820 }}>
            Unstructured Alpha is an educational and informational tool. Nothing on this site is personalized
            financial, investment, tax or legal advice, or a recommendation to buy, sell or hold any security.
            Exposure figures describe how portfolios have moved in the past; relationships change and past
            behaviour does not guarantee future results.
          </p>
          <p style={{ marginTop: 12 }}>© {new Date().getFullYear()} Unstructured Alpha</p>
        </div>
      </footer>
    </div>
  );
}
