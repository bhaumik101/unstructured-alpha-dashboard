// "Your desk": a returning visitor's progress, read from the stores the public
// pages already keep in this browser. Nothing is sent anywhere.
//   ua_progress_v1  learning steps and daily games   (utils/progress.py)
//   ua-seen-v1      stocks viewed, newest first        (utils/since_visit.py)
//   ua-list         the saved list                     (utils/list_page.py)
//   ua-xray-last    the last X-ray mix                  (utils/xray_page.py)
// The XP and level rules mirror utils/progress.py; tests/test_desk.py keeps
// the two in step.

export const STEPS: [string, string, string][] = [
  ["learn", "Read a reading", "/learn#evidence"],
  ["quiz", "Which way did it move?", "/quiz"],
  ["guess", "Whose fingerprint?", "/guess"],
  ["explore", "What if? Move a force", "/explore"],
  ["xray", "X-ray a portfolio", "/xray"],
];
export const STEP_XP = 50;
export const LEVELS: [number, string][] = [
  [0, "Newcomer"], [100, "Reader"], [300, "Apprentice"], [700, "Analyst"],
  [1500, "Senior analyst"], [3000, "Macro strategist"],
];
export const GAME_XP: Record<string, [number, number]> = { quiz: [20, 10], guess: [20, 20] };

export type Desk = {
  xp: number; level: string; levelNo: number; next: string | null; floor: number; ceil: number;
  streak: number; steps: Record<string, number>; today: Record<string, [number, number]>;
  seen: string[]; list: string[]; mix: string; returning: boolean;
};

function iso(d: Date): string {
  const p = (n: number) => (n < 10 ? "0" : "") + n;
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function parse<T>(raw: string | null, fallback: T): T {
  try { const v = JSON.parse(raw || ""); return v ?? fallback; } catch { return fallback; }
}

export function desk(raw: { progress: string | null; seen: string | null; list: string | null; mix: string | null },
                     now: Date = new Date()): Desk {
  const p = parse<{ d?: Record<string, Record<string, [number, number]>>; l?: Record<string, number> }>(raw.progress, {});
  const days = p && typeof p.d === "object" && p.d ? p.d : {};
  const steps = p && typeof p.l === "object" && p.l ? p.l : {};
  let xp = 0;
  for (const [k] of STEPS) if (steps[k]) xp += STEP_XP;
  for (const day of Object.keys(days)) {
    for (const g of Object.keys(GAME_XP)) {
      const r = days[day][g];
      if (r) xp += GAME_XP[g][0] + GAME_XP[g][1] * r[0];
    }
  }
  let lv = 0;
  LEVELS.forEach(([need], i) => { if (xp >= need) lv = i; });
  const next = LEVELS[lv + 1];
  const d = new Date(now.getTime());
  if (!days[iso(d)]) d.setDate(d.getDate() - 1);   // today not played yet: the streak still stands
  let streak = 0;
  while (days[iso(d)]) { streak++; d.setDate(d.getDate() - 1); }

  const seenObj = parse<Record<string, { t?: number }>>(raw.seen, {});
  const seen = seenObj && typeof seenObj === "object" && !Array.isArray(seenObj)
    ? Object.keys(seenObj).sort((a, b) => (seenObj[b]?.t || 0) - (seenObj[a]?.t || 0)) : [];
  const listRaw = parse<unknown>(raw.list, []);
  const list = Array.isArray(listRaw) ? listRaw.filter((x): x is string => typeof x === "string") : [];
  const mix = typeof raw.mix === "string" && /^[A-Z0-9.:,\-]+$/i.test(raw.mix) ? raw.mix : "";
  return {
    xp, level: LEVELS[lv][1], levelNo: lv + 1, next: next ? next[1] : null, floor: LEVELS[lv][0],
    ceil: next ? next[0] : xp, streak, steps, today: days[iso(now)] || {}, seen, list, mix,
    returning: xp > 0 || seen.length > 0 || list.length > 0 || !!mix,
  };
}
