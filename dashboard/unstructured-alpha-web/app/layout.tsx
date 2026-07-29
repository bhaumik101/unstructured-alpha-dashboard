import type { Metadata } from "next";
import "./globals.css";

const SITE_URL = "https://unstructuredalpha.com";
const OG_IMAGE = `${SITE_URL}/og-image.png`;

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Unstructured Alpha — Macro Signal Intelligence for Active Investors",
    template: "%s | Unstructured Alpha",
  },
  description:
    "47 macro signals — insider flows, credit spreads, energy positioning, Fed indicators — scored daily from public data. Understand the macro environment behind your stocks before you size in. Free to start.",
  keywords: [
    "macro signals",
    "investing dashboard",
    "credit spreads",
    "insider trading signals",
    "confluence score",
    "FRED data",
    "macro investing",
    "market regime",
    "active investors",
    "alternative data",
    "SEC EDGAR signals",
    "yield curve",
    "HY spread",
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
    title: "Unstructured Alpha — Macro Signals for Active Investors",
    description:
      "47 macro signals scored daily from FRED, SEC EDGAR, FINRA, EIA, and CBOE. Know whether the macro environment supports your thesis — before the move.",
    images: [
      {
        url: OG_IMAGE,
        width: 1200,
        height: 630,
        alt: "Unstructured Alpha — Macro Signal Dashboard",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    site: "@UnstructuredAlpha",
    creator: "@UnstructuredAlpha",
    title: "Unstructured Alpha — Macro Signals for Active Investors",
    description:
      "47 macro signals scored daily. Insider flows, credit spreads, energy data, Fed indicators. Free dashboard for active investors.",
    images: [OG_IMAGE],
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html:
              '(function(){try{var s=localStorage.getItem("ua-theme");' +
              'var t=(s==="light"||s==="dark")?s:' +
              '(matchMedia("(prefers-color-scheme: light)").matches?"light":"dark");' +
              'document.documentElement.setAttribute("data-theme",t)}catch(e){}})()',
          }}
        />
        <link rel="icon" href="/favicon.ico" sizes="any" />
        <link rel="apple-touch-icon" href="/logo.svg" />
        <meta name="theme-color" content="#090b11" />
        {/* WebApplication JSON-LD — helps Google understand product type and pricing */}
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
              "description": "47 macro signals scored daily from FRED, SEC EDGAR, FINRA, EIA, and CBOE. Understand the macro environment behind your portfolio. Free dashboard for active investors.",
              "offers": [
                { "@type": "Offer", "name": "Free Plan", "price": "0", "priceCurrency": "USD", "description": "Signal Dashboard, Today's Brief, Ticker Deep Dive — free forever." },
                { "@type": "Offer", "name": "Pro Plan", "price": "20", "priceCurrency": "USD", "description": "Score history, sector percentiles, watchlist alerts, morning digest.", "priceSpecification": { "@type": "UnitPriceSpecification", "price": "20", "priceCurrency": "USD", "unitCode": "MON" } }
              ],
              "featureList": ["47 macro signals from FRED, SEC EDGAR, FINRA, EIA, CBOE", "Confluence Score per ticker", "Today's Brief", "Signal Dashboard", "Sector Percentile Rankings", "Score History Charts", "Watchlist Alerts"],
              "publisher": { "@type": "Organization", "name": "Unstructured Alpha", "url": "https://unstructuredalpha.com" }
            })
          }}
        />
        {/* FAQPage JSON-LD — eligible for Google FAQ rich results */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "FAQPage",
              "mainEntity": [
                { "@type": "Question", "name": "What is a macro signal?", "acceptedAnswer": { "@type": "Answer", "text": "A macro signal is a publicly available economic or financial data series — like the yield curve, credit spreads, or insider buying — that has historically moved before broad market prices responded. Unstructured Alpha tracks 47 such signals scored daily from FRED, SEC EDGAR, FINRA, EIA, and CBOE." } },
                { "@type": "Question", "name": "How much does Unstructured Alpha cost?", "acceptedAnswer": { "@type": "Answer", "text": "The core Signal Dashboard, Today's Brief, and Ticker Deep Dive are free with an account — no credit card required. Pro is $20/month and adds score history charts, sector percentile rankings, watchlist alerts, and the morning email digest." } },
                { "@type": "Question", "name": "How is Unstructured Alpha different from a Bloomberg Terminal?", "acceptedAnswer": { "@type": "Answer", "text": "Bloomberg Terminal costs approximately $27,000/year and is designed for institutional desks. Unstructured Alpha focuses on the macro signal layer at $20/month for active individual investors. Different scope, different audience, very different price." } }
              ]
            })
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
