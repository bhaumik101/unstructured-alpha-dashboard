import type { Metadata } from "next";
import "./globals.css";

const SITE_URL = "https://unstructuredalpha.com";
const OG_IMAGE = `${SITE_URL}/og-image.png`;

const DESCRIPTION =
  "See which economic forces a portfolio is exposed to — interest rates, inflation, the dollar, oil and credit spreads — with the uncertainty shown on every number. Built for advisers. Not a forecast.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Unstructured Alpha — Portfolio exposure to economic forces",
    template: "%s | Unstructured Alpha",
  },
  description: DESCRIPTION,
  keywords: [
    "portfolio exposure",
    "interest rate sensitivity",
    "inflation exposure",
    "dollar exposure",
    "oil exposure",
    "credit spread sensitivity",
    "portfolio risk report",
    "financial adviser tools",
    "RIA tools",
    "macro exposure",
  ],
  authors: [{ name: "Unstructured Alpha" }],
  creator: "Unstructured Alpha",
  publisher: "Unstructured Alpha",
  robots: { index: true, follow: true },
  alternates: { canonical: SITE_URL },
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: "Unstructured Alpha",
    title: "Unstructured Alpha — See what your portfolio is exposed to",
    description: DESCRIPTION,
    images: [
      {
        url: OG_IMAGE,
        width: 1200,
        height: 630,
        alt: "Unstructured Alpha — portfolio exposure report",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    site: "@UnstructuredAlpha",
    creator: "@UnstructuredAlpha",
    title: "Unstructured Alpha — See what your portfolio is exposed to",
    description: DESCRIPTION,
    images: [OG_IMAGE],
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-theme="light" suppressHydrationWarning>
      <head>
        {/*
          Theme: a stored choice wins; otherwise light. Light is the default
          because advisers print and screen-share reports.
        */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              '(function(){try{var s=localStorage.getItem("ua-theme");' +
              'var t=(s==="light"||s==="dark")?s:"light";' +
              'document.documentElement.setAttribute("data-theme",t)}catch(e){}})()',
          }}
        />
        {/*
          Analytics beacon. Until this existed the marketing site recorded
          nothing at all, so visitor -> signup conversion had no denominator and
          could not be computed. Posted to /api/track, which next.config.ts
          rewrites to the SEO service so it is same-origin and shares the app's
          visitor_id derivation (one person = one visitor across both sites).

          Inline and dependency-free, matching the theme script above: no
          third-party analytics, nothing added to the bundle, and no cookie, so
          there is no consent banner to show. Identity is a salted server-side
          hash of coarse request attributes; the browser stores nothing.

          Next does client-side route transitions, which do not re-run a <head>
          script, so history methods are wrapped to catch them. Consecutive
          duplicates of the same path are dropped -- the defect just removed
          from the bounce metric came from counting one reader many times.
        */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              '(function(){try{' +
              // Guard on window, not a closure variable. This script is
              // evaluated more than once (server-rendered head, then again on
              // hydration), and a per-closure guard let one page load record
              // two page views -- which would inflate traffic and, worse, make
              // a one-page visit look like an engaged two-page one.
              'if(window.__uaTrackInit)return; window.__uaTrackInit=1;' +
              'var names={"/":"Landing","/uranium":"Uranium"};' +
              'function send(){try{' +
              'var p=location.pathname.replace(/\\/+$/,"")||"/";' +
              'if(p===window.__uaLastPath)return; window.__uaLastPath=p;' +
              'var b=JSON.stringify({event:"page_view",page:names[p]||"Other"});' +
              'if(navigator.sendBeacon){' +
              'navigator.sendBeacon("/api/track",new Blob([b],{type:"application/json"}));' +
              '}else{fetch("/api/track",{method:"POST",body:b,keepalive:true,' +
              'headers:{"Content-Type":"application/json"}}).catch(function(){});}' +
              '}catch(e){}}' +
              'var ps=history.pushState,rs=history.replaceState;' +
              'history.pushState=function(){ps.apply(this,arguments);send();};' +
              'history.replaceState=function(){rs.apply(this,arguments);send();};' +
              'addEventListener("popstate",send);' +
              'if(document.readyState==="loading"){' +
              'addEventListener("DOMContentLoaded",send);}else{send();}' +
              '}catch(e){}})()',
          }}
        />
        <link rel="icon" href="/favicon.ico" sizes="any" />
        <link rel="apple-touch-icon" href="/logo.svg" />
        <meta name="theme-color" content="#fafaf8" />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "WebApplication",
              "name": "Unstructured Alpha",
              "url": "https://unstructuredalpha.com",
              "applicationCategory": "FinanceApplication",
              "operatingSystem": "Web",
              "description": DESCRIPTION,
              "offers": [
                { "@type": "Offer", "name": "Free", "price": "0", "priceCurrency": "USD", "description": "Exposure report for one portfolio, up to 15 holdings." },
                { "@type": "Offer", "name": "Investor Pro", "price": "20", "priceCurrency": "USD", "description": "Save portfolios, up to 25 holdings. Early-access pricing.", "priceSpecification": { "@type": "UnitPriceSpecification", "price": "20", "priceCurrency": "USD", "unitCode": "MON" } }
              ],
              "featureList": ["Interest rate exposure", "Inflation exposure", "U.S. dollar exposure", "Oil exposure", "Credit spread exposure", "Holdings behind each exposure", "Evidence label and 90% range on every number"],
              "publisher": { "@type": "Organization", "name": "Unstructured Alpha", "url": "https://unstructuredalpha.com" }
            })
          }}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "FAQPage",
              "mainEntity": [
                { "@type": "Question", "name": "Is Unstructured Alpha a forecast?", "acceptedAnswer": { "@type": "Answer", "text": "No. It describes how a portfolio has moved alongside interest rates, inflation expectations, the dollar, oil and credit spreads over the past three years, with a 90% range and an evidence label on every number. It does not predict returns." } },
                { "@type": "Question", "name": "How much does Unstructured Alpha cost?", "acceptedAnswer": { "@type": "Answer", "text": "The exposure report for one portfolio is free, with no account needed for the first report. Investor Pro is $20/month at early-access pricing. An advisor pilot is available on request." } },
                { "@type": "Question", "name": "Where does the data come from?", "acceptedAnswer": { "@type": "Answer", "text": "Economic series come from the Federal Reserve Bank of St. Louis (FRED); prices come from Yahoo Finance and include dividends. Unavailable data is left out and named, never filled in." } }
              ]
            })
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
