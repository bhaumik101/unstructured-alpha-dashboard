'use client';

// Where each exposure comes from: the sample's holdings on the left, the
// forces on the right, one ribbon per holding-to-force contribution, its width
// the size of that contribution (sampleData.ts FLOWS, from the stored report).
// Credit spreads is not drawn: its reading could not be told apart from zero.

import { useState } from 'react';
import { FLOWS } from './sampleData';

type Force = { key: string; label: string; impact: number; evidence: string };

export default function Flow({ holdings, forces }: { holdings: [string, number][]; forces: Force[] }) {
  const [on, setOn] = useState<string | null>(null);
  const W = 640, H = 380, NODE = 10, GAP = 16, LX = 92, RX = W - 200;
  const total = FLOWS.reduce((n, f) => n + Math.abs(f[2]), 0);
  const usable = (n: number) => H - GAP * (n - 1);
  const leftKeys = holdings.map(([t]) => t).filter((t) => FLOWS.some((f) => f[0] === t));
  const rightKeys = forces.map((f) => f.key).filter((k) => FLOWS.some((f) => f[1] === k));
  const kL = usable(leftKeys.length) / total, kR = usable(rightKeys.length) / total;
  const k = Math.min(kL, kR);
  const sum = (pred: (f: (typeof FLOWS)[number]) => boolean) => FLOWS.filter(pred).reduce((n, f) => n + Math.abs(f[2]), 0);

  // Node positions, centred vertically.
  const place = (keys: string[], size: (key: string) => number) => {
    const hs = keys.map((key) => size(key) * k);
    let y = (H - (hs.reduce((a, b) => a + b, 0) + GAP * (keys.length - 1))) / 2;
    const out: Record<string, { y: number; h: number; used: number }> = {};
    keys.forEach((key, i) => { out[key] = { y, h: hs[i], used: 0 }; y += hs[i] + GAP; });
    return out;
  };
  const L = place(leftKeys, (t) => sum((f) => f[0] === t));
  const R = place(rightKeys, (key) => sum((f) => f[1] === key));
  const order = (key: string) => rightKeys.indexOf(key);
  const flows = [...FLOWS].sort((a, b) => leftKeys.indexOf(a[0]) - leftKeys.indexOf(b[0]) || order(a[1]) - order(b[1]));

  const ribbons = flows.map(([t, key, v]) => {
    const w = Math.abs(v) * k;
    const y0 = L[t].y + L[t].used, y1 = R[key].y + R[key].used;
    L[t].used += w; R[key].used += w;
    const x0 = LX + NODE, x1 = RX, mx = (x0 + x1) / 2;
    const d = `M${x0},${y0} C${mx},${y0} ${mx},${y1} ${x1},${y1} L${x1},${y1 + w} C${mx},${y1 + w} ${mx},${y0 + w} ${x0},${y0 + w} Z`;
    const lit = !on || on === t || on === key;
    const f = forces.find((x) => x.key === key)!;
    return (
      <path key={`${t}-${key}`} d={d} className={`lp-flow-rib f-${key}`} opacity={lit ? 0.62 : 0.08}>
        <title>{`${t} → ${f.label}: ${v > 0 ? '+' : '−'}${Math.abs(v).toFixed(2)} points of the portfolio's ${f.impact > 0 ? '+' : '−'}${Math.abs(f.impact).toFixed(2)}%`}</title>
      </path>
    );
  });

  const weight = Object.fromEntries(holdings);
  return (
    <figure className="lp-flow" onMouseLeave={() => setOn(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label={`Where each exposure comes from: ${flows.map(([t, key, v]) => `${t} to ${forces.find((f) => f.key === key)!.label} ${Math.abs(v).toFixed(2)} points`).join('; ')}.`}>
        <defs>
          <linearGradient id="lp-flow-fade" x1="0" x2="1">
            <stop offset="0" stopColor="#fff" stopOpacity="0.55" /><stop offset="0.35" stopColor="#fff" stopOpacity="1" />
          </linearGradient>
          <mask id="lp-flow-mask"><rect x="0" y="0" width={W} height={H} fill="url(#lp-flow-fade)" /></mask>
        </defs>
        <g mask="url(#lp-flow-mask)">{ribbons}</g>
        {leftKeys.map((t) => (
          <g key={t} onMouseEnter={() => setOn(t)} className="lp-flow-node">
            <rect x={LX} y={L[t].y} width={NODE} height={Math.max(2, L[t].h)} rx="2" className="lp-flow-bar" />
            <text x={LX - 12} y={L[t].y + L[t].h / 2 + 4} textAnchor="end" className="lp-flow-t">{t}</text>
            <text x={LX - 12} y={L[t].y + L[t].h / 2 + 19} textAnchor="end" className="lp-flow-s">{weight[t]}%</text>
          </g>
        ))}
        {rightKeys.map((key) => {
          const f = forces.find((x) => x.key === key)!;
          const cy = R[key].y + R[key].h / 2;
          return (
            <g key={key} onMouseEnter={() => setOn(key)} className="lp-flow-node">
              <rect x={RX} y={R[key].y} width={NODE} height={Math.max(2, R[key].h)} rx="2" className={`lp-flow-fbar f-${key}`} />
              <text x={RX + NODE + 12} y={cy - 2} className="lp-flow-t">
                {f.label.length > 14 && f.label.includes(' ')
                  ? <><tspan x={RX + NODE + 12} dy="-0.6em">{f.label.split(' ')[0]}</tspan><tspan x={RX + NODE + 12} dy="1.1em">{f.label.split(' ').slice(1).join(' ')}</tspan></>
                  : f.label}
              </text>
              <text x={RX + NODE + 12} y={cy + 15 + (f.label.length > 14 && f.label.includes(' ') ? 8 : 0)} className="lp-flow-s">
                {f.impact > 0 ? '+' : '−'}{Math.abs(f.impact).toFixed(2)}% · {f.evidence}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="lp-small">
        Ribbon width: each holding&rsquo;s contribution (its weight times its own sensitivity). Hover a holding or a force
        to trace it. Credit spreads is left out: not distinguishable from zero.
      </figcaption>
    </figure>
  );
}
