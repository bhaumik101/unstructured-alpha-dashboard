'use client';

// The quiet proof strip under the hero, read from the same feed as the demo:
// what is covered, how often it is refreshed, and through when. Counts of
// held-up readings live further down (LiveMovers), where they explain
// something; here they would compete with the product. Hidden if the feed
// can't be read -- never a number typed in.

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

  const stats: [string, string][] = [
    [feed.stocks.toLocaleString('en-US'), 'Stocks and ETFs measured'],
  ];
  if (feed.forces_measured) stats.push([String(feed.forces_measured), 'Economic forces']);
  stats.push(['Weekly', 'Refreshed, three years of returns']);
  stats.push([date(feed.as_of), 'Data through']);
  return (
    <section className="lp-wrap lp-proof" aria-label="Coverage">
      <dl>
        {stats.map(([v, k]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
