"""
What an activity looks like on a card (B1, B2, B3): the library's content, adjusted so PARAKH shows it correctly.

  codes      PARAKH prints a curricular goal or competency only when the code is in its own list (the codes its
             own activities use). The school's activities for R1-R3, PE, Skill, Other learning and Bagless days
             carry NCF codes PARAKH has no list for, so the card showed empty boxes. Their codes are written as
             a line at the top of the activity text ("Curricular Goal: ... | Competency: ..."), which PARAKH prints.
  approach   (Middle, the school's own activities) "Any Other" holding only the codes is not an approach: removed. Art Education is
             Art-Integrated and Physical Education is Sports-Integrated by definition; a real "Any Other" text
             ("Inquiry Based") stays. When nothing else is left, "Any Other" stays with a real approach written in
             ("Activity-Based Learning") instead of the codes: PARAKH counts an activity without an approach as
             unfinished, and these activities are finished in every other way.
"""
import copy
import re
from typing import Any, Dict, Iterable, List, Optional

CODES_LINE = "Curricular Goal: {goals} | Competency: {competencies}"
ACTIVITY_LIMIT = 4000                                   # PARAKH's activity text limit (field_limits b.activity)
BY_SUBJECT = {"SAE": 1, "SPE": 2}                       # Middle: Art-Integrated, Sports-Integrated
ANY_OTHER = 5
FALLBACK_APPROACH = "Activity-Based Learning"           # Any Other's text when the codes were all it had
_CODE_WORD = re.compile(r"^(?=[A-Z0-9 .\-]*\d)[A-Z0-9][A-Z0-9 .\-]{0,14}$")   # "R1CG 2", "C-2.2", "SSC -1.2"


def codes_only(text: str) -> bool:
    """True when an "Any Other" text is just curricular codes ("R3CG 1 , R3C-1.1", "MCG 2, C-2.2")."""
    parts = [p.strip() for p in re.split(r"[,;/]", str(text or "")) if p.strip()]
    return bool(parts) and all(_CODE_WORD.match(p) for p in parts)


def unknown_codes(content: Dict[str, Any], known: Optional[Iterable[str]]) -> List[str]:
    """The activity's goal/competency codes PARAKH's list does not have (all of them when known is None)."""
    known = set(known or ())
    return [c for c in [*(content.get("gl") or []), *(content.get("cpt") or [])] if str(c) not in known]


def for_card(stage: str, content: Dict[str, Any], subjects: List[str], known: Optional[Iterable[str]],
             school_made: bool = True) -> Dict[str, Any]:
    """A copy of the library content as it goes on a card (see the module notes). `known`: PARAKH's codes.
    school_made False (PARAKH's own bank activities): the approach stays as NCERT wrote it - its codes are in
    PARAKH's list and ticked, and taking the approach away would leave the activity unfinishable."""
    out = copy.deepcopy(content or {})
    goals, comps = list(out.get("gl") or []), list(out.get("cpt") or [])
    desc = (list(out.get("desc") or []) + ["", ""])[:2]
    if (goals or comps) and unknown_codes(out, known) and not str(desc[0]).startswith("Curricular Goal:"):
        line = CODES_LINE.format(goals=", ".join(goals) or "-", competencies=", ".join(comps) or "-")
        if len(line) + 1 + len(str(desc[0])) <= ACTIVITY_LIMIT:
            desc[0] = f"{line}\n{desc[0]}" if desc[0] else line
        out["desc"] = desc
    if stage.lower().startswith("mid") and school_made:
        approaches = [int(a) for a in out.get("approaches") or [] if str(a).isdigit() and int(a) > 0]
        other = str(out.get("any-other") or "").strip()
        removed = ANY_OTHER in approaches and (not other or codes_only(other))
        if removed:
            approaches = [a for a in approaches if a != ANY_OTHER]
            other = ""
        for s in subjects or []:
            if s in BY_SUBJECT and BY_SUBJECT[s] not in approaches:
                approaches.append(BY_SUBJECT[s])
        if not approaches and removed:
            approaches, other = [ANY_OTHER], FALLBACK_APPROACH
        out["approaches"], out["any-other"] = sorted(approaches), other
    return out


def card_problems(stage: str, caption: str, content: Dict[str, Any]) -> List[str]:
    """What an activity still lacks on a card: goal, competency (B1) and, for Middle, an approach (B3)."""
    out = []
    if not content.get("gl"):
        out.append(f"'{caption}' has no curricular goal - add it in the Activity Library")
    if not content.get("cpt"):
        out.append(f"'{caption}' has no competency - add it in the Activity Library")
    if stage.lower().startswith("mid") and not content.get("approaches"):
        out.append(f"'{caption}' has no approach (Art-Integrated, Sports-Integrated, Toy-Based, Technology-Integrated or "
                   "Any Other with its name) - set it in the Activity Library; PARAKH needs one to count it finished")
    return out
