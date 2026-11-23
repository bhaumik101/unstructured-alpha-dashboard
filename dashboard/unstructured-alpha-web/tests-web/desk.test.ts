// The desk's logic, run with Node's own test runner:  npm test
// (the Python suite checks the constants mirror utils/progress.py and
// utils/since_visit.py; this checks what the desk computes from them).
import { test } from "node:test";
import assert from "node:assert/strict";
import { desk, changes, fresh, HEAT_WEEKS } from "../app/desk.ts";

const NOW = new Date("2026-11-23T15:00:00");          // a Monday
const blank = { progress: null, seen: null, list: null, mix: null };
const prog = (d: Record<string, object>, l: Record<string, number> = {}) => JSON.stringify({ d, l });

test("a first-time visitor is not returning and has earned nothing", () => {
  const d = desk(blank, NOW);
  assert.equal(d.returning, false);
  assert.equal(d.milestones.filter((m) => m.done).length, 0);
  assert.equal(d.best, 0);
});

test("the best streak is the longest run ever, not the current one", () => {
  const days = {
    "2026-11-01": { quiz: [5, 10] }, "2026-11-02": { quiz: [5, 10] }, "2026-11-03": { guess: [2, 5] },
    "2026-11-04": { quiz: [1, 10] },                                   // a run of four
    "2026-11-22": { quiz: [3, 10] }, "2026-11-23": { quiz: [3, 10] },   // a current run of two
  };
  const d = desk({ ...blank, progress: prog(days) }, NOW);
  assert.equal(d.streak, 2);
  assert.equal(d.best, 4);
  const m = Object.fromEntries(d.milestones.map((x) => [x.key, x]));
  assert.equal(m.streak3.done, true);
  assert.equal(m.streak7.done, false);
  assert.equal(m.streak7.have, 4);
});

test("a streak across a month boundary counts", () => {
  const d = desk({ ...blank, progress: prog({ "2026-10-31": { quiz: [1, 10] }, "2026-11-01": { quiz: [1, 10] }, "2026-11-02": { quiz: [1, 10] } }) }, NOW);
  assert.equal(d.best, 3);
});

test("the heatmap is twelve Monday-first weeks ending this week, counting games per day", () => {
  const d = desk({ ...blank, progress: prog({ "2026-11-23": { quiz: [1, 10], guess: [1, 5] }, "2026-11-20": { quiz: [1, 10] } }) }, NOW);
  assert.equal(d.heat.length, HEAT_WEEKS);
  assert.ok(d.heat.every((w) => w.length === 7));
  const last = d.heat[HEAT_WEEKS - 1];
  assert.equal(last[0].day, "2026-11-23");            // Monday of this week
  assert.equal(last[0].n, 2);
  assert.equal(last[1].future, true);
  assert.equal(d.heat[HEAT_WEEKS - 2][4].day, "2026-11-20");
  assert.equal(d.heat[HEAT_WEEKS - 2][4].n, 1);
  assert.equal(d.heat[0][0].day, "2026-09-07");
  assert.equal(d.daysPlayed, 2);
});

test("a perfect round needs every answer right, and a round of zero questions is not perfect", () => {
  const ok = desk({ ...blank, progress: prog({ "2026-11-20": { quiz: [10, 10], guess: [4, 5] } }) }, NOW);
  const m = Object.fromEntries(ok.milestones.map((x) => [x.key, x.done]));
  assert.equal(m.sharp, true);
  assert.equal(m.prints, false);
  const zero = desk({ ...blank, progress: prog({ "2026-11-20": { quiz: [0, 0] } }) }, NOW);
  assert.equal(zero.milestones.find((x) => x.key === "sharp")!.done, false);
});

test("path, curiosity and list milestones count what the stores hold", () => {
  const seen = JSON.stringify(Object.fromEntries(Array.from({ length: 10 }, (_, i) => [`T${i}`, { t: i }])));
  const d = desk({ progress: prog({}, { learn: 1, quiz: 1, guess: 1, explore: 1, xray: 1 }), seen, list: '["A","B"]', mix: null }, NOW);
  const m = Object.fromEntries(d.milestones.map((x) => [x.key, x]));
  assert.equal(m.first.done, true);
  assert.equal(m.path.done, true);
  assert.equal(m.curious.done, true);
  assert.equal(m.keeper.done, false);
  assert.equal(m.keeper.have, 2);
});

test("fresh milestones are those earned and not yet shown", () => {
  const d = desk({ ...blank, progress: prog({}, { learn: 1 }) }, NOW);
  assert.deepEqual(fresh(d.milestones, null), ["first"]);
  assert.deepEqual(fresh(d.milestones, '["first"]'), []);
  assert.deepEqual(fresh(d.milestones, "not json"), ["first"]);
});

const FEED = {
  f: [["oil", "Oil", ""], ["rates", "Rates", ""], ["usd", "U.S. dollar", ""]] as [string, string, string][],
  s: {
    AAA: ["A co", "Tech", [[1.2, 1], [0.3, 0], [2.0, 1]]],
    BBB: ["B co", "Tech", [[0.1, 0], [0.9, 1], null]],
  } as Record<string, [string, string, ([number, number] | null)[]]>,
};

test("changes follow since_visit's rule: gained, then lost, then moved by at least MOVE", () => {
  const seen = JSON.stringify({
    AAA: { r: [[1.0, 0], [0.3, 1], [1.4, 1]], t: 1 },   // oil gained, rates lost, usd moved 0.6
    BBB: { r: [[0.9, 0], [0.5, 1], [1, 1]], t: 2 },     // rates held, moved 0.4 (< MOVE); usd now missing
    ZZZ: { r: [[1, 1]], t: 3 },                          // no longer in the feed
  });
  const c = changes(seen, FEED);
  assert.deepEqual(c.map((x) => `${x.t}:${x.label}:${x.kind}`), ["AAA:Oil:gained", "AAA:Rates:lost", "AAA:U.S. dollar:moved"]);
});

test("nothing remembered, a broken store or no feed means no changes", () => {
  assert.deepEqual(changes(null, FEED), []);
  assert.deepEqual(changes("{bad", FEED), []);
  assert.deepEqual(changes('{"AAA":{"r":[[1.2,1],[0.3,0],[2.0,1]]}}', FEED), []);
  assert.deepEqual(changes('{"AAA":{"r":[]}}', null), []);
});
