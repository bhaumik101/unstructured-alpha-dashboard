'use client';

// The landing page's live demo: pick a core force, drag the size of the move,
// see the real stocks that rose and fell most in weeks like it. Reads the
// small /landing.json feed (proxied to the SEO service). Only readings that
// held up are listed, the data date is always shown, and if the feed cannot
// be read the whole section stays hidden rather than show anything invented.

import { useEffect, useState } from 'react';

type Row = [string, string, number, string];
type Force = {
  key: string; label: string; lower?: string; phrase: string; step: number; unit: string;
  measured: number; none: number; held_up: number; held_down: number; up: Row[]; down: Row[];
};
type Feed = { as_of: string; stocks: number; forces: Force[] };

const MAX_MULTIPLE = 3;

// Mirrors fmt_pct in utils/exposure_pages.py: two decimals below 0.95%, so a
// small move never prints as "−0.0%", and a figure that rounds to zero has no sign.
export function pct(v: number): string {
  const a = Math.abs(v);
  const d = a >= 0.95 ? 1 : 2;
  const s = a.toFixed(d);
  if (Number(s) === 0) return `${(0).toFixed(d)}%`;
  return `${v > 0 ? '+' : '−'}${s}%`;
}

function move(v: number, unit: string): string {
  if (v === 0) return 'no change';
  const sign = v > 0 ? '+' : '−';
  const a = Math.abs(v);
  return unit === '%' ? `${sign}${a.toFixed(a < 1 ? 1 : 0)}%` : `${sign}${a.toFixed(2)} ${unit}`;
}

function date(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso
    : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}

function List({ title, rows, k, max }: { title: string; rows: Row[]; k: number; max: number }) {
  return (
    <div className="lp-live-col">
      <h3 className="lp-live-h3">{title}</h3>
      {rows.length === 0 ? <p className="lp-live-none">No stock on record moved this way in a way that held up.</p> : (
        <ol className="lp-live-list">
          {rows.map(([t, name, impact, ev]) => {
            const v = impact * k;
            const w = max ? Math.max(3, (100 * Math.abs(v)) / max) : 3;
            return (
              <li key={t}>
                <a href={`/exposure/${encodeURIComponent(t)}`}>
                  <b>{t}</b><span>{name}</span>
                </a>
                <span className="lp-live-track" aria-hidden="true">
                  <span className={`lp-live-bar ${v >= 0 ? 'up' : 'down'}`} style={{ width: `${w.toFixed(1)}%` }} />
                </span>
                <span className="lp-live-v">{pct(v)}{ev === 'tentative' && <small> tentative</small>}</span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

export default function LiveMovers() {
  const [feed, setFeed] = useState<Feed | null>(null);
  const [key, setKey] = useState('oil');
  const [k, setK] = useState(2);

  useEffect(() => {
    let live = true;
    fetch('/landing.json')
      .then((r) => (r.ok ? r.json() : null))
      .then((d: Feed | null) => { if (live && d && Array.isArray(d.forces) && d.forces.length) setFeed(d); })
      .catch(() => { /* the section simply stays hidden */ });
    return () => { live = false; };
  }, []);

  if (!feed) return null;
  const f = feed.forces.find((x) => x.key === key) ?? feed.forces[0];
  // Moving the force down flips who rose: the stocks that move down with it.
  const rose = k >= 0 ? f.up : f.down;
  const fell = k >= 0 ? f.down : f.up;
  const max = Math.max(0, ...[...rose, ...fell].map((r) => Math.abs(r[2] * k)));
  const held = f.held_up + f.held_down;

  return (
    <section className="lp-band lp-live" aria-labelledby="live-title">
      <div className="lp-wrap">
        <p className="lp-eyebrow">Live · {feed.stocks.toLocaleString('en-US')} U.S. stocks · data through {date(feed.as_of)}</p>
        <h2 id="live-title" className="lp-h2">Move a force. See who moved with it.</h2>
        <p className="lp-lead lp-live-lead">
          Pick an economic force and the size of the move. These are the stocks that have risen and fallen
          most in weeks like it, beyond the stock market&rsquo;s own move, over the last three years.
        </p>

        <div className="lp-live-controls">
          <div className="lp-live-chips" role="radiogroup" aria-label="Economic force">
            {feed.forces.map((x) => (
              <button key={x.key} type="button" role="radio" aria-checked={x.key === f.key}
                      className={`lp-live-chip f-${x.key}`} onClick={() => setKey(x.key)}>
                <span className="lp-live-dot" aria-hidden="true" />{x.label}
              </button>
            ))}
          </div>
          <label className="lp-live-slider">
            <span>Size of the move: <b>{f.label} {move(k * f.step, f.unit)}</b></span>
            <input type="range" min={-MAX_MULTIPLE} max={MAX_MULTIPLE} step={0.5} value={k}
                   aria-valuetext={`${f.label} ${move(k * f.step, f.unit)}`}
                   onChange={(e) => setK(Number(e.target.value))} />
            <span className="lp-live-ticks" aria-hidden="true"><span>Fell</span><span>No change</span><span>Rose</span></span>
          </label>
        </div>

        {k === 0 ? (
          <p className="lp-live-none">Move the slider to see which stocks moved most with {f.lower ?? f.label.toLowerCase()}.</p>
        ) : (
          <div className="lp-live-cols" aria-live="polite">
            <List title="Rose most in weeks like this" rows={rose} k={k} max={max} />
            <List title="Fell most in weeks like this" rows={fell} k={k} max={max} />
          </div>
        )}

        <p className="lp-live-note">
          {held} of {f.measured} stocks moved with {f.lower ?? f.label.toLowerCase()} in a way that held up; the other {f.none}{' '}showed
          no link that could be told apart from noise, so they are not listed. Each figure is a stock&rsquo;s typical weekly
          move when {f.phrase}, scaled to the move you chose. It describes the past; it is not a forecast or advice.
        </p>
        <div className="lp-cta-row">
          <a className="lp-btn lp-btn-primary" href={`/explore#${f.key}:${k}`}>See every stock for this move</a>
          <a className="lp-btn lp-btn-secondary" href={`/scenario#${f.key}:${k}`}>Move several forces at once</a>
          <a className="lp-btn lp-btn-secondary" href="/map">Explore the stock map</a>
        </div>
      </div>
    </section>
  );
}
