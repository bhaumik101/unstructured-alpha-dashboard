import { NextRequest, NextResponse } from "next/server";

/**
 * Analytics beacon relay for the marketing site.
 *
 * This is a real route rather than a next.config rewrite for one reason: the
 * visitor's IP must reach the upstream explicitly. A rewrite proxies from this
 * server, so the upstream would see this server's address, every landing
 * visitor would hash to the same visitor_id, and the admin dashboard would
 * report one unique visitor forever while looking perfectly healthy.
 *
 * The upstream derives identity as a salted server-side hash of coarse request
 * attributes. No raw IP is stored anywhere and no cookie is set, so there is
 * nothing here that requires a consent banner.
 *
 * The shared token matters: /api/track on the SEO service trusts the
 * x-forwarded-for it is handed. Without a secret only this server knows,
 * anyone could POST a forged IP and manufacture unlimited fake visitors --
 * corrupting the one number this whole exercise exists to establish. It is
 * read server-side and never reaches the browser.
 */

const SEO_ORIGIN = process.env.SEO_ORIGIN ?? "https://seo.unstructuredalpha.com";
const INGEST_TOKEN = process.env.TRACK_INGEST_TOKEN ?? "";

// Always 204, whatever happens. The beacon must never alter what a visitor
// sees, and must never tell an anonymous caller whether their row was kept.
const noContent = () => new NextResponse(null, { status: 204 });

function clientIp(req: NextRequest): string {
  const forwarded = req.headers.get("x-forwarded-for") ?? "";
  // Left-most entry is the original client; the rest are proxy hops.
  return (
    forwarded.split(",")[0].trim() ||
    req.headers.get("cf-connecting-ip")?.trim() ||
    req.headers.get("x-real-ip")?.trim() ||
    ""
  );
}

export async function POST(req: NextRequest) {
  try {
    if (!INGEST_TOKEN) {
      // Fail closed. Accepting unauthenticated writes would let anyone forge
      // traffic, and silently-wrong analytics is worse than none.
      console.error("[track] TRACK_INGEST_TOKEN is not set; event dropped");
      return noContent();
    }

    const ip = clientIp(req);
    if (!ip) return noContent();

    const body = await req.text();
    if (body.length > 2048) return noContent();

    await fetch(`${SEO_ORIGIN}/api/track`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-ua-track-token": INGEST_TOKEN,
        "x-forwarded-for": ip,
        // Forwarded so the upstream can classify device family and drop bots.
        // Only a coarse signature is derived; the string itself is discarded.
        "user-agent": req.headers.get("user-agent") ?? "",
      },
      body,
    });
  } catch (err) {
    console.error("[track] relay error:", err);
  }
  return noContent();
}
