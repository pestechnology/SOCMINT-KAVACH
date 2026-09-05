"""Bulk subject-sheet intake (.xlsx / .csv / .docx) — parser edge cases plus the two
HTTP endpoints.

The parsers' own invariants are asserted by the module self-check (`python -m
backend.ingestion.bulk_subjects`); this file covers the HTTP surface: auth, rejection of
unsupported formats, preview creating nothing, and one case per subject on create.
"""
import uuid

from backend.ingestion.bulk_subjects import (
    _docx, _p, _row, _xlsx, parse_csv, parse_docx, parse_subjects, parse_xlsx,
)

# One Khoj-shaped subject block + a second subject after a blank line.
TWO_SUBJECTS = _docx("".join([
    _p("Name: Jayadeep Prasad Walthati"),
    _p("Phone: 8121569830"),
    _p("Email Address: jayadeep92@gmail.com"),
    _p("UPI/VPA Accounts: 8121569830@ybl, 8121569830@axl"),
    _p("Alias: JAYADEEPPRASAD; jaydip cse"),
    _p("Notes: financial fraud"),
    _p(""),
    _p("Name: Asha Rao"),
    _p("Mobile Number: 9800011122"),
]))


def _auth(client):
    u = "bulk_" + uuid.uuid4().hex[:8]
    tok = client.post("/auth/register",
                      json={"username": u, "password": "secret123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _upload(data=TWO_SUBJECTS, name="subjects.docx"):
    return {"file": (name, data,
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}


# ---- parser ----------------------------------------------------------------------
def test_repeated_non_name_field_is_one_subject_not_two():
    """The Khoj report gives one man nine aliases and two UPI IDs. Repeated values must
    stay ONE subject; only a repeated Name starts the next."""
    subjects = parse_docx(TWO_SUBJECTS)
    assert len(subjects) == 2
    upis = [s["value"] for s in subjects[0]["seeds"] if s["type"] == "upi"]
    assert upis == ["8121569830@ybl", "8121569830@axl"]


def test_grid_table_one_subject_per_row():
    doc = _docx("<w:tbl>" + _row(["Name", "Phone", "Email"])
                + _row(["Asha Rao", "9800011122", "asha@example.com"])
                + _row(["Vikram S", "9800022233", "-"]) + "</w:tbl>")
    subjects = parse_docx(doc)
    assert [s["title"] for s in subjects] == ["Asha Rao", "Vikram S"]
    # the "-" placeholder is dropped, never searched
    assert [s["type"] for s in subjects[1]["seeds"]] == ["name", "phone"]


def test_every_field_works_alone_no_field_is_required():
    """No field is mandatory — any single identifier is a runnable subject on its own,
    and the case title falls back to that identifier when there is no Name."""
    for label, value, seed_type in [
        ("Name", "Jayadeep Prasad", "name"),
        ("Phone", "8121569830", "phone"),
        ("Email", "jayadeep92@gmail.com", "email"),
        ("Username", "jaydipcse", "username"),
        ("UPI", "8121569830@ybl", "upi"),
        ("Profile URL", "https://facebook.com/100001700990021", "url"),
        ("Photo URL", "https://example.com/face.jpg", "face"),
    ]:
        subjects = parse_docx(_docx(_p(f"{label}: {value}")))
        assert len(subjects) == 1, label
        assert subjects[0]["seeds"] == [{"type": seed_type, "value": value}], label
        assert subjects[0]["title"] == value, label   # title falls back to the identifier


def test_subjects_need_no_name_to_be_separated():
    """Blank lines separate subjects even when not one of them has a Name field."""
    doc = _docx(_p("Phone: 8121569830") + _p("")
                + _p("Email: asha@example.com") + _p("")
                + _p("UPI: vikram@okaxis"))
    subjects = parse_docx(doc)
    assert [s["seeds"][0]["type"] for s in subjects] == ["phone", "email", "upi"]


def test_sparse_grid_rows_each_become_their_own_subject():
    """A table row populating only one column is still its own subject; a fully empty
    row is skipped rather than becoming an empty case."""
    doc = _docx("<w:tbl>" + _row(["Name", "Phone", "Email"])
                + _row(["", "8121569830", ""])
                + _row(["", "", "asha@example.com"])
                + _row(["", "", ""]) + "</w:tbl>")
    subjects = parse_docx(doc)
    assert [s["seeds"][0]["type"] for s in subjects] == ["phone", "email"]


def test_subject_with_no_identifier_is_rejected_not_created():
    """Metadata alone cannot be investigated — a case with zero seeds is never created."""
    try:
        parse_docx(_docx(_p("Case: Operation X") + _p("Notes: fraud")))
        raise AssertionError("expected ValueError for a subject with no identifier")
    except ValueError:
        pass


def test_realistic_word_xml_split_runs_and_content_controls():
    """A real Word file is not as tidy as a hand-built fixture: it splits one sentence
    across several <w:r> runs (spell-check, formatting), wraps template content in
    <w:sdt>/<w:sdtContent>, and puts <w:tblPr>/<w:trPr>/<w:tcPr> property elements in
    among the rows and cells. All of it must still parse."""
    split_para = ("<w:p><w:proofErr w:type=\"spellStart\"/>"
                  "<w:r><w:t>Name</w:t></w:r><w:r><w:t>: Jaya</w:t></w:r>"
                  "<w:r><w:t>deep</w:t></w:r><w:r><w:t> Prasad</w:t></w:r></w:p>")
    tbl = ("<w:tbl><w:tblPr><w:tblW w:w=\"0\"/></w:tblPr><w:tblGrid><w:gridCol/></w:tblGrid>"
           "<w:tr><w:trPr/><w:tc><w:tcPr/>" + _p("Phone") + "</w:tc>"
           "<w:tc><w:tcPr/>" + _p("8121569830") + "</w:tc></w:tr></w:tbl>")
    doc = _docx("<w:sdt><w:sdtPr/><w:sdtContent>" + split_para + tbl + "</w:sdtContent></w:sdt>")
    subjects = parse_docx(doc)
    assert len(subjects) == 1, subjects
    assert subjects[0]["title"] == "Jayadeep Prasad"
    assert {"type": "phone", "value": "8121569830"} in subjects[0]["seeds"]


def test_unlabelled_prose_is_ignored_not_searched():
    doc = _docx(_p("OSINT is the compass that guides us.") + _p("Name: Ravi K"))
    subjects = parse_docx(doc)
    assert len(subjects) == 1 and subjects[0]["seeds"] == [{"type": "name", "value": "Ravi K"}]


# ---- HTTP ------------------------------------------------------------------------
CSV_SHEET = (
    "Name,Phone,Email,Username,UPI,Profile URLs\n"
    "Jayadeep Prasad Walthati,8121569830,jayadeep92@gmail.com,JAYADEEPPRASAD,8121569830@ybl,"
    '"https://facebook.com/100001700990021 https://instagram.com/jaydip"\n'
    "Asha Rao,9800011122,,,,\n"
).encode()

XLSX_SHEET = _xlsx([
    ["Name", "Phone", "Email", "Profile URLs"],
    ["Jayadeep Prasad Walthati", "8121569830", "jayadeep92@gmail.com",
     "https://facebook.com/100001700990021, https://x.com/jaydip"],
    ["Asha Rao", "9800011122", "", ""],
])


def test_several_profile_urls_in_one_cell_become_separate_url_seeds():
    """An officer pastes the Facebook, Instagram, YouTube and X links into ONE cell —
    space- or comma-separated — and each must become its own searchable url seed."""
    for sheet, name in ((CSV_SHEET, "s.csv"), (XLSX_SHEET, "s.xlsx")):
        subjects = parse_subjects(name, sheet)
        urls = [x["value"] for x in subjects[0]["seeds"] if x["type"] == "url"]
        assert len(urls) == 2, (name, urls)
        assert all(u.startswith("https://") for u in urls), (name, urls)


def test_name_is_never_split_on_whitespace():
    """The URL whitespace-split must not leak into other fields — a three-word name is
    one name, not three seeds."""
    subjects = parse_csv(b"Name,Phone\nJayadeep Prasad Walthati,8121569830\n")
    names = [x["value"] for x in subjects[0]["seeds"] if x["type"] == "name"]
    assert names == ["Jayadeep Prasad Walthati"]


def test_xlsx_sparse_row_keeps_column_alignment():
    """Excel omits empty cells entirely, so cells must be placed by column letter — a row
    with only the 3rd column filled must not shift that value into column 1."""
    sheet = _xlsx([["Name", "Phone", "Email"], ["", "", "asha@example.com"]])
    subjects = parse_xlsx(sheet)
    assert subjects[0]["seeds"] == [{"type": "email", "value": "asha@example.com"}]


def test_semicolon_and_bom_csv_exports_are_read():
    """Excel writes semicolon-delimited CSV in many locales and prefixes a UTF-8 BOM."""
    assert len(parse_csv(b"Name;Phone\nAsha Rao;9800011122\n")) == 1
    assert parse_csv("\ufeffName,Phone\nAsha Rao,9800011122\n".encode())[0]["title"] == "Asha Rao"


def test_shipped_templates_parse():
    """The templates handed to officers must survive their own parser."""
    import pathlib
    public = pathlib.Path("frontend/public")
    for name in ("bulk_template.xlsx", "bulk_template.csv"):
        path = public / name
        assert path.exists(), f"{path} missing - run: python -m scripts.make_bulk_template"
        subjects = parse_subjects(name, path.read_bytes())
        assert len(subjects) == 2, name
        # the example row with only a phone and no name is still a valid subject
        assert subjects[1]["seeds"] == [{"type": "phone", "value": "9800011122"}], name
        # the removed Minor column must not come back
        assert "minor_involved" not in subjects[0], name


def test_no_row_cap_file_size_is_the_limit():
    """There is no arbitrary subject cap — a 90-row sheet yields 90 subjects. The bound
    is the file size, and the preview reports the count for confirmation."""
    rows = "Name,Phone\n" + "".join(f"Person {i},98000000{i:02d}\n" for i in range(90))
    subjects = parse_csv(rows.encode())
    assert len(subjects) == 90, len(subjects)
    assert subjects[-1]["title"] == "Person 89"


def test_oversized_file_rejected_by_size_not_row_count(client):
    from backend.ingestion.bulk_subjects import MAX_FILE_BYTES
    h = _auth(client)
    big = b"Name,Phone\n" + b"x" * (MAX_FILE_BYTES + 1)
    r = client.post("/cases/bulk/preview", files=_upload(big, "big.csv"), headers=h)
    assert r.status_code == 400
    assert "larger than" in r.json()["detail"].lower()


def test_bulk_requires_auth(client):
    assert client.post("/cases/bulk", files=_upload()).status_code == 401
    assert client.post("/cases/bulk/preview", files=_upload()).status_code == 401


def test_preview_parses_but_creates_nothing(client):
    h = _auth(client)
    before = len(client.get("/cases", headers=h).json()["cases"])
    r = client.post("/cases/bulk/preview", files=_upload(), headers=h)
    assert r.status_code == 200
    body = r.json()
    assert [s["title"] for s in body["subjects"]] == ["Jayadeep Prasad Walthati", "Asha Rao"]
    assert body["total_seeds"] == sum(len(s["seeds"]) for s in body["subjects"])
    assert len(client.get("/cases", headers=h).json()["cases"]) == before


def test_bulk_creates_one_case_per_subject(client):
    h = _auth(client)
    r = client.post("/cases/bulk", files=_upload(), headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 2 and body["skipped_subjects"] == 0
    titles = {c["title"] for c in body["cases"]}
    assert titles == {"Jayadeep Prasad Walthati", "Asha Rao"}
    # Identifiers must NOT be merged across subjects — that would fabricate clusters.
    by_title = {c["title"]: c["seeds"] for c in body["cases"]}
    assert not any(s["value"] == "9800011122" for s in by_title["Jayadeep Prasad Walthati"])
    # each case really exists, owned by this user, and carries the parsed context
    mine = {c["case_id"]: c for c in client.get("/cases", headers=h).json()["cases"]}
    for c in body["cases"]:
        assert c["case_id"] in mine
    assert mine[by_case_id(body, "Jayadeep Prasad Walthati")]["case_context"] == "financial fraud"


def by_case_id(body, title):
    return next(c["case_id"] for c in body["cases"] if c["title"] == title)


def test_unsupported_format_rejected(client):
    h = _auth(client)
    for data, name in ((b"%PDF-1.4", "report.pdf"), (b"\xd0\xcf", "old.xls"),
                       (b"x", "old.doc"), (b"x", "noextension")):
        r = client.post("/cases/bulk", files=_upload(data, name), headers=h)
        assert r.status_code == 400, name
        assert "xlsx" in r.json()["detail"].lower(), name
    # right extension, wrong bytes — still a clean 400, never a 500
    for name in ("x.docx", "x.xlsx"):
        assert client.post("/cases/bulk", files=_upload(b"not a zip", name),
                           headers=h).status_code == 400


def test_bulk_accepts_csv_and_xlsx_end_to_end(client):
    h = _auth(client)
    for sheet, name in ((CSV_SHEET, "subjects.csv"), (XLSX_SHEET, "subjects.xlsx")):
        r = client.post("/cases/bulk", files=_upload(sheet, name), headers=h)
        assert r.status_code == 200, (name, r.text)
        body = r.json()
        assert body["created"] == 2, name
        assert {c["title"] for c in body["cases"]} == {"Jayadeep Prasad Walthati", "Asha Rao"}
        # identifiers must not cross rows
        rows = {c["title"]: [s["value"] for s in c["seeds"]] for c in body["cases"]}
        assert "9800011122" not in rows["Jayadeep Prasad Walthati"], name


def test_docx_with_no_subjects_rejected(client):
    h = _auth(client)
    doc = _docx(_p("This document has no labelled fields whatsoever."))
    r = client.post("/cases/bulk", files=_upload(doc), headers=h)
    assert r.status_code == 400 and "No subjects found" in r.json()["detail"]
