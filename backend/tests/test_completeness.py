"""Section 6.2: the completeness report per student and section (offline, from a stored card)."""
from backend.hpc import completeness, suggestions
from backend.hpc.stages import get_stage
from backend.tests.conftest import blank_student


def test_report_lists_empty_defaulted_duplicated_and_inconsistent_and_apaar_is_optional():
    data = blank_student("PREPARATORY")
    st = get_stage("PREPARATORY")
    c = st.PARTS[[p.code for p in st.PARTS].index("C")]
    part_c = c.load(None)
    for d in st.DOMAINS:
        part_c[d] = ["1", "1", "1", "Shows good understanding of the concepts taught."]
    stock = suggestions.SUGGESTIONS["b_observation"][0]
    acts = [{"nm": f"Act {i}", "dt": {"domain": [d], "gl": ["G"], "cpt": ["C"], "tfob": stock, "lp": ["", ""]}}
            for i, d in enumerate(st.DOMAINS[:3])]
    raw = {**data.raw_parts, "part_c": part_c, "part_b": acts}
    rep = completeness.report("PREPARATORY", raw, data.record)
    assert "APAAR ID" in rep["optional_blank"] or "UDID" in rep["optional_blank"]
    sec = rep["sections"]
    assert any("Observational notes" in x for x in sec["B1 Act 0"]["defaulted"])
    assert any("Challenges" in x for x in sec["B1 Act 0"]["empty"])
    assert any("same in 3 activities" in x for x in sec["B"]["duplicated"])
    assert any("same note is under 7 subjects" in x for x in sec["C"]["duplicated"])
    assert any("praises" in x for x in sec["C"]["inconsistent"])
    assert not any("APAAR" in x or "UDID" in x for s in sec.values() for k in s.values() for x in k)
    assert "Asked" not in completeness.as_text(rep) and rep["student"] is not None
