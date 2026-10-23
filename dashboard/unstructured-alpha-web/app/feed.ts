// The landing page's live feed (/landing.json, proxied to the SEO service),
// fetched once and shared by every component that shows it. A failed or
// empty feed resolves to null, and each component then hides itself rather
// than show anything invented.

export type Row = [string, string, number, string];
export type Force = {
  key: string; label: string; lower?: string; phrase: string; step: number; unit: string;
  measured: number; none: number; held_up: number; held_down: number; up: Row[]; down: Row[];
};
export type Feed = { as_of: string; stocks: number; forces_measured?: number; forces: Force[] };

let pending: Promise<Feed | null> | null = null;

export function getFeed(): Promise<Feed | null> {
  pending ??= fetch('/landing.json')
    .then((r) => (r.ok ? r.json() : null))
    .then((d: Feed | null) => (d && Array.isArray(d.forces) && d.forces.length ? d : null))
    .catch(() => null);
  return pending;
}

export function date(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso
    : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}
