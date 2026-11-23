'use client';

// "Your desk": shown only to a returning visitor, right under the hero. Your
// level and streak, the learning path with your next step, what you looked at
// last, and today's games -- everything this browser already remembers, in
// one place, so coming back starts where you left off. Below that: twelve
// weeks of practice, the milestones earned by practising (never by a market
// call), and what changed in the stocks you looked at since you saw them.
// Nothing on the server render (useSyncExternalStore), so the HTML never
// disagrees with the store.

import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { changes, desk, fresh, STEPS, type Change, type Feed } from './desk';

const SHOWN = 'ua-desk-badges';
const GLYPH: Record<string, string> = {
  first: '1', path: '5', streak3: '3', streak7: '7', sharp: '✓', prints: '◎', curious: '10', keeper: '★',
};
const lower = (l: string) => (l.startsWith('U.S.') ? l : l.charAt(0).toLowerCase() + l.slice(1));
const line = (c: Change) => `${c.t}: ${c.kind === 'gained' ? `link to ${lower(c.label)} now holds up`
  : c.kind === 'lost' ? `link to ${lower(c.label)} no longer holds up` : `${lower(c.label)} reading moved`}`;

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
    const out = desk({ progress, seen, list, mix });
    let shown: string | null = null;
    try { shown = localStorage.getItem(SHOWN); } catch { /* blocked store: everything earned reads as new */ }
    return { ...out, seenRaw: seen, fresh: fresh(out.milestones, shown) };
  }, [raw]);

  // Remember which milestones have been shown, so "New" appears once.
  const earnedKey = d ? d.milestones.filter((m) => m.done).map((m) => m.key).join(',') : '';
  useEffect(() => {
    if (!earnedKey) return;
    try { localStorage.setItem(SHOWN, JSON.stringify(earnedKey.split(','))); } catch { /* ignore */ }
  }, [earnedKey]);

  // What changed in the stocks you looked at: fetched only if you looked at some.
  const [feed, setFeed] = useState<Feed | null>(null);
  const hasSeen = !!d && d.seen.length > 0;
  useEffect(() => {
    if (!hasSeen) return;
    let live = true;
    fetch('/xray.json').then((r) => (r.ok ? r.json() : null)).then((f) => { if (live) setFeed(f); }).catch(() => {});
    return () => { live = false; };
  }, [hasSeen]);
  const changed = useMemo(() => (d ? changes(d.seenRaw, feed) : []), [d, feed]);

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
            {changed.length > 0 && (
              <a className="lp-desk-since" href="/mylist#since">
                <b>{changed.length} {changed.length === 1 ? 'change' : 'changes'} since you looked</b>
                <span>{changed.slice(0, 2).map(line).join('; ')}{changed.length > 2 ? '; …' : ''}</span>
              </a>
            )}
            {d.seen.length > 0 && (
              <ul className="lp-desk-chips" aria-label="Recently viewed stocks">
                {d.seen.slice(0, 6).map((t) => (
                  <li key={t}><a href={`/exposure/${encodeURIComponent(t)}`} className={changed.some((c) => c.t === t) ? 'is-changed' : ''}
                                 aria-label={changed.some((c) => c.t === t) ? `${t} (changed since you looked)` : undefined}>{t}</a></li>
                ))}
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

        <div className="lp-desk-grid lp-desk-row2">
          <div className="lp-desk-card lp-desk-practice">
            <div className="lp-desk-k">Your practice · last 12 weeks</div>
            <svg className="lp-heat" viewBox={`0 0 ${d.heat.length * 15 + 26} ${7 * 15}`} role="img"
                 aria-label={`Played on ${d.heat.flat().filter((c) => c.n).length} of the last ${d.heat.length * 7} days. Longest run: ${d.best} ${d.best === 1 ? 'day' : 'days'}.`}>
              {['M', '', 'W', '', 'F', '', ''].map((l, i) => l && <text key={i} x="0" y={i * 15 + 10} className="lp-heat-l">{l}</text>)}
              {d.heat.map((col, w) => col.map((c, i) => (
                <rect key={c.day} x={26 + w * 15} y={i * 15} width="12" height="12" rx="3"
                      className={c.future ? 'lp-heat-f' : `lp-heat-${c.n}`}><title>{c.future ? '' : `${c.day}: ${c.n ? `${c.n} ${c.n === 1 ? 'game' : 'games'}` : 'no games'}`}</title></rect>
              )))}
            </svg>
            <div className="lp-heat-foot">
              <span><b>{d.streak}</b> now</span><span><b>{d.best}</b> longest run</span><span><b>{d.daysPlayed}</b> days played</span>
              <span className="lp-heat-key" aria-hidden="true">less <i className="lp-heat-0" /><i className="lp-heat-1" /><i className="lp-heat-2" /> more</span>
            </div>
          </div>

          <div className="lp-desk-card lp-desk-badges">
            <div className="lp-desk-k">Milestones · {d.milestones.filter((m) => m.done).length} of {d.milestones.length}</div>
            <ul className="lp-badges">
              {d.milestones.map((m) => {
                const isNew = d.fresh.includes(m.key);
                return (
                  <li key={m.key} className={`${m.done ? 'is-done' : ''}${isNew ? ' is-new' : ''}`}
                      title={m.how}>
                    <svg viewBox="0 0 40 44" aria-hidden="true" className="lp-badge">
                      <path d="M20 2 37 11.5v21L20 42 3 32.5v-21Z" className="lp-badge-hex" />
                      {!m.done && m.have > 0 && <path d="M20 2 37 11.5v21L20 42 3 32.5v-21Z" className="lp-badge-prog" pathLength="1"
                                        strokeDasharray={`${(m.have / m.need).toFixed(3)} 1`} />}
                      <text x="20" y="27" textAnchor="middle" className="lp-badge-g">{GLYPH[m.key]}</text>
                    </svg>
                    <span className="lp-badge-n">{m.name}{isNew && <em>New</em>}</span>
                    <span className="lp-badge-s">{m.done ? m.how : `${m.have} of ${m.need} · ${m.how}`}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
