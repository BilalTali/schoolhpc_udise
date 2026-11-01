"""
Part C notes written from the student's own levels (C1, C3).

PARAKH's Part C asks, for each subject (Foundational: each domain), for an observational note that names a strength
and an area to improve in terms of Awareness, Sensitivity and Creativity. The note is built only from that subject's
three ticked levels (and, when the subject's Part B activity is known, its name as evidence):

  strength      the ability with the highest level (ties: Awareness, then Sensitivity, then Creativity)
  to improve    the ability with the lowest level, another ability than the strength
                (all three the same: Creativity, then Sensitivity - the strength stays Awareness)

The words per ability are the subject's own (SUBJECT_WORDS), so no two subjects of a student get the same note and
no subject gets words that do not belong to it (no "written work" for Art, PE, Skill or Bagless days). Without all
three levels there is no note: "" (the caller leaves the field blank and reports it). Nothing else about the student
is assumed.
"""
from typing import Dict, Iterable, List, Optional, Tuple

ABILITIES = ("awareness", "sensitivity", "creativity")
SHORT = {"awareness": "awr", "sensitivity": "sen", "creativity": "cre"}
RANK = {"Beginner": 1, "Proficient": 2, "Advanced": 3}
PORTAL_LEVEL = {"beginner": "Beginner", "proficient": "Proficient", "advance": "Advanced", "advanced": "Advanced"}

# subject / domain code -> (what Awareness, Sensitivity and Creativity mean in it); written: whether written work
# belongs to the subject (used by the checks: a note about written work under Art or PE is wrong)
SUBJECT_WORDS: Dict[str, Dict[str, str]] = {
    # Preparatory
    "PSLS1": {"awareness": "reading, listening and word knowledge in the first language (R1)",
              "sensitivity": "listening to others and answering politely in R1",
              "creativity": "telling and writing own ideas and stories in R1"},
    "PSLS2": {"awareness": "reading and understanding simple texts in the second language (R2)",
              "sensitivity": "using R2 kindly in pair and group talk",
              "creativity": "making own sentences and short texts in R2"},
    "PSLS3": {"awareness": "number concepts, shapes and maths procedures",
              "sensitivity": "patience and care when solving problems with others",
              "creativity": "finding different ways to solve a problem"},
    "PSLS4": {"awareness": "knowledge of plants, animals, family and surroundings",
              "sensitivity": "care for nature and for people around them",
              "creativity": "observing, asking questions and explaining findings"},
    "PSLS5": {"awareness": "art materials, colours and techniques",
              "sensitivity": "appreciating own and others' artwork",
              "creativity": "original ideas in drawing, craft, music or dance"},
    "PSLS6": {"awareness": "rules of games, exercises and healthy habits",
              "sensitivity": "fair play, teamwork and safety in games",
              "creativity": "new moves, strategies and ways to play"},
    "PSLS7": {"awareness": "what is learnt in reading, cultural and other activities",
              "sensitivity": "cooperation and respect while taking part with others",
              "creativity": "own ideas and contributions in these activities"},
    # Middle
    "SL1": {"awareness": "reading, grammar and vocabulary in the first language (R1)",
            "sensitivity": "respectful listening and discussion in R1",
            "creativity": "expressing original ideas in R1 speech and writing"},
    "SL2": {"awareness": "understanding texts and grammar in the second language (R2)",
            "sensitivity": "using R2 appropriately with different listeners",
            "creativity": "composing own sentences, dialogues and texts in R2"},
    "SL3": {"awareness": "everyday words and phrases in the third language (R3)",
            "sensitivity": "using R3 politely with a partner",
            "creativity": "trying new sentences and dialogues in R3"},
    "SM": {"awareness": "mathematical concepts and procedures",
           "sensitivity": "patience and clear reasoning when solving problems with others",
           "creativity": "finding more than one way to solve a problem"},
    "SSC": {"awareness": "scientific ideas and the steps of an investigation",
            "sensitivity": "care for living things, safety and teamwork in experiments",
            "creativity": "asking questions and designing own ways to test ideas"},
    "SSSC": {"awareness": "facts and ideas about places, people and society",
             "sensitivity": "respect for different people, cultures and views",
             "creativity": "linking events to daily life and presenting own views"},
    "SAE": {"awareness": "art forms, materials and techniques",
            "sensitivity": "appreciating and respecting others' artwork",
            "creativity": "original ideas in art, music, dance or theatre"},
    "SPE": {"awareness": "rules of games, fitness and healthy habits",
            "sensitivity": "fair play, teamwork and safety in sports",
            "creativity": "new strategies and ways to play"},
    "SV": {"awareness": "tools, materials and safe work steps",
           "sensitivity": "care, responsibility and teamwork in practical work",
           "creativity": "improving and finishing a product in own way"},
    "SLA": {"awareness": "what is learnt in reading, cultural and sports activities",
            "sensitivity": "teamwork and respect for others in group events",
            "creativity": "own ideas and initiative in clubs and events"},
    "SVE": {"awareness": "the local work and vocations visited",
            "sensitivity": "respect for workers and their work",
            "creativity": "own questions and ideas in hands-on vocational tasks"},
    # Foundational
    "FSDOM1": {"awareness": "body movement, balance and healthy habits",
               "sensitivity": "safety and care for self and others while playing",
               "creativity": "new ways to move, play and use the hands"},
    "FSDOM2": {"awareness": "naming feelings and following class routines",
               "sensitivity": "sharing, taking turns and caring for friends",
               "creativity": "own ways to solve small problems with friends"},
    "FSDOM3": {"awareness": "colours, shapes, numbers and sorting",
               "sensitivity": "curiosity and attention to things around them",
               "creativity": "trying different ways to solve puzzles and tasks"},
    "FSDOM4": {"awareness": "listening, speaking and early reading",
               "sensitivity": "listening when others talk and replying kindly",
               "creativity": "telling own stories and making up rhymes"},
    "FSDOM5": {"awareness": "colours, songs, rhythms and local art forms",
               "sensitivity": "enjoying and respecting others' art and music",
               "creativity": "own drawings, songs, movements and craft ideas"},
    "FSDOM51": {"awareness": "class routines, cleanliness and care of things",
                "sensitivity": "patience, kindness and respect for others",
                "creativity": "taking initiative and trying new things"},
}
# subjects where written work is part of the subject (the others: Art, PE, Skill, Other learning, Bagless days,
# and the Foundational domains)
WRITTEN = {"PSLS1", "PSLS2", "PSLS3", "PSLS4", "SL1", "SL2", "SL3", "SM", "SSC", "SSSC"}

STRENGTH = {"Advanced": "shown confidently and consistently",
            "Proficient": "shown well with little help",
            "Beginner": "beginning to show with support"}
IMPROVE = {"Beginner": "needs guided practice and encouragement",
           "Proficient": "ready for more independent practice",
           "Advanced": "can take on harder challenges and help peers"}


def level_name(value) -> str:
    """'Beginner' / 'Proficient' / 'Advanced' from a Part C or Part B value ('', 'advance', '3' ...)."""
    text = str(value if value is not None else "").strip()
    if text in RANK:
        return text
    if text.lower() in PORTAL_LEVEL:
        return PORTAL_LEVEL[text.lower()]
    return {"1": "Beginner", "2": "Proficient", "3": "Advanced"}.get(text, "")


def pick(levels: Dict[str, str]) -> Optional[Tuple[str, str]]:
    """(strength ability, ability to improve), or None without all three levels."""
    named = {a: level_name(levels.get(a)) for a in ABILITIES}
    if not all(named.values()):
        return None
    strength = max(ABILITIES, key=lambda a: (RANK[named[a]], -ABILITIES.index(a)))
    others = [a for a in reversed(ABILITIES) if a != strength]          # ties: Creativity first, then Sensitivity
    improve = min(others, key=lambda a: RANK[named[a]])
    return strength, improve


def note(domain: str, levels: Dict[str, str], max_len: Optional[int] = None, activity: str = "") -> str:
    """The subject's note from its three levels; "" when a level is missing or the subject is unknown."""
    words = SUBJECT_WORDS.get(domain)
    chosen = pick(levels)
    if not words or chosen is None:
        return ""
    strength, improve = chosen
    s_level, i_level = level_name(levels[strength]), level_name(levels[improve])
    text = (f"Strength - {strength.capitalize()} ({s_level}): {words[strength]}, {STRENGTH[s_level]}. "
            f"To improve - {improve.capitalize()} ({i_level}): {words[improve]}; {IMPROVE[i_level]}.")
    if activity:
        with_evidence = f"{text} Seen in the activity '{activity.strip()}'."
        if not max_len or len(with_evidence) <= max_len:
            return with_evidence
    return text if not max_len or len(text) <= max_len else ""


def levels_from_row(row: Dict[str, object], domain: str) -> Dict[str, str]:
    """{ability: level} for one subject from card/workbook values (c_<domain>_awareness, Foundational c_<domain>_awr)."""
    out = {}
    for ability in ABILITIES:
        value = row.get(f"c_{domain}_{ability}", row.get(f"c_{domain}_{SHORT[ability]}"))
        out[ability] = level_name(value)
    return out


def note_key(key: str) -> Optional[str]:
    """The subject code when key is a Part C note (c_<domain>_remark / c_<domain>_descriptor), else None."""
    for end in ("_remark", "_descriptor"):
        if key.startswith("c_") and key.endswith(end):
            return key[2:-len(end)]
    return None


def activity_names(part_b: Iterable[dict]) -> Dict[str, str]:
    """{subject code: name of the first Part B activity for it} from Part B formdata."""
    out: Dict[str, str] = {}
    for act in part_b or []:
        dt = (act or {}).get("dt") or {}
        name = str((act or {}).get("nm") or "").strip()
        for domain in dt.get("domain") or []:
            if name and str(domain) not in out:
                out[str(domain)] = name
    return out


def activity_levels(part_b: Iterable[dict]) -> Dict[str, List[Dict[str, str]]]:
    """{subject code: [{ability: level}, ...]} - the rubric levels of each Part B activity for the subject."""
    out: Dict[str, List[Dict[str, str]]] = {}
    for act in part_b or []:
        dt = (act or {}).get("dt") or {}
        levels = {a: level_name((list(dt.get(SHORT[a]) or []) + ["", "", "", ""])[3]) for a in ABILITIES}
        if not any(levels.values()):
            continue
        for domain in dt.get("domain") or []:
            out.setdefault(str(domain), []).append(levels)
    return out
