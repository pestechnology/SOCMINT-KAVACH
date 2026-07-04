"""Multilingual normalization: script detection, transliteration, phonetic convergence.

The load-bearing test is the convergence case: the same person written in Kannada, as a bare
Latin name, and as two handle variants must collapse to ONE phonetic key — while genuinely
different names must not. All deterministic (no LLM).
"""
from backend.normalization.script_detect import detect_script
from backend.normalization.transliterate import to_latin
from backend.normalization.phonetic import phonetic_key
from backend.normalization.normalize import normalize_identity


# ---------- script detection ----------
def test_detect_pure_scripts():
    assert detect_script("ರಾಜೇಶ್") == "kannada"
    assert detect_script("ராஜேஷ்") == "tamil"
    assert detect_script("రాజేష్") == "telugu"
    assert detect_script("രാജേഷ്") == "malayalam"
    assert detect_script("Rajesh") == "latin"


def test_detect_mixed_and_empty():
    assert detect_script("Rajesh ರಾಜೇಶ್") == "mixed"          # Latin + Indic
    assert detect_script("ರಾಜೇಶ್ ராஜேஷ்") == "mixed"          # two Indic scripts
    assert detect_script("") == "unknown"
    assert detect_script("   ") == "unknown"
    assert detect_script("12345 !!!") == "unknown"


# ---------- transliteration ----------
def test_translit_roundtrip_each_script():
    # each of the four scripts should transliterate to a Latin string containing 'r' and 's'
    for txt, sc in [("ರಾಜೇಶ್", "kannada"), ("ராஜேஷ்", "tamil"),
                    ("రాజేష్", "telugu"), ("രാജേഷ്", "malayalam")]:
        latin = to_latin(txt, sc)
        assert latin and latin != txt, (txt, latin)
    assert to_latin("Rajesh", "latin") == "Rajesh"       # latin unchanged


# ---------- the convergence case (the whole point) ----------
def test_convergence_same_person_one_key():
    keys = {
        phonetic_key("Rajesh"),
        phonetic_key("raajesh_official"),
        phonetic_key("rajeshanna"),
        phonetic_key(to_latin("ರಾಜೇಶ್", "kannada")),
    }
    assert len(keys) == 1, f"expected one shared key, got {keys}"


def test_negative_different_names_do_not_collapse():
    assert phonetic_key("Rajesh") != phonetic_key("Suresh")
    assert phonetic_key("Priya") != phonetic_key("Rajesh")
    assert phonetic_key("Ananya") != phonetic_key("Vikram")


# ---------- determinism ----------
def test_determinism():
    for s in ["Rajesh", "ರಾಜೇಶ್", "raajesh_official", "Rajesh ರಾಜೇಶ್"]:
        a = normalize_identity(s)
        b = normalize_identity(s)
        assert (a.original, a.script, a.translit, a.phonetic_key) == \
               (b.original, b.script, b.translit, b.phonetic_key)


def test_original_is_preserved_verbatim():
    ni = normalize_identity("ರಾಜೇಶ್")
    assert ni.original == "ರಾಜೇಶ್"          # evidence never altered
    assert ni.phonetic_key                    # aid produced alongside


# ---------- correlation integration: reinforces, never links alone ----------
def _score(profiles):
    from backend.normalization.normalize import annotate_profiles
    from backend.correlation.correlation_engine import correlate
    from backend.scoring.scoring_engine import score
    annotate_profiles(profiles)
    return score(profiles, correlate(profiles))


def test_phonetic_reinforces_a_pair_that_shares_another_signal():
    from backend.ingestion.base_module import make_profile
    # cross-script name (Latin vs Kannada) + a shared phone. The phonetic key supplies the
    # 2nd signal that lets the pair link (phone alone can't — LINK_MIN_SIGNALS>=2).
    a = make_profile("social_account", "acct_one", "instagram", "ua", {"name": "Rajesh", "phone": "+15551230000"})
    b = make_profile("social_account", "acct_two", "twitter", "ub", {"name": "ರಾಜೇಶ್", "phone": "+15551230000"})
    clusters = _score([a, b])
    assert a.metadata["phonetic_key"] == b.metadata["phonetic_key"]     # matched across scripts
    linked = [c for c in clusters if len(c.member_indices) >= 2]
    assert linked, "phone + phonetic should link"
    assert "phonetic_name_match" in linked[0].signals


def test_phonetic_alone_never_forms_a_cluster():
    from backend.ingestion.base_module import make_profile
    # ONLY shared thing is the phonetic key (names differ by script, handles differ). Must
    # NOT cluster — a phonetic match can never be sufficient on its own.
    a = make_profile("social_account", "acct_one", "instagram", "ua", {"name": "Rajesh"})
    b = make_profile("social_account", "acct_two", "twitter", "ub", {"name": "ರಾಜೇಶ್"})
    clusters = _score([a, b])
    assert a.metadata["phonetic_key"] == b.metadata["phonetic_key"]
    assert not [c for c in clusters if len(c.member_indices) >= 2], "phonetic alone must not link"
