"""
backend/ingestion/bulk_subjects.py — parse a subject sheet (.xlsx / .csv / .docx)
into case seeds.

Bulk intake: an officer arrives with one Word document listing several subjects (the
shape a Khoj/TrueCaller-style OSINT sheet already has — Name, Alias, Email, Phone,
UPI/VPA, Profile URL). This turns that document into N ready-to-run investigations.

ONE SUBJECT = ONE CASE, never one case with everybody's seeds merged: the correlation
engine links accounts that share signals, so pouring five people's identifiers into a
single case would manufacture cross-subject clusters out of nothing.

No new dependency for any of the three. A .docx and an .xlsx are both ZIPs of XML, so
zipfile + ElementTree read them; .csv is the stdlib csv module. openpyxl/python-docx
would each add a dependency to do what these ~90 lines already do.

XLSX is the format officers actually work in, CSV is what every other system exports,
and .docx is kept because a subject sheet often starts life as a Word report.

Two layouts are accepted, because both are what people actually send:

  A. FIELD LINES              B. GRID TABLE
     Name: Jayadeep Prasad       | Name    | Phone      | Email        |
     Phone: 8121569830           | Jayadeep| 8121569830 | j92@mail.com |
     Email: j92@mail.com         | Asha R  | 9800011122 | asha@mail.com|
     (blank line)
     Name: Asha R
     Phone: 9800011122

  In layout A a new subject starts at a blank line, a separator line (---, ===, ***),
  an explicit "Subject:"/"Subject 2" marker, or a repeated Name field. A repeated
  *other* field is a second VALUE, not a new subject — the Khoj report lists nine
  aliases and two UPI IDs for one person, and that must stay one person.

Every parse is fail-safe. The number of subjects is bounded by MAX_FILE_BYTES rather
than an arbitrary row count: the sheet is the officer's, and the preview step means a
row count is always seen and confirmed before anything runs. MAX_SEEDS_PER_SUBJECT still
caps ONE row's identifiers, because that bounds the query cost of a single case.
Malformed input raises ValueError with a readable reason; it never raises anything else.

Self-check:  python -m backend.ingestion.bulk_subjects
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from xml.etree import ElementTree as ET

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Bounds. A bulk upload is officer-supplied but still untrusted input, so the FILE is
# capped; the number of rows inside it is not. Subjects are only ever created after the
# preview endpoint has reported the exact count back for confirmation.
MAX_SEEDS_PER_SUBJECT = 25
MAX_FILE_BYTES = 5 * 1024 * 1024

# Field label -> seed type. Keys are normalized (lowercase, alphanumerics only), so
# "Phone Number", "phone_number" and "PHONE NUMBER" all collapse to "phonenumber".
# The wordier entries are the literal section headings a Khoj OSINT report prints.
_SEED_FIELDS = {
    "name": "name", "fullname": "name", "subjectname": "name", "suspect": "name",
    "suspectname": "name", "person": "name", "accountholder": "name",
    "username": "username", "usernames": "username", "alias": "username",
    "aliases": "username", "handle": "username", "handles": "username",
    "nickname": "username", "nick": "username", "screenname": "username",
    "user": "username", "profilename": "username",
    "email": "email", "emails": "email", "emailaddress": "email",
    "emailaddresses": "email", "emailid": "email", "mail": "email",
    "phone": "phone", "phones": "phone", "phonenumber": "phone", "mobile": "phone",
    "mobilenumber": "phone", "contact": "phone", "contactnumber": "phone",
    "number": "phone", "msisdn": "phone", "cellphone": "phone",
    "upi": "upi", "upis": "upi", "vpa": "upi", "upiid": "upi", "upivpa": "upi",
    "upivpaaccounts": "upi", "upiaccounts": "upi",
    # Profile URLs. ONE column may hold several links (an officer pastes the Facebook,
    # Instagram, YouTube and X profiles into a single cell) — see _values(), which splits
    # URL fields on whitespace as well as , ; | so that just works. Per-platform columns
    # are accepted too, for sheets that prefer one link per column; both land as `url`
    # seeds and are searched identically.
    "url": "url", "urls": "url", "link": "url", "links": "url", "profile": "url",
    "profileurl": "url", "profileurls": "url", "profilelink": "url", "profilelinks": "url",
    "socialprofile": "url", "socialprofiles": "url", "socialmedia": "url",
    "socialmediaurls": "url", "socialmedialinks": "url", "website": "url",
    "facebookprofileurl": "url", "facebook": "url", "facebookurl": "url", "fb": "url",
    "fburl": "url", "instagram": "url", "instagramurl": "url", "insta": "url",
    "instaurl": "url", "youtube": "url", "youtubeurl": "url", "yt": "url", "yturl": "url",
    "x": "url", "xurl": "url", "twitter": "url", "twitterurl": "url",
    "linkedin": "url", "linkedinurl": "url", "telegram": "url", "telegramurl": "url",
    "tiktok": "url", "tiktokurl": "url", "snapchat": "url", "reddit": "url",
    "github": "url", "githuburl": "url", "otherprofiles": "url", "otherurls": "url",
    "face": "face", "faceurl": "face", "photo": "face", "photourl": "face",
    "image": "face", "imageurl": "face", "picture": "face", "avatar": "face",
}

# Field label -> case attribute (not a seed — these configure the case itself).
_META_FIELDS = {
    "case": "title", "casetitle": "title", "title": "title", "casename": "title",
    "reference": "title", "refno": "title", "referencenumber": "title",
    "context": "case_context", "casecontext": "case_context", "casetype": "case_context",
    "notes": "case_context", "note": "case_context", "remarks": "case_context",
    "description": "case_context", "details": "case_context", "offence": "case_context",
    "region": "country_filter", "country": "country_filter",
    "countryfilter": "country_filter", "jurisdiction": "country_filter",
}

# Values that mean "this cell is empty", not a real identifier.
_PLACEHOLDERS = {"", "-", "--", "---", "n/a", "na", "nil", "none", "null", "unknown", "nan"}

_SEPARATOR_RE = re.compile(r"^\s*(?:[-=_*~]{3,}|#{3,})\s*$")
_SUBJECT_MARKER_RE = re.compile(r"^\s*subject\b[\s:#0-9]*$", re.IGNORECASE)
# Multi-value split: one field may carry several identifiers ("8121569830@ybl; …@axl").
_VALUE_SPLIT_RE = re.compile(r"[,;|\n\r]+")


def _key(label: str) -> str:
    """Normalize a field label to its lookup key: lowercase alphanumerics only."""
    return re.sub(r"[^a-z0-9]", "", str(label or "").lower())


def _para_text(node) -> str:
    """Visible text of one <w:p>, with breaks/tabs treated as spaces."""
    parts: list[str] = []
    for el in node.iter():
        if el.tag == _W + "t":
            parts.append(el.text or "")
        elif el.tag in (_W + "br", _W + "cr", _W + "tab"):
            parts.append(" ")
    return " ".join("".join(parts).split())


def _cell_text(tc) -> str:
    return " ".join(t for t in (_para_text(p) for p in tc.findall(_W + "p")) if t).strip()


def _blocks(data: bytes) -> list[tuple]:
    """Document body in reading order as ("p", text) and ("table", [[cell, …], …])."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml")
    except KeyError:
        raise ValueError("Not a Word document (no word/document.xml inside).")
    except zipfile.BadZipFile:
        raise ValueError("File is not a readable .docx (expected a Word .docx, not .doc or .pdf).")
    try:
        body = ET.fromstring(xml).find(_W + "body")
    except ET.ParseError as e:
        raise ValueError(f"Word document XML is corrupt: {e}")
    if body is None:
        raise ValueError("Word document has no body.")

    out: list[tuple] = []

    def walk(parent) -> None:
        """Emit paragraphs and tables in reading order.

        Word does not always put them directly under <w:body>: a document built from a
        template wraps content in <w:sdt>/<w:sdtContent> (content controls), so a flat
        pass over body's children silently reads nothing. Recurse through any other
        container, but never descend INTO an emitted <w:p>/<w:tbl> — a table's cell
        paragraphs belong to the table, and would otherwise be read twice."""
        for child in parent:
            if child.tag == _W + "p":
                out.append(("p", _para_text(child)))
            elif child.tag == _W + "tbl":
                rows = [[_cell_text(tc) for tc in tr.findall(_W + "tc")]
                        for tr in child.findall(_W + "tr")]
                if rows:
                    out.append(("table", rows))
            elif len(child):
                walk(child)

    walk(body)
    return out


def _values(raw: str, seed_type: str | None = None) -> list[str]:
    """Split one field's raw text into individual identifiers, dropping placeholders.

    Link fields split on WHITESPACE too, because several profile URLs pasted into one
    cell are usually separated by a space or a newline rather than a comma. Every other
    field must not: "Jayadeep Prasad Walthati" is one name, not three."""
    pieces = _VALUE_SPLIT_RE.split(str(raw or ""))
    if seed_type in ("url", "face"):
        pieces = [w for piece in pieces for w in piece.split()]
    out: list[str] = []
    for piece in pieces:
        v = piece.strip().strip(".")
        if v.lower() in _PLACEHOLDERS or v in out:
            continue
        out.append(v)
    return out


class _Subject:
    """Accumulates one subject's fields, then renders the create_case() arguments."""

    def __init__(self):
        self.seeds: list[dict] = []
        self.title = ""
        self.case_context = ""
        self.country_filter = "ALL"
        self._names: list[str] = []
        self._seen: set[tuple] = set()
        self.dropped = 0            # seeds discarded by the per-subject cap

    def add(self, label: str, raw: str) -> None:
        k = _key(label)
        seed_type = _SEED_FIELDS.get(k)
        if seed_type:
            for v in _values(raw, seed_type):
                if seed_type == "name":
                    self._names.append(v)
                if len(self.seeds) >= MAX_SEEDS_PER_SUBJECT:
                    self.dropped += 1
                    continue
                key = (seed_type, v.lower())
                if key in self._seen:
                    continue
                self._seen.add(key)
                self.seeds.append({"type": seed_type, "value": v})
            return
        attr = _META_FIELDS.get(k)
        if not attr:
            return
        val = str(raw or "").strip()
        if val.lower() in _PLACEHOLDERS:
            return
        if attr == "country_filter":
            up = val.upper()
            self.country_filter = "INDIA" if up.startswith("IND") else "ALL"
        elif attr == "title":
            self.title = val[:200]
        else:
            self.case_context = (self.case_context + " " + val).strip()[:500]

    @property
    def has_name(self) -> bool:
        return bool(self._names)

    def to_dict(self, index: int) -> dict:
        title = self.title or (self._names[0] if self._names else "") \
            or (self.seeds[0]["value"] if self.seeds else "") or f"Subject {index}"
        return {"title": title[:200], "seeds": self.seeds,
                "case_context": self.case_context,
                "country_filter": self.country_filter,
                "dropped_seeds": self.dropped}


def _is_header_row(cells: list[str]) -> bool:
    """A grid table's first row: >=2 columns and >=2 of them recognized field labels."""
    if len(cells) < 2:
        return False
    known = sum(1 for c in cells if _key(c) in _SEED_FIELDS or _key(c) in _META_FIELDS)
    return known >= 2


def _from_grid(rows: list[list[str]]) -> list[_Subject]:
    header, subjects = rows[0], []
    for row in rows[1:]:
        if not any(c.strip() for c in row):
            continue
        s = _Subject()
        for label, cell in zip(header, row):
            s.add(label, cell)
        if s.seeds:
            subjects.append(s)
    return subjects


def _from_lines(lines: list[str]) -> list[_Subject]:
    """Field-line layout. New subject on a blank line, a separator, a 'Subject:' marker,
    or a repeated Name — a repeated *other* label is another value for the same person."""
    subjects: list[_Subject] = []
    cur = _Subject()

    def flush():
        nonlocal cur
        if cur.seeds:
            subjects.append(cur)
        cur = _Subject()

    for line in lines:
        text = line.strip()
        if not text or _SEPARATOR_RE.match(text) or _SUBJECT_MARKER_RE.match(text):
            flush()
            continue
        label, sep, value = text.partition(":")
        if not sep:
            continue                       # prose/heading with no field — ignored
        k = _key(label)
        if k not in _SEED_FIELDS and k not in _META_FIELDS:
            continue
        if _SEED_FIELDS.get(k) == "name" and cur.has_name:
            flush()                        # second person's Name line
        cur.add(label, value)
    flush()
    return subjects


def _rows_as_lines(rows: list[list[str]]) -> list[str]:
    """A non-grid table read as field lines: first cell is the label, the rest the value."""
    out: list[str] = []
    for row in rows:
        if len(row) >= 2 and row[0].strip():
            out.append(f"{row[0]}: {' '.join(c for c in row[1:] if c.strip())}")
        elif row:
            out.append(row[0])
    return out


def _rows_to_subjects(rows: list[list[str]]) -> list[_Subject]:
    """Spreadsheet rows -> subjects. A header row makes it a grid (one subject per row);
    without one, the sheet is read as label/value pairs describing a single subject."""
    rows = [r for r in rows if any(str(c).strip() for c in r)]
    if not rows:
        return []
    if _is_header_row(rows[0]):
        return _from_grid(rows)
    return _from_lines(_rows_as_lines(rows))


def parse_csv(data: bytes) -> list[dict]:
    """A .csv subject sheet. Decoded as UTF-8 (BOM-tolerant, since Excel writes one),
    falling back to latin-1 so an oddly-encoded export is never rejected outright.
    csv.Sniffer picks up semicolon/tab exports; comma is the fallback."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel                      # single-column or unsniffable -> comma
    rows = [[(c or "").strip() for c in row] for row in csv.reader(io.StringIO(text), dialect)]
    return _finish(_rows_to_subjects(rows))


_X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_CELL_REF_RE = re.compile(r"^([A-Z]+)")


def _col_index(ref: str) -> int:
    """'A1' -> 0, 'C5' -> 2. Excel OMITS empty cells, so a row's cells must be placed by
    their column letter; appending them in order would shift every value left."""
    letters = _CELL_REF_RE.match(str(ref or "").upper())
    if not letters:
        return 0
    n = 0
    for ch in letters.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def parse_xlsx(data: bytes) -> list[dict]:
    """An .xlsx subject sheet — first worksheet only. Same ZIP-of-XML trick as .docx, so
    no openpyxl dependency: shared strings live in xl/sharedStrings.xml and cells
    reference them by index (t="s"); inline and numeric cells carry their own value."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            sheet = ("xl/worksheets/sheet1.xml" if "xl/worksheets/sheet1.xml" in names
                     else next((n for n in sorted(names)
                                if n.startswith("xl/worksheets/") and n.endswith(".xml")), None))
            if not sheet:
                raise ValueError("Workbook contains no worksheet.")
            sheet_xml = z.read(sheet)
            shared: list[str] = []
            if "xl/sharedStrings.xml" in names:
                for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(_X + "si"):
                    shared.append("".join(t.text or "" for t in si.iter(_X + "t")))
    except zipfile.BadZipFile:
        raise ValueError("File is not a readable .xlsx (expected an Excel workbook).")
    except ET.ParseError as e:
        raise ValueError(f"Workbook XML is corrupt: {e}")

    rows: list[list[str]] = []
    for row in ET.fromstring(sheet_xml).iter(_X + "row"):
        cells: dict[int, str] = {}
        for c in row.findall(_X + "c"):
            kind = c.get("t")
            if kind == "inlineStr":
                text = "".join(t.text or "" for t in c.iter(_X + "t"))
            else:
                v = c.find(_X + "v")
                text = "" if v is None else (v.text or "")
                if kind == "s":                  # index into the shared-string table
                    try:
                        text = shared[int(text)]
                    except (ValueError, IndexError):
                        text = ""
            cells[_col_index(c.get("r", ""))] = text.strip()
        rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
    return _finish(_rows_to_subjects(rows))


def parse_subjects(filename: str, data: bytes) -> list[dict]:
    """Route an uploaded subject sheet to the reader for its extension.

    This is the entrypoint the API uses; the per-format functions are exposed for tests."""
    if not data:
        raise ValueError("Uploaded file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"File is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    name = str(filename or "").lower()
    if name.endswith(".xlsx"):
        return parse_xlsx(data)
    if name.endswith(".csv"):
        return parse_csv(data)
    if name.endswith(".docx"):
        return parse_docx(data)
    raise ValueError("Upload an .xlsx, .csv or .docx subject sheet. "
                     "(.xls and .doc are the older binary formats - re-save as .xlsx/.docx.)")


def _finish(subjects: list[_Subject]) -> list[dict]:
    """Shared tail of every parser: reject an empty sheet, cap, and render."""
    if not subjects:
        raise ValueError(
            "No subjects found. Use a header row naming the fields (Name, Phone, Email, "
            "Username, UPI, Profile URLs), one subject per row - or labelled "
            "'Field: value' lines with a blank line between subjects.")
    return [s.to_dict(i + 1) for i, s in enumerate(subjects)]


def parse_docx(data: bytes) -> list[dict]:
    """A .docx of subject details -> [{title, seeds, case_context, country_filter,
    dropped_seeds}, …], one entry per subject.

    Raises ValueError (readable message) if the file is not a .docx, is too large, or
    contains no recognizable subject."""
    if not data:
        raise ValueError("Uploaded file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"File is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")

    subjects: list[_Subject] = []
    lines: list[str] = []
    for kind, payload in _blocks(data):
        if kind == "p":
            lines.append(payload)
        elif _is_header_row(payload[0]):
            subjects.extend(_from_grid(payload))
            lines.append("")               # a grid ends any open field-line subject
        else:
            lines.extend(_rows_as_lines(payload))
    subjects.extend(_from_lines(lines))
    return _finish(subjects)


# --------------------------------------------------------------------------------------
# Self-check — builds real .docx bytes in memory and asserts both layouts parse.
# --------------------------------------------------------------------------------------
def _docx(body_xml: str) -> bytes:
    """Minimal valid .docx containing body_xml."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org'
                   '/package/2006/content-types"><Default Extension="xml" ContentType='
                   '"application/xml"/></Types>')
        z.writestr("word/document.xml",
                   '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats'
                   f'.org/wordprocessingml/2006/main"><w:body>{body_xml}</w:body></w:document>')
    return buf.getvalue()


def _p(text: str) -> str:
    return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"


def _row(cells) -> str:
    return "<w:tr>" + "".join(f"<w:tc>{_p(c)}</w:tc>" for c in cells) + "</w:tr>"


def _xlsx(rows: list[list[str]], *, inline: bool = False) -> bytes:
    """Minimal but genuinely Excel-openable .xlsx from a grid of strings.

    Used by the self-check and by scripts/make_bulk_template.py. `inline` switches to
    inline strings instead of the shared-string table, so both cell encodings that real
    workbooks use are exercised."""
    def esc(t):
        return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    shared: list[str] = []
    sheet_rows = []
    for r_i, row in enumerate(rows, start=1):
        cells = []
        for c_i, val in enumerate(row):
            if not str(val).strip():
                continue                     # omit empties, exactly as Excel does
            ref = ""
            n = c_i
            while True:
                ref = chr(65 + n % 26) + ref
                n = n // 26 - 1
                if n < 0:
                    break
            if inline:
                cells.append(f'<c r="{ref}{r_i}" t="inlineStr"><is><t>{esc(val)}</t></is></c>')
            else:
                if val not in shared:
                    shared.append(val)
                cells.append(f'<c r="{ref}{r_i}" t="s"><v>{shared.index(val)}</v></c>')
        sheet_rows.append(f'<row r="{r_i}">{"".join(cells)}</row>')

    NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.'
            'openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            + ('' if inline else '<Override PartName="/xl/sharedStrings.xml" ContentType='
               '"application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>')
            + '</Types>')
        z.writestr("_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml",
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook {NS} {R}>'
            '<sheets><sheet name="Subjects" sheetId="1" r:id="rId1"/></sheets></workbook>')
        rels = ('<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
                '2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>')
        if not inline:
            rels += ('<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
                     'officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>')
        z.writestr("xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + rels + '</Relationships>')
        z.writestr("xl/worksheets/sheet1.xml",
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet {NS}>'
            f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>')
        if not inline:
            z.writestr("xl/sharedStrings.xml",
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><sst {NS} '
                f'count="{len(shared)}" uniqueCount="{len(shared)}">'
                + "".join(f"<si><t>{esc(v)}</t></si>" for v in shared) + "</sst>")
    return buf.getvalue()


def demo() -> None:
    # Layout A — field lines, two subjects split by a blank line, Khoj-style headings.
    a = parse_docx(_docx("".join([
        _p("Name: Jayadeep Prasad Walthati"),
        _p("Phone: 8121569830"),
        _p("Email Address: jayadeep92@gmail.com"),
        _p("UPI/VPA Accounts: 8121569830@ybl, 8121569830@axl"),
        _p("Alias: JAYADEEPPRASAD; jaydip cse"),
        _p("Notes: financial fraud"),
        _p(""),
        _p("Name: Asha Rao"),
        _p("Mobile Number: 9800011122"),
    ])))
    assert len(a) == 2, a
    assert a[0]["title"] == "Jayadeep Prasad Walthati"
    assert a[0]["case_context"] == "financial fraud"
    # Two UPI lines/values stay ONE subject; the second Name starts the next.
    assert {"type": "upi", "value": "8121569830@ybl"} in a[0]["seeds"]
    assert {"type": "upi", "value": "8121569830@axl"} in a[0]["seeds"]
    assert sum(1 for s in a[0]["seeds"] if s["type"] == "username") == 2
    assert a[1]["seeds"] == [{"type": "name", "value": "Asha Rao"},
                             {"type": "phone", "value": "9800011122"}]

    # Layout B — grid table with a header row.
    b = parse_docx(_docx("<w:tbl>" + _row(["Name", "Phone", "Email"])
                         + _row(["Asha Rao", "9800011122", "asha@mail.com"])
                         + _row(["Vikram S", "9800022233", "-"]) + "</w:tbl>"))
    assert len(b) == 2, b
    assert [s["type"] for s in b[1]["seeds"]] == ["name", "phone"]   # "-" dropped

    # A key-value table (no header row) is read as field lines, not as a grid.
    c = parse_docx(_docx("<w:tbl>" + _row(["Name", "Ravi K"])
                         + _row(["Username", "ravik99"]) + "</w:tbl>"))
    assert len(c) == 1 and len(c[0]["seeds"]) == 2, c

    # Bounds and failure modes.
    # No row-count cap: every subject in the file is returned. The file-size limit is
    # what bounds a bulk upload, and MAX_FILE_BYTES is enforced by parse_subjects().
    many = "".join(_p(f"Name: P{i}") for i in range(120))
    assert len(parse_docx(_docx(many))) == 120
    try:
        parse_subjects("big.csv", b"x" * (MAX_FILE_BYTES + 1))
        raise AssertionError("expected ValueError for an oversized file")
    except ValueError as e:
        assert "larger than" in str(e), e
    wide = _p("Name: Wide") + "".join(_p(f"Alias: alias{i}") for i in range(60))
    assert len(parse_docx(_docx(wide))[0]["seeds"]) == MAX_SEEDS_PER_SUBJECT
    for bad, why in ((b"not a zip", "zip"), (b"", "empty")):
        try:
            parse_docx(bad)
            raise AssertionError(f"expected ValueError for {why} input")
        except ValueError:
            pass
    try:
        parse_docx(_docx(_p("Just some prose with no fields at all.")))
        raise AssertionError("expected ValueError when no subject is found")
    except ValueError:
        pass
    # --- CSV: header row, one subject per row, several URLs in ONE cell ---------------
    csv_bytes = (
        "Name,Phone,Email,Username,UPI,Profile URLs\n"
        "Jayadeep Prasad,8121569830,jayadeep92@gmail.com,JAYADEEPPRASAD,8121569830@ybl,"
        '"https://facebook.com/100001700990021 https://instagram.com/jaydip'
        ' https://x.com/jaydip"\n'
        "Asha Rao,9800011122,,,,\n"
    ).encode()
    cs = parse_csv(csv_bytes)
    assert len(cs) == 2, cs
    urls = [x["value"] for x in cs[0]["seeds"] if x["type"] == "url"]
    assert len(urls) == 3 and all(u.startswith("https://") for u in urls), urls
    # a row with only Name+Phone is a complete subject; blank columns are simply absent
    assert [x["type"] for x in cs[1]["seeds"]] == ["name", "phone"]
    # Excel also exports semicolon-delimited CSV in many locales.
    assert len(parse_csv(b"Name;Phone\nAsha Rao;9800011122\n")) == 1
    assert parse_csv("\ufeffName,Phone\nAsha,98000\n".encode())[0]["title"] == "Asha"

    # --- XLSX: both cell encodings, and sparse rows (Excel omits empty cells) ---------
    grid = [["Name", "Phone", "Email", "Profile URLs"],
            ["Jayadeep Prasad", "8121569830", "jayadeep92@gmail.com",
             "https://facebook.com/100001700990021, https://youtube.com/@jaydip"],
            ["", "9800011122", "", ""]]
    for inline in (False, True):
        xs = parse_xlsx(_xlsx(grid, inline=inline))
        assert len(xs) == 2, (inline, xs)
        assert len([x for x in xs[0]["seeds"] if x["type"] == "url"]) == 2
        # the sparse second row must keep Phone in the Phone column, not shift left
        assert xs[1]["seeds"] == [{"type": "phone", "value": "9800011122"}], xs[1]

    # per-platform URL columns land as url seeds too
    per_platform = parse_csv(b"Name,Facebook,Instagram,X\nA B,https://fb.com/a,"
                             b"https://insta.com/a,https://x.com/a\n")
    assert len([x for x in per_platform[0]["seeds"] if x["type"] == "url"]) == 3

    # --- dispatcher routes by extension and rejects the old binary formats ------------
    assert len(parse_subjects("sheet.csv", csv_bytes)) == 2
    assert len(parse_subjects("sheet.xlsx", _xlsx(grid))) == 2
    for bad in ("sheet.xls", "sheet.doc", "sheet.pdf", "sheet"):
        try:
            parse_subjects(bad, csv_bytes)
            raise AssertionError(f"expected ValueError for {bad}")
        except ValueError:
            pass

    print("bulk_subjects self-check OK (.docx / .csv / .xlsx)")


if __name__ == "__main__":
    demo()
