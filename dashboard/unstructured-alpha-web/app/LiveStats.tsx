'use client';

// A strip of live figures under the hero, read from the same feed as the demo:
// how many stocks are measured, through when, how many of their core readings
// held up, and how many forces have readings. Hidden if the feed can't be read.

import { useEffect, useState } from 'react';
import { date, getFeed, type Feed } from './feed';

export default function LiveStats() {
  const [feed, setFeed] = useState<Feed | null>(null);
  useEffect(() => {
    let live = true;
    getFeed().then((d) => { if (live) setFeed(d); });
    return () => { live = false; };
  }, []);
  if (!feed) return null;

  const measured = feed.forces.reduce((n, f) => n + f.measured, 0);
  const held = feed.forces.reduce((n, f) => n + f.held_up + f.held_down, 0);
  // The core force with the most stocks whose reading held up, either way.
  const top = [...feed.forces].sort((a, b) => (b.held_up + b.held_down) - (a.held_up + a.held_down))[0];
  const stats: [string, string, string][] = [
    [feed.stocks.toLocaleString('en-US'), 'U.S. stocks measured', 'updated every week'],
    [date(feed.as_of), 'Data through', 'three years of weekly returns'],
    [`${held.toLocaleString('en-US')} of ${measured.toLocaleString('en-US')}`, 'Core readings held up',
     'the rest: no clear link'],
    [top.label, 'Most shared link',
     `${(top.held_up + top.held_down).toLocaleString('en-US')} of ${top.measured.toLocaleString('en-US')} stocks`],
  ];
  if (feed.forces_measured) {
    stats.splice(1, 0, [String(feed.forces_measured), 'Economic forces', 'rates and oil to gold and the yen']);
  }
  return (
    <section className="lp-wrap lp-stats-wrap" aria-label="Live figures">
      <dl className="lp-stats">
        {stats.map(([v, k, s]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd><b>{v}</b><span>{s}</span></dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
