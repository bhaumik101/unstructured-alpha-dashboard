import type { Metadata } from "next";
import Link from "next/link";

const APP_URL =
  "https://app.unstructuredalpha.com/?utm_source=uranium_landing&utm_medium=organic&utm_campaign=uranium_wedge";

export const metadata: Metadata = {
  // The layout template adds " | Unstructured Alpha"; writing it here too doubled it.
  title: "Macro Signals for Uranium & Nuclear Stocks",
  description:
    "Track the macro backdrop around uranium and nuclear stocks including CCJ, LEU, UEC, CEG, and VST. See what changed, which holdings are exposed, and why it matters.",
  alternates: { canonical: "https://www.unstructuredalpha.com/uranium" },
  openGraph: {
    title: "Macro Signals for Uranium & Nuclear Stocks",
    description:
      "See when the macro backdrop around uranium and nuclear holdings materially changes.",
    url: "https://www.unstructuredalpha.com/uranium",
    siteName: "Unstructured Alpha",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Macro Signals for Uranium & Nuclear Stocks",
    description:
      "See when the macro backdrop around uranium and nuclear holdings materially changes.",
  },
};

const tickers = ["CCJ", "LEU", "UEC", "CEG", "VST"];

const signals = [
  {
    title: "Energy and commodity pressure",
    body: "Separate a uranium-company thesis from the broader energy, inflation, and commodity regime surrounding it.",
  },
  {
    title: "Credit and risk appetite",
    body: "See when credit spreads, volatility, and liquidity conditions become a tailwind or a warning for higher-beta names.",
  },
  {
    title: "Policy and demand context",
    body: "Connect public macro and regulatory data to the utilities, miners, and fuel-cycle companies most exposed to a changing regime.",
  },
];

const changes = [
  { label: "Credit stress eased", impact: "Supports speculative risk appetite", score: "+12" },
  { label: "Energy inflation accelerated", impact: "Raises sector sensitivity", score: "+8" },
  { label: "Volatility regime stayed mixed", impact: "Keeps conviction below maximum", score: "0" },
];

const shell: React.CSSProperties = {
  minHeight: "100vh",
  background: "#0b0d12",
  color: "#e8eaf2",
  fontFamily: "var(--font-geist), Inter, system-ui, sans-serif",
};
const container: React.CSSProperties = { maxWidth: 1120, margin: "0 auto", padding: "0 24px" };
const card: React.CSSProperties = {
  background: "linear-gradient(180deg, rgba(24,29,42,.94), rgba(16,20,30,.94))",
  border: "1px solid rgba(255,255,255,.08)",
  borderRadius: 18,
};

export default function UraniumLandingPage() {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "WebPage",
    name: "Macro Signals for Uranium and Nuclear Stocks",
    url: "https://www.unstructuredalpha.com/uranium",
    description:
      "A focused macro-monitoring page for uranium and nuclear equity investors.",
    isPartOf: { "@type": "WebSite", name: "Unstructured Alpha", url: "https://www.unstructuredalpha.com" },
  };

  return (
    <main style={shell}>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />

      <header style={{ borderBottom: "1px solid rgba(255,255,255,.07)" }}>
        <div style={{ ...container, height: 68, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Link href="/" style={{ color: "#e8eaf2", textDecoration: "none", fontWeight: 800, letterSpacing: "-.02em" }}>
            Unstructured <span style={{ color: "#00d566" }}>Alpha</span>
          </Link>
          <a href={APP_URL} style={{ color: "#0b0d12", background: "#00d566", padding: "10px 16px", borderRadius: 9, fontWeight: 800, textDecoration: "none", fontSize: 14 }}>
            Check a stock free
          </a>
        </div>
      </header>

      <section style={{ position: "relative", overflow: "hidden", padding: "92px 0 72px" }}>
        <div aria-hidden style={{ position: "absolute", width: 700, height: 500, left: "50%", top: -230, transform: "translateX(-50%)", background: "radial-gradient(circle, rgba(0,213,102,.14), transparent 66%)", filter: "blur(22px)" }} />
        <div style={{ ...container, position: "relative", display: "grid", gridTemplateColumns: "minmax(0,1.05fr) minmax(340px,.95fr)", gap: 56, alignItems: "center" }} className="uranium-hero-grid">
          <div>
            <div style={{ color: "#00d566", fontSize: 12, fontWeight: 800, letterSpacing: ".12em", textTransform: "uppercase", marginBottom: 18 }}>
              Built for uranium and nuclear investors
            </div>
            <h1 style={{ fontSize: "clamp(42px,6vw,72px)", lineHeight: 1.02, letterSpacing: "-.055em", margin: 0, maxWidth: 760 }}>
              Know when the macro backdrop around your nuclear stocks changes.
            </h1>
            <p style={{ color: "#aeb7cc", fontSize: 19, lineHeight: 1.65, maxWidth: 680, margin: "24px 0 30px" }}>
              Unstructured Alpha turns public macro, credit, energy, volatility, and disclosure data into a clear context layer for the companies you already follow.
            </p>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <a href={APP_URL} style={{ color: "#07110b", background: "#00d566", padding: "14px 22px", borderRadius: 10, fontWeight: 850, textDecoration: "none" }}>
                Check a nuclear stock free →
              </a>
              <a href="#how-it-works" style={{ color: "#e8eaf2", border: "1px solid rgba(255,255,255,.13)", padding: "13px 20px", borderRadius: 10, fontWeight: 700, textDecoration: "none" }}>
                See how it works
              </a>
            </div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 30 }}>
              {tickers.map((ticker) => (
                <span key={ticker} style={{ border: "1px solid rgba(255,255,255,.09)", background: "rgba(255,255,255,.035)", borderRadius: 999, padding: "7px 12px", color: "#b8c0d4", fontFamily: "ui-monospace, SFMono-Regular, monospace", fontSize: 13 }}>
                  {ticker}
                </span>
              ))}
            </div>
          </div>

          <div style={{ ...card, padding: 24, boxShadow: "0 24px 80px rgba(0,0,0,.4)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
              <div>
                <div style={{ color: "#7b86a2", fontSize: 11, textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 800 }}>Example portfolio change</div>
                <div style={{ fontSize: 20, fontWeight: 800, marginTop: 6 }}>What changed around your holdings</div>
              </div>
              <span style={{ color: "#00d566", background: "rgba(0,213,102,.1)", border: "1px solid rgba(0,213,102,.25)", borderRadius: 999, padding: "5px 9px", fontSize: 11, fontWeight: 800 }}>2 high-impact</span>
            </div>
            <div style={{ display: "grid", gap: 12 }}>
              {changes.map((change) => (
                <div key={change.label} style={{ padding: "14px 14px 14px 16px", borderLeft: `3px solid ${change.score === "0" ? "#6b7280" : "#00d566"}`, background: "rgba(255,255,255,.025)", borderRadius: "0 10px 10px 0" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 16, fontWeight: 750 }}>
                    <span>{change.label}</span><span style={{ color: change.score === "0" ? "#8892aa" : "#00d566", fontFamily: "ui-monospace, monospace" }}>{change.score}</span>
                  </div>
                  <div style={{ color: "#8892aa", fontSize: 13, marginTop: 5 }}>{change.impact}</div>
                </div>
              ))}
            </div>
            <p style={{ color: "#59627a", fontSize: 11, lineHeight: 1.55, margin: "16px 0 0" }}>
              Illustrative interface. Unstructured Alpha provides research context, not personalized investment advice or a price forecast.
            </p>
          </div>
        </div>
      </section>

      <section id="how-it-works" style={{ padding: "78px 0", borderTop: "1px solid rgba(255,255,255,.06)" }}>
        <div style={container}>
          <div style={{ maxWidth: 720, marginBottom: 36 }}>
            <div style={{ color: "#00d566", fontSize: 12, fontWeight: 800, letterSpacing: ".11em", textTransform: "uppercase" }}>A sharper research workflow</div>
            <h2 style={{ fontSize: "clamp(30px,4vw,48px)", letterSpacing: "-.04em", lineHeight: 1.08, margin: "12px 0" }}>Stop tracking the sector in disconnected tabs.</h2>
            <p style={{ color: "#929db5", lineHeight: 1.7, fontSize: 17 }}>The product does not predict the uranium price. It shows whether multiple pieces of the surrounding macro environment are aligning, weakening, or contradicting one another.</p>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: 16 }} className="uranium-card-grid">
            {signals.map((signal, index) => (
              <article key={signal.title} style={{ ...card, padding: 26 }}>
                <div style={{ width: 34, height: 34, borderRadius: 10, background: "rgba(0,213,102,.1)", color: "#00d566", display: "grid", placeItems: "center", fontWeight: 900, marginBottom: 20 }}>{index + 1}</div>
                <h3 style={{ fontSize: 19, margin: "0 0 10px" }}>{signal.title}</h3>
                <p style={{ color: "#929db5", lineHeight: 1.65, margin: 0 }}>{signal.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section style={{ padding: "76px 0" }}>
        <div style={{ ...container }}>
          <div style={{ ...card, padding: "clamp(28px,5vw,54px)", display: "grid", gridTemplateColumns: "1.1fr .9fr", gap: 40, alignItems: "center" }} className="uranium-cta-grid">
            <div>
              <div style={{ color: "#00d566", fontSize: 12, fontWeight: 800, letterSpacing: ".11em", textTransform: "uppercase" }}>Start with the stocks you already own</div>
              <h2 style={{ fontSize: "clamp(30px,4vw,48px)", letterSpacing: "-.04em", lineHeight: 1.08, margin: "12px 0" }}>Add one ticker. See the macro forces behind it.</h2>
              <p style={{ color: "#929db5", fontSize: 17, lineHeight: 1.7, margin: 0 }}>The free account includes the signal dashboard, Today&apos;s Brief, and ticker deep dives. No card is required.</p>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <a href={APP_URL} style={{ color: "#07110b", background: "#00d566", padding: "15px 23px", borderRadius: 10, fontWeight: 850, textDecoration: "none", textAlign: "center" }}>
                Analyze a ticker free →
              </a>
            </div>
          </div>
        </div>
      </section>

      <footer style={{ borderTop: "1px solid rgba(255,255,255,.07)", padding: "30px 0 42px" }}>
        <div style={{ ...container, display: "flex", justifyContent: "space-between", gap: 20, flexWrap: "wrap", color: "#68728a", fontSize: 12, lineHeight: 1.6 }}>
          <span>© 2026 Unstructured Alpha</span>
          <span style={{ maxWidth: 720 }}>For research and informational purposes only. Not investment advice. Scores describe macro context and do not guarantee future returns.</span>
        </div>
      </footer>

      <style>{`
        @media (max-width: 860px) {
          .uranium-hero-grid, .uranium-cta-grid { grid-template-columns: 1fr !important; }
          .uranium-card-grid { grid-template-columns: 1fr !important; }
          .uranium-cta-grid > div:last-child { justify-content: flex-start !important; }
        }
      `}</style>
    </main>
  );
}
