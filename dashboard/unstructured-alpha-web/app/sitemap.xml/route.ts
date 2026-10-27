const SEO_ORIGIN =
  process.env.SEO_ORIGIN ?? "https://seo.unstructuredalpha.com";

const BRAND_ORIGIN = "https://www.unstructuredalpha.com";

const URANIUM_ENTRY = `
  <url>
    <loc>${BRAND_ORIGIN}/uranium</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>`;

function fallbackSitemap(): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>${BRAND_ORIGIN}</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
${URANIUM_ENTRY}
</urlset>`;
}

function addUraniumEntry(xml: string): string {
  if (xml.includes(`${BRAND_ORIGIN}/uranium`)) {
    return xml;
  }

  if (!xml.includes("</urlset>")) {
    return fallbackSitemap();
  }

  return xml.replace("</urlset>", `${URANIUM_ENTRY}\n</urlset>`);
}

export async function GET(): Promise<Response> {
  try {
    const upstream = await fetch(`${SEO_ORIGIN}/sitemap.xml`, {
      headers: { Accept: "application/xml,text/xml" },
      next: { revalidate: 3600 },
    });

    if (!upstream.ok) {
      throw new Error(`SEO sitemap returned ${upstream.status}`);
    }

    const xml = addUraniumEntry(await upstream.text());

    return new Response(xml, {
      status: 200,
      headers: {
        "Content-Type": "application/xml; charset=utf-8",
        "Cache-Control":
          "public, s-maxage=3600, stale-while-revalidate=86400",
      },
    });
  } catch (error) {
    console.error("Unable to compose sitemap from SEO service", error);

    // 503, not a two-URL fallback: a 200 with only the homepage would tell
    // search engines the other 543 pages are gone. A 503 with Retry-After
    // keeps them on the last good sitemap until the SEO service is back.
    return new Response("Sitemap temporarily unavailable", {
      status: 503,
      headers: { "Retry-After": "600", "Cache-Control": "no-store" },
    });
  }
}
