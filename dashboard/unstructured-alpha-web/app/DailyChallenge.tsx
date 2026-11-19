'use client';

// "Today's challenge": the two daily games, and -- for someone who has played
// before -- their streak and what they have already done today. Rendered as
// an invitation first (what a newcomer and a crawler see), then personalised
// from the browser store after mount (app/progress.ts). Nothing is sent.

import { useMemo, useSyncExternalStore } from 'react';
import { KEY, summarize, type Progress } from './progress';

const GAMES = [
  { key: 'quiz' as const, href: '/quiz', title: 'Which way did it move?', what: '10 questions · about 2 minutes',
    blurb: 'When oil, rates or the dollar moved, did each stock rise, fall, or show no clear link?' },
  { key: 'guess' as const, href: '/guess', title: 'Whose fingerprint?', what: '5 rounds · about 2 minutes',
    blurb: 'See a mystery stock’s five-force profile and pick it out of four.' },
];

// The store as an external source: null on the server (the invitation), the
// raw string in the browser; another tab finishing a round updates it.
function subscribe(on: () => void) {
  window.addEventListener('storage', on);
  return () => window.removeEventListener('storage', on);
}
function snapshot(): string | null {
  try { return localStorage.getItem(KEY); } catch { return null; }   // storage blocked: stay an invitation
}

export default function DailyChallenge() {
  const raw = useSyncExternalStore(subscribe, snapshot, () => null);
  const me: Progress | null = useMemo(() => (raw === null ? null : summarize(raw)), [raw]);
  const streak = me?.streak ?? 0;
  return (
    <section className="lp-band lp-daily" aria-labelledby="daily-title">
      <div className="lp-wrap">
        <div className="lp-daily-head">
          <div>
            <p className="lp-eyebrow">Today&rsquo;s challenge</p>
            <h2 id="daily-title" className="lp-h2">Two minutes a day, and you&rsquo;ll read the market differently</h2>
          </div>
          {me?.any ? (
            <a className="lp-daily-streak" href="/learn#path">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2c1 3.5 4.5 5.6 4.5 10a4.5 4.5 0 0 1-9 0c0-1.7.7-3 1.7-4.1.2 1.6 1 2.7 2.3 3.1C11 8.6 11 5 12 2z"/></svg>
              {streak ? `${streak}-day streak` : 'Start a new streak today'} <span>· your path →</span>
            </a>
          ) : null}
        </div>
        <ul className="lp-daily-games">
          {GAMES.map((g) => {
            const done = me?.today[g.key];
            return (
              <li key={g.key}>
                <a href={g.href} className={done ? 'is-done' : ''}>
                  <span className="lp-daily-what">{g.what}</span>
                  <b>{g.title}</b>
                  <span className="lp-daily-blurb">{g.blurb}</span>
                  <span className="lp-daily-cta">
                    {done ? `✓ Done today: ${done[0]} of ${done[1]}. Practise again →` : 'Play today’s round →'}
                  </span>
                </a>
              </li>
            );
          })}
        </ul>
        <p className="lp-daily-note">Same questions for everyone each day, from measured data. Your streak stays in this browser. Practice reading the data, not investing advice.</p>
      </div>
    </section>
  );
}
