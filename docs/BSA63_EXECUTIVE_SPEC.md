# BSA-63 Executive Report — Build Spec

Read this whole document before writing code. It tells you exactly what to build,
what data you get, and what "done" looks like. Follow it precisely.

## 0. The one rule that matters most

Build a **new, standalone file**: `bsa63_executive_generator.py`.
Do **not** open, import from, or modify `bsa63_generator.py`. If you need logic
from it, re-implement it in the new file. This is non-negotiable.

## 1. What you're building and why

The current report (`bsa63_generator.py`) is correct but unreadable for its
actual audience: judges, magistrates, and investigating officers who are not
engineers. Right now the first thing a reader sees is a table of SHA-256
hashes and internal action names. The real finding — "these two accounts
belong to the same person, here's why" — is buried on page 4 or later.

You are building a second script that takes the exact same underlying case
data and produces a different PDF: the important conclusions up front in
plain language, and all the cryptographic/legal proof material moved to an
appendix at the back where a lawyer would expect to find supporting exhibits.

Nothing about the underlying evidence changes. You are only changing what is
shown first, what is shown at all in the summary, and how it looks.

## 2. Input data contract

Do not hardcode the case in the script. Write a function that accepts a
Python dict (or loads one from a JSON file path passed as a CLI argument)
shaped like this:

```json
{
  "case": {
    "case_reference": "46de969091e340bb900bb6df25007203",
    "case_title": "test111",
    "seed_identifiers": ["username: ash29_03"],
    "investigating_officer": "admin",
    "jurisdiction": null,
    "report_generated_utc": "2026-07-04T05:30:00Z",
    "produced_by": "VERTEX"
  },
  "clusters": [
    {
      "cluster_id": 1,
      "tier": "HIGH",
      "confidence_pct": 100.0,
      "accounts": ["steam: Ash290", "steamcommunity: ash290"],
      "reasoning": "Identical username, visually identical profile photos, same face detected in both photos."
    }
  ],
  "accounts": [
    {
      "platform": "steam",
      "account_name": "Ash290",
      "status": "Confirmed",
      "last_active_utc": null
    }
  ],
  "forensics": {
    "tone_label": "Positive",
    "tone_score": 0.802,
    "sample_size": 9,
    "top_keywords": ["ash", "images", "followers", "discover", "docker"],
    "hashtags": ["#x2022", "#x25e5"],
    "most_active_hours_utc": null,
    "engagement_note": "No public engagement metrics available"
  },
  "search_manifest": [
    {"step": 1, "action": "investigation_started", "search_id": "53791230b4...", "input_hash": "64e65b0d...", "output_hash": "12ae32cb...", "timestamp_utc": "2026-07-04T05:23:42Z"}
  ],
  "artifacts": [
    {"type": "json_dump", "filename": "f55fab5e....json", "sha256": "4a328a8c...", "captured_utc": "2026-07-04T05:29:05Z"}
  ],
  "chain_of_custody": [
    {"step": 1, "action": "investigation_started", "actor": "system", "timestamp_utc": "2026-07-04T05:23:42Z", "prev_hash": "GENESIS"}
  ],
  "certificate_a": {
    "electronic_record_desc": "VERTEX evidence package for case ...",
    "manner_of_production": "Automated collection ...",
    "device_system": "VERTEX SOCMINT/OSINT pipeline",
    "period_of_operation": null,
    "person_in_charge": "admin",
    "designation": null
  },
  "certificate_b": {
    "records": [{"filename": "f55fab5e....json", "sha256": "4a328a8c..."}],
    "hashing_algorithm": "SHA-256",
    "expert_name": null,
    "expert_credentials": null
  }
}
```

Field notes:
- `tier` is always one of `HIGH`, `MEDIUM`, `LOW`, `REJECT`.
- Any field that is `null` in the source data must render as a blank
  underscore line (`____________________`) in the PDF, exactly like the
  original report does for fields awaiting manual completion. Never print
  the word "None" or "null".
- Ship a small sample JSON file (`sample_case.json`) built from these values
  so the script can be run standalone for testing.

## 3. Confidence tiers — what gets shown where

| Tier | Shown in Executive Briefing? | Color |
|---|---|---|
| HIGH | Yes | Green |
| MEDIUM | Yes | Amber/Orange |
| LOW | No — appendix only | Grey |
| REJECT | No — appendix only | Grey, muted |

The Executive Briefing (Part 1) must **only** show HIGH and MEDIUM clusters.
Everything else — every LOW "possible lead" and every REJECT — still belongs
in the report for completeness and legal defensibility, but it goes in the
Legal Appendix (Part 2), not the front matter. Never delete data, only move
and re-prioritize it.

## 4. Document structure

The final PDF has two parts, in this order. Insert a plain divider page
between them that says "LEGAL APPENDIX — SUPPORTING RECORDS" so a reader
can visually tell where the briefing ends and the proof material begins.

```
PART 1 — EXECUTIVE BRIEFING
  Page 1: Case header + Target Profile block + Confirmed Digital Footprint
  Page 2: Why These Accounts Are Linked + Behavioural Forensics

--- divider page ---

PART 2 — LEGAL APPENDIX
  A1. Search Manifest        (from search_manifest[])
  A2. Captured Artifacts     (from artifacts[])
  A3. Certificate — Part A   (System Operations, from certificate_a)
  A3. Certificate — Part B   (Cryptographic Verification, from certificate_b)
  A4. Chain of Custody       (from chain_of_custody[])
  A5. Full Findings Ledger   (every cluster, all tiers, including LOW/REJECT)
```

Every page, in both parts, keeps the same footer used in the original
report: `CONFIDENTIAL` banner, case reference, generation timestamp, and
page number. Consistency here matters for admissibility — a judge should be
able to tell at a glance this is one continuous document.

### Page 1 — The Who and What

- Header block: case title, case reference, seed identifier(s), investigating
  officer, jurisdiction, generation date. Plain labels, no internal field
  names.
- **Target Profile** box: a bordered box, border and background tinted by the
  *highest* confidence tier present (green if any HIGH cluster exists,
  otherwise amber if any MEDIUM exists). Inside it: the seed identifier, the
  number of confirmed linked accounts, and one sentence summarizing the
  strongest finding in plain English, e.g. "High-confidence match: the same
  person operates the Steam and Steam Community accounts under the username
  Ash290."
- **Confirmed Digital Footprint** table: one row per HIGH/MEDIUM account.
  Each row shows the platform logo (see Section 6), platform name, account
  name/handle, and a small colored tier badge (HIGH/MEDIUM). No SHA-256, no
  search IDs, no timestamps on this page.

### Page 2 — The Why and the Forensics

- **Why these accounts are linked**: for each HIGH/MEDIUM cluster, one bullet
  written in plain English. Do not print raw reasoning strings verbatim if
  they contain system terms — run them through the rewrite step in Section 7.
- **Behavioural Forensics**: this is not a data table. Render it as
  scannable visual blocks:
  - A tone pill (colored by sentiment: green = positive, grey = neutral,
    red = negative) with the label and sample size, e.g. "Positive (9 samples)".
  - Keywords as small rounded chips/tags, wrapped across the page — not a
    bulleted list.
  - "Most active hours" as a single badge; if the data says there isn't
    enough information, show "Not enough data to determine a pattern" rather
    than a blank or an error.
  - Engagement note as a single plain sentence.

### Legal Appendix pages

These can reuse the original report's table layouts almost as-is — that
part already works for its purpose. The only two changes:
1. Add the section labels A1–A5 exactly as listed above so anyone can find
   the underlying evidence for anything claimed in Part 1.
2. Add one sentence at the top of A5 (Full Findings Ledger) explaining that
   LOW and REJECT entries are included here for completeness but were not
   treated as confirmed links, e.g. "The entries below did not meet the
   corroboration threshold used in the Executive Briefing and are listed
   here for completeness."

## 5. Visual style

- Palette: dark navy/charcoal for headers and body text, a single accent
  green for HIGH/positive, amber for MEDIUM, grey for LOW/REJECT/neutral,
  soft red only for negative sentiment — never for tier badges (REJECT is
  grey, not red; it isn't a negative finding, just an unconfirmed one).
- Use whitespace generously on Pages 1–2. These two pages are the ones a
  judge actually reads; they should never feel crowded.
- Consistent margins, a running header/footer, and rounded-corner boxes for
  the Target Profile block and the forensics chips are enough to make this
  feel designed rather than dumped. Don't over-engineer beyond that.

## 6. SVG logo integration (do this exactly as written)

Logos live locally at `frontend/public/logos/` (1080 files, offline only —
**never fetch anything from the network at runtime**).

```python
LOGO_DIR = "frontend/public/logos"

ALIASES = {
    "twitter": "x",
    "x": "x",
    "hibp": "breach",
    "have i been pwned": "breach",
    "docker hub": "docker",
    "docker hub (user)": "docker",
    "docker hub (organization)": "docker",
    "steam (group)": "steam",
    "steamcommunity": "steam",
    "youtube user": "youtube",
    "youtube user2": "youtube",
    "youtube channel": "youtube",
    "arch linux gitlab": "gitlab",
    "githubgist": "github",
}

def normalize(platform_name: str) -> str:
    key = platform_name.strip().lower()
    key = ALIASES.get(key, key)
    return key.replace(" ", "-")

def resolve_logo_path(platform_name: str) -> str:
    """
    Returns an absolute, existing file path to an SVG, or the generic
    fallback if nothing matches. Never raises for a missing logo.
    """
    base = normalize(platform_name)
    candidates = [f"{base}.svg", f"{base}-icon.svg", f"{base}-logo.svg"]
    for candidate in candidates:
        full_path = os.path.join(LOGO_DIR, candidate)
        if os.path.isfile(full_path):
            return full_path
    return os.path.join(LOGO_DIR, "generic.svg")
```

Rendering: use `svglib.svglib.svg2rlg()` to load the file, then
`reportlab.graphics import renderPDF` (`renderPDF.draw(drawing, canvas, x, y)`)
to place it directly on the canvas. Scale the drawing to a fixed logo size
(e.g. 18×18pt) so every row lines up regardless of the source SVG's native
size.

**Defensive requirement:** if `svglib` is not installed, or the resolved
file (including `generic.svg`) doesn't exist or fails to parse, do not crash
the report. Fall back to drawing a small filled circle with the platform's
first letter in it. A report with a placeholder icon is fine; a report that
fails to generate is not.

## 7. Plain-English rewrite step

Some reasoning strings in the source data still contain system vocabulary
(`mock_scrape`, `input_hash`, `false_positive_filter`, etc.). Before printing
any reasoning text in Part 1, pass it through a small rewrite function that
replaces known jargon terms with a plain-language equivalent (a dictionary
lookup is enough — no need for anything clever):

```python
JARGON_REPLACEMENTS = {
    "mock_scrape": "automated collection",
    "input_hash": "the recorded input",
    "output_hash": "the recorded result",
    "false_positive_filter": "an accuracy check",
    "scrape:username": "a username search",
}
```

This only applies to Part 1 (the Executive Briefing). Part 2 (the Legal
Appendix) keeps the original technical language exactly as-is — that
precision is the point of an appendix meant for cross-examination.

## 8. What "done" looks like (acceptance checklist)

- [ ] New file `bsa63_executive_generator.py` exists; `bsa63_generator.py` is
      untouched.
- [ ] Script runs standalone against a sample JSON file and produces a PDF
      with no errors, even with `svglib` uninstalled or logos missing.
- [ ] Page 1 shows only HIGH/MEDIUM accounts with logos and tier badges.
- [ ] Page 1 Target Profile box color matches the highest tier present.
- [ ] Page 2 has plain-English bullets (no raw jargon) and a non-tabular,
      visual forensics section.
- [ ] A divider page clearly separates Part 1 from Part 2.
- [ ] Every SHA-256 hash, search-manifest row, and certificate lives only in
      Part 2, under labels A1–A5.
- [ ] No LOW or REJECT cluster appears anywhere in Part 1.
- [ ] Every LOW and REJECT cluster still appears in A5, with the explanatory
      sentence at the top of that section.
- [ ] Footer (CONFIDENTIAL banner, case reference, timestamp, page number)
      is present and consistent on every page in both parts.
- [ ] No network calls anywhere in the script.
