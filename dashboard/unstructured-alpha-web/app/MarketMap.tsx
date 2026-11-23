'use client';

// Every measured stock on two forces at once, from this week's /xray.json
// (the same feed as the X-ray). Two modes:
//   * <MarketMap />            the landing's showpiece: pick the two forces,
//                              light up a sector, hover a dot, click through.
//   * <MarketMap backdrop />   the hero's starfield: the same real dots, faint,
//                              no labels, aria-hidden.
// Nothing is drawn without the feed. Readings beyond the axis are drawn at its
// edge, and the page says so; nothing is invented or smoothed.

import { useEffect, useMemo, useState } from 'react';
import type { XrayFeed } from './blend';

const SECTOR_HUES: Record<string, string> = {
  'Information Technology': '#6fa4ec', 'Financials': '#55c3d8', 'Health Care': '#4fc79b',
  'Consumer Discretionary': '#ef9179', 'Consumer Staples': '#c9a3f0', 'Industrials': '#a8b5c7',
  'Energy': '#eab54f', 'Utilities': '#8fd18a', 'Real Estate': '#f0a3c4', 'Materials': '#d6b48a',
  'Communication Services': '#7fd6e6', 'ETF': '#b3bfd2',
};
const OTHER = '#8794a8';

let pending: Promise<XrayFeed | null> | null = null;
function getXray(): Promise<XrayFeed | null> {
  pending ??= fetch('/xray.json').then((r) => (r.ok ? r.json() : null))
    .then((d: XrayFeed | null) => (d && d.s && Object.keys(d.s).length ? d : null)).catch(() => null);
  return pending;
}

// The first interaction per page load (an axis, a sector, a dot): a page
// view says someone arrived, this says they used the map. Same relay and
// allowlist as the landing's other events (seo/track_api.py).
let mapUsed = false;
function recordMapUse() {
  if (mapUsed) return;
  mapUsed = true;
  try {
    const internal = (window as unknown as { __uaInternal?: boolean }).__uaInternal || undefined;
    const body = JSON.stringify({ event: "tool_used", page: "Landing", tool: "market_map", internal });
    if (navigator.sendBeacon) navigator.sendBeacon("/api/track", new Blob([body], { type: "application/json" }));
    else void fetch("/api/track", { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true });
  } catch {
    // Measurement must never get in the visitor's way.
  }
}

function fmt(v: number): string {
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(Math.abs(v) >= 0.95 ? 1 : 2)}%`;
}

type Dot = { t: string; name: string; sector: string; x: number; y: number; hx: boolean; hy: boolean };

export default function MarketMap({ backdrop = false }: { backdrop?: boolean }) {
  const [feed, setFeed] = useState<XrayFeed | null>(null);
  const [ax, setAx] = useState(0);          // interest rates
  const [ay, setAy] = useState(3);          // oil and energy
  const [sector, setSector] = useState('');
  const [hover, setHover] = useState<Dot | null>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    let live = true;
    getXray().then((d) => { if (live) { setFeed(d); requestAnimationFrame(() => setShown(true)); } });
    return () => { live = false; };
  }, []);

  const dots = useMemo<Dot[]>(() => {
    if (!feed) return [];
    const out: Dot[] = [];
    for (const [t, [name, sector, r]] of Object.entries(feed.s)) {
      const a = r[ax], b = r[ay];
      if (!a || !b) continue;                       // not measured on both: not drawn
      out.push({ t, name, sector: sector || 'ETF', x: a[0], y: b[0], hx: !!a[1], hy: !!b[1] });
    }
    return out;
  }, [feed, ax, ay]);

  if (!feed || !dots.length) return null;

  // A shared, symmetric scale per axis at the 97th percentile of |reading|, so
  // a handful of extreme names do not flatten the rest. Beyond it: drawn at the edge.
  const span = (vals: number[]) => {
    const s = vals.map(Math.abs).sort((p, q) => p - q);
    const v = s[Math.floor(s.length * 0.97)] || 1;
    return Math.max(0.5, Math.ceil(v * 2) / 2);
  };
  const sx = span(dots.map((d) => d.x)), sy = span(dots.map((d) => d.y));
  const W = backdrop ? 900 : 1000, H = backdrop ? 620 : 580, P = backdrop ? 0 : 52;
  const X = (v: number) => P + ((Math.max(-sx, Math.min(sx, v)) + sx) / (2 * sx)) * (W - 2 * P);
  const Y = (v: number) => H - P - ((Math.max(-sy, Math.min(sy, v)) + sy) / (2 * sy)) * (H - 2 * P);
  const clipped = dots.filter((d) => Math.abs(d.x) > sx || Math.abs(d.y) > sy).length;
  const sectors = Object.keys(SECTOR_HUES).filter((s) => dots.some((d) => d.sector === s));
  const fx = feed.f[ax], fy = feed.f[ay];

  const circles = dots.map((d) => {
    const held = d.hx || d.hy;
    const hue = SECTOR_HUES[d.sector] ?? OTHER;
    const dim = sector && d.sector !== sector;
    return (
      <circle key={d.t} cx={X(d.x).toFixed(1)} cy={Y(d.y).toFixed(1)} r={backdrop ? 2.2 : held ? 4.2 : 3}
              fill={held ? hue : 'none'} stroke={hue} strokeWidth={held ? 0 : 1}
              opacity={backdrop ? (held ? 0.55 : 0.28) : dim ? 0.08 : held ? 0.92 : 0.5}
              onMouseEnter={backdrop ? undefined : () => setHover(d)}
              onClick={backdrop ? undefined : () => { recordMapUse(); window.location.href = `/exposure/${encodeURIComponent(d.t)}`; }}
              style={backdrop ? undefined : { cursor: 'pointer' }} />
    );
  });

  if (backdrop) {
    return (
      <svg className={`lp-stars${shown ? ' is-on' : ''}`} viewBox={`0 0 ${W} ${H}`} aria-hidden="true" preserveAspectRatio="xMidYMid slice">
        <line x1={W / 2} y1="0" x2={W / 2} y2={H} className="lp-stars-axis" />
        <line x1="0" y1={H / 2} x2={W} y2={H / 2} className="lp-stars-axis" />
        {circles}
      </svg>
    );
  }

  return (
    <div className="lp-map2">
      <div className="lp-map2-controls">
        <div className="lp-map2-axis" role="group" aria-label="Across">
          <span>Across</span>
          {feed.f.map(([k, label], i) => (
            <button key={k} type="button" aria-pressed={ax === i} disabled={ay === i}
                    onClick={() => { setAx(i); recordMapUse(); }}><i className={`lp-fdot f-${k}`} aria-hidden="true" />{label}</button>
          ))}
        </div>
        <div className="lp-map2-axis" role="group" aria-label="Up and down">
          <span>Up</span>
          {feed.f.map(([k, label], i) => (
            <button key={k} type="button" aria-pressed={ay === i} disabled={ax === i}
                    onClick={() => { setAy(i); recordMapUse(); }}><i className={`lp-fdot f-${k}`} aria-hidden="true" />{label}</button>
          ))}
        </div>
      </div>
      <div className="lp-map2-stage" onMouseLeave={() => setHover(null)}>
        <svg className={`lp-map2-svg${shown ? ' is-on' : ''}`} viewBox={`0 0 ${W} ${H}`} role="img"
             aria-label={`${dots.length} stocks and funds plotted by how they moved with ${fx[1].toLowerCase()} (across) and ${fy[1].toLowerCase()} (up and down). Open the stock map for a searchable version.`}>
          <defs>
            <radialGradient id="lp-map2-glow" cx="50%" cy="50%" r="55%">
              <stop offset="0%" stopColor="#6ce5d2" stopOpacity="0.07" /><stop offset="100%" stopColor="#6ce5d2" stopOpacity="0" />
            </radialGradient>
          </defs>
          <rect x={P} y={P} width={W - 2 * P} height={H - 2 * P} fill="url(#lp-map2-glow)" />
          {[-1, -0.5, 0.5, 1].map((f) => (
            <g key={f}>
              <line x1={X(f * sx)} y1={P} x2={X(f * sx)} y2={H - P} className="lp-map2-grid" />
              <line x1={P} y1={Y(f * sy)} x2={W - P} y2={Y(f * sy)} className="lp-map2-grid" />
            </g>
          ))}
          <line x1={X(0)} y1={P} x2={X(0)} y2={H - P} className="lp-map2-zero" />
          <line x1={P} y1={Y(0)} x2={W - P} y2={Y(0)} className="lp-map2-zero" />
          {/* Axis captions sit in the margin, never on the dots. */}
          <text x={W - P} y={H - P + 22} textAnchor="end" className="lp-map2-lab">{fmt(sx)} with {fx[1].toLowerCase()} →</text>
          <text x={P} y={H - P + 22} className="lp-map2-lab">← {fmt(-sx)}</text>
          <text x={X(0)} y={H - P + 22} textAnchor="middle" className="lp-map2-lab">0</text>
          <text x={P} y={P - 18} className="lp-map2-lab">↑ {fmt(sy)} with {fy[1].toLowerCase()}</text>
          <text x={P} y={P - 4} className="lp-map2-lab lp-map2-lab-dim">↓ to {fmt(-sy)} at the bottom</text>
          {circles}
          {hover && (
            <circle cx={X(hover.x)} cy={Y(hover.y)} r="9" fill="none" stroke="#ffffff" strokeWidth="1.5" pointerEvents="none" />
          )}
        </svg>
        {hover && (
          <div className="lp-map2-tip" style={{ left: `${(X(hover.x) / W) * 100}%`, top: `${(Y(hover.y) / H) * 100}%` }}>
            <b>{hover.t}</b> <span>{hover.name}</span>
            <div>{fx[1]}: <b>{fmt(hover.x)}</b>{hover.hx ? '' : ' · no clear link'}</div>
            <div>{fy[1]}: <b>{fmt(hover.y)}</b>{hover.hy ? '' : ' · no clear link'}</div>
          </div>
        )}
      </div>
      <div className="lp-map2-legend" role="group" aria-label="Light up a sector">
        {sectors.map((s) => (
          <button key={s} type="button" aria-pressed={sector === s} onClick={() => { setSector(sector === s ? '' : s); recordMapUse(); }}>
            <i style={{ background: SECTOR_HUES[s] }} aria-hidden="true" />{s}
          </button>
        ))}
      </div>
      <p className="lp-small lp-map2-note">
        {dots.length} stocks and funds, data through {feed.as_of}. Each dot is one stock&rsquo;s typical weekly move
        beyond the market when that force moved by its standard amount. Filled: the reading held up on at least
        one axis; ring: on neither. {clipped > 0 && <>{clipped} beyond the edge are drawn at it. </>}The past, not a forecast.
      </p>
    </div>
  );
}
