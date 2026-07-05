/* lib/timeline.js
   Account-wise timeline model. Turns raw entities (+ their cluster tier) into a set
   of per-account "lifelines" built ONLY from real, source-provided dates:
     • account creation   — GitHub/Maigret created_at, Reddit created_utc
     • activity            — recent_posts[].posted_at (GitHub events, Reddit submissions)
     • last seen           — Wayback archived_at (YYYYMMDDHHMMSS)
     • breach exposure     — breach_details[].date
   Nothing is fabricated: an account with no genuine date is returned under `undated`
   and never plotted with a made-up timestamp. Both the timeline graph and the
   account cards consume this one model so they can never disagree.

   Why account-wise (profiling): an investigator reads a person by the shape of their
   footprint over time — which handle is oldest (their earliest online presence),
   whether a burst of accounts was created together (a life event, or the same person
   spinning up profiles), which accounts are still live vs. long-dormant, and when
   their data leaked. A flat month list buries all of that; per-account lifelines on a
   shared axis surface it. */

export const MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"];
const WEEKDAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// ---------- date parsing (source formats differ per scraper) ----------
export function parseWaybackTimestamp(ts) {
  const s = String(ts || "");
  if (s.length < 8) return null;
  const y = Number(s.slice(0, 4));
  const mo = Number(s.slice(4, 6)) - 1;
  const d = Number(s.slice(6, 8));
  const hh = Number(s.slice(8, 10) || "0");
  const mm = Number(s.slice(10, 12) || "0");
  const ss = Number(s.slice(12, 14) || "0");
  const dt = new Date(Date.UTC(y, mo, d, hh, mm, ss));
  return isNaN(dt.getTime()) ? null : dt;
}

export function parseDate(v) {
  if (!v) return null;
  const dt = new Date(v);
  return isNaN(dt.getTime()) ? null : dt;
}

// Reddit created_utc etc. are UNIX epochs, usually in SECONDS. Detect magnitude and
// scale up when it's clearly seconds (< ~year 2286 in ms) so it doesn't resolve to 1970.
export function parseEpoch(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  if (!isFinite(n) || n <= 0) return null;
  const ms = n < 1e12 ? n * 1000 : n;
  const dt = new Date(ms);
  return isNaN(dt.getTime()) ? null : dt;
}

// ---------- formatting ----------
export function formatFullDate(dt) {
  return `${WEEKDAY_NAMES[dt.getDay()]}, ${dt.getDate()} ${MONTH_NAMES[dt.getMonth()].slice(0, 3)} ${dt.getFullYear()}`;
}

export function formatTime(dt) {
  const hh = String(dt.getHours()).padStart(2, "0");
  const mm = String(dt.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

export function formatMonthYear(dt) {
  return `${MONTH_NAMES[dt.getMonth()].slice(0, 3)} ${dt.getFullYear()}`;
}

// Human "age" of an account from its creation date to now (or between two dates).
export function durationHuman(from, to) {
  const ms = to.getTime() - from.getTime();
  if (ms < 0) return "";
  const days = Math.floor(ms / 86400000);
  if (days < 1) return "today";
  if (days < 31) return days === 1 ? "1 day" : `${days} days`;
  const months = Math.floor(days / 30.44);
  if (months < 12) return months === 1 ? "1 month" : `${months} months`;
  const years = Math.floor(days / 365.25);
  const remMonths = Math.floor((days - years * 365.25) / 30.44);
  if (years >= 1 && remMonths > 0 && years < 5) return `${years}y ${remMonths}m`;
  return years === 1 ? "1 year" : `${years} years`;
}

export function relativeTime(dt, now) {
  const diffMs = now.getTime() - dt.getTime();
  if (diffMs < 0) return "in the future";
  const sec = Math.floor(diffMs / 1000);
  if (sec < 45) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return min === 1 ? "1 minute ago" : `${min} minutes ago`;
  const hrs = Math.floor(min / 60);
  if (hrs < 24) return hrs === 1 ? "1 hour ago" : `${hrs} hours ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return "1 day ago";
  if (days < 7) return `${days} days ago`;
  const weeks = Math.floor(days / 7);
  if (days < 30) return weeks === 1 ? "1 week ago" : `${weeks} weeks ago`;
  const months = Math.floor(days / 30.44);
  if (days < 365) return months <= 1 ? "1 month ago" : `${months} months ago`;
  const years = Math.floor(days / 365.25);
  return years === 1 ? "1 year ago" : `${years} years ago`;
}

export function displayName(platform) {
  const p = (platform || "").toLowerCase();
  const known = {
    github: "GitHub", instagram: "Instagram", telegram: "Telegram", reddit: "Reddit",
    linkedin: "LinkedIn", twitter: "Twitter", x: "X", hibp: "HIBP",
    xposedornot: "XposedOrNot", dehashed: "DeHashed", leakcheck: "LeakCheck",
    wayback: "Web Archive", facebook: "Facebook", youtube: "YouTube", tiktok: "TikTok",
    gitlab: "GitLab", medium: "Medium", spotify: "Spotify", steam: "Steam",
  };
  return known[p] || (platform ? platform.charAt(0).toUpperCase() + platform.slice(1) : "Account");
}

// Event-kind vocabulary shared by graph glyphs and card rows.
export const EVENT_KINDS = {
  created:  { label: "Account created", glyph: "ring",    order: 0 },
  activity: { label: "Activity",        glyph: "dot",     order: 1 },
  archived: { label: "Last seen (Web Archive)", glyph: "square", order: 2 },
  breach:   { label: "Data breach",     glyph: "diamond", order: 3 },
};

// Confidence tier → color + label. Neutral gray for "not linked" is deliberate (it
// reads as absence-of-evidence, not a fifth category). Breach markers override to red.
export const TIER_STYLE = {
  HIGH:   { color: "#00ff88", soft: "rgba(0,255,136,0.14)",  label: "Strong match" },
  MEDIUM: { color: "#ffb703", soft: "rgba(255,183,3,0.14)",  label: "Possible match" },
  LOW:    { color: "#64748b", soft: "rgba(100,116,139,0.16)", label: "Not linked" },
  REJECT: { color: "#64748b", soft: "rgba(100,116,139,0.16)", label: "Not linked" },
};
export const BREACH_COLOR = "#ff3366";

export function tierStyle(tier) {
  return TIER_STYLE[tier] || TIER_STYLE.LOW;
}

// Build the per-account lifelines. `tierByEntity` maps entity_id -> "HIGH"|"MEDIUM"|...
// (from the case's clusters); missing => "LOW" (not linked).
export function buildTimeline(entities, tierByEntity = {}) {
  const accounts = [];
  const undated = [];
  let minDate = null;
  let maxDate = null;
  const bump = (dt) => {
    if (!dt) return;
    if (!minDate || dt < minDate) minDate = dt;
    if (!maxDate || dt > maxDate) maxDate = dt;
  };

  (entities || []).forEach((e) => {
    const m = e.metadata || {};
    const platform = e.platform || "";
    const tier = tierByEntity[e.entity_id] || "LOW";
    const isBreach = e.type === "breach";
    const events = [];

    if (isBreach) {
      const details = Array.isArray(m.breach_details) && m.breach_details.length
        ? m.breach_details
        : (Array.isArray(m.breaches) ? m.breaches.map((n) => ({ name: n, date: null })) : []);
      details.forEach((d) => {
        const dt = parseDate(d.date);
        if (dt) { bump(dt); }
        events.push({
          kind: "breach", date: dt, hasTime: false,
          label: EVENT_KINDS.breach.label,
          detail: d.name || m.breach_name || "Unknown breach",
        });
      });
    } else {
      const created = parseDate(m.created_at) || parseEpoch(m.created_utc);
      if (created) {
        bump(created);
        events.push({ kind: "created", date: created, hasTime: true,
          label: EVENT_KINDS.created.label, detail: e.value || "" });
      }
      const archived = parseWaybackTimestamp(m.archived_at);
      if (archived) {
        bump(archived);
        events.push({ kind: "archived", date: archived, hasTime: true,
          label: EVENT_KINDS.archived.label, detail: e.value || "" });
      }
      if (Array.isArray(m.recent_posts)) {
        m.recent_posts.forEach((post) => {
          const dt = parseDate(post.posted_at);
          if (!dt) return;
          bump(dt);
          events.push({ kind: "activity", date: dt, hasTime: true,
            label: post.title || EVENT_KINDS.activity.label, detail: e.value || "" });
        });
      }
    }

    const datedEvents = events.filter((ev) => ev.date).sort((a, b) => a.date - b.date);
    const account = {
      entity_id: e.entity_id,
      platform,
      value: e.value || "",
      name: displayName(platform),
      tier,
      isBreach,
      exactMatch: !!m.exact_seed_match,   // the literal handle/email searched — pinned to Strong
      url: e.source_url || "",
      events: datedEvents,
      undatedEvents: events.filter((ev) => !ev.date),
      firstDate: datedEvents.length ? datedEvents[0].date : null,
      lastDate: datedEvents.length ? datedEvents[datedEvents.length - 1].date : null,
    };

    if (datedEvents.length) accounts.push(account);
    else undated.push(account);
  });

  // Oldest-first: the earliest online presence sits at the top of the graph, and
  // creation bursts line up visually.
  accounts.sort((a, b) => (a.firstDate - b.firstDate) || (a.name.localeCompare(b.name)));

  // Pad the domain so end markers don't sit on the frame; ensure "now" is visible so
  // dormancy (a lifeline that stops well short of today) is legible.
  const now = new Date();
  const domainEnd = maxDate && maxDate > now ? maxDate : now;
  const domainStart = minDate || domainEnd;
  const span = Math.max(1, domainEnd - domainStart);
  const pad = span * 0.03;
  const domain = [new Date(domainStart.getTime() - pad), new Date(domainEnd.getTime() + pad)];

  return {
    accounts,
    undated,
    domain,
    now,
    stats: {
      dated: accounts.length,
      undated: undated.length,
      breaches: accounts.filter((a) => a.isBreach).length,
      earliest: minDate,
      latest: maxDate,
    },
  };
}

// Evenly spaced year boundaries covering the domain, for axis ticks + gridlines.
export function yearTicks(domain) {
  const [start, end] = domain;
  const startYear = start.getFullYear();
  const endYear = end.getFullYear();
  const span = end - start;
  // Choose a year step that keeps ticks readable (~<= 12 labels).
  const yearsSpanned = endYear - startYear + 1;
  const step = yearsSpanned <= 12 ? 1 : yearsSpanned <= 24 ? 2 : Math.ceil(yearsSpanned / 12);
  const ticks = [];
  for (let y = startYear; y <= endYear; y += step) {
    const dt = new Date(Date.UTC(y, 0, 1));
    const pct = ((dt - start) / span) * 100;
    if (pct >= -1 && pct <= 101) ticks.push({ year: y, pct: Math.max(0, Math.min(100, pct)) });
  }
  return ticks;
}

// Position (0..100) of a date within the domain.
export function pctOf(date, domain) {
  const [start, end] = domain;
  const span = Math.max(1, end - start);
  return Math.max(0, Math.min(100, ((date - start) / span) * 100));
}

// Split accounts into the three confidence bands the case room already uses, so the
// timeline reads the same way as everything else: Strong / Possible / Not linked.
// Breaches are pulled out entirely — they're leak EVENTS, not the person's accounts,
// and live in their own exposure band. Decisions (per product):
//   • exact-seed-match accounts ride in STRONG even if the linker rated them low —
//     the literal thing you searched for is never buried.
//   • an account already counts as strong via HIGH tier OR exact match.
export function groupByTier(accounts) {
  const breaches = [];
  const strong = [];
  const possible = [];
  const notLinked = [];
  (accounts || []).forEach((a) => {
    if (a.isBreach) { breaches.push(a); return; }
    if (a.tier === "HIGH" || a.exactMatch) strong.push(a);
    else if (a.tier === "MEDIUM") possible.push(a);
    else notLinked.push(a);
  });
  return { strong, possible, notLinked, breaches };
}

// One-line "who is this person, over time" summary derived from the CONFIRMED identity
// (strong + possible) — the set we actually stand behind. `count` reflects ALL such
// accounts (dated + undated), because most platforms — Instagram, Threads, YouTube —
// publish no scrapable date, and it would be wrong to say "2 accounts" when 5 were
// confirmed just because only 2 could be plotted. The time facts (span, oldest, last
// active) are derived from whatever accounts DO carry a real date. Returns null only
// when there is nothing at all to summarize.
export function personSummary(accounts, now = new Date()) {
  const list = (accounts || []).filter((a) => !a.isBreach);
  if (!list.length) return null;
  const dated = list.filter((a) => a.firstDate);

  let earliest = null, latest = null, oldestAccount = null;
  const yearCounts = {};
  dated.forEach((a) => {
    const created = a.events.find((e) => e.kind === "created");
    const anchor = created ? created.date : a.firstDate;
    if (!earliest || anchor < earliest) { earliest = anchor; oldestAccount = a; }
    if (!latest || a.lastDate > latest) latest = a.lastDate;
    a.events.forEach((e) => { const y = e.date.getFullYear(); yearCounts[y] = (yearCounts[y] || 0) + 1; });
  });

  // Busiest year (only meaningful with a real cluster of activity across >1 year).
  let busiestYear = null, busiestCount = 0;
  Object.entries(yearCounts).forEach(([y, c]) => { if (c > busiestCount) { busiestCount = c; busiestYear = Number(y); } });
  const multiYear = Object.keys(yearCounts).length > 1;

  return {
    count: list.length,
    datedCount: dated.length,
    hasDates: dated.length > 0,
    earliest,
    latest,
    span: earliest ? durationHuman(earliest, latest) : null,
    earliestYear: earliest ? earliest.getFullYear() : null,
    latestYear: latest ? latest.getFullYear() : null,
    oldestPlatform: oldestAccount ? oldestAccount.name : null,
    lastActive: latest ? relativeTime(latest, now) : null,
    busiestYear: multiYear && busiestCount >= 2 ? busiestYear : null,
  };
}

// Account-creation histogram: bin creation dates so bursts are visible over the axis.
export function creationBins(accounts, domain, binCount = 48) {
  const [start, end] = domain;
  const span = Math.max(1, end - start);
  const bins = new Array(binCount).fill(0);
  accounts.forEach((a) => {
    const created = a.events.find((ev) => ev.kind === "created");
    const anchor = created ? created.date : a.firstDate;
    if (!anchor) return;
    let idx = Math.floor(((anchor - start) / span) * binCount);
    idx = Math.max(0, Math.min(binCount - 1, idx));
    bins[idx] += 1;
  });
  const max = bins.reduce((m, v) => Math.max(m, v), 0);
  return { bins, max, binWidthPct: 100 / binCount };
}
