// The X-ray's arithmetic, shared by the landing page's live card. Mirrors
// utils/xray_page.py: a mix's figure for a force is the weighted average of
// each holding's typical move; a force any holding lacks is left out; funds
// that track the S&P 500 count as zero (readings are beyond the market's own
// move, and they are that move). Weights here are always equal.

export type Reading = [number, number] | null;            // [typical move, 1 if it held up]
export type XrayFeed = {
  f: [string, string, string][];                          // [key, label, shock phrase]
  s: Record<string, [string, string, Reading[]]>;         // ticker -> [name, sector, readings]
  mkt: string[];
  as_of: string;
};
export type ForceRow = { key: string; label: string; phrase: string; ok: boolean; value: number;
  heldShare: number; drivers: [string, number][] };

export function known(feed: XrayFeed, t: string): boolean {
  return t in feed.s || feed.mkt.indexOf(t) >= 0;
}

export function blend(feed: XrayFeed, holdings: string[]): ForceRow[] {
  const w = holdings.length ? 1 / holdings.length : 0;
  return feed.f.map(([key, label, phrase], i) => {
    let value = 0, ok = holdings.length > 0, heldShare = 0;
    const drivers: [string, number][] = [];
    for (const t of holdings) {
      if (feed.mkt.indexOf(t) >= 0) { heldShare += w; continue; }
      const r = feed.s[t] ? feed.s[t][2][i] : null;
      if (!r) { ok = false; continue; }
      value += w * r[0];
      if (r[1]) heldShare += w;
      drivers.push([t, w * r[0]]);
    }
    drivers.sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
    return { key, label, phrase, ok, value, heldShare, drivers: drivers.slice(0, 2) };
  });
}

export function biggest(rows: ForceRow[]): ForceRow | null {
  const ok = rows.filter((r) => r.ok);
  return ok.length ? ok.reduce((a, b) => (Math.abs(b.value) > Math.abs(a.value) ? b : a)) : null;
}
