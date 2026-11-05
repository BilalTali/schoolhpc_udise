"""
Printable PDF reports of what is pending, for the head of school and the office: one look, one layout -
a title band (school, UDISE code, session, when made), summary tiles, then tables grouped by what to do, each row
with its reason. A4 landscape; the table headers repeat on every page; "Page x of y" at the foot.

  aadhaar     AADHAAR not verified: UIDAI's reason and what to do, by group
  apaar       APAAR IDs: pending with SDMS's reason and the next step, then those generated
  completion  SDMS forms not complete: each student's missing or wrong fields
  compare     UDISE+ against PARAKH: on one and not the other, and matched students whose details differ
"""
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)
from reportlab.platypus.flowables import Flowable

INK, MUTED, LINE = colors.HexColor("#0f172a"), colors.HexColor("#64748b"), colors.HexColor("#e2e8f0")
NAVY, ZEBRA = colors.HexColor("#0b3b66"), colors.HexColor("#f8fafc")
TONES = {"bad": colors.HexColor("#b91c1c"), "warn": colors.HexColor("#b45309"), "good": colors.HexColor("#15803d"),
         "info": colors.HexColor("#0b5fa5")}
PAGE = landscape(A4)
MARGIN = 12 * mm


def _fonts() -> Tuple[str, str]:
    """Arial from Windows when there (covers names and dashes well), else the PDF's own Helvetica."""
    fonts = Path("C:/Windows/Fonts")
    try:
        if "Report" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("Report", str(fonts / "arial.ttf")))
            pdfmetrics.registerFont(TTFont("Report-Bold", str(fonts / "arialbd.ttf")))
        return "Report", "Report-Bold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


REGULAR, BOLD = _fonts()
pdfmetrics.registerFontFamily(REGULAR, normal=REGULAR, bold=BOLD, italic=REGULAR, boldItalic=BOLD)
CELL = ParagraphStyle("cell", fontName=REGULAR, fontSize=7.6, leading=9.4, textColor=INK, alignment=TA_LEFT)
HEAD = ParagraphStyle("head", parent=CELL, fontName=BOLD, textColor=colors.white)
H2 = ParagraphStyle("h2", fontName=BOLD, fontSize=11.5, leading=14, textColor=NAVY, spaceBefore=8, spaceAfter=2)
NOTE = ParagraphStyle("note", fontName=REGULAR, fontSize=8, leading=10.5, textColor=MUTED, spaceAfter=4)


def _p(value: Any, style: ParagraphStyle = CELL) -> Paragraph:
    text = "" if value is None else str(value)
    return Paragraph(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>"), style)


class Tiles(Flowable):
    """The summary: a row of boxes, each a big number and what it counts."""

    def __init__(self, tiles: Sequence[Tuple[str, Any, str]], width: float):
        super().__init__()
        self.tiles, self.width, self.height = list(tiles), width, 17 * mm

    def wrap(self, *_):
        return self.width, self.height + 3 * mm

    def draw(self):
        c, gap = self.canv, 3 * mm
        w = (self.width - gap * (len(self.tiles) - 1)) / max(len(self.tiles), 1)
        for i, (label, value, tone) in enumerate(self.tiles):
            x = i * (w + gap)
            c.setFillColor(colors.white)
            c.setStrokeColor(LINE)
            c.roundRect(x, 0, w, self.height, 2.2 * mm, stroke=1, fill=1)
            c.setFillColor(TONES.get(tone, INK))
            c.rect(x, 2.2 * mm, 1.1 * mm, self.height - 4.4 * mm, stroke=0, fill=1)
            c.setFont(BOLD, 15)
            c.drawString(x + 4.5 * mm, 8 * mm, str(value))
            c.setFillColor(MUTED)
            c.setFont(REGULAR, 7.4)
            c.drawString(x + 4.5 * mm, 3.4 * mm, label[:48])


def _table(columns: Sequence[Tuple[str, float]], rows: List[List[Any]], width: float) -> Table:
    total = sum(w for _, w in columns)
    widths = [width * w / total for _, w in columns]
    data = [[_p(h, HEAD) for h, _ in columns]] + [[v if isinstance(v, Flowable) else _p(v) for v in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE), ("BOX", (0, 0), (-1, -1), 0.5, LINE),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    style += [("BACKGROUND", (0, i), (-1, i), ZEBRA) for i in range(2, len(data), 2)]
    t.setStyle(TableStyle(style))
    return t


class _Doc(BaseDocTemplate):
    def __init__(self, buf, title: str, school: Dict[str, str]):
        super().__init__(buf, pagesize=PAGE, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=31 * mm, bottomMargin=13 * mm,
                         title=title, author=school.get("name") or "", creator="TeacherAssist")
        self.report_title, self.school = title, school
        frame = Frame(MARGIN, 13 * mm, PAGE[0] - 2 * MARGIN, PAGE[1] - 44 * mm, id="body", leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate("page", frames=[frame], onPage=self._band)])

    def _band(self, c, doc):
        w, h = PAGE
        c.saveState()
        c.setFillColor(NAVY)
        c.rect(0, h - 24 * mm, w, 24 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont(BOLD, 16)
        c.drawString(MARGIN, h - 11 * mm, self.report_title)
        c.setFont(REGULAR, 9)
        line = " · ".join(x for x in (self.school.get("name"), f"UDISE {self.school['udise']}" if self.school.get("udise") else "",
                                      self.school.get("session")) if x)
        c.drawString(MARGIN, h - 17.5 * mm, line)
        c.setFont(REGULAR, 8)
        c.drawRightString(w - MARGIN, h - 11 * mm, "Made " + datetime.now().strftime("%d %b %Y, %I:%M %p"))
        if self.school.get("source"):
            c.drawRightString(w - MARGIN, h - 17.5 * mm, self.school["source"])
        c.setFillColor(MUTED)
        c.setFont(REGULAR, 7.5)
        c.drawString(MARGIN, 7 * mm, f"{self.report_title} · {self.school.get('name') or ''}")
        c.restoreState()


class _Numbered(canvas.Canvas):
    """Holds each page until the end, so the foot can say "Page x of y"."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pages: List[Dict[str, Any]] = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self.setFillColor(MUTED)
            self.setFont(REGULAR, 7.5)
            self.drawRightString(PAGE[0] - MARGIN, 7 * mm, f"Page {self._pageNumber} of {total}")
            super().showPage()
        super().save()


def build(title: str, school: Dict[str, str], tiles: Sequence[Tuple[str, Any, str]],
          sections: Sequence[Dict[str, Any]], intro: str = "") -> bytes:
    """sections: [{"title", "note", "columns": [(header, relative width)], "rows": [[cells]], "empty": text}]."""
    buf = io.BytesIO()
    doc = _Doc(buf, title, school)
    width = PAGE[0] - 2 * MARGIN
    story: List[Any] = []
    if intro:
        story.append(_p(intro, NOTE))
    story += [Tiles(tiles, width), Spacer(1, 2 * mm)]
    for s in sections:
        head = [_p(f"{s['title']}  ({len(s['rows'])})", H2)] + ([_p(s["note"], NOTE)] if s.get("note") else [])
        if s["rows"]:
            story += [CondPageBreak(35 * mm), KeepTogether(head), _table(s["columns"], s["rows"], width)]
        else:
            story += [KeepTogether(head + [_p(s.get("empty") or "None.", NOTE)])]
    doc.build(story, canvasmaker=_Numbered)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# The reports
# ---------------------------------------------------------------------------

def _school(school, data: Optional[Dict[str, Any]], source: str) -> Dict[str, str]:
    from backend.udise.sdms import session_label
    return {"name": getattr(school, "school_name", "") or "", "udise": getattr(school, "udise_code", "") or "",
            "session": f"Session {session_label({'yearId': data.get('year_id')})}" if data and data.get("year_id") else "",
            "source": source}


def _fetched(data: Dict[str, Any]) -> str:
    try:
        return "SDMS as fetched " + datetime.fromisoformat(data["fetched_at"].rstrip("Z")).strftime("%d %b %Y, %I:%M %p") + " UTC"
    except (KeyError, ValueError):
        return "SDMS as last fetched"


def _in_class_order(rows: List[Dict[str, Any]], data: Dict[str, Any]) -> List[Dict[str, Any]]:
    order = {s["general"].get("studentId"): s["general"].get("classId") for s in data["students"]}
    rank = lambda r: order.get(r["student_id"]) if order.get(r["student_id"]) is not None else 99
    return sorted(rows, key=lambda r: (rank(r), str(r["section"] or ""), str(r["name"] or "")))


def _step(text: str) -> str:
    """The app's next step without its on-screen pointers ("(step 2)")."""
    return re.sub(r"\s*\((step \d|step \d / consent sheet)\)", "", text)


def aadhaar(school_id: str, school) -> Optional[bytes]:
    from backend.services import sdms_apaar_excel
    from backend.services.sdms_data import load
    rows = sdms_apaar_excel._rows(school_id)
    if rows is None:
        return None
    data = load(school_id)
    rows = _in_class_order(rows, data)
    groups = [("mismatch", "Details do not match the AADHAAR card", "Correct the name, gender or date of birth exactly as on the card, then verify again."),
              ("retry", "UIDAI could not check (technical error)", "Nothing is wrong with the details: verify again."),
              ("no_aadhaar", "No AADHAAR on SDMS", "Enter the student's AADHAAR number on SDMS.")]
    cols = [("#", 3), ("Class", 9), ("Student", 15), ("Father's name", 14), ("PEN", 10), ("DOB", 7), ("Status on SDMS", 14),
            ("Reason (UIDAI)", 17), ("What to do", 17)]
    sections = []
    for key, title, note in groups:
        rs = [r for r in rows if r["group"] == key]
        sections.append({"title": title, "note": note, "columns": cols, "rows": [
            [n, f"{r['class'] or ''} {r['section'] or ''}", r["name"], r.get("father"), r["pen"], r["dob"], r["status"] or "Not verified",
             r["reason"] or "—", _step(sdms_apaar_excel._next_step({**r, "apaar_ready": False}))] for n, r in enumerate(rs, 1)]})
    count = lambda k: sum(1 for r in rows if r["group"] == k)
    tiles = [("Students", len(rows), "info"), ("Verified", count("verified"), "good"), ("Mismatch", count("mismatch"), "bad"),
             ("Technical error", count("retry"), "warn"), ("No AADHAAR", count("no_aadhaar"), "bad")]
    return build("AADHAAR verification pending", _school(school, data, _fetched(data)), tiles, sections)


def apaar(school_id: str, school) -> Optional[bytes]:
    from backend.services import sdms_apaar_excel
    from backend.services.sdms_data import load
    rows = sdms_apaar_excel._rows(school_id)
    if rows is None:
        return None
    data = load(school_id)
    rows = _in_class_order(rows, data)
    read = any("apaar" in s or "apaarIdStatus" in s["general"] for s in data["students"])
    pending = [r for r in rows if not r["apaar_id"]]
    done = [r for r in rows if r["apaar_id"]]
    cols = [("#", 3), ("Class", 9), ("Student", 15), ("Father's name", 14), ("PEN", 10), ("AADHAAR", 10),
            ("Reason (SDMS)", 20), ("What to do next", 21)]
    ready = [r for r in pending if r["apaar_ready"]]
    waiting = [r for r in pending if not r["apaar_ready"]]
    line = lambda n, r: [n, f"{r['class'] or ''} {r['section'] or ''}", r["name"], r.get("father"), r["pen"],
                         r["status"] if r["group"] != "verified" else "Verified", r["apaar_status"] or "Not generated yet",
                         _step(sdms_apaar_excel._next_step(r))]
    sections = [
        {"title": "Pending: ready to generate", "note": "PEN and verified AADHAAR: generate with the parent's physical consent.",
         "columns": cols, "rows": [line(n, r) for n, r in enumerate(ready, 1)]},
        {"title": "Pending: AADHAAR to fix first", "note": "SDMS generates an APAAR ID only after the AADHAAR is verified.",
         "columns": cols, "rows": [line(n, r) for n, r in enumerate(waiting, 1)]},
        {"title": "Generated", "columns": [("#", 3), ("Class", 8), ("Student", 18), ("Father's name", 16), ("PEN", 11),
                                          ("APAAR ID", 12), ("Generated on", 10)],
         "rows": [[n, f"{r['class'] or ''} {r['section'] or ''}", r["name"], r.get("father"), r["pen"], r["apaar_id"],
                   r.get("apaar_date") or "—"] for n, r in enumerate(done, 1)]},
    ]
    tiles = [("Students", len(rows), "info"), ("APAAR generated", len(done), "good"), ("Ready to generate", len(ready), "warn"),
             ("AADHAAR to fix first", len(waiting), "bad")]
    intro = "" if read else "The APAAR status has not been read from SDMS yet: press 'Read APAAR status from SDMS' for SDMS's reasons."
    return build("APAAR ID status", _school(school, data, _fetched(data)), tiles, sections, intro)


def completion(school_id: str, school) -> Optional[bytes]:
    from backend.udise import sdms_form
    from backend.services.sdms_data import FORM_STATUS, load
    data = load(school_id)
    if not data:
        return None
    masters = data.get("masters") or {}
    rows, per_field = [], {}
    students = sorted(data["students"], key=lambda s: (s["general"].get("classId") if s["general"].get("classId") is not None else 99,
                                                       str(s["general"].get("sectionDesc") or ""), str(s["general"].get("studentName") or "")))
    for s in students:
        g = s["general"]
        issues = [c for c in sdms_form.completion(s, masters) if c["issue"]]
        for c in issues:
            per_field[c["label"]] = per_field.get(c["label"], 0) + 1
        if issues:
            rows.append([len(rows) + 1, f"{g.get('classDesc') or ''} {g.get('sectionDesc') or ''}", g.get("studentName"), g.get("fatherName"),
                         g.get("studentCodeNat"), FORM_STATUS.get(g.get("formStatus"), "In progress"),
                         "\n".join(f"• {c['tab']}: {c['label']} — {c['issue']}" for c in issues)])
    not_done = sum(1 for s in data["students"] if s["general"].get("formStatus") != 6)
    tiles = [("Students", len(data["students"]), "info"), ("Forms completed on SDMS", len(data["students"]) - not_done, "good"),
             ("Forms not completed", not_done, "warn"), ("Students with fields to fill", len(rows), "bad")]
    sections = [
        {"title": "Students with required fields to fill", "note": "Fill these in the completion sheet (or on SDMS) and sync.",
         "columns": [("#", 3), ("Class", 9), ("Student", 14), ("Father's name", 13), ("PEN", 10), ("Form", 7), ("What is missing or wrong", 46)],
         "rows": rows, "empty": "Every student's required fields are filled."},
        {"title": "The fields most often missing", "columns": [("Field", 70), ("Students", 10)],
         "rows": [[k, v] for k, v in sorted(per_field.items(), key=lambda kv: -kv[1])]},
    ]
    return build("SDMS student forms pending", _school(school, data, _fetched(data)), tiles, sections)


def compare(school_id: str, school, result: Dict[str, Any]) -> bytes:
    from backend.services.sdms_data import load
    data = load(school_id)
    c = result["counts"]
    one = [("#", 3), ("Student", 15), ("Parentage", 15), ("Adm. no", 8), ("Class", 9), ("DOB", 7), ("APAAR ID", 10), ("Status", 10)]
    side = lambda xs: [[n, s["name"], s["parent"], s["adm_no"], s["class"], s["dob"], s["apaar"] or "—", s["status"]] for n, s in enumerate(xs, 1)]
    differ = [m for m in result["matched"] if m["differs"]]
    sections = [
        {"title": "On PARAKH, not on UDISE+", "note": "Admit on SDMS (new admission or import from the Dropbox), or correct the details so they match.",
         "columns": one, "rows": side(result["only_parakh"]), "empty": "None: every PARAKH student is on UDISE+."},
        {"title": "On UDISE+, not on PARAKH", "note": "Add to the class on PARAKH, or send to the Dropbox on SDMS if the student has left.",
         "columns": one + [("PEN", 9)], "rows": [r + [s.get("pen")] for r, s in zip(side(result["only_udise"]), result["only_udise"])],
         "empty": "None: every UDISE+ student is on PARAKH."},
        {"title": "On both, with different details", "note": "Matched by the key shown; make the two records agree.",
         "columns": [("#", 3), ("Student (UDISE+)", 14), ("Parentage (UDISE+)", 13), ("Class: UDISE+ / PARAKH", 11),
                     ("Adm. no: UDISE+ / PARAKH", 11), ("DOB: UDISE+ / PARAKH", 11), ("Matched by", 9), ("Differs in", 12)],
         "rows": [[n, m["udise"]["name"], m["udise"]["parent"], f"{m['udise']['class']} / {m['parakh']['class']}",
                   f"{m['udise']['adm_no'] or '—'} / {m['parakh']['adm_no'] or '—'}", f"{m['udise']['dob']} / {m['parakh']['dob']}",
                   m["by"], ", ".join(m["differs"])] for n, m in enumerate(differ, 1)]},
    ]
    tiles = [("On UDISE+ (classes compared)", c["udise"], "info"), ("On PARAKH", c["parakh"], "info"), ("On both", c["matched"], "good"),
             ("Only on PARAKH", c["only_parakh"], "bad"), ("Only on UDISE+", c["only_udise"], "bad"), ("Details differ", c["differ"], "warn")]
    intro = ("PARAKH's students are the classes the teachers fetched; parentage on PARAKH is Part A1's guardian name. "
             + (f"{c['udise_higher_classes']} UDISE+ students in classes PARAKH does not cover are left out." if c.get("udise_higher_classes") else ""))
    return build("UDISE+ and PARAKH: students compared", _school(school, data, "From the app's last reads of both"), tiles, sections, intro)


def _when(iso: str) -> str:
    try:
        return datetime.fromisoformat(str(iso).rstrip("Z")).strftime("%d %b %Y, %I:%M %p") + " UTC"
    except ValueError:
        return str(iso or "")


def profile(school, found: Dict[str, Any]) -> bytes:
    """UDISE+ School Profile & Facilities: where each form stands, every question still needed with its exact place
    (DCF item, and sheet and row of the app's workbook), totals that do not add up, and what the app updated."""
    year = found.get("year") or ""
    forms, needed, problems = found["forms"], found["needed"], found["problems"]
    updated = [u for u in found["updated"] if not year or u.get("year") in (None, year)]
    info = {"name": found["school"].get("name") or getattr(school, "school_name", ""),
            "udise": found["school"].get("udise_code") or getattr(school, "udise_code", ""),
            "session": f"Session {year}" if year else "", "source": "UDISE+ as read " + _when(found["read_at"])}
    tiles = [("Forms", len(forms), "info"), ("Questions asked", sum(f["questions"] for f in forms), "info"),
             ("Answered", sum(f["answered"] for f in forms), "good"), ("Still needed", len(needed), "bad" if needed else "good"),
             ("Totals to correct", len(problems), "bad" if problems else "good"), ("Updated from the app", len(updated), "info"),
             ("Forms certified", sum(1 for f in forms if f["certified"]), "warn")]
    sections = [
        {"title": "Forms", "note": "Answered = questions asked of this school (its classes, and 'if Yes' questions only after a Yes) "
                                   "that have an answer on UDISE+.",
         "columns": [("DCF items", 10), ("Form", 32), ("Answered", 9), ("Still needed", 9), ("Last saved on UDISE+", 13),
                     ("Certified", 7), ("Workbook sheet", 20)],
         "rows": [[f["dcf"], f["title"] + (f"\nCould not be read: {f['error']}" if f["error"] else ""),
                   f"{f['answered']} of {f['questions']}", f["needed"] or "—", (f["modified"] or "never")[:16], "Yes" if f["certified"] else "No",
                   f["sheet"]] for f in forms]},
        {"title": "Still needed", "note": "Each question to answer, where it is: the DCF item on UDISE+, and the sheet and row "
                                          "in the workbook downloaded from the app.",
         "columns": [("#", 3), ("DCF items", 9), ("Item", 8), ("Question", 40), ("Workbook: sheet, row", 18), ("Allowed answers", 22)],
         "rows": [[n, x["dcf"], x["item"], x["question"], f"{x['sheet']}, row {x['row']}", x["allowed"]] for n, x in enumerate(needed, 1)],
         "empty": "Every question asked of this school has an answer on UDISE+."},
        {"title": "Totals that do not add up", "note": "UDISE+ refuses to save these forms until they agree.",
         "columns": [("DCF items", 10), ("Form", 30), ("What to correct", 60)],
         "rows": [[p["dcf"], p["title"], p["message"]] for p in problems], "empty": "None."},
        {"title": f"Updated from the app{' for ' + year if year else ''}", "note": "Every answer the app saved to UDISE+: when, "
                                                                                    "where, what it was and what it is now.",
         "columns": [("#", 3), ("When", 12), ("DCF items", 8), ("Item", 8), ("Question", 33), ("Before", 11), ("After", 11), ("Result", 10)],
         "rows": [[n, _when(u["at"]), u["dcf"], u["item"], u["question"], u["before"] if u["before"] not in (None, "") else "—",
                   u["after"], u["result"]] for n, u in enumerate(reversed(updated), 1)],
         "empty": "Nothing has been saved from the app yet."},
    ]
    return build("UDISE+ School Profile & Facilities: status", info, tiles, sections)


def teachers(school, found: Dict[str, Any]) -> bytes:
    """UDISE+ Teacher module: each kind of staff, who is complete, every field still needed with its exact place in
    the workbook (sheet, row, column), and what the app updated."""
    groups, needed = found["groups"], found["needed"]
    updated = found["updated"]
    info = {"name": getattr(school, "school_name", ""), "udise": getattr(school, "udise_code", ""), "session": "",
            "source": "UDISE+ Teacher module as read " + _when(found["read_at"])}
    total = sum(g["staff"] for g in groups)
    tiles = [("Staff", total, "info"), ("Complete on UDISE+", sum(g["complete"] for g in groups), "good"),
             ("Staff with fields needed", sum(1 for g in groups for p in g["people"] if p["missing"]), "bad"),
             ("Fields still needed", len(needed), "bad" if needed else "good"), ("Updated from the app", len(updated), "info")]
    people = [[g["label"], p["name"], p["national_code"] or "—", "Yes" if p["complete_on_udise"] else "No",
               len(p["missing"]) or "—", f"{g['label'][:31]}, row {p['row']}"] for g in groups for p in g["people"]]
    sections = [
        {"title": "Staff", "note": "Complete = UDISE+ shows all forms of the person as complete and nothing asked is empty.",
         "columns": [("Kind", 14), ("Name", 24), ("National code", 14), ("Forms complete", 9), ("Fields needed", 9), ("Workbook: sheet, row", 22)],
         "rows": people, "empty": "No staff on UDISE+."},
        {"title": "Still needed", "note": "Each empty field, and exactly where it is in the workbook downloaded from the app.",
         "columns": [("#", 3), ("Name", 18), ("Form", 6), ("Field", 34), ("Workbook: sheet, cell", 18), ("Allowed answers", 25)],
         "rows": [[n, x["staff"], x["form"], x["field"], f"{x['sheet']}, {x['column']}{x['row']}", x["allowed"]]
                  for n, x in enumerate(needed, 1)], "empty": "Every field asked is filled on UDISE+."},
        {"title": "Updated from the app", "note": "Every value the app saved to UDISE+: when, who, what it was and what it is now.",
         "columns": [("#", 3), ("When", 12), ("Name", 16), ("Form", 6), ("Field", 26), ("Before", 13), ("After", 13), ("Result", 10)],
         "rows": [[n, _when(u["at"]), u["staff"], u["form"], u["field"], u["before"] or "—", u["after"], u["result"]]
                  for n, u in enumerate(reversed(updated), 1)], "empty": "Nothing has been saved from the app yet."},
    ]
    return build("UDISE+ Teacher module: status", info, tiles, sections)
