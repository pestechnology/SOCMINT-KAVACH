# VERTEX — Master Architecture & Build Guide

**SOCMINT & OSINT Suspect Profiling System**
**Hackathon:** CIDECODE 2026 · CCITR + CID Karnataka · PES University · July 4–5, 2026
**Team:** Pog, Ashwin, +1
**Document version:** 1.0 · Built for live data, agent-based construction

---

## HOW TO READ THIS DOCUMENT

This is the single source of truth for building VERTEX. It is organised so you can build it agent-by-agent in Antigravity without holding the whole thing in your head.

- **Section 1** — what VERTEX is, in plain words
- **Section 2** — the three decisions that shape everything (read before building)
- **Section 3** — what YOU (human) must do manually: API keys, accounts, installs
- **Section 4** — the full system architecture (the pipeline, every layer)
- **Section 5** — every tool, what it does, how it connects
- **Section 6** — the data model (how everything is stored and linked)
- **Section 7** — the scoring engine (how accounts get linked)
- **Section 8** — the UI, screen by screen, designed for non-technical investigators
- **Section 9** — the expected output (what the investigator actually sees)
- **Section 10** — the BSA-63 evidence package (the moat — handle with care)
- **Section 11** — how all the tools connect and run seamlessly
- **Section 12** — the agent build plan (the order you build in)
- **Section 13** — demo day runbook
- **Section 14** — open risks and honest limitations

---

## SECTION 1 — WHAT VERTEX IS, IN PLAIN WORDS

An investigator types in one thing they know about a suspect — a name, an email, a phone number, a username, a UPI ID, or a face photo. VERTEX goes out to the public internet, finds every account and trace connected to that one piece of information, works out which of them belong to the same person, and draws it all as a connected map. It then produces a court-ready evidence file.

The investigator does not need to know what "OSINT", "scraping", or "correlation" means. They type one thing, press one button, and get a clear picture: *here are the accounts, here's how confident we are that they're the same person, and here's why.*

**The one-line pitch:** "One identifier in. A complete, court-admissible digital profile out."

---

## SECTION 2 — THE TWO DECISIONS THAT SHAPE EVERYTHING

Read these before building anything. They are baked into the rest of this document.

### Decision 1 — Deployment: laptop, full live, 2–5 minute budget

The demo runs live on a laptop on college wifi. There is NO cache layer and NO mock-data fallback on stage — judges hand over a random name or number and the system scrapes it live in front of them. This is the whole point of the product, so the architecture commits to it.

This is feasible because the time budget is 2–5 minutes, not 60 seconds. With that long, every scraper can run, retry once on failure, and still finish. Removing the cache layer simplifies the build — one data mode (`live`), no `DATA_MODE` switching on stage. (`mock` mode still exists, but only for development, never for the demo.)

Two things still matter even with a generous time budget:

- **Stream results as they arrive.** A screen that shows nothing for 4 minutes then dumps everything feels broken, even if it's fast. Results must populate the screen one source at a time so the judge watching *sees the system working*. This is a UX requirement, not a performance one.
- **Seed type changes difficulty.** A phone or email returns clean results fast. A name alone is ambiguous and low-signal. If judges let you choose, steer toward phone/email. If forced onto a name, set expectations out loud: "names are the weakest OSINT seed — watch how the system surfaces candidates but refuses to link unconfirmed ones."

Server deployment is possible if ever needed, but laptop + live is the assumed model throughout.

### Decision 2 — Legal claims: flagged, not asserted

The BSA Section 63 evidence package is the moat — but the brief already caught two wrong legal citations (PMLA §12, CPCR §12). The legal layer needs a lawyer's eye before demo. In this document, every legal assertion is marked **[VERIFY-LEGAL]**. Before July 4, get one person to confirm each marked claim against a primary source or a law professional. Do not present any [VERIFY-LEGAL] claim as settled until checked.

---

## SECTION 3 — WHAT YOU (HUMAN) MUST DO MANUALLY

These are the things no code can do for you. Do all of them **before July 4**. Each has an owner column — assign it now.

### 3.1 — API keys to acquire

| Service | What it's for | Cost | How to get it | Owner |
|---|---|---|---|---|
| **HIBP (Have I Been Pwned)** | Email → list of breaches | ~$3.95/mo (Core plan) | haveibeenpwned.com/API/Key — credit card required, buy Core tier, cancel after July 5 | TBD |
| **Serper.dev** | Google search/dorking backbone | Free tier: 2,500 queries | serper.dev — sign up, copy API key from dashboard | TBD |
| **GitHub Personal Access Token** | Email→username, repo/commit data | Free | github.com/settings/tokens → "Generate new token (classic)" → NO scopes needed for public data → copy token | TBD |
| **NumVerify** (optional, PhoneInfoga can use it) | Phone carrier/line-type validation | Free tier: 100/mo | numverify.com → sign up → copy API access key | TBD |
| **NVIDIA Cloud API** | LLM calls (entity extraction + explanations) | You already have it | Confirm key works against `https://integrate.api.nvidia.com/v1` (OpenAI-compatible, Bearer `nvapi-` key); models verified live: `meta/llama-3.3-70b-instruct` + `deepseek-ai/deepseek-v4-pro` | TBD |
| **Telegram API (api_id + api_hash)** | Telethon public channel scraping | Free | my.telegram.org → log in with your phone → "API development tools" → create an app → copy api_id and api_hash | TBD |

**Critical note on HIBP:** the Core plan ($3.95/mo) gives direct email search at up to 1,000 requests/minute. That is all VERTEX needs. Do NOT buy a higher tier.

**Critical note on Telegram:** you authenticate Telethon ONCE on your machine, which creates a `.session` file. Do this at home on stable wifi — never try to authenticate at the venue. Once the session file exists, no re-auth is needed.

### 3.2 — Accounts and tools to set up

| Item | Action | Owner |
|---|---|---|
| **A burner Telegram account** | Telethon needs a real Telegram account (a phone number). Use a spare SIM or a teammate's. This account does the public-channel reading. | TBD |
| **GitHub repo** | Create the VERTEX repo, set branch strategy (main + one branch per person), invite all 3. Do this Day 1 Hour 1. | TBD |
| **A test identifier set** | Pick ~10 real public figures with known cross-platform accounts (a tech YouTuber, an indie developer, etc.). Hand-verify their real accounts. Use these for development testing AND as safe demo material. | TBD |

### 3.3 — Software to install locally (all three machines)

Run these installs on every dev machine before building. Verify each works before the agent that uses it is built.

```bash
# Core Python OSINT tools
pip install maigret
pip install user-scanner          # replaces holehe (maintained)
pip install socialscan
pip install ignorant              # phone-based registration check
pip install waybackpy             # Wayback Machine CDX
pip install telethon              # Telegram public channels
pip install imagehash pillow      # profile photo pHash
pip install thefuzz python-Levenshtein   # fuzzy username matching
pip install scikit-learn          # stylometry (TF-IDF cosine)
pip install spacy && python -m spacy download en_core_web_sm   # NER pre-pass

# Backend
pip install fastapi uvicorn httpx python-jose[cryptography] bcrypt pydantic-settings
pip install reportlab             # BSA-63 PDF generation

# Blackbird (clone, not pip)
git clone https://github.com/p1ngul1n0/blackbird
cd blackbird && pip install -r requirements.txt && cd ..

# PhoneInfoga (Go binary - download release)
# Get latest from github.com/sundowndev/phoneinfoga/releases
# Or run via Docker: docker pull sundowndev/phoneinfoga:latest
```

**Verification step — run before building the agent that uses each tool:**

```bash
# Test Maigret on a known username — confirm JSON output structure
maigret octocat --json simple --no-progressbar

# Test user-scanner on a known email
user-scanner -e "test@example.com" -v

# Test socialscan
socialscan octocat

# Test waybackpy
python -c "import waybackpy; print('wayback OK')"
```

**Why this matters:** the JSON output structure of Maigret is what every downstream module normalises against. If you don't know that structure before building, the normalisation agent builds against a guess and breaks at integration. **Run Maigret on a real username TODAY and save the output.**


## SECTION 4 — FULL SYSTEM ARCHITECTURE

VERTEX is a pipeline. Data flows through five stages: `Seed input → Data source layer → Normalization + dedup → Correlation engine → Scoring engine → Outputs`. Two layers cut across all stages: the audit + hash ledger (every search gets a unique ID and SHA-256) and the data-mode switch (routes every data source to live or, in development only, mock).

### The layers explained

**Layer 0 — Auth + Case Management.** JWT login, role-based access (investigator / admin), case CRUD. Gates everything — judges test multi-user access first.

**Layer 1 — Data Source abstraction.** The single most important engineering decision. Every scraper implements one interface: `DataSource.resolve(identifier) -> list[RawProfile]`. Downstream code never knows or cares whether data came from a live scrape or (in development) a mock. This lets you swap data sources with one config flag and test correlation logic without hitting the network.

**Layer 2 — Data Source implementations (the scrapers).** 15+ tools, each wrapped to emit standard `RawProfile` objects. Run in parallel via `asyncio.gather()`. Each one fails silently to empty list — never crashes the pipeline.

**Layer 3 — Normalization + dedup.** All `RawProfile` objects from all sources get unified: same username from two tools becomes one record, identifiers get canonical form (+91 prefix on phones, lowercase emails), duplicates removed.

**Layer 4 — Correlation engine.** Compares every profile against every other. Computes signals: shared phone, shared email, username similarity, photo pHash distance, posting-time overlap, stylometry cosine, breach co-occurrence.

**Layer 5 — Scoring engine.** Turns correlation signals into a confidence score (0-100) and tier (HIGH / MEDIUM / LOW / REJECT). Contains the red-herring rejection logic.

**Layer 6 — Outputs.** Network graph (sigma.js), cross-platform timeline (vis-timeline), profile cards (plain-English per platform), and the BSA-63 PDF evidence package.

**Cross-cutting — Audit ledger.** Every search and every captured artifact gets a SHA-256 hash and timestamp, stored append-only. This is the spine of the court-admissibility story.

**Cross-cutting — Data-mode switch.** One config flag chooses LiveScraper (real, used on stage) or MockScraper (fixed test data, development only). The demo is fully live — no cache.

---

## SECTION 5 — EVERY TOOL: WHAT IT DOES, HOW IT CONNECTS

Each tool is wrapped in a class that extends `BaseDataSource` and emits `RawProfile` objects. Grouped by which seed type triggers it.

### 5.1 — EMAIL seed triggers these

| Tool | What it returns | How it connects | Manual setup |
|---|---|---|---|
| **HIBP API** | List of breaches the email appeared in, with dates | `httpx` GET to `/v3/breachedaccount/{email}` with API key header | API key (§3.1) |
| **user-scanner** | Which of 120+ sites the email is registered on | Subprocess call, parse JSON output | pip install |
| **Blackbird (email mode)** | Accounts across 600+ sites tied to email, with metadata | Subprocess call `--email`, parse JSON | git clone |
| **Epieos technique** | Google account display name + profile photo + Maps/Calendar links | `httpx` GET to Google account lookup endpoints | none (custom code) |
| **GitHub API** | GitHub username if email used in commits | `httpx` GET `/search/users?q={email}+in:email` | GitHub token (§3.1) |
| **Serper email dork** | Web mentions of the email across all indexed sites | `httpx` POST to Serper with `"{email}"` query | Serper key (§3.1) |

### 5.2 — PHONE seed triggers these

| Tool | What it returns | How it connects | Manual setup |
|---|---|---|---|
| **PhoneInfoga** | Carrier, country, line type, VoIP flag, dork URLs | Go binary via subprocess OR Docker, or its REST API | binary/Docker |
| **ignorant** | Whether phone is registered on Snapchat, Instagram, etc. | Subprocess call, parse output | pip install |
| **Epieos phone technique** | WhatsApp/Telegram registration status | `httpx` to public endpoints | none |
| **UPINameLookup** | Bank-registered name (via UPI payment-init endpoint) | Playwright, initiate-then-cancel | none (custom) |
| **Serper Truecaller dork** | Crowdsourced name from Truecaller | `httpx` POST `site:truecaller.com "{phone}"` | Serper key |
| **FacebookPhoneChecker** | Whether phone links to an FB account + masked digits | Playwright against FB password-recovery flow | none (custom) |

### 5.3 — USERNAME seed triggers these

| Tool | What it returns | How it connects | Manual setup |
|---|---|---|---|
| **Maigret** | Accounts across 3000+ sites WITH profile data (bio, photo, name, followers) | Subprocess `maigret {user} --json`, parse | pip install |
| **Blackbird (username mode)** | Accounts across 600+ sites via WhatsMyName | Subprocess call, parse JSON | git clone |
| **socialscan** | High-confidence registration check on 11 major platforms (zero false positives) | Subprocess/import, parse | pip install |
| **Reddit public JSON** | Post/comment history | `httpx` GET `/u/{user}.json` | none |
| **Telethon** | Public Telegram channels/groups the user appears in | Telethon client with session file | Telegram API + session (§3.1) |
| **Serper username dork** | Web mentions of the username | `httpx` POST Serper | Serper key |

### 5.4 — UPI seed triggers these (India-specific — the differentiator)

| Tool | What it returns | How it connects | Manual setup |
|---|---|---|---|
| **UPI parser** | Bank name from suffix (`@oksbi`→SBI), phone if embedded in ID | Pure Python, dictionary lookup + regex | none |
| **UPINameLookup** | Bank-registered account holder name | Playwright, initiate-then-cancel payment | none (custom) |
| **Serper UPI dork** | Posts/complaints mentioning this UPI ID | `httpx` POST `"{upi_id}"` | Serper key |
| **Username extraction** | The username portion → fed into Maigret as new seed | Pure Python split | none |

### 5.5 — NAME seed triggers these

| Tool | What it returns | How it connects | Manual setup |
|---|---|---|---|
| **Serper multi-dork** | Profiles across LinkedIn, Instagram, Twitter, Reddit, Facebook | 5-6 parallel `httpx` POST queries with `site:` operators | Serper key |

### 5.6 — FACE IMAGE seed triggers these

| Tool | What it returns | How it connects | Manual setup |
|---|---|---|---|
| **pHash matcher** | Perceptual hash of uploaded image, compared to all collected profile photos | imagehash library, Hamming distance | pip install |

### 5.7 — ANY seed (runs on every discovered profile URL)

| Tool | What it returns | How it connects | Manual setup |
|---|---|---|---|
| **Wayback Machine CDX** | Archived snapshots of deleted/changed profiles | `waybackpy` or `httpx` to CDX API | pip install |


## SECTION 5A — MAIGRET DEEP-DIVE (VERIFIED, THE PRIMARY USERNAME SCRAPER)

This is the workhorse. It was installed and run against a real username (`octocat`) — the structure and behaviour below are verified from actual output, not assumed. Read this before building Agent 8.

### 5A.1 — Install and run (verified working)

```bash
# inside the project venv (NOT system python / conda — see Section 3.3)
python -m venv venv
source venv/bin/activate
pip install maigret

# run — note the flags, they matter (see 5A.3)
maigret USERNAME --json simple --no-recursion --timeout 10 --no-progressbar --folderoutput reports
```

Output saves to `reports/report_USERNAME_simple.json`. The terminal output is human-formatted; your code parses the JSON file, which is shaped differently.

### 5A.2 — The JSON structure (verified)

Top-level keys are platform names. The fields you want live under `[platform]["status"]`. Everything else (the `site` block, `regexCheck`, `presenseStrs`) is Maigret's internal config — ignore it.

```json
{
  "YouTube": {
    "status": {
      "status": "Claimed",          // ONLY keep "Claimed" — ignore Available/Unknown/Illegal
      "site_name": "YouTube",
      "url": "https://www.youtube.com/@octocat/about",
      "ids": {                      // the goldmine — varies per platform, may be {}
        "fullname": "Octocat",
        "bio": "A video repository of things I made...",
        "image": "https://yt3.googleusercontent.com/...",
        "follower_count": "...",    // present on some platforms
        "created_at": "...",        // present on some platforms
        "location": "..."           // present on some platforms
      },
      "tags": ["video"]
    }
  },
  "Substack": { "status": { ... } }
}
```

The `status.ids` dict is what feeds the scoring engine: `fullname`, `image` (photo for pHash), `bio` (keyword/stylometry), `created_at`, `location`, `follower_count`. It is different per platform and is often empty — code defensively with `.get()`.

### 5A.3 — Two critical flags (learned from real output)

- `--no-recursion` — **essential.** Without it, Maigret takes IDs it extracts from one profile (e.g. a linked username in a bio) and searches those too. In testing, an `octocat` search recursively pulled in a completely unrelated person's entire digital footprint (a "Konrad Gibaszewski" in Berlin). The investigator searched one suspect — they do not want a stranger's accounts polluting results. Turn recursion off.
- `--timeout 10` — caps each site check so one slow site can't hang the run.

**Optional — handling the bot challenges you'll see.** In testing, `octocat` already produced "Just a moment: bot redirect challenge (8%)" and "Access denied (3%)" errors from your home IP. These are sites behind Cloudflare/WAF JS challenges. Maigret can route those through a local FlareSolverr instance to solve them: run `docker run -d -p 8191:8191 --name flaresolverr ghcr.io/flaresolverr/flaresolverr:latest`, then add `--cloudflare-bypass USERNAME`. This is opt-in and only fires for protected sites. For the hackathon it's a nice-to-have, not required — the fail-safe design means challenged sites just don't return, and you still get 100+ accounts. Don't add it unless a specific must-have platform (e.g. Instagram) is consistently failing. (Verified: Maigret 0.6.1, the version you installed, is current as of May 2026.)

### 5A.4 — The username-collision reality (the most important finding)

A username search returns every account that shares the *string*, NOT every account belonging to one person. The verified `octocat` run returned 142 accounts — but among them:

- GitHub `octocat` → "The Octocat" (the real one)
- Calendly `octocat` → "Daniel Li"
- PayPal `octocat` → "Wolfgang Zimmermann"
- Chess.com `octocat` → "Paul Wyka"
- DeviantArt `octocat` → "Salina", female, joined 2004

These are **different people sharing a username.** This is why the Maigret wrapper must return all claimed accounts *honestly* and let the SCORING ENGINE separate same-person from same-string. Username match alone is only ~30 of ~250 possible points (Section 7). Accounts cluster HIGH only when corroborated by a shared real name, photo (pHash), linked email/phone, or bio. This collision-handling is the demo's credibility moment: VERTEX keeps the corroborated octocat accounts and rejects the string-only ones. The data model carries `fullname` and `photo_url` on every profile precisely so the scoring engine can do this.

### 5A.5 — The verified scraper (drop-in, Agent 8 starting point)

```python
import json, subprocess, hashlib, datetime, os
from dataclasses import dataclass, field

@dataclass
class RawProfile:
    type: str
    value: str
    platform: str
    source_url: str
    metadata: dict = field(default_factory=dict)
    data_mode: str = "live"
    collected_at: str = ""
    sha256: str = ""

def _hash(*parts):
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()

class MaigretScraper:
    name = "maigret"

    async def resolve(self, username: str, data_mode: str = "live") -> list[RawProfile]:
        if data_mode == "mock":
            return self._mock(username)
        try:
            return self._run_live(username)
        except Exception as e:
            print(f"[maigret] failed: {e}")
            return []   # never crash the pipeline

    def _run_live(self, username: str) -> list[RawProfile]:
        outdir = "reports"
        subprocess.run(
            ["maigret", username, "--json", "simple",
             "--no-recursion", "--timeout", "10", "--no-progressbar",
             "--folderoutput", outdir],
            capture_output=True, timeout=180
        )
        path = os.path.join(outdir, f"report_{username}_simple.json")
        if not os.path.exists(path):
            return []
        with open(path) as f:
            data = json.load(f)
        return self._parse(data, username)

    def _parse(self, data: dict, username: str) -> list[RawProfile]:
        profiles = []
        now = datetime.datetime.utcnow().isoformat()
        for platform_name, entry in data.items():
            status = entry.get("status", {})
            if status.get("status") != "Claimed":      # only confirmed accounts
                continue
            url = status.get("url", "")
            ids = status.get("ids", {})                 # rich metadata, may be {}
            profiles.append(RawProfile(
                type="social_account",
                value=ids.get("username", username),
                platform=platform_name.lower(),
                source_url=url,
                metadata={
                    "fullname": ids.get("fullname"),
                    "bio": ids.get("bio"),
                    "photo_url": ids.get("image"),
                    "follower_count": ids.get("follower_count"),
                    "created_at": ids.get("created_at"),
                    "location": ids.get("location"),
                    "tags": status.get("tags", []),
                    "all_ids": ids,                     # keep everything for later
                },
                data_mode="live",
                collected_at=now,
                sha256=_hash(url, platform_name, username),
            ))
        return profiles

    def _mock(self, username):
        return [RawProfile(type="social_account", value=username,
                platform="github", source_url=f"https://github.com/{username}",
                metadata={"fullname": "Test User", "bio": "mock"},
                data_mode="mock", collected_at="", sha256=_hash("mock", username))]
```

Standalone test:
```bash
python -c "import asyncio; from backend.ingestion.maigret_scraper import MaigretScraper; \
print(len(asyncio.run(MaigretScraper().resolve('octocat'))))"
```


## SECTION 6 — THE DATA MODEL

Everything in VERTEX is built around two core objects and a SQLite schema.

### 6.1 — The RawProfile object (what every scraper emits)

```python
@dataclass
class RawProfile:
    type: str           # "social_account" | "email" | "phone" | "username" | "upi" | "breach" | "post" | "name"
    value: str          # the actual identifier or content
    platform: str       # "instagram" | "github" | "telegram" | "hibp" | etc.
    source_url: str     # where it was found
    metadata: dict      # platform-specific: bio, photo_url, photo_phash, followers, posting_history, etc.
    data_mode: str      # "live" | "mock"  (mock = development only)
    collected_at: str   # ISO timestamp
    sha256: str         # hash of value+platform+source_url (evidence integrity)
```

Every scraper, no matter how different internally, returns a `list[RawProfile]`. This is what makes the system composable.

### 6.2 — SQLite schema (single file, zero setup)

Six tables. Use stdlib `sqlite3` — no ORM. Reset with `rm vertex.db`.

```sql
CREATE TABLE users (
    user_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL, role TEXT DEFAULT 'investigator', created_at TEXT
);

CREATE TABLE cases (
    case_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
    seeds_json TEXT NOT NULL,          -- [{"type":"upi","value":"x@oksbi"}, ...]
    minor_involved INTEGER DEFAULT 0,  -- POCSO/JJ redaction flag [VERIFY-LEGAL]
    status TEXT DEFAULT 'pending', created_at TEXT, updated_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE entities (
    entity_id TEXT PRIMARY KEY, case_id TEXT NOT NULL,
    type TEXT, value TEXT, platform TEXT, confidence REAL,
    metadata_json TEXT, source_url TEXT, data_mode TEXT,
    sha256 TEXT, created_at TEXT,
    FOREIGN KEY (case_id) REFERENCES cases(case_id)
);

CREATE TABLE clusters (
    cluster_id TEXT PRIMARY KEY, case_id TEXT NOT NULL,
    entity_ids_json TEXT NOT NULL, confidence_score REAL, tier TEXT,
    explanation TEXT,            -- plain-English "why same person"
    signals_json TEXT,           -- which signals fired + points each
    created_at TEXT, FOREIGN KEY (case_id) REFERENCES cases(case_id)
);

CREATE TABLE audit_ledger (
    ledger_id TEXT PRIMARY KEY, case_id TEXT, action TEXT,
    search_id TEXT, input_hash TEXT, output_hash TEXT,
    previous_hash TEXT,          -- chain linkage (tamper-evident)
    actor TEXT, timestamp TEXT
);

CREATE TABLE artifacts (
    artifact_id TEXT PRIMARY KEY, case_id TEXT, entity_id TEXT,
    artifact_type TEXT,          -- "screenshot" | "json_dump" | "profile_photo"
    file_path TEXT, sha256 TEXT, captured_at TEXT
);

CREATE INDEX idx_entities_case ON entities(case_id);
CREATE INDEX idx_entities_value ON entities(value);
CREATE INDEX idx_clusters_case ON clusters(case_id);
CREATE INDEX idx_ledger_case ON audit_ledger(case_id);
```

---

## SECTION 7 — THE SCORING ENGINE (HOW ACCOUNTS GET LINKED)

This is the brain. It decides which accounts belong to the same person and — critically — refuses to link when evidence is thin.

### 7.1 — Signal weights

```python
SIGNAL_WEIGHTS = {
    "exact_phone_match":             40,   # same phone on both accounts
    "exact_email_match":             35,
    "exact_upi_match":               40,   # same UPI ID
    "username_exact_match":          30,
    "username_substring_match":      15,   # "arjun99" in "arjun99dev"
    "username_fuzzy_match":          10,   # Levenshtein < 3
    "profile_photo_phash":           25,   # Hamming distance < 8
    "posting_hours_overlap":         15,   # Jaccard > 0.6 on active hours
    "stylometry_cosine":             20,   # writing style cosine > 0.75
    "breach_co_occurrence":          18,   # appeared in same breach datasets
    "bio_keyword_overlap":            8,
    "reciprocal_mention":            15,   # A mentions B and B mentions A
}
# MAX_POSSIBLE = sum of all weights, used to normalize to 0-100
```

### 7.2 — Tier thresholds

```
HIGH:   normalized > 75   → strong match, present as likely same person
MEDIUM: 50–75             → possible match, investigator confirms
LOW:    25–50             → weak, flag but do not link
REJECT: < 25              → no link
```

### 7.3 — Red-herring rejection (the credibility moment)

This is the most important rule in the whole system:

```python
# If ONLY ONE signal fired (e.g. phone matches but nothing else),
# CAP the confidence at LOW regardless of that signal's weight.
if num_signals_fired == 1:
    tier = min(tier, "LOW")
    explanation += " Only a single signal matched — insufficient to link."
```

**Why this wins:** a phone number alone can match because of SIM reassignment, shared family phones, or a typo. A tool that blindly links on one signal is untrustworthy. A tool that says "I found a phone match but I'm NOT linking these because nothing else corroborates" is one an investigator trusts. Demo this explicitly — it's the moment a CID judge leans forward.

### 7.4 — Plain-English explanation

The score is deterministic maths. But the investigator sees plain English, generated from which signals fired:

> "These two accounts share the same registered phone number and post during the same late-night hours. Their profile photos are visually identical. Together these strongly indicate the same person."

NOT: `confidence: 0.82, signals: [phone:40, photo:25, hours:15]`

Build a template that turns fired signals into sentences. A template alone is reliable on stage. The LLM layer (Section 7A) can produce a richer version on top — but the template is the fallback that always works.

---

## SECTION 7A — THE LLM LAYER (NVIDIA CLOUD)

You have NVIDIA Cloud access to `meta/llama-3.3-70b-instruct` and `deepseek-ai/deepseek-v4-pro` (verified live on build.nvidia.com). Use them in exactly three places, all as enhancement-only with hard fallbacks. The LLM NEVER sits on the critical path and NEVER makes a linking decision.

### The non-negotiable rule

The scoring engine is deterministic maths and stays that way. The LLM only ever *describes* or *extracts* — it never decides confidence, never decides whether to link accounts, never blocks the graph from rendering. The moment an LLM decides linking, your "explainable, auditable, court-ready" story collapses, because you cannot reproduce or defend an LLM's judgment the way you can defend "+40 for exact phone match."

Every LLM call is wrapped in try/except with a hardcoded fallback. If NVIDIA is slow or returns garbage, the system degrades gracefully and the demo continues.

### Use 1 — Entity extraction from messy scraped text

When a Serper dork or a scraped bio returns a blob of prose, the LLM pulls structured identifiers out of it that regex would miss (a phone written "nine eight four...", a UPI ID buried mid-sentence, a username inside a paragraph).

- Model: `llama-3.3-70b-instruct`, temperature 0.1, max_tokens 1024
- Output: strict JSON array of `{type, value, confidence}` — system prompt says "output ONLY valid JSON, return [] if nothing found"
- **Fallback:** if the call fails or returns non-JSON, fall back to regex extraction (phone/email/UPI patterns). Pipeline continues either way.

### Use 2 — Plain-English "why same person" explanation

The scoring engine produces the maths (phone +40, photo +25, hours +15). The LLM turns the fired signals into the sentence the investigator reads.

- Model: `deepseek-ai/deepseek-v4-pro` (non-think mode for speed), temperature 0.7, max_tokens 200
- Input: the list of fired signals and the tier — NOT the raw score maths
- Rule: the prompt explicitly says "describe why these accounts likely belong to the same person based on these signals; use 'strongly indicates' not 'proves'; 2–3 sentences"
- **Fallback:** the deterministic template from Section 7.4. The LLM version is nicer; the template always works.

### Use 3 — Case-summary paragraph for the report (optional)

A 3–4 sentence human summary at the top of the BSA-63 PDF.

- Model: `deepseek-ai/deepseek-v4-pro`, temperature 0.5, max_tokens 300
- **Fallback:** skip it — the report is complete without it.

### Integration notes

- Use the full model string `deepseek-ai/deepseek-v4-pro` (provider/model-name convention, like the Llama string). Verified live on build.nvidia.com: `deepseek-v4-pro` and `deepseek-v4-flash` are current; the older `deepseek-v3.2` / `deepseek-v3.1-terminus` endpoints are flagged for deprecation, so do not target a v3 string.
- NVIDIA endpoint base: `https://integrate.api.nvidia.com/v1`, OpenAI-compatible `/chat/completions`. Auth via Bearer token (your NVIDIA API key).
- One shared `LLMClient` class with `extract_entities()`, `explain_match()`, and `summarize_case()` methods, each with its own try/except and fallback. Build this as part of Agent 5's neighbourhood or a dedicated agent before the orchestrator wires it in.
- Timeout every call at ~15s. With a 2–5 min total budget that's safe, but a hung LLM call should never stall the run — on timeout, take the fallback.

---

## SECTION 8 — THE UI, SCREEN BY SCREEN (FOR NON-TECHNICAL INVESTIGATORS)

The brief says: a junior investigator and non-technical people must understand it. Every screen is designed around that. No jargon, one primary action per screen, plain language everywhere.

### Design principles (non-negotiable)

1. **One primary action per screen.** Never make the user choose between five buttons.
2. **No OSINT jargon visible.** Not "seed identifier" — say "what do you know about the suspect?". Not "entity" — say "account" or "trace". Not "confidence tier" — say "how sure we are".
3. **Plain-English confidence.** "Strong match — likely the same person", not "0.82 HIGH".
4. **Every number explained.** A confidence badge is always next to a one-line reason.
5. **Dark professional theme.** Judges' reference point is commercial tools (ProfileIntel, Maltego). Match that polish.

### Screen 1 — Login

Just username, password, one "Sign in" button. Clean. Sets the tone of "real tool, not student project."

### Screen 2 — Case list (home)

A searchable list of cases. One prominent button: "+ New investigation". Each case shows title, date, status, and how many accounts were found. Search bar filters by title (this covers the "searchable dashboard" requirement).

### Screen 3 — New investigation (the input screen)

This is the screen that makes or breaks the "easy to use" requirement. Layout:

- A dropdown to pick what you have: **Name / Email / Phone number / Username / UPI ID / Face photo**
- A text box (or, for face, a drag-and-drop image area) that changes its placeholder based on the dropdown
- A "+ Add another" link to enter multiple things about the same suspect
- One big button: "Start investigation"

The dropdown removes all ambiguity for a non-technical user. They know what they have; they pick it; they type it.

### Screen 4 — Investigation in progress

A friendly progress screen. Plain-language status lines appear as work happens:
- "Searching social media platforms..."
- "Checking breach databases..."
- "Looking for linked accounts..."
- "Building the connection map..."

No technical tool names. A progress bar with status lines. Takes 2–5 minutes live, with results streaming in as each source returns (see 11.4).

### Screen 5 — The results dashboard (the main event)

Three-panel layout:

- **LEFT — Accounts found.** A scrollable list of every account/trace, each as a card: platform icon, username, and a plain-English confidence badge ("Strong match" / "Possible" / "Weak"). The red herring sits here visibly marked "Weak — not linked".
- **CENTRE — The connection map.** The network graph. Nodes are accounts, lines connect accounts believed to be the same person, line thickness/color = confidence. This is the moat visual. Click a node → its details open in the right panel.
- **RIGHT — Details + behaviour.** When you click an account: its bio, photo, posting times, top words/phrases, and WHY it's linked (plain English). Also shows the behavioural summary (active hours, most-used words).

Below the three panels: a timeline strip showing posts across platforms over time, and a row of action buttons: "Generate evidence report", "Export map".

### Screen 6 — The evidence report (BSA-63 PDF)

One button generates the court-ready PDF. The investigator can preview it in-browser and download. (Full spec in Section 10.)


## SECTION 9 — EXPECTED OUTPUT (WHAT THE INVESTIGATOR ACTUALLY SEES)

A worked example. Investigator inputs a UPI ID: `arjun.trades99@oksbi`.

### What comes back

**Accounts found (left panel):**
- Instagram `arjun.trades99` — Strong match
- Telegram `arjun_helpdesk` — Strong match
- Reddit `arjun_redditor` — Strong match
- GitHub `arjun-trades` — Possible match
- LinkedIn `arjun_sharma_blr` — Weak — not linked (the red herring)

**Bank identification (instant from UPI parser):**
- "This UPI ID belongs to State Bank of India (from the @oksbi suffix)"

**Registered name (from UPI name lookup):**
- "Account holder name on file: Arjun Mehta"

**The connection map (centre):**
- 4 nodes clustered tightly together with thick confidence lines (the same person across platforms)
- 1 node (the LinkedIn red herring) floating separate, thin/grey, clearly not connected

**Details when you click the Instagram node (right panel):**
- Photo, bio: "Investment advisor | DM for returns"
- Active hours: "Posts mostly 11pm–1am"
- Top phrases: "guaranteed returns", "double your money"
- Why linked: "Shares the same phone number as the Telegram and Reddit accounts, posts at the same hours, and uses the same investment vocabulary."

**Behavioural summary:**
- Peak activity: late night (11pm–1am)
- Repeated slogans across platforms
- 4 accounts created within a 5-day window (coordinated setup pattern)

**The red herring moment (when judge asks "what about this LinkedIn one?"):**
> "The system found a similar username but refused to link it. It's marked Weak at 34% — only the username looks similar. There's no shared phone, email, photo, or behaviour. The system flags it for the investigator's attention but does NOT claim it's the same person."

**The evidence report:**
A multi-page PDF with the case summary, every account with its confidence and reasoning, every captured artifact with its SHA-256 hash, the dual-signature certificate template, and a chain-of-custody log.

---

## SECTION 10 — THE BSA-63 EVIDENCE PACKAGE (THE MOAT — HANDLE WITH CARE)

This is the differentiator. It is also the highest-risk element because it makes legal claims. Every legal assertion here is marked **[VERIFY-LEGAL]** — confirm before demo.

### 10.1 — Why it matters

Most teams output a graph and a confidence number. VERTEX outputs a court-admissible evidence file. For a CID Karnataka audience, "evidence that survives in court" is the phrase that lands.

### 10.2 — What goes in the PDF (in order)

1. **Cover page** — case number, investigating officer, jurisdiction, date
2. **Search manifest** — every search run, its unique ID, SHA-256 of inputs+outputs, timestamp
3. **Findings summary** — linked identities, confidence scores, tiers, plain-English reasoning
4. **Annexure A** — captured artifacts (screenshots, JSON dumps, profile photos), each with its own SHA-256 hash
5. **[VERIFY-LEGAL] Part A certificate** — identifies the electronic records, describes how they were produced, particulars of the system. Signed by the person in charge of the system (auto-filled: logged-in investigator's name)
6. **[VERIFY-LEGAL] Part B certificate** — hash value of each record (SHA-256), the algorithm used, expert's name/credentials. The signature field is left for a real certified expert to fill — VERTEX never fakes a signature
7. **Chain of custody log** — every action on the case: who, when, what, what hash

### 10.3 — The claims to verify before demo [VERIFY-LEGAL]

Get a person (ideally a law student or professional) to confirm each of these against a primary source before July 4:

- That BSA (Bharatiya Sakshya Adhiniyam) 2023 Section 63 governs electronic-record admissibility and is in force
- That Section 63(4) requires a dual-part certificate (Part A by system-in-charge, Part B by an expert stating the hash and algorithm)
- That SHA-256 is accepted as the hashing standard in Indian courts
- The correct citation for the case law on inadmissibility-without-certificate (the brief cites *Arjun Panditrao Khotkar v. Kailash Kushanrao Gorantyal* — verify this is right and current)

**Do NOT cite PMLA Section 12 or "CPCR Section 12-compliant output" — both are wrong (the brief already caught these). If you mention a companion law, the brief suggests Section 94 BNSS 2023 (summons for production of records) — also [VERIFY-LEGAL].**

### 10.4 — The minor-redaction feature [VERIFY-LEGAL]

If a case is flagged "minor involved", the report should redact the minor's name/photo/identifiers. The brief says the relevant frameworks are POCSO Act 2012 §23 and JJ Act 2015 §74 — NOT "CPCR Section 12". Verify, then build the redaction toggle.

### 10.5 — The hash-verification demo moment

The killer demo move: a judge takes your PDF, picks any captured artifact, recomputes its SHA-256 independently, and it matches the value in the certificate. That proves the evidence wasn't tampered with. Practice this — have a terminal ready to compute a hash live.

---

## SECTION 11 — HOW ALL THE TOOLS CONNECT AND RUN SEAMLESSLY

This is the integration glue. The thing that makes 15 different tools feel like one system.

### 11.1 — The orchestrator

When an investigation starts, the orchestrator:

1. Reads the case seeds (e.g. one UPI ID)
2. For each seed, looks up which tools apply (the seed→tool map)
3. Wraps every applicable tool call as an async coroutine
4. Runs them ALL in parallel with `asyncio.gather(..., return_exceptions=True)`
5. Collects every `RawProfile`, ignoring any tool that errored (return_exceptions stops one failure killing the batch)
6. Passes the combined list to normalization → correlation → scoring
7. Stores results, updates case status, returns

```python
SEED_TOOL_MAP = {
    "email":    [HIBP, UserScanner, BlackbirdEmail, Epieos, GitHubSearch, SerperDork],
    "phone":    [PhoneInfoga, Ignorant, EpieosPhone, UPINameLookup, SerperTruecaller, FacebookPhoneCheck],
    "username": [Maigret, BlackbirdUser, Socialscan, RedditJSON, Telethon, SerperDork],
    "upi":      [UPIParser, UPINameLookup, SerperDork, UsernameExtract],  # extract feeds Maigret
    "name":     [SerperMultiDork],
    "face":     [PHashMatcher],
}

async def run_investigation(case_id, seeds):
    tasks = []
    for seed in seeds:
        for ToolClass in SEED_TOOL_MAP.get(seed["type"], [SerperDork]):
            tasks.append(ToolClass().resolve(seed["value"]))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    profiles = flatten_and_dedup([r for r in results if not isinstance(r, Exception)])
    # every profile is also Wayback-checked
    profiles += await wayback_check_all(profiles)
    clusters = ScoringEngine().score(CorrelationEngine().correlate(profiles))
    save_all(case_id, profiles, clusters)
    return {"status": "complete", "accounts": len(profiles), "clusters": len(clusters)}
```

### 11.2 — The fail-safe principle

Every single tool wrapper follows this rule: **never crash, always return a list (possibly empty).**

```python
async def resolve(self, identifier):
    try:
        return await self._run_live(identifier)   # or mock, per DATA_MODE
    except Exception as e:
        log.warning(f"{self.name} failed: {e}")
        return []     # empty, never an exception that stops the batch
```

This is why one rate-limited scraper never breaks the demo. If Sherlock times out, the other 14 tools still return, the investigation still completes, the graph still draws.

### 11.3 — The two data modes (one flag)

```python
# config.py
DATA_MODE = "live"   # "live" | "mock"
```

- `live` — real scrapes. This is what runs on stage. The whole demo is live.
- `mock` — fixed test data. Used ONLY during development so you can build correlation/scoring without hitting the network. Never used on stage.

The `BaseDataSource.resolve()` method checks this flag and routes accordingly. Downstream code never knows the difference. There is no cache mode — the demo is fully live per Decision 1.

### 11.4 — Streaming results to the screen

With a 2–5 minute live budget, the risk isn't speed — it's a screen that looks frozen. Stream results as each tool returns instead of waiting for all of them:

- The investigation endpoint kicks off the orchestrator as a background task and immediately returns a `case_id`.
- The frontend polls a status endpoint (or uses SSE/websocket) every 1–2 seconds.
- As each `RawProfile` batch lands in the DB, it appears on screen — accounts populate the left panel one source at a time, the graph grows node by node.
- A plain-language status line updates: "Searching social media…", "Checking breach databases…", "Found 3 linked accounts…".

This makes a 3-minute live scrape feel alive and intentional rather than stuck.

### 11.5 — Why NOT n8n

n8n was considered for orchestration and rejected. Reason: n8n's nodes can't run your Python tools natively — you'd wrap Python in shell-exec nodes inside n8n, which is harder to debug under time pressure than `asyncio.gather()`, and slower (sequential vs parallel). `asyncio` finishes 15 tools in 20-30 seconds; n8n would take minutes. Keep orchestration in FastAPI. (n8n is fine only if you later add a "re-investigate every 24h" scheduled feature — optional, not core.)


## SECTION 12 — THE AGENT BUILD PLAN

Build in this order. Each agent has a gate test — do not move to the next agent until the current one passes. Paste the context block (12.1) before every agent prompt. Each agent reads all prior `reference_agent*.md` files before starting and writes its own when done (12.4). The full paste-ready prompts are in 12.5.

### 12.1 — Context block (paste before every agent prompt)

```
Project: VERTEX — SOCMINT/OSINT suspect profiling tool for CID Karnataka hackathon.
Stack: FastAPI + SQLite (stdlib sqlite3, no ORM) backend. Next.js + Tailwind frontend.
        sigma.js network graph, vis-timeline, ReportLab PDF. NVIDIA Cloud LLM (llama-3.3-70b + deepseek-v4-pro) for entity extraction + explanations, enhancement-only with fallbacks.
Architecture: live-data pipeline. Seed -> data sources -> normalize -> correlate -> score -> outputs.
Every scraper implements BaseDataSource.resolve(identifier) -> list[RawProfile].
Every tool wrapper NEVER crashes — returns empty list on any failure.
DATA_MODE flag ("live"|"mock") routes all data sources. Build against "mock" first; demo runs fully "live".
All money/legal claims in the PDF are placeholders to be verified — do not hardcode legal text as fact.
UI is for non-technical investigators: no jargon, plain-English confidence, one primary action per screen.
HANDOFF RULE: when you finish, write reference_agentN.md (N = your agent number) recording exactly what you built — files created, public functions/classes with signatures, schema or interface decisions, how to import/call your work, gotchas. The next agent reads it instead of re-reading your code. Read all earlier reference_agent*.md files before you start.
```

### 12.2 — The agents

| # | Agent | Gate test | Attach to agent |
|---|---|---|---|
| 1 | **Foundation + DB + config** | `python -c "from backend.database import init_db; init_db(); print('OK')"` creates vertex.db with 6 tables | nothing |
| 2 | **Auth (JWT + bcrypt)** | register + login + token decode all succeed via curl | config, database |
| 3 | **Case management** | create case with 2 seeds, list cases, access control blocks other users | config, database, auth |
| 4 | **BaseDataSource + MockScraper** | mock returns 3+ RawProfile objects for a test seed | config, database |
| 5 | **Correlation + scoring engine** | two known-same mock profiles score HIGH; red herring scores LOW/REJECT | config, BaseDataSource |
| 5A | **LLM client** (NVIDIA: llama-3.3-70b + deepseek-v4-pro) | extract_entities returns JSON or regex-fallback; explain_match returns text or template-fallback; both survive a forced API failure | config |
| 6 | **Email scrapers** (HIBP, user-scanner, Blackbird, Epieos, GitHub, Serper) | each returns RawProfile or [] on a test email; no crashes | config, BaseDataSource, keys |
| 7 | **Phone scrapers** (PhoneInfoga, ignorant, UPINameLookup, Epieos, Serper, FBCheck) | each returns RawProfile or [] on a test phone | config, BaseDataSource, keys |
| 8 | **Username + UPI scrapers** (Maigret, Blackbird, socialscan, Reddit, Telethon, UPIParser) | Maigret returns only Claimed profiles for "octocat"; UPI parser identifies bank | ref4, ref1, Section 5A, Telegram session |
| 9 | **Wayback + name + face** (CDX, Serper multi-dork, pHash) | Wayback returns snapshots for a known profile URL | config, BaseDataSource |
| 10 | **Orchestrator** | one seed → all applicable tools run parallel → combined RawProfile list → LLM entity-extraction on text blobs → scored clusters with LLM explanations saved | everything above + LLM client |
| 11 | **Audit ledger + artifact hashing** | every search writes a ledger row with SHA-256; chain links verify | config, database |
| 12 | **BSA-63 PDF generator** | generates multi-section PDF with artifact hashes + cert templates | config, database, ledger |
| 13 | **Frontend: auth + case list + new-investigation form** | login → case list → create case with dropdown seed picker | API running |
| 14 | **Frontend: results dashboard** (3-panel + sigma.js graph + vis-timeline) | graph renders nodes, click node opens details, timeline shows posts | API with real case data |
| 15 | **Demo polish + streaming** | results stream to screen as sources return; full live run end-to-end finishes inside 5 min | everything |

### 12.3 — Antigravity session structure (every agent)

1. Paste context block (12.1)
2. **Read all earlier `reference_agent*.md` files** so you build against what already exists, not a guess
3. Paste the agent's specific prompt (12.5) and gate test
4. Attach only the dependency files listed in the table — not the whole repo
5. After output, copy files into the repo via terminal immediately
6. Run the gate test; fix in the same session if it fails
7. **Write `reference_agentN.md`** (12.4) recording what you built
8. Close the session only after the gate test passes AND the reference file is written

### 12.4 — The reference-file convention (read this — it's what keeps agents in sync)

Antigravity sessions don't share memory. Each agent starts blind. The reference files are the relay baton: every agent leaves a short, factual record of what it built so the next agent calls it correctly instead of re-deriving it (or worse, guessing a function name and breaking).

Each `reference_agentN.md` must contain, in plain terms:

```
# reference_agent3.md — Case Management

## Files created
- backend/cases/case_service.py
- backend/cases/case_routes.py

## Public functions / classes (with signatures)
- create_case(user_id: str, title: str, seeds: list[dict]) -> str   # returns case_id
- get_case(case_id: str, user_id: str) -> dict | None               # None if no access
- list_cases(user_id: str) -> list[dict]

## How to call my work
from backend.cases.case_service import create_case
case_id = create_case(user_id, "Test", [{"type":"upi","value":"x@oksbi"}])

## Schema / interface decisions
- seeds stored as JSON string in cases.seeds_json
- access control: get_case returns None if case.user_id != caller (enforce in routes too)

## Gotchas
- seeds_json must be json.dumps'd before insert; parse on read
- case_id is a uuid4 hex string, not an int
```

Keep it factual and short — signatures and decisions, not prose. The next agent reads every prior reference file before writing code. This single habit prevents the most common multi-agent failure: Agent 6 inventing a function name that Agent 4 didn't actually create.

### 12.5 — The full agent prompts (paste-ready)

Each prompt below is pasted into Antigravity AFTER the context block (12.1) and AFTER reading prior reference files. Each ends by requiring its reference file.

---

**AGENT 1 — Foundation + DB + config**

```
Build the VERTEX project skeleton and database layer.

Create:
- backend/config.py — loads from .env: DATA_MODE (default "live"), JWT_SECRET, and all
  API keys (HIBP_KEY, SERPER_KEY, GITHUB_TOKEN, NVIDIA_KEY, TELEGRAM_API_ID,
  TELEGRAM_API_HASH, NUMVERIFY_KEY). A validate_keys() function that WARNS on missing
  keys but never crashes. Use pydantic-settings or plain os.getenv.
- backend/database/__init__.py — stdlib sqlite3 (NO ORM). An init_db() function that
  creates all 6 tables: users, cases, entities, clusters, audit_ledger, artifacts
  (exact schema in Section 6.2 of the architecture). A get_db() helper returning a
  connection with row_factory = sqlite3.Row. Create the indexes listed in 6.2.
- backend/main.py — minimal FastAPI app with a /health route returning {"status":"ok"}.
- .env.example listing every key name with blank values.
- .gitignore including venv/, .env, *.db, reports/, __pycache__/

Use absolute imports from backend.* throughout.

GATE TEST: python -c "from backend.database import init_db; init_db(); print('OK')"
must create vertex.db with all 6 tables. Verify with:
sqlite3 vertex.db ".tables"

When done, write reference_agent1.md (files, config keys available, db helper signatures,
table names, how to import get_db/init_db).
```

---

**AGENT 2 — Auth (JWT + bcrypt)**

```
Build authentication on top of Agent 1's database. Read reference_agent1.md first.

Create:
- backend/auth/auth_service.py — register_user(username, password) -> user_id (bcrypt hash
  the password), authenticate(username, password) -> user dict | None, create_token(user_id)
  -> jwt string, decode_token(token) -> user_id | None. Use python-jose for JWT, bcrypt for
  hashing. Token expiry 12 hours.
- backend/auth/auth_middleware.py — a FastAPI dependency get_current_user(authorization
  header) that decodes the token and returns the user_id, raising 401 if invalid.
- backend/auth/auth_routes.py — POST /auth/register, POST /auth/login (returns token).
  Wire the router into backend/main.py.

Passwords are never stored or logged in plaintext.

GATE TEST: start the server, then via curl:
register a user, log in to get a token, call a token-protected test route — all succeed;
a bad token returns 401.

When done, write reference_agent2.md (auth function signatures, how to protect a route with
get_current_user, token format/expiry, how to get a token for testing later agents).
```

---

**AGENT 3 — Case management**

```
Build case CRUD with access control. Read reference_agent1.md and reference_agent2.md first.

Create:
- backend/cases/case_service.py — create_case(user_id, title, seeds: list[dict]) -> case_id
  (seeds like [{"type":"upi","value":"x@oksbi"}], stored as json in cases.seeds_json),
  get_case(case_id, user_id) -> dict | None (None if the case doesn't belong to user_id),
  list_cases(user_id) -> list[dict].
- backend/cases/case_routes.py — POST /cases (create), GET /cases (list mine),
  GET /cases/{id} (one, access-controlled). All routes require get_current_user from Agent 2.
  Wire the router into main.py.

Valid seed types: name, email, phone, username, upi, face.

GATE TEST: as user A create a case with 2 seeds; list cases (shows it); fetch by id (works);
as user B fetch user A's case id -> returns 404/None (access control works).

When done, write reference_agent3.md (case_service signatures, seed dict shape, seeds_json
storage decision, access-control behaviour, how to create a case for testing later agents).
```

---

**AGENT 4 — BaseDataSource + RawProfile + MockScraper**

```
Build the data-source abstraction every scraper will implement. Read reference_agent1.md first.
This is the most important interface in the system — everything downstream depends on it.

Create:
- backend/ingestion/base_module.py — the RawProfile dataclass EXACTLY as specified in
  Section 5A.5 of the architecture (type, value, platform, source_url, metadata dict,
  data_mode, collected_at, sha256), plus the _hash() helper. Also an abstract BaseDataSource
  class with: async def resolve(self, identifier: str, data_mode: str = "live") ->
  list[RawProfile], and a name attribute. resolve() must wrap _run_live in try/except and
  return [] on any exception — NEVER raise.
- backend/ingestion/mock_scraper.py — a MockScraper(BaseDataSource) that returns 3+
  realistic RawProfile objects for any identifier, including two that represent the SAME
  person (shared fullname + photo_url) and one red herring (same username string, different
  fullname, no other overlap). This mock is what Agent 5 builds the scoring engine against.

GATE TEST: python -c "import asyncio; from backend.ingestion.mock_scraper import MockScraper;
print(len(asyncio.run(MockScraper().resolve('test'))))" prints >= 3.

When done, write reference_agent4.md (the EXACT RawProfile field list with types, BaseDataSource
interface, the _hash signature, what the mock returns and which two profiles are same-person vs
the red herring — Agent 5 needs this).
```

---

**AGENT 5 — Correlation + scoring engine**

```
Build the brain: turn a list of RawProfile into scored clusters. Read reference_agent4.md first
(use the exact RawProfile fields and the mock's same-person/red-herring profiles to test).

Create:
- backend/correlation/correlation_engine.py — correlate(profiles: list[RawProfile]) -> list of
  candidate pairs/groups with the signals that fired between them. Signals to compute:
  exact phone/email/upi match, username exact/substring/fuzzy (use thefuzz), profile photo
  pHash distance (imagehash; Hamming < 8), posting-hours overlap, bio keyword overlap,
  stylometry cosine (sklearn TF-IDF on bio/posts), breach co-occurrence, reciprocal mention.
- backend/scoring/scoring_engine.py — the SIGNAL_WEIGHTS dict and thresholds from Section 7.
  score(correlation_result) -> clusters, each with confidence_score (0-100 normalized), tier
  (HIGH/MEDIUM/LOW/REJECT), signals_json (which fired + points), and a deterministic
  plain-English explanation template.
  CRITICAL: implement the red-herring rule — if only ONE signal fired, cap tier at LOW.

The score is pure deterministic math. No LLM here.

GATE TEST: run against MockScraper output — the two same-person mock profiles cluster HIGH;
the red herring (username-only) scores LOW/REJECT and is NOT in the HIGH cluster.

When done, write reference_agent5.md (correlate + score signatures, the cluster dict shape,
SIGNAL_WEIGHTS, tier thresholds, the red-herring rule, signals_json format — Agents 10 and 12
consume clusters).
```

---

**AGENT 5A — LLM client (NVIDIA)**

```
Build the LLM enhancement layer. Read reference_agent1.md (for NVIDIA_KEY) and reference_agent5.md.
The LLM is enhancement-only — it NEVER decides scores or linking, and every call has a fallback.

Create backend/llm/llm_client.py with one LLMClient class, NVIDIA base URL
https://integrate.api.nvidia.com/v1, OpenAI-compatible /chat/completions, Bearer auth:
- extract_entities(text: str) -> list[dict]  # model meta/llama-3.3-70b-instruct, temp 0.1,
  strict-JSON system prompt; FALLBACK to regex (phone/email/upi patterns) on any failure or
  non-JSON.
- explain_match(signals: list[str], tier: str) -> str  # model deepseek-ai/deepseek-v4-pro (use the
  explicit name, not deepseek-chat), temp 0.7, max_tokens 200, 2-3 sentences, "strongly
  indicates" not "proves"; FALLBACK to the deterministic template from Agent 5.
- summarize_case(findings: dict) -> str  # deepseek-ai/deepseek-v4-pro, temp 0.5; FALLBACK returns "".
Every method: try/except, 15s timeout, fallback on failure. Never raises.

GATE TEST: each method returns a sensible result with a working key; then temporarily break
the key and confirm all three return their fallbacks without raising.

When done, write reference_agent5a.md (LLMClient method signatures, model names used, the
fallback behaviour of each method — Agents 10/12 call these).
```

---

**AGENT 6 — Email scrapers**

```
Build the email-seed scrapers, each a BaseDataSource. Read reference_agent4.md (RawProfile +
interface) and reference_agent1.md (keys). Every scraper returns [] on failure, never raises.

Create in backend/ingestion/ (one file each, all extending BaseDataSource):
- hibp_scraper.py — GET https://haveibeenpwned.com/api/v3/breachedaccount/{email} with TWO
  required headers: hibp-api-key AND a user-agent (e.g. "VERTEX-OSINT"). MISSING user-agent
  returns HTTP 403 — this is the #1 HIBP integration mistake. Each breach -> a
  RawProfile(type="breach", platform="hibp"). Default response is truncated to breach names;
  that is all VERTEX needs.
- user_scanner_scraper.py — subprocess user-scanner on the email; parse registered sites.
- blackbird_email_scraper.py — subprocess Blackbird in --email mode; parse JSON.
- epieos_scraper.py — the Google-account technique: httpx to Google account/calendar
  endpoints; return display name + photo + maps/calendar links as RawProfiles.
- github_email_scraper.py — GET api.github.com/search/users?q={email}+in:email with token.
- serper_email_dork.py — POST to Serper with query "{email}"; each result -> RawProfile.

GATE TEST: run each on a throwaway test email — each returns a list (possibly empty) and none
raises. Break a key and confirm that scraper returns [] cleanly.

When done, write reference_agent6.md (each scraper class name + import path, what RawProfile
type/platform each emits, which key each needs).
```

---

**AGENT 7 — Phone scrapers**

```
Build the phone-seed scrapers, each a BaseDataSource. Read reference_agent4.md and
reference_agent1.md. Every scraper returns [] on failure.

Create in backend/ingestion/:
- phoneinfoga_scraper.py — run PhoneInfoga (Docker or binary or its REST API) on the number;
  parse carrier, country, line type, VoIP flag -> RawProfile(type="phone_intel").
- ignorant_scraper.py — subprocess ignorant; parse which platforms the number is registered on.
- upi_name_lookup.py — Playwright: initiate (then CANCEL, never send) a UPI payment to read
  the bank-registered name. Return RawProfile(type="name"). Document clearly that no money moves.
- epieos_phone_scraper.py — WhatsApp/Telegram registration check via Epieos technique.
- serper_truecaller_dork.py — POST Serper 'site:truecaller.com "{phone}"'.
- facebook_phone_checker.py — Playwright against FB password-recovery flow; return whether an
  account exists + the masked contact (e.g. +***67) as RawProfile(type="fb_phone_match").

GATE TEST: run each on a test number — each returns a list, none raises.

When done, write reference_agent7.md (scraper class names + import paths, RawProfile types
emitted, external dependencies like Playwright/Docker noted).
```

---

**AGENT 8 — Username + UPI scrapers**

```
Build username- and UPI-seed scrapers. Read reference_agent4.md and reference_agent1.md.
The Maigret scraper is ALREADY SPECIFIED AND VERIFIED in Section 5A.5 — use that code as-is.

Create in backend/ingestion/:
- maigret_scraper.py — EXACTLY the verified code in Section 5A.5 (with --no-recursion --timeout
  10). This is the primary username scraper.
- blackbird_user_scraper.py — subprocess Blackbird --username mode; parse JSON.
- socialscan_scraper.py — socialscan on the username across its 11 high-confidence platforms.
- reddit_scraper.py — GET reddit.com/u/{username}.json; parse post/comment history ->
  RawProfiles (include posting timestamps for behavioural analysis).
- telethon_scraper.py — Telethon with the saved session file (Section 3.1); read PUBLIC
  channels/groups only. data_mode handling: if no session, return [].
- upi_module.py — the UPI seed handler from Section 5.4: parse bank from suffix
  (@oksbi->SBI etc.), extract embedded phone if the id is a number, emit the username portion
  as a new username RawProfile, Serper-dork the full id, call upi_name_lookup.

GATE TEST: maigret_scraper returns claimed profiles for "octocat" (only status=="Claimed");
upi_module on "test.user@oksbi" identifies SBI and emits a username RawProfile.

When done, write reference_agent8.md (scraper class names + import paths, the Maigret RawProfile
shape from 5A, the UPI bank-map, what upi_module emits — note the username-collision behaviour
so the orchestrator/scoring know username matches need corroboration).
```

---

**AGENT 9 — Wayback + name + face**

```
Build the remaining seed handlers. Read reference_agent4.md.

Create in backend/ingestion/:
- wayback_scraper.py — given any discovered profile URL, query the Wayback CDX API
  (web.archive.org/cdx/search/cdx?url=...&output=json) via waybackpy or httpx; return archived
  snapshots with timestamps as RawProfile(type="archive"). Runs on every discovered URL.
- serper_name_dork.py — given a name, run parallel Serper dorks: site:linkedin.com/in,
  site:instagram.com, site:twitter.com, site:reddit.com, site:facebook.com — each result a
  RawProfile. Note name is low-signal; always needs corroboration.
- phash_matcher.py — given an uploaded face image, compute its pHash (imagehash) and compare
  Hamming distance to the photo_url of every collected profile; distance < 8 = match.

GATE TEST: wayback_scraper returns snapshots for a known archived profile URL; phash_matcher
correctly matches two identical images and rejects two different ones.

When done, write reference_agent9.md (function/class signatures, RawProfile types emitted,
how phash_matcher should be called with the collected-profiles list).
```

---

**AGENT 10 — Orchestrator**

```
Wire everything into one pipeline. Read reference_agent4,5,5a,6,7,8,9.md first.

Create backend/pipeline/orchestrator.py:
- SEED_TOOL_MAP mapping each seed type to its scraper classes (Section 11.1).
- async run_investigation(case_id, seeds) that: builds a task per applicable scraper per seed,
  runs them all with asyncio.gather(..., return_exceptions=True), flattens results (dropping
  exceptions), runs wayback on every discovered URL, runs LLM extract_entities on any free-text
  blobs, dedups, then calls correlation -> scoring (Agent 5), saves entities + clusters to the DB
  (Agent 1/3 schema), calls explain_match (Agent 5a) per cluster, updates case status.
- Stream-friendly: write entities to the DB as they arrive so the frontend can poll progress.

GATE TEST: create a case with one username seed, run run_investigation -> entities and clusters
are saved; a same-person cluster is HIGH; a username-only match is not in the HIGH cluster.
No single scraper failure stops the run.

When done, write reference_agent10.md (run_investigation signature, SEED_TOOL_MAP, the DB write
pattern for streaming, case status values — the frontend polls these).
```

---

**AGENT 11 — Audit ledger + artifact hashing**

```
Build the tamper-evident audit trail. Read reference_agent1.md (schema) and reference_agent10.md.

Create backend/ledger/audit_ledger.py:
- log_action(case_id, action, input_data, output_data, actor) — writes an audit_ledger row with
  input_hash, output_hash (SHA-256), and previous_hash linking to the prior row for this case
  (hash chain). 
- save_artifact(case_id, entity_id, artifact_type, content) — stores the artifact (screenshot/
  json/photo), computes its SHA-256, writes an artifacts row.
- verify_chain(case_id) -> bool — recomputes the chain and confirms no tampering.
Wire log_action into the orchestrator's key steps.

GATE TEST: run an investigation; every major step writes a ledger row; verify_chain returns True;
manually edit one row's hash and verify_chain returns False.

When done, write reference_agent11.md (function signatures, the hash-chain scheme, how the PDF
generator should pull artifact hashes — Agent 12 needs this).
```

---

**AGENT 12 — BSA-63 PDF generator**

```
Build the court-ready evidence package. Read reference_agent5,10,11.md and Section 10 of the
architecture. EVERY legal string is a placeholder marked [VERIFY-LEGAL] — do NOT assert legal
facts as settled; render them as clearly-marked template text.

Create backend/report/bsa63_generator.py using ReportLab:
generate_report(case_id) -> pdf path, producing the sections in Section 10.2: cover page, search
manifest (every search + SHA-256 + timestamp from the ledger), findings summary (clusters,
confidence, tiers, plain-English reasoning from Agent 5/5a), Annexure A (artifacts each with its
SHA-256 from Agent 11), Part A + Part B certificate TEMPLATES (signature fields blank — never
fake a signature), chain-of-custody log. Optional case-summary paragraph from LLM summarize_case
(skip on failure). If case.minor_involved, redact minor identifiers [VERIFY-LEGAL].

GATE TEST: generate_report on a completed case produces a multi-section PDF; a captured
artifact's SHA-256 in the PDF matches an independent shasum of that artifact.

When done, write reference_agent12.md (generate_report signature, PDF section list, where legal
placeholders are, how the hash-verification demo moment works).
```

---

**AGENT 13 — Frontend: auth + case list + new-investigation form**

```
Build the investigator-facing entry screens. Read reference_agent2,3.md for the auth + case API.
Next.js + Tailwind, dark professional theme. NON-TECHNICAL USERS: no jargon, plain language,
one primary action per screen (Section 8).

Build:
- Login screen (username, password, Sign in) — stores the JWT, attaches it to API calls.
- Case list (home): searchable list of cases, prominent "+ New investigation" button; each case
  shows title, date, status, account count.
- New investigation screen: a dropdown to choose seed type (Name / Email / Phone / Username /
  UPI ID / Face photo); the input changes with the choice (text box, or drag-drop image for
  face); a "+ Add another" to add multiple seeds about the same suspect; one "Start
  investigation" button that POSTs to /cases then triggers the run.

No OSINT jargon anywhere. "What do you know about the suspect?" not "seed identifier".

GATE TEST: log in -> see case list -> create a case via the dropdown form -> it appears in the
list and the investigation starts.

When done, write reference_agent13.md (routes/pages built, how the frontend stores the token and
calls the API, the seed-type values it sends — must match Agent 3's valid types).
```

---

**AGENT 14 — Frontend: results dashboard**

```
Build the main results screen. Read reference_agent10,13.md (case status polling + token/API).
Three-panel layout from Section 8, Screen 5.

Build:
- A polling/streaming results page: while status is running, show plain-language progress lines
  and stream accounts in as they appear.
- LEFT panel: list of found accounts as cards (platform icon, username, plain-English confidence
  badge: Strong / Possible / Weak). The red herring shows "Weak — not linked".
- CENTRE: the connection map using sigma.js — nodes = accounts, edges = same-person links, edge
  color/width = confidence. Click a node -> right panel. Clustered same-person nodes pull
  together; rejected nodes float separate.
- RIGHT: clicked account's details — photo, bio, posting hours, top phrases, and the plain-English
  "why linked" (from Agent 5/5a).
- Below: a vis-timeline strip of posts across platforms; buttons "Generate evidence report"
  (calls Agent 12) and "Export map".

GATE TEST: open a completed case -> graph renders nodes -> clicking a node opens its details ->
timeline shows entries -> "Generate evidence report" downloads the PDF.

When done, write reference_agent14.md (pages/components built, how it polls status and renders
clusters, any data-shape expectations it has of the API).
```

---

**AGENT 15 — Demo polish + streaming**

```
Final integration and demo hardening. Read all prior reference files.

Tasks:
- Confirm results stream to the screen as each source returns (not one big dump at the end).
- Confirm a full live run on one real identifier completes end-to-end inside 5 minutes.
- Confirm every scraper failure degrades gracefully (kill a key, run anyway).
- Confirm the LLM fallbacks fire when NVIDIA is unreachable.
- Polish the three-panel dashboard spacing, badges, empty states, and the progress copy.
- Verify the BSA-63 hash-verification moment works: a judge can shasum an artifact and match it
  to the PDF.

GATE TEST: from a cold start (uvicorn + npm), log in, create a case from a fresh identifier, watch
it stream, see the graph + timeline, generate the PDF, and independently verify one artifact hash
— all inside 5 minutes.

When done, write reference_agent15.md (final run instructions, known limitations, the exact demo
sequence that was rehearsed and works).
```

---

## SECTION 13 — DEMO DAY RUNBOOK

The demo is fully live. Judges give a random identifier; VERTEX scrapes it on stage in 2–5 minutes.

### Night before

- [ ] `npm run build` — zero errors
- [ ] Full end-to-end live run on a test identifier — confirm graph, timeline, PDF all render
- [ ] Confirm Telethon session file present and valid
- [ ] Confirm all API keys in `.env` and working (HIBP, Serper, GitHub, NVIDIA, Telegram)
- [ ] Confirm NVIDIA LLM calls work AND confirm the fallbacks work (temporarily break the key, verify regex + template kick in)
- [ ] Test on the actual college wifi you'll use, with a real identifier, timed — confirm it finishes inside 5 min
- [ ] Charge everything
- [ ] Back up the whole repo + db

### Morning of

- [ ] Boot, `uvicorn` backend + `npm start` frontend, confirm both up
- [ ] `DATA_MODE="live"`
- [ ] One full live dry run start to finish on a test identifier
- [ ] Terminal ready with a SHA-256 command for the hash-verification moment

### Demo sequence (live)

1. Login (sets "real tool" tone) — 10s
2. New investigation — take the identifier the judges give you, pick the matching type from the dropdown, paste it — 20s
3. Hit start — results stream in live: status lines update, accounts populate one source at a time, graph grows node by node — 2–5 min (narrate while it works)
4. Once populated: walk the connection map — the clustered same-person accounts vs the separate ones — 30s
5. **Red-herring moment** — point to the weak/unlinked node, explain why VERTEX refuses to link on a single signal — 45s
6. Click a node — show behaviour and the plain-English "why linked" (LLM or template) — 30s
7. Timeline — cross-platform posting pattern — 20s
8. **BSA-63 moment** — generate the PDF, scroll the dual-signature certificate, recompute a captured artifact's SHA-256 live in the terminal to prove integrity — 60s
9. Close: "This is OSINT that survives in court — and you just watched it run live."

### If the live scrape is slow or thin

- Narrate the streaming so it never looks frozen ("social media coming back now, breach check running…").
- If a name seed returns little, lean into the honesty: "names are the weakest seed; here's what we surfaced, and here's the system correctly refusing to over-claim."
- The red-herring rejection and the BSA-63 hash verification do not depend on volume of results — they land regardless. Make sure you reach them.

---

## SECTION 14 — OPEN RISKS & HONEST LIMITATIONS

State these in the limitations section of your report and to judges. Honesty about limits is a credibility signal to people who know OSINT.

| Risk / limitation | Mitigation |
|---|---|
| **Legal claims (BSA-63) may be wrong** | Every legal claim marked [VERIFY-LEGAL]; confirm with a law source before July 4 |
| **Facebook / LinkedIn full profiles are login-gated** | Surface only what's publicly indexed; say so plainly. Don't claim full FB/LinkedIn scraping |
| **Follower/following data needs platform OAuth** | Mentions/replies are live; follower graphs are limited. State this in the report |
| **Single IP gets rate-limited mid-demo** | Each tool retries once then fails to empty list; 2–5 min budget absorbs retries; college wifi (trusted) over shared venue wifi |
| **Name-only seed is low-signal** | Always needs corroboration; never link on name alone |
| **Scrapers break when sites change** | Fail-safe design (empty list on failure) means one broken tool never stops the run |
| **No ground-truth for "accuracy"** | Claim only what's defensible: correct clustering on a known validation set + red-herring rejection |
| **Telethon session can expire** | Authenticate at home on stable wifi; keep the session file backed up |

---

## APPENDIX — QUICK REFERENCE

**Repo layout:**
```
vertex/
├── backend/
│   ├── config.py
│   ├── database/__init__.py
│   ├── auth/ (auth_service, auth_middleware, auth_routes)
│   ├── cases/ (case_service, case_routes)
│   ├── ingestion/ (base_module + one file per scraper)
│   ├── pipeline/ (orchestrator)
│   ├── correlation/ (correlation_engine)
│   ├── scoring/ (scoring_engine)
│   ├── ledger/ (audit_ledger)
│   ├── report/ (bsa63_generator)
│   ├── llm/ (llm_client — NVIDIA, with fallbacks)
│   └── main.py
├── frontend/ (Next.js app)
├── reports/ (maigret JSON output — gitignored)
├── references/ (reference_agent1.md ... reference_agent15.md — the agent handoff trail)
├── data/ (test identifier set)
└── vertex.db
```

**The five things that matter most:**
1. The data-source interface — build it first, everything depends on it
2. Fail-safe wrappers — one broken tool must never stop the run
3. Red-herring rejection — the credibility moment
4. Plain-English UI — a non-technical investigator must get it instantly
5. The BSA-63 package with verified legal claims — the moat

*End of document.*
