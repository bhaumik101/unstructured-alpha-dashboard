// The learner's progress, read from the same browser store the public tool
// pages write (utils/progress.py, key ua_progress_v1). The landing and those
// pages share the www origin, so a returning player is recognised here too.
// Only what the landing shows is read: the streak and today's plays. The
// streak rule mirrors utils/progress.py (a test runs both on the same store).

export const KEY = 'ua_progress_v1';
export type Played = [number, number];
export type Progress = { streak: number; today: { quiz?: Played; guess?: Played }; any: boolean };

function iso(d: Date): string {
  const p = (n: number) => (n < 10 ? '0' : '') + n;
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function summarize(raw: string | null, now: Date = new Date()): Progress {
  let days: Record<string, { quiz?: Played; guess?: Played }> = {};
  let steps = 0;
  try {
    const p = JSON.parse(raw || '{}');
    if (p && typeof p === 'object') {
      if (p.d && typeof p.d === 'object') days = p.d;
      if (p.l && typeof p.l === 'object') steps = Object.keys(p.l).length;
    }
  } catch { /* a corrupt store is a fresh start */ }
  const d = new Date(now.getTime());
  if (!days[iso(d)]) d.setDate(d.getDate() - 1);   // today not played yet: the streak still stands
  let streak = 0;
  while (days[iso(d)]) { streak++; d.setDate(d.getDate() - 1); }
  const today = days[iso(now)] || {};
  return { streak, today, any: streak > 0 || steps > 0 || Object.keys(days).length > 0 };
}
