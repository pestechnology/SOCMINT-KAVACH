# Context: Enrichment work done on VERTEX

This documents every enrichment-related change made in this working session — what was
broken, how it was diagnosed, what changed, the actual code, and the measured before/
after effect on a real live case. "Enrichment" here means: turning "an account exists at
this handle" into "here's this account's real name, bio, photo, and other identifiers,"
and feeding newly-discovered identifiers back into the search loop.

---

## 0. Why this mattered — the starting symptom

The reported symptom was: *"the enrichment is not that good."* Concretely, on a live
case (seed: `instagram.com/vismay_hs`, 87 entities discovered), only **12 of 79 social
accounts (15%)** had any name/bio/photo at all. The other 85% were bare handles.

This isn't a cosmetic problem. VERTEX's correlation engine (`backend/correlation/
correlation_engine.py`) links two accounts as "the same person" using signals like:

- `profile_photo_phash` — same image file reused across two accounts
- `face_match` — same face, different photo (SFace embedding)
- `exact_name_match` — same real name on two profiles

**Every one of these signals requires a fetched field.** An account with no photo, no
name, and no bio contributes zero evidence — it can never link into a cluster no matter
who it actually belongs to. So the enrichment gap wasn't just "missing nice-to-have
data," it was silently disabling the strongest half of the scoring engine for 85% of
discovered accounts.

---

## 1. Root cause: `MAX_FETCH` was capped at 20

### Diagnosis

`backend/ingestion/profile_page_fetcher.py` is what actually fetches an account's page
and pulls `og:image`/`og:description` (Open Graph tags) into `metadata["photo_url"]` and
`metadata["bio"]`. It's called once per case, over every discovered profile URL still
missing both fields — but capped:

```python
MAX_FETCH = 20
_TIMEOUT = 5.0
_CONCURRENCY = 8
```

On the live case, 86 accounts had a fetchable URL. Only the first 20 (in whatever order
the list happened to be in) ever got a request. The other 66 were silently skipped —
not because they failed, but because the function returned before reaching them.

### Verifying the fetch was actually fast enough to raise the cap

Before touching the number, I timed it for real rather than guessing:

```python
t0 = time.time()
n = asyncio.run(enrich_profiles_from_page(profs))     # 2 real Instagram profiles
print(f"enriched={n}  elapsed={time.time()-t0:.1f}s")
# -> enriched=2  elapsed=1.1s  (timeout is 5.0s/request)
```

1.1s for 2 profiles at concurrency 8 meant ~90 URLs would take roughly 12 batches,
~15–25 extra seconds on a case that already runs ~2 minutes. Cheap enough to raise.

### The fix

```python
# MAX_FETCH was 20, which silently starved enrichment: on a real 87-entity case only 16
# of 86 fetchable URLs were ever fetched, so 85% of discovered accounts carried no name,
# bio or photo at all. That matters beyond display — profile_photo_phash, face_match and
# exact_name_match are among the strongest correlation signals and ALL of them require a
# fetched field, so an unfetched account is structurally incapable of linking.
# Measured cost: 2 profiles took 1.1s against a 5s timeout at concurrency 8, so ~90 URLs
# is ~12 rounds ≈ 15-25s on a run that already takes ~2 minutes. Still bounded and still
# fail-safe (any individual fetch that errors is skipped silently).
MAX_FETCH = 100
```

### Measured effect (same seed, before → after)

Re-ran the *identical* case (`instagram.com/vismay_hs/`) end-to-end, live, twice:

| Metric | Before (cap=20) | After (cap=100) |
|---|---|---|
| Enriched social accounts | 12/79 (15%) | **34/78 (44%)** |
| `bio` populated | 12 | **37** |
| `photo_url` populated | 15 | **35** |
| `photo_phash` computed | 10 | **24** |
| `name` recovered | 7 | **11** |
| Runtime | ~2m00s | ~2m25s |
| **HIGH-confidence clusters** | 3 | **5** |

Three times more enriched accounts → almost double the photo hashes computed → two
extra HIGH-confidence clusters, from a one-line change plus verifying it was safe.

---

## 2. Profile-URL extraction feeding the name back into search

This was internship task 1: *"extract details from a submitted profile URL and feed
them back into the search to reiterate and enrich results."*

### What was there before

`backend/ingestion/url_scraper.py` only pulled the raw handle out of a URL via a loose
regex, with no idea whether the URL was even a real profile. Concretely it was broken:

```
facebook.com/profile.php?id=100012345678901  →  handle = "profile.php"   (junk)
facebook.com/people/John-Doe/100087654321098 →  handle = "people"        (junk)
facebook.com/groups/somegroup                →  handle = "groups"        (junk)
```

This wasn't just useless — it was actively dangerous. `bio_url_match` (a bio linking to
someone's own account) is a **hard anchor** signal in `scoring_engine.py`, meaning it's
standalone-sufficient to link two accounts at HIGH confidence. Two *unrelated* Facebook
accounts both reducing to the handle `"profile.php"` could satisfy that signal and merge
on a single false signal.

### The fix — structured extraction with a profile/non-profile distinction

Rewrote `extract_profile_url()` to return platform, handle, a platform-native id
(Facebook numeric / YouTube channel / X numeric), a name recovered from a vanity slug,
and — critically — whether the URL is even a `"profile"` at all vs. a `"non_profile"`
(a post, a group, a search page):

```python
def extract_profile_url(url: str) -> dict | None:
    """Structured parse of a social profile URL.
    Returns None for a non-social/unrecognised host. Otherwise a dict with:
        platform    — instagram | facebook | twitter | youtube | github | linkedin | reddit
        kind        — "profile" (a person's account) or "non_profile" (post/video/group/…)
        handle      — the username, if the URL carries one (None otherwise)
        platform_id — the platform's own stable id, if the URL carries one
        id_kind     — facebook_numeric_id | twitter_numeric_id | youtube_channel_id
        name_hint   — display name recovered from a vanity slug (e.g. /people/John-Doe/)
        note        — which rule matched, for the evidence trail
    """
```

A `profile.php?id=...` URL now correctly extracts the **numeric id** (a stronger,
immutable identifier than a handle) and yields `handle: None` — so it can never
masquerade as a username in the hard-anchor signal.

### Feeding it back into the search (`derive.py`)

```python
elif seed_type == "url":
    info = extract_profile_url(value)
    if info and info.get("kind") == "profile":
        handle = info.get("handle")
        name_hint = info.get("name_hint")

        if handle and _valid_handle(handle):
            emit("username", handle, "url_handle", 0.9)
            for email in emails_from_handle(handle):
                emit("email", email, "url_handle_to_email_guess", 0.3)
            for name in names_from_handle(handle):
                emit("name", name, "url_handle_to_name_guess", 0.5)
                for variant in handles_from_name(name):
                    if _valid_handle(variant):
                        emit("username", variant, "url_handle_variant", 0.6)

        if name_hint:
            # Observed in the URL slug, so more trustworthy than a name GUESSED
            # from an opaque handle (0.5 above).
            emit("name", name_hint, "url_slug_name", 0.8)
            for variant in handles_from_name(name_hint):
                if _valid_handle(variant):
                    emit("username", variant, "url_name_to_handle_variant", 0.6)
```

A non-profile URL (a post/group/video) now derives **zero** seeds — it used to derive
junk before this rewrite.

### Verified live, end to end

Fed in `https://www.instagram.com/vismay_hs/` as the *only* seed for a fresh case:

```
1 URL seed
  → extracted handle "vismay_hs"
  → derived 11 candidate seeds (username variants, email guesses, a recovered name)
  → the recovered name "Vismay Hs" triggered a NAME PIVOT — a fresh search on the name
  → that pivot alone surfaced 66 additional entities
= 87 total entities, 12 clusters (3 HIGH / 2 MEDIUM / 3 LOW / 4 REJECT)
```

That `found_via_name_pivot: 66` field on the resulting entities is the literal proof
that "feed them back into the search to reiterate" is working — the name recovered
from the URL, not typed by a human, drove a second wave of discovery.

---

## 3. New enrichment source: Hudson Rock (free, no API key)

### Why

Existing breach sources (HIBP, XposedOrNot) answer "was this email in an old data
dump." None of them answer a more current, higher-signal question: *was this person's
own computer compromised by info-stealer malware*, which typically exfiltrates
everything saved in the browser (passwords, autofill, session cookies) — a live, recent
compromise rather than an old leak.

### What it does

`backend/ingestion/hudsonrock_scraper.py` queries Hudson Rock's free, key-less public
API for both email and username identifiers, and pulls:

```
stealer_family, computer_name, operating_system, date_compromised, masked logins
```

`computer_name` is a genuinely useful field — machine names very often embed a real
name (e.g. `"DESKTOP-5U6IRUV (HP)"`, `"PC (TemitopeGX)"`).

### A real over-claiming bug caught during testing

Live-probing the username `"admin"` returned FIVE unrelated infected machines:

```
DESKTOP-NBI3PVA (ShahJalal), ROHAN (rohan), DESKTOP-M0IPOMI (DELL),
SAITHEONE (SaiTheONE), LAPTOP-PG...
```

Obviously different people sharing a common username. Left unguarded, this would have
been exactly the kind of over-claiming the correlation engine is designed to refuse.
Fixed by making an email match identity-bearing, and a username match an explicit
**lead only**:

```python
is_email = "@" in ident
meta = {"infostealer_infection": True, "identifier_kind": "email" if is_email else "username", ...}
if not is_email:
    # A username is NOT a unique identity. Hudson Rock returns every infected
    # machine whose stolen credentials contained this handle, so a common
    # handle conflates unrelated people — a live probe for "admin" came back
    # with machines named ShahJalal, rohan and SaiTheONE in one response.
    # An email match is identity-bearing; a username match is a LEAD ONLY.
    meta["identity_confirmed"] = False
    meta["note"] = ("Handle-scoped match: these infections belong to accounts using "
                    "this username, which may be different people. Lead only — "
                    "not evidence that the subject's own machine was infected.")
else:
    meta["identity_confirmed"] = True
```

Also deliberately **never** stores `top_passwords` (returned masked by the free tier —
liability with no investigative value) and never writes into `metadata["breaches"]`
(that field drives a correlation signal that already excludes mega-breaches for being
non-discriminating; "was infected by a stealer" is the same kind of property).

Verified live: a real email returned `stealer_count=5`, a real compromise date, and
`total_user_services=32`; your own test email/username came back clean (`stealers: []`,
HTTP 200 — a genuine negative, not a silent failure).

---

## 4. New enrichment sources: account-existence oracles that also enrich

### Why not just use more of holehe

`holehe` (already wired) is a fixed ~120-site CLI we can't extend. `backend/ingestion/
account_oracle_scraper.py` is an **in-repo, extensible registry** for exactly the
mechanism fingerprint.to uses (a per-service public API check) — for services holehe
doesn't cover.

Shipped four, each individually verified live before being added: **chess.com,
lichess, gitlab, duolingo**. Unlike holehe's plain yes/no, these return real fields —
GitLab's response for a real handle included `name: "Vismay H S"` and an avatar URL.

### The safety rule that mattered most here

Some existence checks (any "forgot password" flow) silently email or OTP the account
owner — which would tip off an investigation subject. Every oracle in the registry
declares this explicitly, and the scraper refuses to run anything else:

```python
@dataclass
class Oracle:
    name: str
    notifies_target: bool     # True => sends the subject a mail/OTP => NEVER auto-run
    ...

oracles = [o for o in _ORACLES
           if o.id_type == id_type and not o.notifies_target]
```

This is also *why* the flashy Jio/Snapdeal/AJIO-style results from a competitor demo
weren't replicated here: probed live, they all authenticate by phone+OTP, so an
existence check would notify the subject. Documented as a deliberate exclusion, not an
oversight — a test asserts a notifying oracle is never called.

---

## 5. The other half of "good enrichment": stop claiming what wasn't earned

While measuring the `MAX_FETCH` fix, I found the UI was overstating confidence. On the
same live case, **14 of 25 accounts marked "Strong match" had zero enrichment** —
no name, no bio, no photo. They existed under a matching handle, discovered by a
username enumerator, but nothing on the actual page had ever been checked.

A username enumerator only proves *"a page exists at this handle"* — it does not prove
*whose* page it is. Presenting that as a 100-confidence "Strong match" is the same class
of over-claiming problem as the Hudson Rock username issue above.

```jsx
// frontend/components/ui/AccountCard.jsx
const hasProfileData = !!(
  meta.fullname || meta.name || meta.bio || meta.photo_url || meta.title || meta.email
);
const tier = hasProfileData ? rawTier : "UNVERIFIED";
```

```jsx
{!hasProfileData && (
  <span title="A page exists at this handle, but no profile data (name, bio or photo)
               was retrieved from it, so nothing corroborates that it belongs to
               the subject.">
    handle only — no profile data retrieved
  </span>
)}
```

Effect on the same case: **67 of 79 accounts (85%) were re-labelled "Unverified"**
instead of a false "Strong"/"Possible match" — because that's what was actually true.
This isn't cosmetic: it makes the *size of the enrichment gap itself visible* on every
card, which is exactly what motivated raising `MAX_FETCH` in the first place. The two
fixes are a pair — one stops lying about what wasn't enriched, the other actually goes
and enriches more of it.

---

## 6. What was investigated and deliberately NOT added

Being enriched isn't the same as being *more* — a few candidates were tested and
rejected on evidence, not skipped out of laziness:

- **qeeqbox/social-analyzer** — installed and control-tested. A random 20-character
  string scored **100% confidence on facebook.com**. Its rating engine isn't calibrated
  against non-existence; it would have added noise, not signal.
- **Maigret** — diagnosed, not fixed, because it wasn't broken in *our* code. A control
  probe (random username) came back "Claimed" on 57 of the same sites a real username
  hit 59 — Maigret's own site detection has rotted, and the existing `fp_filter`
  correctly strips ~97% of its output already.
- **holehe returning 0** — correct behaviour, not a bug: the test case had no email
  seed. Verified holehe works by running it against a real email directly (3 real hits).

---

## Summary — files touched, tests added

| File | Change |
|---|---|
| `backend/ingestion/profile_page_fetcher.py` | `MAX_FETCH` 20 → 100 |
| `backend/ingestion/url_scraper.py` | rewritten: structured extraction, profile/non-profile distinction, platform ids, name-slug recovery |
| `backend/ingestion/derive.py` | new `url` seed-type branch, feeds handle/name back into search |
| `backend/ingestion/hudsonrock_scraper.py` | new — free infostealer-exposure source |
| `backend/ingestion/account_oracle_scraper.py` | new — extensible existence-oracle registry (chess.com/lichess/gitlab/duolingo) |
| `frontend/components/ui/AccountCard.jsx` | "Unverified" badge when nothing was actually fetched |
| `tests/test_url_profile_extract.py` | 45 tests, incl. the hard-anchor false-positive regression guard |
| `tests/test_hudsonrock_scraper.py` | 13 tests, incl. the username lead-only guard |
| `tests/test_account_oracle.py` | 8 tests, incl. the notifying-oracle safety guard |

All changes were verified against a real live case end-to-end (not just unit tests) —
the before/after numbers in section 1 and the 87-entity/12-cluster result in section 2
came from actually running the pipeline, not from reading the code and assuming.
