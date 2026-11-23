// "Your desk": a returning visitor's progress, read from the stores the public
// pages already keep in this browser. Nothing is sent anywhere.
//   ua_progress_v1  learning steps and daily games   (utils/progress.py)
//   ua-seen-v1      stocks viewed, newest first        (utils/since_visit.py)
//   ua-list         the saved list                     (utils/list_page.py)
//   ua-xray-last    the last X-ray mix                  (utils/xray_page.py)
//   ua-desk-badges  milestones this browser has already been shown (desk only)
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

// Milestones measure practice only -- never a market call. Each is
// [key, name, what earns it, need]; `have` comes from the stores below.
export const MILESTONES: [string, string, string, number][] = [
  ["first", "First step", "Finish any step on the path", 1],
  ["path", "Path walker", "Finish all five steps", 5],
  ["streak3", "Three in a row", "Play on three days running", 3],
  ["streak7", "A full week", "Play on seven days running", 7],
  ["sharp", "Sharp eye", "A perfect round of Which way did it move?", 1],
  ["prints", "Fingerprint reader", "A perfect round of Whose fingerprint?", 1],
  ["curious", "Curious", "Look up ten different stocks", 10],
  ["keeper", "Keeper", "Save three stocks to your list", 3],
];
export const HEAT_WEEKS = 12;
// utils/since_visit.py: a held reading must shift this many points to count as moved.
export const MOVE = 0.5;

export type Milestone = { key: string; name: string; how: string; need: number; have: number; done: boolean };
export type Desk = {
  xp: number; level: string; levelNo: number; next: string | null; floor: number; ceil: number;
  streak: number; best: number; steps: Record<string, number>; today: Record<string, [number, number]>;
  seen: string[]; list: string[]; mix: string; returning: boolean;
  heat: { day: string; n: number; future: boolean }[][]; daysPlayed: number;
  milestones: Milestone[];
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

  // best run of consecutive played days, ever
  const played = Object.keys(days).filter((k) => /^\d{4}-\d{2}-\d{2}$/.test(k)).sort();
  let best = 0, run = 0, prev = "";
  for (const k of played) {
    const y = new Date(k + "T12:00:00"); y.setDate(y.getDate() - 1);
    run = prev && iso(y) === prev ? run + 1 : 1; prev = k; best = Math.max(best, run);
  }

  // the last HEAT_WEEKS weeks, Monday-first columns, ending with this week
  const heat: { day: string; n: number; future: boolean }[][] = [];
  const start = new Date(now.getTime());
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7) - 7 * (HEAT_WEEKS - 1));
  const todayIso = iso(now);
  for (let w = 0; w < HEAT_WEEKS; w++) {
    const col: { day: string; n: number; future: boolean }[] = [];
    for (let i = 0; i < 7; i++) {
      const c = new Date(start.getTime()); c.setDate(start.getDate() + w * 7 + i);
      const k = iso(c), e = days[k];
      col.push({ day: k, n: e ? Object.keys(GAME_XP).filter((g) => e[g]).length : 0, future: k > todayIso });
    }
    heat.push(col);
  }

  const seenObj = parse<Record<string, { t?: number }>>(raw.seen, {});
  const seen = seenObj && typeof seenObj === "object" && !Array.isArray(seenObj)
    ? Object.keys(seenObj).sort((a, b) => (seenObj[b]?.t || 0) - (seenObj[a]?.t || 0)) : [];
  const listRaw = parse<unknown>(raw.list, []);
  const list = Array.isArray(listRaw) ? listRaw.filter((x): x is string => typeof x === "string") : [];
  const mix = typeof raw.mix === "string" && /^[A-Z0-9.:,\-]+$/i.test(raw.mix) ? raw.mix : "";
  const perfect = (g: string) => played.some((k) => { const r = days[k][g]; return !!r && r[1] > 0 && r[0] === r[1]; }) ? 1 : 0;
  const stepsDone = STEPS.filter(([k]) => steps[k]).length;
  const have: Record<string, number> = {
    first: stepsDone, path: stepsDone, streak3: best, streak7: best,
    sharp: perfect("quiz"), prints: perfect("guess"), curious: seen.length, keeper: list.length,
  };
  const milestones = MILESTONES.map(([key, name, how, need]) => {
    const h = Math.min(need, have[key] || 0);
    return { key, name, how, need, have: h, done: h >= need };
  });
  return {
    xp, level: LEVELS[lv][1], levelNo: lv + 1, next: next ? next[1] : null, floor: LEVELS[lv][0],
    ceil: next ? next[0] : xp, streak, best, steps, today: days[iso(now)] || {}, seen, list, mix,
    heat, daysPlayed: played.length, milestones,
    returning: xp > 0 || seen.length > 0 || list.length > 0 || !!mix,
  };
}

// "Since you looked": the same rule and order as utils/since_visit.py diff(),
// so the desk and My list never disagree about what changed.
export type Feed = { f: [string, string, string][]; s: Record<string, [string, string, ([number, number] | null)[]]>; as_of?: string };
export type Change = { t: string; label: string; kind: "gained" | "lost" | "moved"; was: number; now: number };

export function changes(seenRaw: string | null, feed: Feed | null): Change[] {
  if (!feed || !feed.s || !Array.isArray(feed.f)) return [];
  const o = parse<Record<string, { r?: ([number, number] | null)[] }>>(seenRaw, {});
  if (!o || typeof o !== "object" || Array.isArray(o)) return [];
  const out: Change[] = [];
  for (const t of Object.keys(o)) {
    const b = o[t], cur = feed.s[t];
    if (!cur || !b || !Array.isArray(b.r)) continue;
    feed.f.forEach((f, i) => {
      const was = b.r![i], now = cur[2][i];
      if (!was || !now) return;
      const kind = now[1] && !was[1] ? "gained" : was[1] && !now[1] ? "lost"
        : now[1] && Math.abs(now[0] - was[0]) >= MOVE ? "moved" : "";
      if (kind) out.push({ t, label: f[1], kind, was: was[0], now: now[0] });
    });
  }
  const rank = { gained: 0, lost: 1, moved: 2 };
  out.sort((a, b) => rank[a.kind] - rank[b.kind] || Math.abs(b.now - b.was) - Math.abs(a.now - a.was) || (a.t < b.t ? -1 : 1));
  return out;
}

// Milestones earned that this browser has not been shown yet.
export function fresh(milestones: Milestone[], shownRaw: string | null): string[] {
  const shown = parse<unknown>(shownRaw, []);
  const s = new Set(Array.isArray(shown) ? shown : []);
  return milestones.filter((m) => m.done && !s.has(m.key)).map((m) => m.key);
}
