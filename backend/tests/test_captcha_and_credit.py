"""Captcha solving and credit calculation against real portal samples."""
import json

from backend.hpc import captcha, credit
from backend.tests.conftest import FIXTURES


def test_captcha_samples_solve_to_portal_verified_answers():
    answers = json.loads((FIXTURES / "captcha" / "answers.json").read_text())
    for name, expected in answers.items():
        image = (FIXTURES / "captcha" / name).read_bytes()
        import base64
        answer, expr = captcha.solve_base64(base64.b64encode(image).decode())
        assert (answer, expr) == (expected["answer"], expected["expression"]), name


def test_credit_tables_match_what_the_portal_stored(credit_cases):
    for case in credit_cases:
        domains = list(case["part_c_ratings"])
        domains.remove("overall")
        got = credit.build_tables(case["stage"], case["part_c_ratings"], domains, case["marks"], case["grade_code"])
        assert json.dumps(got["table2"]) == json.dumps(case["table2"]), case["stage"]
        assert json.dumps(got["table3"]) == json.dumps(case["table3"]), case["stage"]


def test_js_rounding_and_number_strings():
    assert credit._round2(0.125) == 0.13          # JS toFixed rounds halves up
    assert credit._js_round(2.5) == 3              # Math.round
    assert credit.js_str(198.0) == "198" and credit.js_str(15.84) == "15.84"
