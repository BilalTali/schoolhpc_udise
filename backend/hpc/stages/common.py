"""
Building blocks shared by every stage definition.

A stage (Preparatory, Middle) is an ordered list of Parts. Each Part knows:
  - its portal column (hpc_col) and code (A1, A2, ... D),
  - a blank template of its formdata (copied from the portal's page code),
  - the Excel Fields that map into that formdata,
  - finish(): fills values the portal page calculates itself, checks the same
    required fields the page checks, and returns any extra keys for the save request.
"""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.hpc.fields import Field
from backend.hpc.portal import Portal

MONTHS = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
GUARDIAN = {"Mother": "MOTHER", "Father": "FATHER", "Guardian": "GUARDIAN"}
RATING_1_3 = {"Beginner": "1", "Proficient": "2", "Advanced": "3"}
RUBRIC = {"Beginner": "beginner", "Proficient": "proficient", "Advanced": "advance"}


def clean(text: Any) -> str:
    """The portal's GM(): collapse whitespace and trim."""
    return " ".join(str(text or "").split())


# Where Lookups gets the Activity Bank: set by backend.services.activity_library to read the app's own copy
# (kept up to date by the school admin's sync). PARAKH's bank is read only while that copy is empty.
ACTIVITY_SOURCE: Optional[Callable[[str], Dict[int, Dict[str, Any]]]] = None


class Lookups:
    """Dropdown lists the portal pages load from its API, fetched once per run."""

    def __init__(self, portal: Portal, stage_code: str):
        self.portal = portal
        get = lambda path, **kw: portal._request("GET", path, **kw)["data"]
        with ThreadPoolExecutor(max_workers=6) as pool:      # six independent reads, about 2 s each
            cats = pool.submit(get, "/categories/MED_INST,LOCATION")
            interests = pool.submit(get, "/categories/STU_INTRST")
            grades = pool.submit(get, f"/states/{portal.state}/grades")
            sections = pool.submit(get, f"/states/{portal.state}/districts/{portal.district_id}/schools/{portal.school_id}/sections")
            domains = pool.submit(portal.activity_categories, stage_code)
            stored = ACTIVITY_SOURCE(stage_code) if ACTIVITY_SOURCE else {}
            bank = None if stored else pool.submit(portal.activity_bank_page, 1, 1000)
            self.medium = cats.result()["MED_INST"]
            self.location = cats.result()["LOCATION"]
            self.interests = interests.result()
            self.grades = grades.result().get(stage_code, [])
            self.sections = sections.result()["records"]
            self.domains = domains.result()
            records = bank.result()["records"] if bank else []
        self.activities: Dict[int, Dict[str, Any]] = dict(stored)
        for a in records:
            a["content"] = json.loads(a.get("activity_data_json") or "{}")
            # Activities with pictures need the page's image re-upload step, which we don't do.
            has_images = any((a["content"].get("dt") or {}).get("img") or [])
            if a.get("hpc_stage") == stage_code and not has_images:
                self.activities[int(a["id"])] = a

    def activity_label(self, bank_id: Any) -> str:
        a = self.activities.get(int(bank_id)) if str(bank_id).isdigit() else None
        return f"{a['id']}: {a['activity_caption']}" if a else ""

    def section_name(self, section_id: Any) -> str:
        return next((s["section_caption"] for s in self.sections if str(s["id"]) == str(section_id)), "")

    def grade_code(self, grade_id: Any) -> str:
        return next((g["grade_code"] for g in self.grades if str(g["id"]) == str(grade_id)), "")

    def options(self, items, label_key="catg_item_caption", value_key="catg_item_code") -> Dict[str, Any]:
        return {i[label_key]: i[value_key] for i in items}


@dataclass
class StudentContext:
    """What a Part may need besides its own formdata."""
    record: Dict[str, Any]          # GET without hpc_col: stu_info, sch_info, ids
    lookups: Lookups
    parts: Dict[str, Any]           # hpc_col -> formdata, after Excel values were applied

    @property
    def stu(self) -> Dict[str, Any]:
        return self.record.get("stu_info") or {}

    @property
    def grade_code(self) -> str:
        return self.lookups.grade_code(self.stu.get("grade_id")) or self.record.get("cond_class", "")


FinishResult = Tuple[Dict[str, Any], List[str]]   # (extra request keys, errors)


@dataclass
class Part:
    code: str
    col: str
    title: str
    blank: Callable[[], Any]
    fields: Callable[[Lookups], List[Field]]
    finish: Callable[[Any, StudentContext], FinishResult] = lambda fd, ctx: ({}, [])
    as_json_string: bool = True     # Part B is sent as a raw list; every other part as a JSON string

    def load(self, raw: Any) -> Any:
        """Portal formdata (string, dict, list or empty) -> structure shaped like the blank template."""
        if isinstance(raw, str):
            try:
                raw = json.loads(raw) if raw.strip() else None
            except ValueError:
                raw = None
        return merge_into_blank(self.blank(), raw)


def merge_into_blank(blank: Any, loaded: Any) -> Any:
    """Keeps loaded values but guarantees every key/list slot the page expects exists."""
    if loaded is None or (isinstance(loaded, dict) and not loaded):
        return copy.deepcopy(blank)
    if isinstance(blank, dict) and isinstance(loaded, dict):
        out = {k: merge_into_blank(v, loaded.get(k)) for k, v in blank.items()}
        out.update({k: v for k, v in loaded.items() if k not in blank})
        return out
    if isinstance(blank, list) and isinstance(loaded, list):
        if len(blank) == 1 and isinstance(blank[0], dict):
            # A list of records (Part B activities): shape every record like the template.
            return [merge_into_blank(blank[0], item) for item in loaded] or copy.deepcopy(blank)
        if blank and len(loaded) < len(blank):
            return list(loaded) + copy.deepcopy(blank[len(loaded):])
    return loaded


def required(errors: List[str], value: Any, label: str) -> None:
    if not str(value if value is not None else "").strip():
        errors.append(f"{label}: required")
