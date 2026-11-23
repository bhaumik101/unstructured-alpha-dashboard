'use client';

// "Your desk": shown only to a returning visitor, right under the hero. Your
// level and streak, the learning path with your next step, what you looked at
// last, and today's games -- everything this browser already remembers, in
// one place, so coming back starts where you left off. Nothing on the server
// render (useSyncExternalStore), so the HTML never disagrees with the store.

import { useMemo, useSyncExternalStore } from 'react';
import { desk, STEPS } from './desk';

const KEYS = ['ua_progress_v1', 'ua-seen-v1', 'ua-list', 'ua-xray-last'] as const;

function subscribe(cb: () => void) {
  window.addEventListener('storage', cb);
  return () => window.removeEventListener('storage', cb);
}
function snapshot(): string | null {
  try { return JSON.stringify(KEYS.map((k) => localStorage.getItem(k))); } catch { return null; }
}

export default function Desk() {
  const raw = useSyncExternalStore(subscribe, snapshot, () => null);
  const d = useMemo(() => {
    if (!raw) return null;
    const [progress, seen, list, mix] = JSON.parse(raw) as (string | null)[];
    return desk({ progress, seen, list, mix });
  }, [raw]);
  if (!d || !d.returning) return null;

  const span = Math.max(1, d.ceil - d.floor);
  const frac = d.next ? Math.min(1, (d.xp - d.floor) / span) : 1;
  const R = 34, C = 2 * Math.PI * R;
  const nextStep = STEPS.find(([k]) => !d.steps[k]);
  const games: [string, string, string][] = [['quiz', 'Which way did it move?', '/quiz'], ['guess', 'Whose fingerprint?', '/guess']];

  return (
    <section className="lp-desk" aria-labelledby="desk-title">
      <div className="lp-wrap">
        <div className="lp-desk-head">
          <p className="lp-kicker">Welcome back</p>
          <h2 id="desk-title" className="lp-desk-title">Your desk</h2>
          <span className="lp-small">Kept in this browser only.</span>
        </div>
        <div className="lp-desk-grid">
          <div className="lp-desk-card lp-desk-level">
            <svg viewBox="0 0 80 80" className="lp-ring" role="img"
                 aria-label={`${d.level}, ${d.xp} XP${d.next ? `, ${d.ceil - d.xp} to ${d.next}` : ''}`}>
              <circle cx="40" cy="40" r={R} className="lp-ring-track" />
              <circle cx="40" cy="40" r={R} className="lp-ring-fill" strokeDasharray={`${(C * frac).toFixed(1)} ${C.toFixed(1)}`}
                      transform="rotate(-90 40 40)" />
              <text x="40" y="38" textAnchor="middle" className="lp-ring-n">{d.levelNo}</text>
              <text x="40" y="52" textAnchor="middle" className="lp-ring-l">LEVEL</text>
            </svg>
            <div>
              <b className="lp-desk-big">{d.level}</b>
              <div className="lp-small">{d.xp} XP{d.next ? ` · ${d.ceil - d.xp} to ${d.next}` : ' · top level'}</div>
              <div className="lp-desk-streak">
                <span aria-hidden="true">{d.streak > 0 ? '◆' : '◇'}</span>
                {d.streak > 0 ? `${d.streak}-day streak` : 'Start a streak today'}
              </div>
            </div>
          </div>

          <div className="lp-desk-card lp-desk-path">
            <div className="lp-desk-k">Your path · {Object.keys(d.steps).filter((k) => STEPS.some(([s]) => s === k)).length} of {STEPS.length}</div>
            <ol className="lp-path" aria-label="Learning path">
              {STEPS.map(([k, label, href]) => {
                const done = !!d.steps[k], isNext = nextStep && nextStep[0] === k;
                return (
                  <li key={k} className={done ? 'is-done' : isNext ? 'is-next' : ''}>
                    <a href={href} aria-label={`${label}${done ? ' (done)' : isNext ? ' (next)' : ''}`}>
                      <i aria-hidden="true">{done ? '✓' : ''}</i><span>{label}</span>
                    </a>
                  </li>
                );
              })}
            </ol>
            {nextStep
              ? <a className="lp-btn lp-btn-primary lp-btn-sm" href={nextStep[2]}>Next: {nextStep[1]} →</a>
              : <span className="lp-small">Path complete. Keep your streak with today&rsquo;s games.</span>}
          </div>

          <div className="lp-desk-card lp-desk-resume">
            <div className="lp-desk-k">Pick up where you left off</div>
            {d.seen.length > 0 && (
              <ul className="lp-desk-chips" aria-label="Recently viewed stocks">
                {d.seen.slice(0, 6).map((t) => <li key={t}><a href={`/exposure/${encodeURIComponent(t)}`}>{t}</a></li>)}
              </ul>
            )}
            <div className="lp-desk-links">
              {d.mix && <a href={`/xray?p=${encodeURIComponent(d.mix)}`}>Your last X-ray mix →</a>}
              {d.list.length > 0 && <a href="/mylist">Your list · {d.list.length} →</a>}
              {!d.mix && !d.list.length && !d.seen.length && <a href="/exposure">Look up a stock →</a>}
            </div>
            <div className="lp-desk-games">
              {games.map(([g, label, href]) => {
                const r = d.today[g];
                return (
                  <a key={g} href={href} className={r ? 'is-done' : ''}>
                    <b>{label}</b><span>{r ? `Today: ${r[0]}/${r[1]}` : 'Today’s round →'}</span>
                  </a>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
