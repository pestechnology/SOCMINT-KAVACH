# VERTEX — Legal Claims Verification

**Verified:** June 27, 2026 · against public primary/secondary sources
**Status of each claim:** ✅ CONFIRMED / ⚠️ CONFIRMED-WITH-NUANCE / ❌ WRONG

> **IMPORTANT — read this first.** This verification is research-grade, done against
> bare-act text and reputable legal commentary. It is **not legal advice** and does
> **not** replace sign-off by a qualified advocate. The Master Architecture rule still
> stands: have a real lawyer or law student confirm each item before presenting it to a
> CID/CCITR audience on July 4. What this document does is tell you which claims are
> safe to make and which were already wrong in the brief — so you don't get caught on stage.

---

## ✅ Claim 1 — BSA 2023 Section 63 governs electronic-record admissibility and is in force

**CONFIRMED.**

- The Bharatiya Sakshya Adhiniyam (BSA), 2023 came into force **1 July 2024**, replacing the
  Indian Evidence Act, 1872.
- **Section 63** is the direct successor to the old **Section 65B IEA**. It governs the
  admissibility of electronic records: information in an electronic record that is printed,
  stored, recorded or copied is "deemed to be a document" and is admissible without further
  proof or production of the original, **provided the conditions in the section (including the
  certificate) are met.**

**Safe to say on stage:** "Electronic-record admissibility in India is governed by Section 63
of the Bharatiya Sakshya Adhiniyam, 2023, which replaced Section 65B of the Indian Evidence
Act when the BSA came into force on 1 July 2024."

---

## ✅ Claim 2 — Section 63(4) requires a dual-part certificate (Part A by system-in-charge, Part B by an expert), and Part B states the hash + algorithm

**CONFIRMED.** This is the strongest legal pillar of the whole product.

- Section **63(4)** requires a certificate **each time** an electronic record is submitted for
  admission. The certificate format is prescribed in **THE SCHEDULE [See section 63(4)(c)]**,
  appended to the Act.
- The Schedule certificate has **two parts**:
  - **Part A** — filled and signed by the **party producing the electronic record** (the person
    in charge of the device / management of the relevant activities). Identifies the record and
    describes how it was produced.
  - **Part B** — filled and signed by an **expert**. This is the genuine change from the old §65B
    single-signature model.
- **Part B explicitly records the HASH VALUE of the electronic record and the algorithm used.**
  Recognised algorithms named in the Schedule/commentary include **SHA-1, SHA-256, and MD5.**

**Why this matters for VERTEX:** your BSA-63 PDF generating a Part A (auto-filled investigator
section) + Part B (hash value, SHA-256, expert signature line left blank) is an *accurate*
implementation of the statutory schedule. This is real, not theatre.

**Safe to say on stage:** "Section 63(4) and its Schedule require a two-part certificate — Part A
by the person in charge of the system, Part B by an expert who records the hash value of each
record and the algorithm used. VERTEX produces exactly this, populating the hash fields with
SHA-256 and leaving the expert signature blank for a certified examiner — we never fake a
signature."

---

## ✅ Claim 3 — SHA-256 is accepted for hashing electronic evidence

**CONFIRMED (with the honest nuance below).**

- The BSA §63(4) Schedule and surrounding legal commentary explicitly contemplate cryptographic
  hash functions — **SHA-1, SHA-256, MD5** — as the means of generating the "digital fingerprint"
  that proves a file is unaltered. SHA-256 is the modern, defensible choice (MD5 and SHA-1 are
  considered cryptographically weak).

**Honest nuance:** the statute lists hash algorithms as the accepted *mechanism*; it does not
"mandate SHA-256" specifically. So claim **"SHA-256 is an accepted hashing standard for this
purpose"** — do **not** claim "the law mandates SHA-256." Both MD5 and SHA-256 appear in the
Schedule; you simply chose the strongest one.

---

## ⚠️ Claim 4 — Case law: *Arjun Panditrao Khotkar v. Kailash Kushanrao Gorantyal*

**CONFIRMED, with one nuance you must state correctly.**

- The citation is **correct and current**: *Arjun Panditrao Khotkar v. Kailash Kushanrao
  Gorantyal & Ors.*, Supreme Court of India, **14 July 2020**, (2020) 7 SCC 1.
- It held that a **certificate is mandatory** for the admissibility of electronic evidence (under
  the then §65B(4) IEA) — a **condition precedent**. It overruled *Shafhi Mohammad* and reaffirmed
  *Anvar P.V. v. P.K. Basheer* (2014).
- **The nuance:** this case was decided under the **old §65B**, not under BSA §63. That's fine —
  it is the *foundational precedent* for the mandatory-certificate principle that §63 now carries
  forward. State it that way.
- **One real exception worth knowing** (a judge may probe this): the Court clarified that if the
  **original device itself** is produced and its owner testifies, **no certificate is needed**.
  VERTEX deals in *copies of public web data*, not seized original devices — so the certificate
  requirement squarely applies to your output. Good answer to have ready.

**Safe to say on stage:** "The leading authority is *Arjun Panditrao Khotkar v. Kailash Kushanrao
Gorantyal* (Supreme Court, 2020), which held the electronic-evidence certificate is mandatory — a
condition precedent to admissibility. It was decided under the old Section 65B; the same principle
carries into Section 63 of the BSA. That's exactly why VERTEX generates the certificate by default."

---

## ✅ Claim 5 — Companion provision: Section 94 BNSS 2023 (summons for production)

**CONFIRMED — use this instead of the wrong PMLA §12 citation.**

- **Section 94 of the Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023** empowers a court or police
  officer to issue a summons/written order (physical or electronic) requiring production of
  **documents, electronic communications, and communication devices likely to contain digital
  evidence** necessary for an investigation/inquiry/trial.
- It is the correct modern successor to the old CrPC §91 and explicitly covers digital evidence
  held by intermediaries.

**Safe to say:** "Production of digital records is compelled under Section 94 BNSS, 2023 — the
modern successor to CrPC Section 91." Keep this as a *supporting* citation, not a core claim.

---

## ✅ Claim 6 — Minor-redaction provisions: POCSO §23 and JJ Act §74

**CONFIRMED — these are the correct citations (the brief's earlier "CPCR Section 12" was wrong).**

- **POCSO Act, 2012 — Section 23:** prohibits any media report from disclosing the identity of a
  child — *name, address, photograph, family details, school, neighbourhood, or any particular
  that may lead to identification.* Disclosure allowed only by the Special Court, for reasons
  recorded in writing, in the child's interest. Breach carries 6 months–1 year imprisonment and/or
  fine.
- **Juvenile Justice (Care and Protection of Children) Act, 2015 — Section 74:** prohibits
  disclosure in any media of the name/address/school/any identifying particular, or the picture,
  of a child in conflict with law / a child in need of care and protection / a child victim or
  witness. Exception only by the Board/Committee, reasons in writing, best interest of the child.
  Breach: up to 6 months and/or fine up to ₹2,00,000.

**For VERTEX's `minor_involved` redaction toggle:** redacting a minor's name, photo, and
identifying particulars from the report is a *correct and defensible* feature directly traceable to
POCSO §23 and JJ §74.

**Safe to say:** "When a case is flagged as involving a minor, VERTEX redacts the child's name,
photograph and identifying particulars from the report, consistent with Section 23 of the POCSO
Act, 2012 and Section 74 of the Juvenile Justice Act, 2015."

---

## ❌ Do NOT say these (already wrong in the original brief — confirmed wrong)

- ❌ **"PMLA Section 12"** as the production/evidence authority. PMLA §12 concerns reporting-entity
  obligations (record-keeping by banks/FIs) under anti-money-laundering law — it is **not** the
  basis for compelling production of digital evidence. Use **BNSS §94** instead.
- ❌ **"CPCR Section 12 / CPCR-compliant output"** for minor protection. Wrong framework. Use
  **POCSO §23** and **JJ Act §74**.
- ❌ **"The law mandates SHA-256."** It accepts hash algorithms generally (SHA-256 is one of them).
  Say "accepted," not "mandated."

---

## Net effect on the demo

Every legal claim VERTEX makes can now be stated **accurately and confidently** — the BSA §63(4)
dual certificate with hash value, the *Arjun Panditrao* precedent, BNSS §94, and the POCSO/JJ
redaction basis. The two wrong citations the brief originally carried (PMLA §12, CPCR §12) are
confirmed wrong and replaced. **Still get a human lawyer to co-sign before July 4 — but you are
now standing on solid ground, not guesses.**

---

### Sources

BSA §63 / §63(4) Schedule (Part A & B, hash value):
- [Section 63 — Indian Kanoon](https://indiankanoon.org/doc/125020475/)
- [THE SCHEDULE, See section 63(4)(c) — India Code (official)](https://upload.indiacode.nic.in/schedulefile?aid=AC_CEN_5_23_00049_2023-47_1719292804654&rid=1163)
- [Admissibility of Electronic Evidence, Certificate and Hash Value, S 63 BSA — Corpotech Legal](https://corpotechlegal.com/admissibility-electronic-evidence-sec-63-bsa/)
- [How to fulfil admissibility requirements under S.63 BSA — LiveLaw](https://www.livelaw.in/articles/electronic-evidence-admissibility-section-63-bhartiya-saksha-adhiniyam-2023-261511)
- [Electronic Evidence under BSA 2023 — Drishti Judiciary](https://www.drishtijudiciary.com/bharatiya-sakshya-adhiniyam-&-indian-evidence-act/electronic-evidence-under-bhartiya-sakshya-adhiniyam-2023)

Case law:
- [Arjun Panditrao Khotkar v. Kailash Kushanrao Gorantyal — SCC Times analysis](https://www.scconline.com/blog/post/2021/06/07/electronic-evidence-2/)
- [Judgment PDF — A.P. High Court mirror](https://aphc.gov.in/docs/imp_judgements/Arjun%20Panditrao%20Khotkar%20_%20Kailash%20Kushanrao%20Gorantyal%20And%20Ors._1701334263.pdf)

BNSS §94:
- [Section 94 BNSS — Indian Kanoon](https://indiankanoon.org/doc/144691869/)
- [Section 94 BNSS — KanoonGPT bare act](https://kanoongpt.in/bare-acts/the-bharatiya-nagarik-suraksha-sanhita-2023/arrangement-of-sections-chapter-vii-a-summons-to-produce-section-94-bdda49bc4e9dc2d8)

POCSO §23 / JJ §74:
- [POCSO Act 2012 — India Code (official PDF)](https://www.indiacode.nic.in/bitstream/123456789/2079/1/AA2012-32.pdf)
- [JJ Act 2015 — India Code (official PDF)](https://www.indiacode.nic.in/bitstream/123456789/2148/1/a2016-2.pdf)
- [Section 74 JJ Act — Indian Kanoon](https://indiankanoon.org/doc/190194922/)
