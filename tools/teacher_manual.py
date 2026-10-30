"""
Builds the teachers' user manual (PDF) - the guide teachers download from the app's sidebar.

    python tools/teacher_manual.py            -> frontend/public/Teacher_Manual.pdf (served by the app)

Written for class teachers: plain words, one task per section, the app's own button names in bold.
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reportlab.lib import colors                                                    # noqa: E402
from reportlab.lib.pagesizes import A4                                              # noqa: E402
from reportlab.lib.styles import ParagraphStyle                                     # noqa: E402
from reportlab.lib.units import mm                                                  # noqa: E402
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, KeepTogether, NextPageTemplate, PageBreak,  # noqa: E402
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents                      # noqa: E402

from backend.services.reports_pdf import BOLD, REGULAR                              # noqa: E402  (Arial when there)
from reportlab.pdfbase.pdfmetrics import registerFontFamily                         # noqa: E402

registerFontFamily(REGULAR, normal=REGULAR, bold=BOLD, italic=REGULAR, boldItalic=BOLD)   # <b> in text: the bold face

NAVY, BLUE, INK, MUTED = colors.HexColor("#0b3b66"), colors.HexColor("#0b5fa5"), colors.HexColor("#0f172a"), colors.HexColor("#64748b")
LINE, SOFT = colors.HexColor("#e2e8f0"), colors.HexColor("#f1f5f9")
GREEN, AMBER, RED = colors.HexColor("#15803d"), colors.HexColor("#b45309"), colors.HexColor("#b91c1c")
W, H = A4
M = 18 * mm
TEXT_W = W - 2 * M

BODY = ParagraphStyle("body", fontName=REGULAR, fontSize=10.4, leading=15, textColor=INK, spaceAfter=6)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=9, leading=12.5, textColor=MUTED, spaceAfter=3)
H1 = ParagraphStyle("h1", fontName=BOLD, fontSize=19, leading=24, textColor=NAVY, spaceAfter=4, keepWithNext=1)
H2 = ParagraphStyle("h2", fontName=BOLD, fontSize=12.5, leading=17, textColor=BLUE, spaceBefore=9, spaceAfter=4, keepWithNext=1)
LEAD = ParagraphStyle("lead", parent=BODY, fontSize=11.2, leading=16.5, textColor=MUTED, spaceAfter=10)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=9.4, leading=13, spaceAfter=0)
CELL_B = ParagraphStyle("cellb", parent=CELL, fontName=BOLD)
TOC1 = ParagraphStyle("toc1", fontName=REGULAR, fontSize=11, leading=20, textColor=INK, leftIndent=4)


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

class Chapter(Paragraph):
    """A chapter title that also goes into the contents."""

    def __init__(self, number: int, title: str):
        super().__init__(f"{number}. {title}", H1)
        self.toc = f"{number}.&nbsp;&nbsp;{title}"


def p(text, style=BODY):
    return Paragraph(text, style)


def steps(items):
    """Numbered steps, each in a round badge."""
    rows = []
    for n, text in enumerate(items, 1):
        badge = Table([[Paragraph(f"<font color='white'><b>{n}</b></font>", ParagraphStyle("n", fontName=BOLD, fontSize=9.5,
                                                                                             leading=11, alignment=1))]],
                      colWidths=[6.5 * mm], rowHeights=[6.5 * mm])
        badge.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BLUE), ("ROUNDEDCORNERS", [3.2 * mm] * 4),
                                   ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        rows.append([badge, Paragraph(text, CELL)])
    t = Table(rows, colWidths=[10 * mm, TEXT_W - 10 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def box(kind, text):
    """A tip, a caution or a 'remember' callout."""
    tone, label = {"tip": (GREEN, "Tip"), "warn": (AMBER, "Careful"), "stop": (RED, "Important"),
                   "note": (BLUE, "Good to know")}[kind]
    t = Table([[Paragraph(f"<b><font color='{tone.hexval()}'>{label}</font></b><br/>{text}", CELL)]], colWidths=[TEXT_W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SOFT), ("LINEBEFORE", (0, 0), (0, -1), 3, tone),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                           ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return KeepTogether([Spacer(1, 2 * mm), t, Spacer(1, 3 * mm)])


def table(head, rows, widths):
    total = sum(widths)
    data = [[Paragraph(f"<font color='white'><b>{h}</b></font>", CELL) for h in head]]
    data += [[Paragraph(c, CELL_B if i == 0 else CELL) for i, c in enumerate(r)] for r in rows]
    t = Table(data, colWidths=[TEXT_W * w / total for w in widths], repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.5, LINE),
             ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
             ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]
    style += [("BACKGROUND", (0, i), (-1, i), SOFT) for i in range(2, len(data), 2)]
    t.setStyle(TableStyle(style))
    return KeepTogether([t, Spacer(1, 4 * mm)]) if len(rows) < 8 else t


class Flow(Flowable):
    """The whole job at a glance: boxes joined by arrows."""

    def __init__(self, labels, subs):
        super().__init__()
        self.labels, self.subs = labels, subs
        self.width, self.height = TEXT_W, 25 * mm

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c, n, gap = self.canv, len(self.labels), 5 * mm
        w = (self.width - gap * (n - 1)) / n
        for i, (label, sub) in enumerate(zip(self.labels, self.subs)):
            x = i * (w + gap)
            c.setFillColor(NAVY if i in (0, n - 1) else colors.white)
            c.setStrokeColor(BLUE)
            c.roundRect(x, 2 * mm, w, 21 * mm, 2.5 * mm, stroke=1, fill=1)
            c.setFillColor(colors.white if i in (0, n - 1) else NAVY)
            c.setFont(BOLD, 9)
            c.drawCentredString(x + w / 2, 15 * mm, label)
            c.setFont(REGULAR, 7.4)
            c.setFillColor(colors.HexColor("#cbd5e1") if i in (0, n - 1) else MUTED)
            for k, line in enumerate(sub.split("\n")):
                c.drawCentredString(x + w / 2, (10.5 - 3.6 * k) * mm, line)
            if i < n - 1:
                c.setStrokeColor(BLUE)
                c.setFillColor(BLUE)
                ax = x + w + 0.8 * mm
                c.line(ax, 12.5 * mm, ax + gap - 1.6 * mm, 12.5 * mm)
                path = c.beginPath()
                path.moveTo(ax + gap - 1.6 * mm, 13.6 * mm)
                path.lineTo(ax + gap - 0.4 * mm, 12.5 * mm)
                path.lineTo(ax + gap - 1.6 * mm, 11.4 * mm)
                c.drawPath(path, stroke=0, fill=1)


class Screen(Flowable):
    """A simple drawing of the teacher's home: the five step cards."""

    def __init__(self):
        super().__init__()
        self.width, self.height = TEXT_W, 52 * mm

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(SOFT)
        c.setStrokeColor(LINE)
        c.roundRect(0, 0, self.width, self.height, 3 * mm, stroke=1, fill=1)
        c.setFillColor(NAVY)
        c.rect(0, self.height - 7 * mm, self.width, 7 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont(BOLD, 8.5)
        c.drawString(4 * mm, self.height - 4.8 * mm, "Teacher Assist  ·  Your HPC steps")
        cards = [("1. Students", "Your class from PARAKH"), ("2. Activities", "Part B, every subject"),
                 ("3. Common answers", "Same answer for many"), ("4. Class settings", "Days, marks, medium"),
                 ("5. Excel & upload", "Download, fill, send")]
        gap, top = 3 * mm, self.height - 11 * mm
        w = (self.width - 8 * mm - gap * 2) / 3
        for i, (t, s) in enumerate(cards):
            col, row = i % 3, i // 3
            x, y = 4 * mm + col * (w + gap), top - (row + 1) * 18 * mm - row * gap
            c.setFillColor(colors.white)
            c.setStrokeColor(LINE)
            c.roundRect(x, y, w, 18 * mm, 2 * mm, stroke=1, fill=1)
            c.setFillColor(BLUE)
            c.rect(x, y + 2 * mm, 1.1 * mm, 14 * mm, stroke=0, fill=1)
            c.setFillColor(INK)
            c.setFont(BOLD, 9)
            c.drawString(x + 4 * mm, y + 11.5 * mm, t)
            c.setFillColor(MUTED)
            c.setFont(REGULAR, 7.5)
            c.drawString(x + 4 * mm, y + 7 * mm, s)
            c.setFillColor(BLUE)
            c.setFont(BOLD, 7.5)
            c.drawString(x + 4 * mm, y + 2.8 * mm, "Open  >")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

class Doc(BaseDocTemplate):
    def __init__(self, path):
        super().__init__(str(path), pagesize=A4, leftMargin=M, rightMargin=M, topMargin=22 * mm, bottomMargin=18 * mm,
                         title="Teacher Assist - Teacher's guide", author="Teacher Assist", subject="Holistic Progress Card (HPC)")
        body = Frame(M, 18 * mm, TEXT_W, H - 40 * mm, id="body")
        self.addPageTemplates([PageTemplate("cover", frames=[Frame(0, 0, W, H, id="c")], onPage=self.cover),
                               PageTemplate("page", frames=[body], onPage=self.page)])

    def afterFlowable(self, flowable):
        if isinstance(flowable, Chapter):
            self.notify("TOCEntry", (0, flowable.toc, self.page))

    @staticmethod
    def cover(c, doc):
        c.saveState()
        c.setFillColor(NAVY)
        c.rect(0, H * 0.42, W, H * 0.58, stroke=0, fill=1)
        c.setFillColor(BLUE)
        c.rect(0, H * 0.42 - 3 * mm, W, 3 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont(REGULAR, 12)
        c.drawString(M, H - 40 * mm, "TEACHER ASSIST")
        c.setFont(BOLD, 32)
        c.drawString(M, H - 70 * mm, "Teacher's guide")
        c.setFont(REGULAR, 15)
        c.drawString(M, H - 82 * mm, "Filling the Holistic Progress Card (HPC)")
        c.drawString(M, H - 90 * mm, "for your class on PARAKH")
        c.setFont(REGULAR, 10.5)
        c.setFillColor(colors.HexColor("#cbd5e1"))
        c.drawString(M, H * 0.42 + 14 * mm, "Sign in  ·  Connect to PARAKH  ·  Five steps  ·  Upload  ·  Fix and upload again")
        c.setFillColor(INK)
        c.setFont(BOLD, 12)
        c.drawString(M, H * 0.42 - 25 * mm, "Who this guide is for")
        c.setFont(REGULAR, 10.5)
        y = H * 0.42 - 33 * mm
        for line in ("Class teachers who fill the HPC for their students with Teacher Assist.",
                     "No computer skills are needed beyond opening an Excel file.",
                     "Keep it next to you the first time; after that, the app's five steps guide you."):
            c.drawString(M, y, line)
            y -= 6.5 * mm
        c.setFillColor(MUTED)
        c.setFont(REGULAR, 8.5)
        c.drawString(M, 20 * mm, "Teacher Assist is an independent tool that helps schools fill the HPC. It is not an official government service.")
        c.drawString(M, 14 * mm, f"Edition of {date.today().strftime('%B %Y')}.")
        c.restoreState()

    @staticmethod
    def page(c, doc):
        c.saveState()
        c.setStrokeColor(LINE)
        c.line(M, H - 14 * mm, W - M, H - 14 * mm)
        c.setFillColor(MUTED)
        c.setFont(REGULAR, 8)
        c.drawString(M, H - 11.5 * mm, "Teacher Assist · Teacher's guide")
        c.drawRightString(W - M, H - 11.5 * mm, "Holistic Progress Card (HPC)")
        c.line(M, 13 * mm, W - M, 13 * mm)
        c.drawRightString(W - M, 8.5 * mm, f"Page {doc.page - 1}")
        c.restoreState()


def b(text):
    return f"<b>{text}</b>"


def content():
    s = [NextPageTemplate("page"), PageBreak()]
    toc = TableOfContents()
    toc.levelStyles = [TOC1]
    toc.dotsMinLevel = 0
    s += [p("Contents", H1), Spacer(1, 4 * mm), toc, PageBreak()]

    # 1 -----------------------------------------------------------------
    s += [CondPageBreak(70 * mm), Chapter(1, "What the app does for you"),
          p("Teacher Assist fills your students' Holistic Progress Cards (HPC) on PARAKH for you. You give the answers once "
            "- on screen or in one Excel file for the whole class - and the app saves every student's card to PARAKH, "
            "part by part, and tells you exactly which ones were saved and which need a fix.", LEAD),
          Flow(["Sign in", "Connect", "Five steps", "Upload", "Done"],
               ["your school's login", "to PARAKH\n(captcha)", "students, activities,\nanswers, settings", "the Excel file\nis checked & saved",
                "saved / not saved\nlists"]),
          Spacer(1, 4 * mm),
          p("The card has the same parts as on PARAKH:"),
          table(["Part", "What it holds", "Where you fill it"],
                [["Part A1", "General details and attendance (working days, days present), mother tongue, medium, guardian.",
                  "Class settings (working days) and the Excel file"],
                 ["Part A2 / A3 / A4", "All about me, the student's own answers; parent-teacher partnership (Middle).",
                  "Common answers, a student's card or the Excel file"],
                 ["Part B", "One activity per subject and the three levels the student reached.", "Activities"],
                 ["Part C", "Overall levels and the teacher's remarks.", "Activities, Common answers or the Excel file"]],
                [18, 50, 32]),
          box("note", "Everything you do in the app stays a draft on this computer until it is saved to PARAKH. "
                      "Nothing reaches PARAKH until you press a save or upload button.")]

    # 2 -----------------------------------------------------------------
    s += [CondPageBreak(70 * mm), Chapter(2, "Before you start"),
          p("Have these ready:"),
          table(["You need", "Why", "Where to get it"],
                [["Your Teacher Assist username and password", "To sign in to the app.", "Your school (the head of school or the office) creates them."],
                 ["Your PARAKH login ID and password", "The app works on PARAKH with your own PARAKH login.", "The same login you use on the PARAKH website."],
                 ["Your mobile phone", "PARAKH may send a code by SMS.", "The number registered on PARAKH."],
                 ["Excel (or a program that opens .xlsx files)", "To fill the class file.", "Any computer with Microsoft Excel or LibreOffice."]],
                [30, 34, 36]),
          box("stop", "Never share your passwords or the SMS code, not even with a colleague. The app never asks for them "
                      "anywhere except its own sign-in boxes.")]

    # 3 -----------------------------------------------------------------
    s += [CondPageBreak(70 * mm), Chapter(3, "Sign in"),
          steps([f"Open the app's address your school gave you in Chrome, Edge or Firefox.",
                 f"Choose the {b('Teacher')} tab.",
                 f"Type the {b('username')} and {b('password')} your school gave you, then press {b('Sign in')}."]),
          box("tip", "After a few wrong passwords the app makes you wait a little before the next try. "
                     "This protects your account. Ask your school to reset the password if you forgot it."),
          box("warn", f"On a shared computer, always press {b('Sign out')} (bottom left) when you finish.")]

    # 4 -----------------------------------------------------------------
    s += [CondPageBreak(70 * mm), Chapter(4, "Connect to PARAKH"),
          p("The app works on PARAKH with your own PARAKH login. You connect once; the connection then stays open while you work."),
          steps([f"Press {b('Connect to PARAKH')} (you will see it until you are connected).",
                 f"Type your {b('PARAKH login ID')} and {b('PARAKH password')}.",
                 f"A {b('captcha')} picture appears: type the characters you see. If you cannot read it, ask for another picture.",
                 f"If PARAKH sends a code by SMS, type it in {b('Code from SMS')}.",
                 "The app shows that you are connected. You can now open your steps."]),
          box("note", "PARAKH ends connections after some time. When the app says the connection has ended, press "
                      f"{b('Reconnect')} (on the Students screen) and type the new captcha - your work in the app is not lost."),
          box("stop", "Only you type the captcha and the SMS code. The app never tries to get past them.")]

    # 5 -----------------------------------------------------------------
    s += [CondPageBreak(70 * mm), Chapter(5, "Your home: five steps"),
          p("After signing in you see your five steps as cards. Click a card to open it; "
            f"{b('Back to your steps')} at the top takes you back. The same steps are in the menu on the left."),
          Screen(), Spacer(1, 4 * mm),
          table(["Step", "What you do there"],
                [["1. Students", "See your class as on PARAKH, open any student's card, and fill or check it on screen."],
                 ["2. Activities", "Choose one activity per subject and the three levels each student reached (Part B)."],
                 ["3. Common answers", "Fill an answer once for the whole class, then change the few students who differ."],
                 ["4. Class settings", "Working days of each month, maximum marks, medium of instruction and the declaration."],
                 ["5. Excel & upload", "Download the class file, fill it, upload it - the app checks it and saves it to PARAKH."]],
                [24, 76]),
          box("tip", "You may work on screen (steps 1-4) or in Excel (step 5), or both. "
                     "Most teachers do steps 2-4 first, then download the Excel file in step 5 to check everything together.")]

    # 6 -----------------------------------------------------------------
    s += [CondPageBreak(70 * mm), Chapter(6, "Step 1 - Students"),
          p("Your class list comes from PARAKH, with each student's progress-card status."),
          steps(["Open the Students card.",
                 f"If your class has changed on PARAKH (a new student, a student left), press {b('Fetch from PARAKH')}.",
                 "Click a student to open the card. It is loaded from PARAKH (the first card of a stage can take about 10 seconds).",
                 f"Fill or correct the answers. Your changes are kept as a {b('draft')}; the card shows what is "
                 f"{b('On PARAKH')} and what you changed.",
                 f"When the card is complete, press {b('Submit to PARAKH')}. The app saves every part and marks it complete."]),
          box("tip", f"{b('Undo changes')} throws away your draft for that student and shows PARAKH's answers again."),
          box("note", "The app shows only the students of your own class. Students of other classes cannot be opened.")]

    # 7 -----------------------------------------------------------------
    s += [CondPageBreak(70 * mm), Chapter(7, "Step 2 - Activities (Part B)"),
          p("Part B needs, for every subject, one activity and the three levels the student reached. "
            "The activities come from PARAKH's own list for each stage, grade and subject."),
          steps(["Open the Activities card. Your students are listed with every subject.",
                 f"Use {b('Quick fill')} to set the same activity and levels for many students at once: choose the subject "
                 f"(or {b('All subjects')}), tick the students ({b('Tick all shown')} ticks the whole list), choose the levels.",
                 f"Choose {b('Each subject\'s own activity')} to give every subject its own activity for each student's grade.",
                 f"{b('Mix all levels')} spreads the levels across the class when the class is mixed.",
                 f"For cells that are already filled choose {b('Keep them')} or {b('Replace them')}, then apply.",
                 "Change any single student by clicking their cell."]),
          box("warn", f"If PARAKH already holds older activities for a student, tick {b('Replace older activities on PARAKH')} "
                      "to remove them when saving. Until then that student is shown as not ready.")]

    # 8 -----------------------------------------------------------------
    s += [CondPageBreak(70 * mm), Chapter(8, "Step 3 - Common answers"),
          p("Many answers are the same for most of the class (for example, a remark or an interest). Fill them once here."),
          steps(["Open the Common answers card and pick the question.",
                 f"Type or choose the answer and press {b('Apply to all')} - or use {b('Fill empty with')} to fill only the students who have no answer yet.",
                 "Change the few students whose answer differs, one by one.",
                 f"Use {b('Suggestions…')} for ready-made wording you can adapt."]),
          box("tip", "The screen shows how many students already have an answer for each question, so you can see what is left.")]

    # 9 -----------------------------------------------------------------
    s += [CondPageBreak(70 * mm), Chapter(9, "Step 4 - Class settings"),
          p("These settings apply to the whole class and go into the Excel file and onto PARAKH."),
          table(["Setting", "What to enter"],
                [["Medium of instruction", "Your class's medium, chosen from PARAKH's list."],
                 ["Rural / Urban", "Where the school is, as on PARAKH."],
                 ["Working days each month", "The number of working days of each month. Fill at least one month; "
                                             f"{b('Copy April to every month')} copies April's number to the rest. "
                                             "The total for the year is shown."],
                 ["Maximum summative marks per subject", f"The maximum marks of each subject; {b('Apply to all')} sets one number for every subject."],
                 ["Declaration (HPC Credit)", "The teacher's confirmation on the last page of the card."]],
                [26, 74]),
          steps([f"Fill the settings for each of your stages and press {b('Finish class settings')}."]),
          box("note", "If the working days in your Excel file and here differ, the app uses the Excel file's numbers when you upload it.")]

    # 10 ----------------------------------------------------------------
    s += [CondPageBreak(70 * mm), Chapter(10, "Step 5 - Excel & upload"),
          p("The Excel file holds your whole class: one row per student, one column per answer, with PARAKH's own choices "
            "in drop-down lists. It is the fastest way to check and send everything.", LEAD),
          p("Download", H2),
          steps([f"Open the Excel & upload card.",
                 f"Press {b('Download the Excel template')} for one stage - or use {b('All your stages in one file')} if you teach more than one stage.",
                 f"Only some students? Press {b('Download chosen students…')} and tick them.",
                 f"{b('Check all stages')} first tells you what is still missing, so the file you download is as complete as possible."]),
          p("Fill", H2),
          steps(["Open the file in Excel. Fill the white cells; the grey columns (names, IDs) identify each student - do not change them.",
                 "Use the drop-down lists where they are offered; type numbers as plain numbers.",
                 "You may delete rows of students you do not want to send this time.",
                 "Save the file (keep it as .xlsx)."]),
          p("Upload", H2),
          steps([f"Press {b('Upload the filled Excel file')} and choose your file.",
                 "The app checks the file at once and shows any problems, student by student. "
                 "Students with problems are skipped; every correct student is sent.",
                 f"The app saves to PARAKH and shows the progress live: {b('Saving to PARAKH…')}, then "
                 f"{b('Finished: all saved to PARAKH')} or {b('Finished, with some not saved')}.",
                 "You can keep working or close the page - saving carries on and the result waits for you."]),
          p("After the upload", H2),
          table(["You see", "What to do"],
                [["All saved", "Nothing more. The cards are on PARAKH."],
                 ["Some not saved because of PARAKH", f"Press {b('Retry')} - PARAKH was busy; nothing in your file is wrong."],
                 ["Some with a mistake in the file", f"Download {b('Excel: the … not saved - fix and upload')}. It holds only those "
                  "students, each with the reason. Correct them and upload that file."]],
                [30, 70]),
          box("tip", "A student already saved is never sent twice, so uploading the same file again is safe."),
          box("warn", "Do not upload an Excel file from another app or an older template. Download a fresh file from step 5.")]

    # 11 ----------------------------------------------------------------
    s += [CondPageBreak(70 * mm), Chapter(11, "A good routine"),
          p("Teachers who finish fastest work in this order:"),
          table(["When", "What"],
                [["Once", "Sign in, connect to PARAKH, fill Class settings (step 4)."],
                 ["Each term", "Activities (step 2) and Common answers (step 3) for the whole class."],
                 ["Then", "Download the Excel file (step 5), check it, fill what is missing, upload it."],
                 ["After the upload", "Retry what PARAKH did not take; fix and upload the 'not saved' file."],
                 ["At the end", "Check that every student shows as complete in Students (step 1). Sign out."]],
                [22, 78])]

    # 12 ----------------------------------------------------------------
    s += [CondPageBreak(70 * mm), Chapter(12, "When something goes wrong"),
          table(["What you see", "What it means", "What to do"],
                [["Not connected to PARAKH", "The PARAKH connection ended (it does after a while).", f"Press {b('Reconnect')} and type the captcha."],
                 ["The captcha is not accepted", "One character was misread.", "Ask for a new picture and type it again; letters may be upper or lower case."],
                 ["The first card takes long", "PARAKH's lists load once per stage.", "Wait about 10 seconds; later cards are faster."],
                 ["The file was not checked", "The file is not an Excel file from this app, or it is damaged.", "Download a fresh file in step 5 and copy your answers in."],
                 ["A student is skipped", "A required answer is missing or not allowed.", "Read the reason next to the student, correct the file, upload again."],
                 ["Some not saved because of PARAKH", "PARAKH was slow or busy.", f"Press {b('Retry')}. If it keeps failing, try later in the day."],
                 ["A new student is missing", "Your class list is older than PARAKH's.", f"Press {b('Fetch from PARAKH')} in Students (step 1), then download a new Excel file."],
                 ["The app waits after wrong passwords", "Protection against guessing.", "Wait a moment, or ask your school to reset your password."]],
                [27, 33, 40]),
          box("note", "If a problem stays, note the time and what you saw, and tell the person who manages the app at your school.")]

    # 13 ----------------------------------------------------------------
    s += [CondPageBreak(70 * mm), Chapter(13, "Privacy and good practice"),
          steps(["Your students' details are private. Do not print, photograph or share the Excel file outside school work.",
                 "Passwords and connections are kept encrypted on the school's computer, never in the Excel file.",
                 "Delete downloaded Excel files from shared computers when you are done.",
                 "Sign out at the end of your work, especially on a shared computer.",
                 "Check the answers before saving: what you save is what PARAKH shows on the card."]),
          CondPageBreak(70 * mm), Chapter(14, "Words used in the app"),
          table(["Word", "Meaning"],
                [["PARAKH", "The national portal where the Holistic Progress Card is kept."],
                 ["HPC", "Holistic Progress Card: each student's card for the year."],
                 ["Stage", "Foundational (Balvatika - Grade 2), Preparatory (Grades 3-5), Middle (Grades 6-8)."],
                 ["Draft", "Your changes kept in the app, not yet saved to PARAKH."],
                 ["Captcha", "The picture of characters PARAKH shows at sign-in, typed by you."],
                 ["Template / Excel file", "The class file downloaded from step 5 - the only file the app accepts."],
                 ["Saved / not saved", "Whether PARAKH accepted a student's card after an upload."],
                 ["APAAR ID", "The student's national academic ID, shown on PARAKH."]],
                [24, 76])]
    return s


def build(out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    Doc(out).multiBuild(content())
    return out


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "frontend" / "public" / "Teacher_Manual.pdf"
    print(build(target))
