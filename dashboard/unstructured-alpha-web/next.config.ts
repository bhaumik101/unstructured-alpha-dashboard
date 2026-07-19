import type { NextConfig } from "next";

/**
 * The SEO service (a FastAPI app on Render) generates 329 crawlable pages:
 * /ticker/{SYMBOL}, /signal/{id}, /signals/report, plus a sitemap and robots.
 * They were reachable only at seo.unstructuredalpha.com, while this site — the
 * brand domain — returned 404 for every one of those paths and served no
 * robots.txt or sitemap at all. Requesting /sitemap.xml here returned the Next
 * HTML shell, which Google rejects as a sitemap outright.
 *
 * The effect was that ranking signals accumulated on a subdomain nobody links
 * to, separately from the domain that carries the brand, and crawlers arriving
 * at the apex were given no map of the site.
 *
 * These rewrites proxy those paths to the SEO service. Rewrites, not redirects,
 * deliberately: a redirect would send both users and crawlers to the subdomain
 * and preserve the split. A rewrite keeps the URL on www and serves the
 * upstream response, so the pages are genuinely part of this domain.
 *
 * Paired with SEO_BASE_URL=https://www.unstructuredalpha.com on the Render
 * service (see dashboard/render.yaml). Both halves are required — proxying the
 * pages while their canonical tags still point at seo.* would tell search
 * engines the subdomain is the real home and waste the consolidation.
 *
 * Note the ordering constraint: Next matches its own routes first, so if a page
 * is ever added at app/ticker/... it will shadow the proxy for that path.
 */

const SEO_ORIGIN =
  process.env.SEO_ORIGIN ?? "https://seo.unstructuredalpha.com";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/ticker/:symbol", destination: `${SEO_ORIGIN}/ticker/:symbol` },
      { source: "/signal/:id", destination: `${SEO_ORIGIN}/signal/:id` },
      { source: "/signals/report", destination: `${SEO_ORIGIN}/signals/report` },
      { source: "/sitemap.xml", destination: `${SEO_ORIGIN}/sitemap.xml` },
      { source: "/robots.txt", destination: `${SEO_ORIGIN}/robots.txt` },
    ];
  },
};

export default nextConfig;
