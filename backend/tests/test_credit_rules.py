"""HPC Credit (C2): every row and the Total row follow PARAKH's rule (credit.verify_tables), Bagless days, and
Vocational/Skill Education's key mismatch on PARAKH (the app follows PARAKH unless SKILL_KEY_FIX)."""
import itertools

from backend.hpc import credit
from backend.hpc.stages import middle, preparatory


def _middle(levels, marks=None):
    part_c = {d: [*levels, ""] for d in middle.DOMAINS}
    marks = marks or [["100", "80"] for _ in middle.DOMAINS]
    return credit.build_tables("middle", part_c, middle.DOMAINS, marks, "grd6")


def test_c2_every_row_and_total_adds_up():
    for combo in itertools.product(["1", "2", "3"], repeat=3):
        assert credit.verify_tables("middle", _middle(combo), "grd6") == []
    prep = credit.build_tables("preparatory", {d: ["2", "1", "3", ""] for d in preparatory.DOMAINS},
                               preparatory.DOMAINS, [["50", "40"] for _ in preparatory.DOMAINS], "grd3")
    assert credit.verify_tables("preparatory", prep, "grd3") == []


def test_c2_a_wrong_total_is_caught():
    tables = _middle(("3", "3", "3"))
    tables["table3"][-1][3] = "1"
    assert any("Total total credit" in p for p in credit.verify_tables("middle", tables, "grd6"))


def test_c2_bagless_days_beginner_proficient_beginner_is_2_36_credits_and_44_marks():
    row = next(r for r in _middle(("1", "2", "1"))["table3"] if r[0].startswith("Bagless"))
    assert row[1:] == [2.36, 0, 2.36, 3.14, 44]


def test_c2_skill_education_earns_0_as_on_parakh_unless_the_key_fix_is_on(monkeypatch):
    skill = lambda t: next(r for r in t["table3"] if r[0] == "Vocational/Skill Education")
    assert skill(_middle(("3", "3", "3")))[1:] == [0, 0, 0, 0, 0]           # PARAKH's own page: 0 (its key mismatch)
    monkeypatch.setattr(credit, "SKILL_KEY_FIX", True)
    fixed = _middle(("3", "3", "3"))
    assert skill(fixed)[1:] == [2.58, 0.88, 3.46, 4.6, 94]                    # 0.86 x 3; 80% of 1.1; x 1.33; /3.67
    assert credit.verify_tables("middle", fixed, "grd6") == []


