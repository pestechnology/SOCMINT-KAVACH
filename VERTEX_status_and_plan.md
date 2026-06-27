# VERTEX — Project Status & Plan

**Date:** June 25, 2026
**Hackathon:** CIDECODE 2026 — Saturday/Sunday July 4-5
**Days remaining:** ~9 days of build, then 24h hackathon

---

## Where we stand right now

### What works today

**Identifier types VERTEX handles correctly:**

| Type | Status | Tools | Notes |
|---|---|---|---|
| Username | ✅ Working | Maigret (500+ sites), GitHub API | Returns ~46 platforms for active users like `torvalds` |
| Email | ✅ Working | holehe | Returns ~17 platforms where email is registered |

**Engine components that work:**

- Live scraping via swappable data source layer
- Parallel scraper fan-out via asyncio
- Photo perceptual hashing computed in parallel
- Response caching in SQLite (24h TTL, configurable)
- Correlation engine with 10 weighted signals
- Red-herring rejection (refuses to link strangers sharing only a username)
- Plain-English "why these are the same person" explanations
- Confidence tiers: HIGH / MEDIUM / LOW / REJECT
- SHA-256 audit ledger with tamper-evident hash chain
- Frontend with dark theme, plain-English UI
- Investigator-friendly results (Strong match / Possible match / Not linked)

**Verified demo:**

Type `torvalds` (username) → ~46 platforms found, 1 MEDIUM-confidence cluster containing the real Linus Torvalds accounts (Disqus, Twitter, Telegram, LiveJournal), 42 singletons correctly NOT merged (they're different people sharing the username string).

This is real working OSINT. Live data. No mocking.

### What's broken or missing

**Known bugs:**

1. **Duplicate platform rows** — when Maigret AND GitHub both return a profile for the same platform/handle, they appear as two cards in the same cluster instead of one merged card.
2. **Holehe platform name parsing** — `any.do` gets stored as `"any"`, header row "email" gets misparsed as a platform name.

**Identifier types NOT yet supported:**

| Type | Status | Tool needed |
|---|---|---|
| Phone number | ❌ Not built | PhoneInfoga + ignorant |
| UPI ID | ❌ Not built | Custom parser → cascade to username search |
| Full name | ❌ Not built | Serper (Google search) for `"Name" "City"` queries |
| Social media URL | ❌ Not built | URL parser → extract handle → username search |
| Photo / face | ❌ Out of scope | Decided not to build |

**Differentiators NOT yet built:**

- BSA-63 court-ready PDF (the moat — most important missing piece)
- Bio-link extraction + iterative seed expansion
- Visualizations beyond results card (graph view, timeline)

### Honest verdict: we are about 40-50% done

The foundation is genuinely solid. The hard architectural decisions (data source layer, swappable scrapers, audit ledger, correlation engine) are all done and proven to work. What's left is:

- Mechanical: adding more scrapers using the established pattern (phone, UPI, name, URL)
- Critical: building the BSA-63 PDF (defensibility moat)
- Polish: bug fixes, UI cleanup, demo rehearsal

---

## What VERTEX will be able to do by hackathon (realistic forecast)

This is what you should promise judges, and what you should NOT promise.

### Promise these — confident

When a judge enters **a real public username** (`naval`, `torvalds`, `pieter`, an Indian dev/influencer with linked socials), VERTEX will:

- Search 500+ platforms via Maigret
- Pull rich profile data from GitHub
- Compute photo similarity across all collected photos
- Cluster accounts that genuinely belong to the same person
- Refuse to merge accounts where evidence is insufficient (this is the strength)
- Generate a BSA-63-compliant court PDF with dual-signature certificate and SHA-256 hashes of every captured artifact
- Show audit trail of every scrape and every decision

When they enter **an email** (`someone@gmail.com`):

- Run holehe to find ~10-30 platforms where it's registered
- Run GitHub API in case the email is publicly listed on a GitHub profile
- Cluster results
- Generate court PDF

When they enter **a phone number** (`+919876543210`):

- Run PhoneInfoga to get carrier, country, validity
- Run ignorant to check WhatsApp/Telegram/Instagram/Amazon/Snapchat registration
- Show which platforms confirm the number is registered

When they enter a **UPI ID** (`arjun@oksbi`):

- Parse bank handle to identify the bank/PSP
- Take the localpart (`arjun`) and run full username search on Maigret + GitHub
- Cluster results

When they enter a **social media URL** (`instagram.com/someone`):

- Extract the handle from the URL
- Run the username search flow

### Don't promise these — honest

When a judge enters **a full name only** (`Rahul Sharma`):

- VERTEX will use Serper to Google-search the name
- Returns candidate profile URLs from search results
- BUT: name searches return many candidates of different people. The system will show them as separate clusters because there's no bridge to merge "Rahul Sharma the lawyer" with "Rahul Sharma the developer."
- Be ready to say: *"Common names produce many candidates. We require additional identifiers — city, photo, or username — to corroborate which one is the suspect. This is intentional — we refuse to claim links we can't defend in court."*

When they enter **a first name alone** (`Rahul`):

- Cannot work. No tool in the world can. Say this honestly.

### What WON'T work no matter what

- **Suspects who actively hide.** Different photo per platform, no cross-links in bios, different usernames everywhere. No tool solves this without insider data.
- **Private accounts.** Instagram private accounts, locked Facebook profiles. We see nothing.
- **Platforms we can't scrape.** Facebook posts, TikTok content, full Twitter timelines — these are walled off without paid APIs.

---

## The pitch to memorize

When judges hand you a test case and you find 4 out of 8 accounts a suspect has, don't apologize. Say this:

> *"VERTEX returned [N] linked accounts at high confidence and [M] at medium confidence. The remaining candidates share only partial signals and would require human investigator judgment to confirm. We chose to refuse low-confidence links rather than risk false positives — those would be inadmissible under BSA Section 63 and could pollute a real prosecution. Here is the court-ready evidence PDF with hash chain. This is how investigative-grade OSINT must work."*

That answer wins. Volume of results doesn't win. Defensibility wins.

---

## Plan for remaining 9 days

### Day 1 (today, June 25 — what's left of it)

**Session 11: Phone scrapers + UPI parser**

- Install PhoneInfoga and ignorant locally
- Build PhoneInfogaScraper, IgnorantScraper, UPIParser
- Wire into orchestrator
- Add UPI→username cascade

Goal: VERTEX now accepts phone and UPI inputs.

### Day 2 (June 26)

**Session 12: Social URL parser + bug fixes**

- URL parser that detects `instagram.com/X`, `twitter.com/X`, etc. and extracts the handle
- Routes the extracted handle through the existing USERNAME flow
- Fix duplicate platform bug (Maigret + GitHub returning same platform)
- Fix holehe platform name parsing

Goal: VERTEX now accepts URLs. Two annoying bugs gone.

### Day 3 (June 27)

**Session 13: Serper integration for full-name search**

- SerperScraper that takes a NAME and Google-searches with multiple queries
- Returns candidate profile URLs from search results
- Each candidate URL gets the URL parser treatment from Day 2
- Honest UI labeling: "name searches return multiple candidates — review manually"

Goal: VERTEX now accepts full names with honest expectations.

### Day 4 (June 28)

**Session 14: Bio-link extraction + iterative expansion**

- Scan every scraped bio for additional emails, usernames, phones
- New identifiers found feed back into the scraper pool
- Max 3 iterations to prevent runaway
- Audit ledger logs each expansion step

Goal: Cross-platform linkage when usernames DIFFER but bios self-disclose.

### Day 5 (June 29)

**Session 15: BSA-63 PDF generator (the moat)**

- ReportLab-based PDF
- Cover page, case summary, findings, annexures of every artifact with SHA-256
- Part A certificate (auto-filled investigator section)
- Part B certificate (hash values, SHA-256 algorithm, expert signature line)
- Chain of custody log

Goal: The court-ready deliverable. Most teams won't build this. This wins the demo.

### Day 6 (June 30)

**Session 16: PDF polish + audit ledger integration**

- Make the PDF look like a real police document (serif headers, conservative styling, no colors)
- Wire ledger entries into the PDF's chain of custody section
- "Verify this report" demo: re-run the search → show same hash → prove no tampering

Goal: BSA-63 PDF goes from working to court-credible.

### Day 7 (July 1)

**Session 17: UI polish + investigator experience**

- Fix any remaining display bugs
- Loading states, error states
- Empty states (no results found, server unreachable, etc.)
- Walk through the full demo flow as an investigator would

Goal: Frontend feels like a real tool, not a hackathon project.

### Day 8 (July 2)

**Session 18: Demo rehearsal + edge cases**

- Run the full demo end-to-end at least 5 times
- Time it (target 5 minutes)
- Practice the honest pitch
- Practice answers to obvious questions ("What about privacy?", "How does this scale?", "What if a suspect uses a VPN?")
- Record a video backup in case live network fails on demo day

Goal: You can demo VERTEX cold, in your sleep, with the network down.

### Day 9 (July 3)

**Buffer / pre-hackathon prep**

- Pack laptops, chargers, ethernet adapter, mobile hotspot
- Test the demo on the actual venue laptop
- Have all dependencies pre-installed
- Sleep early

Goal: Show up to the hackathon ready.

### Day 10-11 (July 4-5) — Hackathon

- 24-hour hackathon
- Integrate whatever test case CCITR gives you (~2-4 hours)
- Polish, demo prep
- Sleep 3 hours
- Present

---

## What success looks like at hackathon

When a CCITR judge hands you a test identifier on July 5:

1. You type it into VERTEX
2. Wait 30-90 seconds while scrapers fan out
3. See a clean dashboard with:
   - 1-3 high-confidence linked clusters
   - Several medium-confidence candidates
   - Singletons clearly marked "not linked"
4. Click "Generate court report"
5. Download a BSA-63-compliant PDF with hash chain, dual-signature certificate, and every captured artifact annexed
6. Show the audit ledger — every search has a unique hash, fully re-verifiable

That's the demo. That's what wins.

---

## Risks to flag

1. **Live network at venue** — College WiFi may block scrapers. Mobile hotspot as backup.
2. **API rate limits** — Serper free tier is 2500 queries. GitHub is 5000/hour. Plan testing carefully.
3. **PhoneInfoga reliability** — Some OSINT scanners it queries are flaky. Failures should be graceful, not crash.
4. **Demo machine** — Set up everything on ONE laptop early in the week. Don't demo from a machine you've never run the system on.
5. **Mentor scope changes** — The mentor confirmed 5 input types. If a judge tests with photo or UPI or something else, have a graceful answer ready.

---

## Bottom line

You will have a working SOCMINT tool that handles 5 input types, refuses false positives, and produces court-admissible evidence packages. You will not have a Maltego-killer. That's the right trade. Quality of evidence beats volume of results for the audience you're presenting to.
