import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });

const SITE_URL = "https://unstructuredalpha.com";
const OG_IMAGE = `${SITE_URL}/og-image.png`;

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Unstructured Alpha — Macro Signal Intelligence for Active Investors",
    template: "%s | Unstructured Alpha",
  },
  description:
    "43 macro signals — insider flows, credit spreads, energy positioning, Fed indicators — scored daily from public data. Understand the macro environment behind your stocks before you size in. Free to start.",
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
      "43 macro signals scored daily from FRED, SEC EDGAR, FINRA, EIA, and CBOE. Know whether the macro environment supports your thesis — before the move.",
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
      "43 macro signals scored daily. Insider flows, credit spreads, energy data, Fed indicators. Free dashboard for active investors.",
    images: [OG_IMAGE],
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={geist.variable}>
      <head>
        <link rel="icon" href="/favicon.ico" sizes="any" />
        <link rel="apple-touch-icon" href="/logo.svg" />
        <meta name="theme-color" content="#0b0d12" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
      </head>
      <body>{children}</body>
    </html>
  );
}
