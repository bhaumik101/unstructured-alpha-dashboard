'use client';

// The landing page's hero: a live Portfolio X-ray. It opens on a starter mix
// with real readings; a visitor can switch mixes or add a ticker and see the
// mix's economic fingerprint at once, then open the full X-ray (weights,
// balancing) or the app's report. Reads /xray.json (proxied to the SEO
// service). Until the feed arrives, or if it cannot be read, the hero shows
// the static example it replaces -- never invented numbers.

import { useEffect, useState, type ReactNode } from 'react';
import { biggest, blend, known, type XrayFeed } from './blend';
import { pct } from './LiveMovers';

const APP_URL = "https://app.unstructuredalpha.com";
// Same starter mixes as /xray (utils/xray_page.py PRESETS; a test keeps them in step).
export const PRESETS: [string, string[]][] = [
  ["Big tech", ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META"]],
  ["Dividend income", ["SCHD", "VYM", "KO", "PG", "JNJ", "XLU"]],
  ["Classic 60/40", ["VTI", "AGG"]],
  ["Real assets", ["XLE", "GLD", "VNQ", "TIP"]],
  ["Banks and rates", ["JPM", "BAC", "KRE", "TLT"]],
];
const MAX = 12;

function lower(label: string): string {
  return label.startsWith("U.S.") ? label : label.charAt(0).toLowerCase() + label.slice(1);
}

export default function HeroXray({ fallback }: { fallback: ReactNode }) {
  const [feed, setFeed] = useState<XrayFeed | null>(null);
  const [held, setHeld] = useState<string[]>(PRESETS[0][1]);
  const [preset, setPreset] = useState<string>(PRESETS[0][0]);
  const [entry, setEntry] = useState("");
  const [say, setSay] = useState("");

  useEffect(() => {
    let live = true;
    fetch('/xray.json')
      .then((r) => (r.ok ? r.json() : null))
      .then((d: XrayFeed | null) => { if (live && d && d.s && Object.keys(d.s).length) setFeed(d); })
      .catch(() => { /* the static example stays */ });
    return () => { live = false; };
  }, []);

  if (!feed) return <>{fallback}</>;
  const mix = held.filter((t) => known(feed, t));
  const rows = blend(feed, mix);
  const top = biggest(rows);
  const scale = Math.max(0.25, ...rows.filter((r) => r.ok).map((r) => Math.abs(r.value)));
  const share = mix.map((t) => `${t}:${Math.round(1000 / mix.length) / 10}`).join(',');

  function add() {
    const t = entry.trim().toUpperCase().replace(/^\$/, '');
    setEntry('');
    if (!t) return;
    if (!known(feed!, t)) { setSay(`${t} is not on record yet.`); return; }
    if (held.includes(t)) { setSay(`${t} is already in the mix.`); return; }
    if (held.length >= MAX) { setSay(`Up to ${MAX} here; the full X-ray takes more.`); return; }
    setHeld([...held, t]); setPreset(''); setSay(`${t} added.`);
  }

  return (
    <div className="lp-xr" aria-labelledby="lp-xr-title">
      <p className="lp-xr-eyebrow" id="lp-xr-title">Live portfolio X-ray</p>
      <div className="lp-xr-presets" role="group" aria-label="Starter mixes">
        {PRESETS.map(([name, ts]) => (
          <button key={name} type="button" aria-pressed={preset === name}
                  onClick={() => { setHeld(ts); setPreset(name); setSay(`${name}: ${ts.join(', ')}.`); }}>{name}</button>
        ))}
      </div>
      <ul className="lp-xr-held" aria-label="Holdings, equal weight">
        {mix.map((t) => (
          <li key={t}>{t}
            <button type="button" aria-label={`Remove ${t}`}
                    onClick={() => { setHeld(held.filter((u) => u !== t)); setPreset(''); setSay(`${t} removed.`); }}>×</button>
          </li>
        ))}
        <li className="lp-xr-add">
          <form onSubmit={(e) => { e.preventDefault(); add(); }}>
            <label htmlFor="lp-xr-q" className="sr-only">Add a ticker</label>
            <input id="lp-xr-q" value={entry} onChange={(e) => setEntry(e.target.value)} placeholder="+ ticker"
                   autoComplete="off" spellCheck={false} maxLength={8} />
          </form>
        </li>
      </ul>
      <p className="lp-xr-say" aria-live="polite">{say}</p>
      {top ? (
        <p className="lp-xr-head">
          Biggest driver: <b>{lower(top.label)}</b>. In weeks when {top.phrase}, this mix has typically
          moved <b>{pct(top.value)}</b> beyond the market.
        </p>
      ) : <p className="lp-xr-head">Add a holding to see its fingerprint.</p>}
      <ul className="lp-xr-bars">
        {rows.map((r) => {
          const w = r.ok ? (50 * Math.abs(r.value)) / scale : 0;
          return (
            <li key={r.key}>
              <span>{r.label}</span>
              <span className="lp-xr-track" aria-hidden="true">
                {r.ok && <i className={r.value >= 0 ? 'up' : 'down'}
                            style={r.value >= 0 ? { left: '50%', width: `${w.toFixed(1)}%` }
                                                : { left: `${(50 - w).toFixed(1)}%`, width: `${w.toFixed(1)}%` }} />}
              </span>
              <b>{r.ok ? pct(r.value) : '—'}</b>
            </li>
          );
        })}
      </ul>
      <p className="lp-xr-note">
        Equal weight. Each figure: the mix&rsquo;s typical weekly move beyond the stock market when that force
        moved by its standard amount, over three years. Past, not a forecast.
      </p>
      <div className="lp-xr-actions">
        <a className="lp-btn lp-btn-bright lp-btn-sm" href={`/xray#p=${share}`}>Balance it, set weights →</a>
        <a className="lp-btn lp-btn-ghost lp-btn-sm"
           href={`${APP_URL}/?h=${encodeURIComponent(share)}&utm_source=landing&utm_medium=owned&utm_content=hero_xray`}>
          Full report, free</a>
      </div>
    </div>
  );
}
