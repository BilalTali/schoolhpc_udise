"""What a cell may contain before anything is sent to PARAKH (H-4, H-7, M-1). Made-up values only."""
import pytest

from backend.hpc import sync
from backend.hpc.stages import get_stage
from backend.tests.conftest import blank_student, filled_row, make_lookups


def _field(stage, part, key):
    lk = make_lookups(stage.upper())
    return next(f for f in next(p for p in get_stage(stage).PARTS if p.code == part).fields(lk) if f.key == key)


# H-4: answers PARAKH stores as positions (0, 1, 2) never take a typed number as that position
@pytest.mark.parametrize("key,part", [("b_sa_liked", "B"), ("b_sa_easy", "B"), ("b_pa_liked", "B"), ("c_FSDOM1_awr", "C")])
@pytest.mark.parametrize("typed", ["0", "1", "2", "1.0"])
def test_a_number_is_not_taken_as_a_position_answer(key, part, typed):
    value, error = _field("Foundational", part, key).parse(typed)
    assert error and "not a number" in error


def test_position_answers_still_take_their_words_and_short_forms():
    liked = _field("Foundational", "B", "b_sa_liked")
    assert liked.parse("Yes") == (0, None) and liked.parse("n") == (1, None) and liked.parse("don") == (2, None)
    level = _field("Foundational", "C", "c_FSDOM1_awr")
    assert level.parse("Proficient") == (1, None) and level.parse("beg") == (2, None)
    needed = _field("Foundational", "B", "b_sa_needed")
    assert needed.parse("Teachers, Books") == ([1, 2], None)
    assert "not a number" in needed.parse("1")[1]


def test_choices_stored_as_codes_still_take_the_code():
    # Preparatory "How I feel" stores "1".."4"; the code is a real answer there, not a position
    feel = _field("Preparatory", "A3", "a3_feel_1")
    assert feel.parse("1") == ("1", None) and feel.parse("Yes") == ("1", None)


def test_the_upload_preview_says_it_in_plain_words():
    row = {**filled_row("FOUNDATIONAL"), "b_sa_liked": "1"}
    _, errors = sync.build_payloads("Foundational", blank_student("FOUNDATIONAL"), row, make_lookups("FOUNDATIONAL"))
    assert any("I liked doing this work" in e and "type the answer" in e for e in errors)
