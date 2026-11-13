"""
Ready phrases for free-text answers, offered next to the text box (the teacher picks one, then can still change
it) and, where an answer may differ from student to student, handed out at random by "Mix". Looked up by the
question's label first (stages share some keys for different questions: Preparatory's "Things about me 1" and
Middle's "I live with my" are both a2_about_1), then by field key; "*_remark" / "*_descriptor" cover every
subject's Part C text. A phrase longer than the field allows on PARAKH is never offered. A text field with
suggestions is a class-wide field (Common answers / the Activities tab).

Some facts are filled from the app's own records instead (RECORD): a student's name (the class list), age (the
date of birth on PARAKH) and, in Foundational, five classmates as friends. Others have no record and no sensible
suggestion (FILL_ONLY: where the student lives): class-wide so "Apply to all" can fill a village, never mixed.
Part C notes are written from each student's own levels for that subject (record_kind "levels", notes.py).
"""
from typing import Dict, List, Optional

# Part C stock notes: no longer offered or mixed (C1 - a note must follow the subject's levels); kept so the checks
# can recognise them on cards filled earlier (backend/hpc/checks.py)
_REMARK = [
    "Shows good understanding of the concepts taught.",
    "Takes part actively; needs more practice in written work.",
    "Making steady progress; encourage regular revision.",
    "Needs support to strengthen the basic concepts.",
    "Excellent effort and interest in the subject.",
]
_DESCRIPTOR = [
    "Shows age-appropriate progress in this domain.",
    "Takes part with interest and is developing well.",
    "Needs encouragement and more practice in this domain.",
    "Shows strong skills for the age.",
]
_STEPS = ["Practise for 30 minutes every day", "Ask my teacher when I have a doubt", "Revise my lessons every weekend",
          "Make a daily timetable and follow it", "Ask my parents to help me keep going"]
_AT_SCHOOL = ["How to work in a group", "New words in English", "How plants grow", "Fractions and decimals",
              "How to make a model"]
_OUTSIDE = ["Cooking a simple dish", "Riding a bicycle", "Caring for animals", "Gardening", "Helping in the shop"]
_LEARN = ["To draw and paint", "To speak English well", "To ride a bicycle", "To use a computer",
          "To play a musical instrument"]

SUGGESTIONS: Dict[str, List[str]] = {
    # Part A1
    "a1_mother_tongue": ["Kashmiri", "Urdu", "Hindi", "Dogri", "Gojri", "Pahari", "Punjabi", "English"],
    "a1_low_attendance": ["Was unwell for some days.", "Family function or travel during the term.",
                          "Long distance to school in bad weather.", "Helped the family at home during the harvest."],
    # Part A2 - all about me (Foundational, Preparatory)
    "a2_grow_up": ["A doctor", "A teacher", "An engineer", "A police officer", "A pilot", "A farmer", "An artist"],
    "a2_fav_colour": ["Red", "Blue", "Green", "Yellow", "Pink"],
    "a2_fav_flower": ["Rose", "Sunflower", "Marigold", "Lotus", "Tulip"],
    "a2_fav_food": ["Rice and rajma", "Apples", "Haak and rice", "Dal and roti", "Fruit"],
    "a2_fav_sport": ["Cricket", "Football", "Kabaddi", "Running", "Badminton"],
    "a2_fav_animal": ["Dog", "Cat", "Cow", "Rabbit", "Parrot"],
    "a2_fav_subject": ["Maths", "English", "Drawing", "Urdu", "Science"],
    "a2_fav_games": ["Cricket and hide-and-seek", "Football", "Kabaddi", "Carrom and chess", "Running races"],
    "a2_fav_festival": ["Eid ul Fitr", "Eid ul Zuha"],
    "a2_learn_1": _LEARN, "a2_learn_2": _LEARN, "a2_learn_3": _LEARN,
    "a2_idol": ["My mother", "My father", "My teacher", "My grandfather", "Dr A. P. J. Abdul Kalam"],
    # Part A2 - all about me and goals (Middle)
    "a2_about_1": ["My parents", "My parents and siblings", "My grandparents", "My family"],
    "a2_about_3": ["Reading story books", "Playing cricket with friends", "Drawing and painting", "Helping at home"],
    "a2_about_4": ["Drawing", "Solving maths problems", "Playing football", "Reciting poems", "Writing stories"],
    "a2_about_5": ["For my books", "At home", "In class", "For my homework"],
    "a2_about_6": ["Handwriting", "Being on time", "Speaking in class", "Mathematics"],
    "a2_about_7": ["Helping my friends with studies", "Sharing my things", "Helping elders at home"],
    "a2_about_8": ["I finish my work on time", "I help someone", "I do well in a test", "I learn something new"],
    "a2_academicGoal_goal": ["Improve my marks in Mathematics", "Read one story book every week",
                             "Write neatly and correctly in English", "Understand Science through experiments"],
    "a2_academicGoal_reason": ["It will help me in higher classes", "I want to understand lessons better",
                               "It will build my confidence"],
    "a2_academicGoal_step1": _STEPS, "a2_academicGoal_step2": _STEPS,
    "a2_personalGoal_goal": ["Wake up early and exercise daily", "Learn to play a new sport", "Help at home every day",
                             "Spend less time on the mobile phone"],
    "a2_personalGoal_reason": ["It keeps me healthy and active", "It makes me responsible", "It helps my family"],
    "a2_personalGoal_step1": _STEPS, "a2_personalGoal_step2": _STEPS,
    "a2_learningAtSchool_1": _AT_SCHOOL, "a2_learningAtSchool_2": _AT_SCHOOL, "a2_learningAtSchool_3": _AT_SCHOOL,
    "a2_learningOutsideSchool_1": _OUTSIDE, "a2_learningOutsideSchool_2": _OUTSIDE,
    "a2_learningOutsideSchool_3": _OUTSIDE,
    "a2_teacher_help": ["Understanding difficult topics in Mathematics.", "Improving my spoken English.",
                        "Preparing for tests.", "Writing answers in my own words."],
    "a2_teacher_know": ["I like to learn by doing activities.", "I sometimes feel shy to ask questions.",
                        "I enjoy working in groups.", "I learn better with pictures and examples."],
    # Part A3 - my ambition (Middle)
    "a3_myAmbition": ["To become a doctor and serve people.", "To become a teacher.", "To become an engineer.",
                      "To join the army and serve the nation.", "To become a scientist."],
    "a3_ambitionAchieveBy": ["Studying hard and staying focused", "Working hard every day",
                             "Learning from my teachers and books"],
    "a3_skillsNeeded": ["Hard work, discipline, communication, teamwork and patience",
                        "Reading, writing, problem solving, confidence and honesty"],
    "a3_subjects": ["Science and Mathematics", "English and Social Science", "Mathematics and English"],
    "a3_habits": ["Regular, disciplined and punctual", "Reading every day and revising lessons",
                  "Healthy eating, enough sleep and daily exercise"],
    "a3_guidanceFrom": ["My teachers and parents", "My teachers", "My elder brother or sister"],
    "a3_helpingPerson": ["Guiding and motivating me", "Helping me with my studies", "Showing me the right way"],
    "a3_newLearning": ["Skills and knowledge every day", "Things from books and the internet",
                       "Ideas from my teachers and friends"],
    "a3_myFeeling": ["Happy and proud", "Confident", "Thankful"],
    "a3_parentsFeeling": ["Proud of me", "Happy", "Very happy and proud"],
    # Part A4 - parent-teacher partnership (Middle)
    "a4_home_support": ["Making sure my child studies regularly at home.",
                        "Talking with my child about what was learnt at school.",
                        "Giving a quiet place and time for study.",
                        "Encouraging reading and limiting screen time."],
    # Part B - the activity: teacher's notes (Foundational, Preparatory)
    "b_observation": [
        "Took part actively and followed the instructions well.",
        "Worked well with friends and shared materials.",
        "Needed some support to start, then finished the task.",
        "Showed curiosity and asked questions during the activity.",
        "Explained their work clearly to classmates.",
        "Was hesitant at first and grew in confidence with encouragement.",
    ],
    "b_challenges": [
        "Found it hard to follow all the steps in order.",
        "Needed help to put ideas into words.",
        "Took time to settle into working with a partner.",
        "Found measuring and counting accurately difficult.",
        "Lost focus during the longer parts of the task.",
    ],
    "b_overcome": [
        "The teacher gave step-by-step guidance and an example.",
        "Worked with a friend who explained the steps.",
        "Practised again with a simpler example first.",
        "Used pictures and real objects to understand.",
        "Was encouraged to try again and managed on their own.",
    ],
    "b_comments": [
        "Enjoys hands-on activities; encourage more practice at home.",
        "Progressing well; give more chances to speak in class.",
        "Needs gentle support to finish tasks; praise the effort.",
        "Shows good habits and helps friends.",
    ],
    "b_resources_other": ["Picture cards", "Clay and paper", "Story books", "Blocks and beads", "Musical instruments"],
    # Part B - the student's reflection and the teacher's support (Middle)
    "b_learnt": [
        "how to plan my work and carry it out step by step.",
        "to work with my classmates and share ideas.",
        "to explain my thinking and give reasons.",
        "how what we learn connects to daily life.",
        "to observe carefully and record what I found.",
    ],
    "b_interesting": ["Working in a group with my friends", "Doing the activity with my own hands",
                      "Finding the answer by myself", "Presenting our work to the class", "Using real objects and materials"],
    "b_need_practice": ["Explaining my answers clearly", "Completing my work on time", "Writing neatly and correctly",
                        "Solving problems on my own", "Speaking confidently in front of others"],
    "b_need_help": ["Understanding difficult words", "Organising my ideas before writing", "Checking my work for mistakes",
                    "Working through longer problems", "Asking questions when I am stuck"],
    "b_strengths_other": ["Leadership", "Drawing and art", "Sports", "Helping others"],
    "b_barriers_other": ["Irregular attendance", "Shy in groups", "Needs more practice"],
    "b_help_progress": [
        "Give regular chances to work in groups and present ideas.",
        "Give extra practice with simple examples, then harder ones.",
        "Encourage reading at home and talk about what was read.",
        "Praise the effort and set small goals to build confidence.",
        "Pair with a classmate for support in difficult tasks.",
    ],
    "b_observations": [
        "Takes part actively and works well in groups.",
        "Shows steady progress; needs encouragement to share ideas.",
        "Completes tasks carefully; ready for more challenging work.",
        "Needs support to stay focused; responds well to praise.",
    ],
}

# facts about a student: a suggestion helps typing, but handing them out at random would be wrong
NO_MIX = {"a1_mother_tongue", "a2_about_1", "a2_avatar"}     # A14: an avatar is the child's own choice

# Several-option questions "Mix" may fill: key -> (the options it may hand out, how many each student gets).
# Part B's assessment lists and the "child needs support with" areas. Barriers to success (B7, required): one each,
# only "None" or a mild study habit - never Peer Pressure, Domestic Issues, behaviour or illness (those label a child;
# the teacher ticks them for the students they apply to). Never "Any Other" (it needs its own text), and
# never an option that says something personal or serious about a student (domestic issues, illness, behaviour,
# peer pressure, managing difficult emotions, "None") - the teacher ticks those for the students they apply to.
# Lists of facts (resources at home ...) are not mixed at all.
MULTI_MIX = {
    "a3_support": (["Oral communication", "Interest in reading", "Numbers and Math", "Self-confidence",
                    "Working with children", "Working independently"], 2),                        # Preparatory
    "a4_support": (["Languages (R1/R2/R3)", "Maths", "Science", "Social Science", "Self-belief and self-reliance",
                    "Social skills and conflict resolution", "Study skills / time management",
                    "Skill guidance / digital literacy"], 2),                                         # Middle
    "b_strengths": (["Follow Instructions", "Collaboration", "Independent Work", "Responsible", "Communication",
                     "Creative", "Solution-Focused Thinking", "Concentration", "Empathy",
                     "Organization & Prioritization"], 2),
    # Foundational Part B: what the activity needed (self and peer) and the learning resources it used - about the
    # activity, not the child. Never "None" (it clears the others) nor "Resources for CWD" (says the child has a
    # disability): the teacher ticks those.
    "b_sa_needed": (["Classmates", "Teachers", "Books", "Computer"], 2),
    "b_pa_needed": (["Classmates", "Teachers", "Books", "Computer"], 2),
    "b_resources": (["Books/Magazines", "Newspaper", "Toys/Games/Sports", "Phone/Computer", "Internet", "Radio",
                     "Broadcast", "TV"], 2),
    "b_barriers": (["None", "Lack of Attention", "Lack of Motivation", "Undefined Goals", "Lack of Preparation"], 1),
    "b_grid_awareness": (None, 2),               # None: every option of the question
    "b_grid_sensitivity": (None, 2),
    "b_grid_creativity": (None, 2),
}


# A ticked "any other" option needs its own words, or PARAKH refuses the save: list key -> (the option, its text
# box, short neutral phrases). Mix writes one only where the option IS ticked and the box is empty (it never ticks
# the option itself).
OTHER_TEXT = {
    "a4_support": ("Any other", "a4_support_other",                                                   # Middle
                   ["Regular revision", "Reading practice", "Handwriting", "Speaking confidence", "General knowledge"]),
    "a3_support": ("Other subject area", "a3_support_other",                                          # Preparatory
                   ["Drawing", "Handwriting", "General awareness", "Speaking English", "Reading aloud"]),
}


# Preparatory's hand drawing (A7): one finger each, 13-24 characters. Facts about the child: offered, never mixed.
BY_LABEL: Dict[str, List[str]] = {
    "Things about me: I am good at": ["Drawing", "Running", "Reading", "Counting", "Singing", "Cricket"],
    "Things about me: I am not so good at": ["Spellings", "Handwriting", "Tables", "Speaking up", "Drawing"],
    "Things about me: I would like to improve my skill of": ["Reading", "Writing", "Handwriting", "English", "Drawing"],
    "Things about me: I like to": ["Play cricket", "Draw pictures", "Read stories", "Help at home", "Sing songs"],
    "Things about me: I don't like to": ["Waste food", "Fight with friends", "Be late for school", "Sit idle"],
}

# questions answered from the app's records: label -> what fills it
RECORD = {"My name is": "name", "Name": "name", "I am ... years old": "age", "Age": "age"}
FILL_ONLY = {"I live in", "We stay at"}


def stock(field_key: str, value) -> bool:
    """True when a text answer is empty or one of the ready phrases for it (not something the teacher wrote)."""
    text = str(value if value is not None else "").strip()
    return not text or text in SUGGESTIONS.get(field_key, [])


def record_kind(label: str, key: str = "") -> str:
    """'name' / 'age' / 'friend' when the answer comes from the app's records, 'levels' for a Part C note (written
    from the subject's own levels, backend/hpc/notes.py), else ''."""
    from backend.hpc.notes import note_key
    if note_key(key):
        return "levels"
    if label.startswith("My friend "):
        return "friend"
    return RECORD.get(label, "")


def _by_label(label: str) -> Optional[List[str]]:
    if label in BY_LABEL:
        return BY_LABEL[label]
    if label in RECORD or label in FILL_ONLY or record_kind(label or ""):
        return []                                    # a fact: never another stage's phrases for the same key
    return None


def _phrases(key: str, label: str = "") -> List[str]:
    own = _by_label(label)
    if own is not None:
        return own
    if key in SUGGESTIONS:
        return SUGGESTIONS[key]
    return []                     # Part C notes: written from each student's own levels (record_kind "levels")


def suggestions_for(key: str, max_len: Optional[int], label: str = "") -> List[str]:
    return [s for s in _phrases(key, label) if not max_len or len(s) <= max_len]


def has_suggestions(key: str, label: str = "") -> bool:
    return bool(_phrases(key, label))


def mixable(key: str, label: str = "") -> bool:
    if label in BY_LABEL:
        return False                                 # A7: what the child is good at / likes is a fact about them
    return key not in NO_MIX and label not in FILL_ONLY


def multi_mix(key: str, options) -> tuple:
    """(options Mix may hand out, how many per student) for a several-option question; ([], 0) when it is not mixed."""
    if key not in MULTI_MIX:
        return [], 0
    allowed, pick = MULTI_MIX[key]
    pool = [o for o in options if allowed is None or o in allowed]
    return (pool, pick) if len(pool) > pick else ([], 0)
