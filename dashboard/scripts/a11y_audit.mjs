#!/usr/bin/env node
/**
 * Accessibility baseline via axe-core, run against the DEPLOYED app.
 *
 * WHY THIS EXISTS
 * ---------------
 * A hand-rolled contrast probe produced badly wrong numbers during the 2026-08-17
 * design audit. It determined an element's background by walking the DOM reading
 * `backgroundColor`, which ignores `background-image` — so the primary CTA, painted
 * with a gradient, was reported at 1.08:1 when it is actually 7.07:1. Correcting the
 * probe to composite gradients and alpha produced numbers that disagreed across
 * pages and still flagged elements whose computed colour was demonstrably fine.
 *
 * Layered alpha over gradients is genuinely hard. axe-core already solves it and is
 * the reference implementation auditors cite. Do not hand-roll this again.
 *
 * TWO THINGS THIS DOES NOT DO
 * ---------------------------
 * 1. It is NOT signed in. Streamlit auth lives behind a cookie this script has no
 *    way to obtain, and credentials must never be scripted. Pro-gated pages
 *    therefore report on their GATE, not their content — Ticker Deep Dive renders
 *    ~3,200 chars here versus ~16,300 signed in. Numbers from this script apply to
 *    public surfaces only, and the output prints the character count so a
 *    suspiciously small page is obvious.
 * 2. A "0 violations" result is meaningless if the page never rendered. Streamlit
 *    boots slowly and paints progressively, so this waits for real content and
 *    prints `rendered:` alongside every result. Treat `rendered: false` as no data,
 *    not as a pass.
 *
 * USAGE
 *   cd dashboard && node scripts/a11y_audit.mjs [urls...]
 *   (needs `npm i puppeteer axe-core` in a scratch dir, or npx)
 *
 * Defaults to the public surfaces, dark and light.
 */
import puppeteer from "puppeteer";
import { readFileSync } from "fs";
import { createRequire } from "module";

const AXE = readFileSync(
  createRequire(import.meta.url).resolve("axe-core/axe.min.js"),
  "utf8",
);

const APP = "https://app.unstructuredalpha.com";
const DEFAULTS = [
  "https://www.unstructuredalpha.com/",
  `${APP}/`,
  `${APP}/?theme=light`,
  `${APP}/signal-dashboard`,
  `${APP}/signal-dashboard?theme=light`,
  `${APP}/track-record`,
  `${APP}/today-s-brief`,
];

// A page is "rendered" once the boot splash has lifted and the main block
// carries copy of its own.
//
// The first version demanded 3,000 chars, which measured the wrong thing. On a
// full 32-route sweep that disqualified 13 pages that HAD rendered -- every Pro
// gate and auth wall (~1,700 chars: chrome plus an upgrade panel) plus four
// real content pages sitting at 2,383-2,988. Their axe results were discarded
// as "no data", including four genuine contrast failures on /sector-view.
//
// A gate is not a failure to render. It is what an anonymous visitor actually
// sees, which makes it one of the more important surfaces to audit, not one to
// throw away. So the bar is the chrome-only baseline (~1,200: nav + 33 proxy
// links + ticker tape) plus a margin, and the page reports WHICH state it
// reached rather than a bare pass/fail.
const CHROME_BASELINE = 1200;
const MIN_CHARS = 1400;   // chrome + something of the page's own
const FULL_PAGE_CHARS = 3000;   // enough copy to be a populated content page
const SETTLE_TRIES = 40;
const SETTLE_MS = 3000;

const urls = process.argv.slice(2).length ? process.argv.slice(2) : DEFAULTS;
const browser = await puppeteer.launch({ headless: "new", args: ["--no-sandbox"] });
let worstNodes = 0;

const failed = [];
for (const url of urls) {
  const page = await browser.newPage();
  try {
  await page.setViewport({ width: 1440, height: 900 });
  try {
    await page.goto(url, { waitUntil: "networkidle2", timeout: 90000 });
  } catch {
    /* measure whatever painted rather than aborting the run */
  }

  // Streamlit is an SPA: it can re-navigate while we are mid-evaluate, which
  // rejects with "Execution context was destroyed". Unhandled, that killed the
  // WHOLE run on the fourth URL and is why this harness had only ever been
  // pointed at a handful of pages. A destroyed context is a retry, not a
  // failure -- the next poll runs in the new context.
  const settle = async (fn, arg) => {
    try {
      return await page.evaluate(fn, arg);
    } catch (e) {
      if (String(e).includes("Execution context was destroyed")) return null;
      throw e;
    }
  };

  let rendered = false;
  for (let i = 0; i < SETTLE_TRIES; i++) {
    const r = await settle((min) => {
      const m = document.querySelector('[data-testid="stMain"]') || document.body;
      return (m.innerText || "").length > min && !document.getElementById("ua-boot-splash");
    }, FULL_PAGE_CHARS);
    rendered = r === true;
    if (rendered) break;
    await new Promise((r) => setTimeout(r, SETTLE_MS));
  }

  const diag = (await settle(() => {
    const m = document.querySelector('[data-testid="stMain"]') || document.body;
    return {
      chars: (m.innerText || "").length,
      theme: document.documentElement.getAttribute("data-ua-theme") || "dark",
    };
  })) || { chars: 0, theme: "unknown" };

  await page.evaluate(AXE);
  const res = await page.evaluate(async () => {
    const r = await window.axe.run(document, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] },
    });
    return {
      violations: r.violations.map((v) => ({
        id: v.id,
        impact: v.impact,
        n: v.nodes.length,
        help: v.help,
      })),
      passes: r.passes.length,
      incomplete: r.incomplete.length,
    };
  });

  const nodes = res.violations.reduce((a, v) => a + v.n, 0);
  // A state, not a boolean. "gate" is a real surface with real results; only
  // "empty" means the numbers below are meaningless.
  const state = diag.chars >= FULL_PAGE_CHARS ? "full"
              : diag.chars >= MIN_CHARS       ? "gate"
              : "empty";
  if (state !== "empty") worstNodes = Math.max(worstNodes, nodes);
  console.log(`\n=== ${url}`);
  console.log(
    `    state=${state}  settled=${rendered}  chars=${diag.chars}  theme=${diag.theme}` +
      (state === "empty"
        ? `   << NO DATA — under the ~${CHROME_BASELINE}-char chrome baseline, ignore the result below`
        : state === "gate"
          ? "   (gate/auth wall — real surface, results count)"
          : ""),
  );
  console.log(
    `    ${res.violations.length} violation types, ${nodes} nodes | ` +
      `${res.passes} passes | ${res.incomplete} incomplete (needs human review)`,
  );
  for (const v of res.violations.sort((a, b) => b.n - a.n)) {
    console.log(
      `      ${String(v.n).padStart(4)}  ${(v.impact || "?").padEnd(8)} ` +
        `${v.id.padEnd(26)} ${v.help.slice(0, 52)}`,
    );
  }
  } catch (e) {
    // One unmeasurable page must not end the sweep. Record it and move on --
    // a partial sweep with a named gap beats no sweep at all.
    failed.push(`${url} :: ${String(e).split("\n")[0]}`);
    console.log(`\n=== ${url}`);
    console.log(`    NOT MEASURED — ${String(e).split("\n")[0]}`);
  } finally {
    await page.close();
  }
}

await browser.close();
console.log(`\nworst single page: ${worstNodes} nodes`);
if (failed.length) {
  console.log(`\n${failed.length} page(s) could not be measured:`);
  for (const f of failed) console.log(`  ${f}`);
}
