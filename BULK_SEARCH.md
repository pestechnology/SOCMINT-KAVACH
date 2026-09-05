# Bulk search + completion notifications

Two features for running many subjects at once:

1. **Bulk intake** — upload one `.docx` listing several subjects; VERTEX opens one
   investigation per subject and runs them all.
2. **Completion notification** — the browser tells you when each run finishes, so you
   can close the tab and come back.

---

## 1. Preparing the subject sheet

**One subject = one case.** Identifiers from different people are never merged into a
single investigation — the correlation engine links accounts that share signals, so
mixing subjects would manufacture cross-subject clusters out of nothing.

**Start from [`bulk_template.xlsx`](frontend/public/bulk_template.xlsx)** (or
[`bulk_template.csv`](frontend/public/bulk_template.csv)) — downloadable straight from the bulk-upload
screen, and already carrying the right header row and two worked examples. Regenerate either with `python -m scripts.make_bulk_template`.

Three formats are read: **`.xlsx`**, **`.csv`** and **`.docx`**. A spreadsheet is the
normal case; the Word reader exists because a subject sheet often starts life as a Word
report.

**No field is required.** Any one identifier is enough to run a subject — a phone with
no name, an email with no phone, a UPI ID on its own. Fill in whatever you have and
leave the rest blank; there is no placeholder to supply and no field that blocks the
run. When there is no `Name`, the case is titled after the identifier itself. The only
thing a subject cannot be is *empty*: a row with nothing but a note has nothing to
search, so it is skipped rather than opened as a blank case.

### Spreadsheet (.xlsx / .csv) — one row per subject

First row names the columns; every row after it is one subject.

| Name | Phone | Email | Username | UPI | Profile URLs | Photo URL |
| --- | --- | --- | --- | --- | --- | --- |
| Jayadeep Prasad Walthati | 8121569830 | jayadeep92@gmail.com | JAYADEEPPRASAD | 8121569830@ybl | `https://facebook.com/1000017…` `https://instagram.com/jaydip` | |
| | 9800011122 | | | | | |
| Asha Rao | | asha@example.com | asha_r | | `https://x.com/asha_r` | |

Columns may appear in any order, and any column you don't need can be deleted outright.
Empty cells and placeholders (`-`, `--`, `N/A`, `NA`, `nil`, `none`, `unknown`) are
dropped, not searched. A row filling only one column is still its own subject; a row
with no identifier at all is skipped.

**Several profile URLs go in the one `Profile URLs` cell** — Facebook, Instagram,
YouTube, X, LinkedIn, Telegram, anything. Separate them with a space, a comma, a
semicolon or a line break; each becomes its own searchable `url` seed:

```
https://facebook.com/100001700990021 https://instagram.com/jaydip https://x.com/jaydip
```

If you prefer one link per column, per-platform headers work too — `Facebook`,
`Instagram`, `YouTube`, `X`, `Twitter`, `LinkedIn`, `Telegram`, `TikTok`, `Reddit`,
`GitHub` (with or without a trailing `URL`). They are searched identically.

CSV specifics: semicolon- and tab-delimited exports are detected automatically, and the
UTF-8 BOM Excel writes is handled — just Save As "CSV UTF-8" and upload.

### Word document (.docx)

Either a table shaped exactly like the spreadsheet above, or labelled field lines — the
shape a Khoj/TrueCaller-style report already has:

```
Name: Jayadeep Prasad Walthati
Phone: 8121569830
Email Address: jayadeep92@gmail.com
UPI/VPA Accounts: 8121569830@ybl, 8121569830@axl
Alias: JAYADEEPPRASAD; jaydip cse; J10 Jayadeep
Profile URL: https://www.facebook.com/100001700990021
Notes: financial fraud via UPI

Name: Asha Rao
Mobile Number: 9800011122
```

A **new subject starts** at a blank line, a separator line (`---`, `===`, `***`), a
`Subject:` marker, or a repeated `Name:` field.

A repeated *other* field is a **second value for the same person**, not a new subject —
the Khoj report lists nine aliases and two UPI IDs for one man, and that has to stay one
man. Several values may also share one line, separated by `,` `;` or `|`.

Lines without a `Label: value` shape are ignored, so headings and prose in an existing
report cause no harm.

> **One thing to watch.** Subjects with **no `Name` field** must be separated by a blank
> line (or `---`). Without one, consecutive `Phone:` lines read as two phone numbers for
> the *same* person — which is exactly right for one subject with two SIMs, and wrong for
> two subjects. Either keep a blank line between people, or use a spreadsheet, where
> every row is unambiguously its own subject.

A worked example is at [`sample_subjects.docx`](sample_subjects.docx) — three subjects,
one with no name and one with a single username.

### Field names

Labels are matched case-insensitively and ignore spaces, underscores and punctuation, so
`Phone Number`, `phone_number` and `PHONE NUMBER` are the same field.

Every one of these is optional; include only the fields you actually have.

| Becomes a seed of type | Accepted labels |
| --- | --- |
| `name` | Name, Full Name, Subject Name, Suspect, Suspect Name, Person, Account Holder |
| `username` | Username, Alias(es), Handle(s), Nickname, Nick, Screen Name, Profile Name, User |
| `email` | Email, Emails, Email Address(es), Email ID, Mail |
| `phone` | Phone, Phones, Phone Number, Mobile, Mobile Number, Contact, Contact Number, Number, MSISDN, Cellphone |
| `upi` | UPI, VPA, UPI ID, UPI/VPA, UPI/VPA Accounts, UPI Accounts |
| `url` | **Profile URLs** (several links in one cell), URL, Link, Profile, Profile Link, Social Profile(s), Website — or per-platform: Facebook, Instagram, YouTube, X, Twitter, LinkedIn, Telegram, TikTok, Reddit, GitHub (with or without a trailing `URL`) |
| `face` | Face, Face URL, Photo, Photo URL, Image, Image URL, Picture, Avatar |

These configure the case instead of becoming a search seed:

| Case attribute | Accepted labels | Values |
| --- | --- | --- |
| Case title | Case, Case Title, Title, Case Name, Reference, Ref No | free text (else the subject's name is used) |
| Case context | Context, Case Context, Case Type, Notes, Remarks, Description, Details, Offence | free text — sharpens the AI guidance layers only, never the search |
| Region | Region, Country, Jurisdiction | `India` (noise-reduced) or anything else → `ALL` |

Anything unrecognized is ignored — an unknown column will not silently become a search.

### Limits

An uploaded file is untrusted input, so the parse is bounded:

| Limit | Value | On exceeding |
| --- | --- | --- |
| File size | 5 MB | rejected (`400`) |
| Formats | `.xlsx`, `.csv`, `.docx` | anything else rejected (`400`) — re-save `.xls`/`.doc` |
| Subjects per file | no limit — bounded by the 5 MB file size | the exact count is reported by the preview for confirmation before anything runs |
| Identifiers per subject | 25 | extra identifiers dropped, count reported per subject |

---

## 2. Using it

**Investigations → New investigation → Bulk upload.**

0. Fill in [`bulk_template.xlsx`](frontend/public/bulk_template.xlsx) (one row per subject).
1. Choose the file. It is parsed and **previewed** — every subject, every identifier
   VERTEX read out of it — before anything runs. Nothing is created and no query is
   spent at this step, so a mis-labelled column costs nothing.
2. Confirm. One case per subject is created and queued.
3. The Investigations list then refreshes on its own while any case is running.

Runs are queued **one at a time**. A single live investigation fans out dozens of
scrapers, so starting them all at once would exhaust the Serper/LLM per-minute budget and
degrade every result; each case finishes in turn and notifies as it does.

There is no cap on how many subjects a file may hold — the 5 MB file size is the limit.
Because each case takes roughly **7 minutes** (measured median of live runs), a large
sheet is a long job: the preview reports the exact subject count and estimated total time
before anything starts, so committing to it is a deliberate choice.

### API

| Method | Path | Body | Purpose |
| --- | --- | --- | --- |
| POST | `/cases/bulk/preview` | `multipart/form-data`, `file=<sheet>` | parse only — returns the subjects, creates nothing |
| POST | `/cases/bulk` | `multipart/form-data`, `file=<sheet>` | create one case per subject and start each run |

Both require the usual `Authorization: Bearer <token>`. `/cases/bulk` returns:

```json
{
  "created": 2,
  "cases": [{"case_id": "…", "title": "Jayadeep Prasad Walthati", "seeds": [...]}],
  "skipped_subjects": 0,
  "warnings": ["Subject 3: 4 identifiers dropped (25 per subject max)."]
}
```

Each case runs exactly the same pipeline as a hand-entered one, is written to the same
tamper-evident ledger, and produces the same BSA-63 report. Bulk intake is a front door,
not a second pipeline.

---

## 3. Completion notifications

Once anything is running, the Investigations page polls `/cases` every 5 seconds and
fires a desktop notification the moment a case flips to **complete**:

> **Investigation complete** — Jayadeep Prasad Walthati · 43 accounts

Clicking it opens that case. Polling stops on its own when nothing is running.

This uses the browser's own Notification API — no email server, no webhook, no push
service, and nothing about the subject leaves the machine. The first time you start a
run the browser asks for permission; if you decline, the page still refreshes live and
shows an in-page banner instead, so nothing is lost but the desktop toast.

Notifications only fire while a VERTEX tab is open. Closing the browser does not stop an
investigation — the run continues server-side and the result is waiting in the list.
