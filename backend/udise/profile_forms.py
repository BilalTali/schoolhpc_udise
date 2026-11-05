"""
UDISE+ School Profile & Facilities: the yearly forms a school fills (DCF 1.31 to 2.28), question by question.

Taken from the Profile service's own pages (profile.udiseplus.gov.in): each form is read with
GET  udiseplus/school/{schoolId}/<path>   and saved with   POST udiseplus/school/{schoolId}/<path>
and the page saves exactly the fields it read, less the ones listed in NOT_SENT (and with modifiedBy/modifiedTime
dropped from the rows of a table form). The app does the same: it reads the form again just before saving, changes
only the answers edited in Excel, and sends the rest back as UDISE+ holds it.

A field:  (item, question, key, kind)
kinds:    "yn"        1-Yes, 2-No
          "yn3"       1-Yes, 2-No, 3-Yes, but not functional
          dict        a code -> words list of its own
          "opt:NAME"  a list UDISE+ gives per school (OPTION_LISTS)
          "multi:..." several codes, e.g. "1,3" (attendance captured by register and biometric)
          "classes"   class numbers taught together, e.g. "1,2"
          "num"       a whole number >= 0
          "dec"       a number with up to 2 decimals (distances, land area)
          "money"     rupees
          "year"      a 4-digit year
          "text"      words
Coded answers stored as 0 or 9 mean "not answered / not applicable" on UDISE+: the page shows them empty and so
does the workbook.

Table forms (1.56, 1.57) are a list of rows, one per item (id.itemId), with one value per level or class; in the
workbook each cell becomes one question row ("1.56.1 ... - Primary").

Not in the workbook (filled on the UDISE+ website): 1.1-1.30 basic profile (edited in the school directory),
1.63 vocational education under NSQF (only NSQF schools; a list of sectors), the state's own questions, the
sports list of 2.13 and the "school running in other school's building" pick of 2.1(a).
"""
from typing import Any, Dict, List, Optional, Tuple

YN = {1: "Yes", 2: "No"}
YN3 = {1: "Yes", 2: "No", 3: "Yes, but not functional"}
MONTHS = {i + 1: m for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                          "September", "October", "November", "December"])}
ATTENDANCE = "multi:1=Attendance Register;2=Electronically;3=Biometric"

NOT_SENT = ("certificationStatus", "formStatus", "modifiedBy", "modifiedTime", "smlAcademicYear")
ROW_NOT_SENT = ("modifiedBy", "modifiedTime")

# lists the Profile service gives per school: name -> path under school/{id}/
OPTION_LISTS = {"residential": "options/residential", "building": "options/schoolBuildingType"}

Field = Tuple[str, str, str, Any]

FORMS: List[Dict[str, Any]] = [
    {"key": "others", "dcf": "1.31 to 1.39", "title": "School Others Details", "path": "profile/form1", "fields": [
        ("1.31", "Does the School offer any Pre-Vocational Exposure at Upper-Primary Stage?", "prevocYn", "yn"),
        ("1.32", "Does the School run any Skill Training Center after School Hours?", "stcYn", "yn"),
        ("1.33", "Is this a Residential School?", "resiSchYn",
         {1: "Completely Residential", 2: "Partially Residential", 3: "Non-Residential"}),
        ("1.33(a)", "If Completely or Partially Residential: Type of Residential School", "resiSchType", "opt:residential"),
        ("1.34", "Is this a Shift School? (runs in more than one shift, e.g. morning and afternoon)", "shiftSchYn", "yn"),
        ("1.35", "Are majority of the pupils taught through their mother tongue at the Primary Level?", "mtonguePri", "yn"),
        ("1.36(a)", "Distance (km) to the nearest Govt./Govt. Aided Primary School/Section (e.g. 2.6)", "distancePri", "dec"),
        ("1.36(b)", "Distance (km) to the nearest Govt./Govt. Aided Upper Primary School/Section", "distanceUpr", "dec"),
        ("1.36(c)", "Distance (km) to the nearest Govt./Govt. Aided Secondary School/Section", "distanceSec", "dec"),
        ("1.36(d)", "Distance (km) to the nearest Govt./Govt. Aided Higher Secondary School/Junior college", "distanceHsec", "dec"),
        ("1.37", "Whether School is Approachable by All-Weather Roads?", "approachRoadYn", "yn"),
        ("1.38", "Number of Instructional Days (in previous academic year)", "noInstructDays", "num"),
        ("1.39", "Is Continuous and Comprehensive Evaluation (CCE) being implemented in School?", "cceYn", "yn"),
        ("1.39(a)", "Are cumulative records of pupils being maintained?", "pcrMaintainedYn", "yn"),
        ("1.39(b)", "If yes, are cumulative records of pupils being shared with parents?", "pcrSharedYn", "yn"),
    ]},
    {"key": "anganwadi", "dcf": "1.40 to 1.55", "title": "Anganwadi, SMC/SMDC & Others", "path": "profile/form2",
     "note": "Questions 1.40 to 1.55 are only for Government and Government Aided schools.", "fields": [
        ("1.40", "Whether Anganwadi Centre(s) is/are located inside the school premises?", "anganwadiYn", "yn"),
        ("1.40(a)", "Number of co-located Anganwadi Centre(s)", "noColocAnganwadi", "num"),
        ("1.40(a) I", "Anganwadi Centre I: Code", "anganwadiCode", "text"),
        ("1.40(a) I", "Anganwadi Centre I: Name", "anganwadiName", "text"),
        ("1.40(a) I", "Anganwadi Centre I: Children - Boys", "anganwadiStuB", "num"),
        ("1.40(a) I", "Anganwadi Centre I: Children - Girls", "anganwadiStuG", "num"),
        ("1.40(a) II", "Anganwadi Centre II: Code", "anganwadiCode2", "text"),
        ("1.40(a) II", "Anganwadi Centre II: Name", "anganwadiName2", "text"),
        ("1.40(a) II", "Anganwadi Centre II: Children - Boys", "anganwadiStuB2", "num"),
        ("1.40(a) II", "Anganwadi Centre II: Children - Girls", "anganwadiStuG2", "num"),
        ("1.40(a) III", "Anganwadi Centre III: Code", "anganwadiCode3", "text"),
        ("1.40(a) III", "Anganwadi Centre III: Name", "anganwadiName3", "text"),
        ("1.40(a) III", "Anganwadi Centre III: Children - Boys", "anganwadiStuB3", "num"),
        ("1.40(a) III", "Anganwadi Centre III: Children - Girls", "anganwadiStuG3", "num"),
        ("1.41", "Whether Balavatika is started in the co-located Anganwadi/school?", "balavatikaLocatedYn", "yn"),
        ("1.42", "Whether any Out of School Children enrolled in the school?", "ooscYn", "yn"),
        ("1.42(a)", "If Yes, whether enrolled Out of School Children are attending Special Training in school?", "oosceEnrYn", "yn"),
        ("1.43", "Number of students attending Remedial Teaching/Extra Classes in current year", "remedialTchEnrol", "num"),
        ("1.44", "Number of students attending Learning Enhancement classes", "learningEnhanceEnrol", "num"),
        ("1.45(a)", "Visits in previous academic year: Number of Academic inspections", "noInspect", "num"),
        ("1.45(b)", "Visits in previous academic year: by CRC Coordinator", "noVisitCrc", "num"),
        ("1.45(c)", "Visits in previous academic year: by Block level officer (BRC/BEO)", "noVisitBrc", "num"),
        ("1.45(d)", "Visits in previous academic year: by District/State level officers", "noVisitDis", "num"),
        ("1.45(e)", "Visits in previous academic year: by Regional Level Officer", "noVisitRlo", "num"),
        ("1.45(f)", "Visits in previous academic year: by Headquarter Level Officer", "noVisitHlo", "num"),
        ("1.46(a)", "Whether School Management Committee (SMC) has been constituted as per RTE norms?", "smcYn", "yn"),
        ("1.46(b)", "Whether School Development and Management Committee (SDMC) constituted as per Samagra Shiksha guidelines?",
         "smdcYn", {1: "Yes", 2: "No", 3: "Same as SMC"}),
        ("1.46(c)", "Number of SMC/SDMC meetings conducted in previous academic year", "smdcMeetings", "num"),
        ("1.46(d)", "Whether SMC/SDMC has prepared the School Development Plan?", "smdcSdpYn", "yn"),
        ("1.46(d)", "If Yes, the year of the School Development Plan", "smdcSdpYear", "year"),
        ("1.47(a)", "Whether the School Building Committee (SBC) has been constituted?", "smdcSbcYn", "yn"),
        ("1.47(b)", "Whether the School has constituted its Academic Committee (AC)?", "smdcAcadcomYn", "yn"),
        ("1.47(c)", "Whether the School has constituted its Parent-Teacher Association (PTA)?", "smdcPtaYn", "yn"),
        ("1.47(c)", "If Yes, number of PTA meetings held during the last academic year", "smdcPtaMeeting", "num"),
        ("1.48", "Is the school registered under Public Financial Management System (PFMS)?", "pfmsYn", "yn"),
        ("1.49", "Whether the school has multi-class units?", "multiClassUnitsYn", "yn"),
        ("1.49 I", "If Yes, classes taught together in one classroom (set I), e.g. 1,2", "ctt1", "classes"),
        ("1.49 II", "Classes taught together in one classroom (set II), e.g. 3,4", "ctt2", "classes"),
        ("1.49 III", "Classes taught together in one classroom (set III)", "ctt3", "classes"),
        ("1.50", "Is the school part of a School Complex?", "partOfComplexYn", "yn"),
        ("1.51", "Is the school a Hub School for the school complex?", "hubSchoolYn", "yn"),
        ("1.51", "If Yes, number of schools in the complex: Pre-Primary", "noPrePri", "num"),
        ("1.51", "If Yes, number of schools in the complex: Primary", "noPri", "num"),
        ("1.51", "If Yes, number of schools in the complex: Upper Primary", "noUpr", "num"),
        ("1.51", "If Yes, number of schools in the complex: Secondary", "noSec", "num"),
        ("1.51", "If Yes, number of schools in the complex: Higher Secondary", "noHsec", "num"),
        ("1.52", "Whether the school has undertaken any activity under Ek Bharat Shreshtha Bharat (EBSB)?", "ebsbYn", "yn"),
        ("1.53", "Is the School certified as Fit India School?", "certifiedFitIndiaYn", "yn"),
        ("1.54", "Is the school providing Holistic Report Card for every learner (peer/self/teacher assessment)?",
         "learnerHolisticRptcardYn", "yn"),
        ("1.55", "Whether Artificial Intelligence is being taught as part of syllabus/curriculum?", "ai_taught", "yn"),
    ]},
    {"key": "tlm", "dcf": "1.56", "path": "profile/form4", "table": True,
     "title": "Free text books, TLM, play material and graded supplementary material",
     "columns": [("prePri", "Pre-Primary", "pp"), ("pri", "Primary", "pri"), ("uppPri", "Upper Primary", "upr"),
                 ("sec", "Secondary", "sec"), ("hsec", "Higher Secondary", "hsec")],
     "rows": [
        (1, "1.56.1", "Whether complete set of free textbooks received?", "yn"),
        (2, "1.56.1.1", "When were the textbooks received in the current academic year? (month)", MONTHS),
        (3, "1.56.2", "Whether TLM available for each grade?", "yn"),
        (6, "1.56.3", "Whether the school received Graded Supplementary Material in previous academic year?", "yn"),
        (17, "1.56.3.1", "If Yes, does the school use graded supplementary material in classroom transactions?", "yn"),
        (12, "1.56.4", "Whether play material, games and sports equipment available for each grade?", "yn"),
        (13, "1.56.5", "Whether the school has provided free uniform to the students?", "yn"),
        (14, "1.56.5.1", "If Yes, the month the uniforms were provided in the current academic year", MONTHS),
    ]},
    {"key": "kpi", "dcf": "1.57", "path": "profile/form3", "table": True,
     "title": "Key Performing Indicators (KPI) on teaching, learning (previous academic year)",
     "columns": [(f"c{i}", f"Class {i}", f"c{i}") for i in range(1, 13)],
     "rows": [
        (4, "1.57.1", "Whether the school actively undertakes academic enrichment activities (project/group work, "
                      "portfolio, virtual labs, class performances, quizzes/debates, creative writing etc.)?", "yn"),
        (6, "1.57.2", "Number of students who received orientation on cyber safety", "num"),
        (7, "1.57.3", "Number of students who received training on psycho-social aspects", "num"),
    ]},
    {"key": "safety", "dcf": "1.58.1 to 1.58.20", "title": "Section 1B School Safety and Other Parameters",
     "path": "sch-pgi-details", "fields": [
        ("1.58.1", "Whether the School Disaster Management Plan (SDMP) has been developed?", "sdmpPlanYn", "yn"),
        ("1.58.2", "Whether Structural Safety Audit has been conducted?", "structSafaudYn", "yn"),
        ("1.58.3", "Whether Non-Structural Safety Audit has been conducted?", "nonstrSafaudYn", "yn"),
        ("1.58.4", "Whether CCTV Cameras are available in school?", "cctvCamYn", "yn"),
        ("1.58.4(a)", "Total number of CCTV cameras installed in the school", "totalFunctionalCctvCameras", "num"),
        ("1.58.5", "Whether Fire Extinguishers are installed?", "fireExtYn", "yn"),
        ("1.58.6", "Does the school have a nodal teacher for school safety?", "nodalTchYn", "yn"),
        ("1.58.7", "Do students and teachers undergo regular training in school safety and disaster preparedness?",
         "saftyTrngYn", "yn"),
        ("1.58.8", "Whether disaster management is being taught as part of the curriculum?", "dismgmtTaugYn", "yn"),
        ("1.58.9", "Whether school has received grant for Self Defense Training for Girls? (Govt. and Govt. aided only)",
         "slfdefGrtYn", "yn"),
        ("1.58.9(a)", "Number of girl students given Self Defense training (Upper Primary, Secondary, Higher Secondary)",
         "slfdefTrained", "num"),
        ("1.58.10", "Whether the school has displayed safety guidelines on Display Board?", "guideDisplayYn", "yn"),
        ("1.58.11", "Whether the school has appointed any teacher as a first level counsellor?", "tchFirstLevelCounsellor", "yn"),
        ("1.58.12", "Frequency of safety and security audit of the school involving all stakeholders", "safeSecAudit",
         {1: "Once", 2: "Twice", 3: "Three times", 4: "Four times", 5: "More than four times a year", 6: "None"}),
        ("1.58.13", "Is the school displaying photographs of all teachers in the school?", "teacherDisplayingPhoto", "yn"),
        ("1.58.14", "Has the school adopted/initiated Vidya Pravesh Module?", "vidyaPravesh", "yn"),
        ("1.58.15", "Students' attendance captured (one or more, e.g. 1,3)", "stuAtndnc", ATTENDANCE),
        ("1.58.16", "Teachers' attendance captured (one or more, e.g. 1,3)", "tchAtndnc", ATTENDANCE),
        ("1.58.17", "Whether the school has constituted Youth Club?", "schYouthClubYn", "yn"),
        ("1.58.18", "Whether the school has constituted Eco Club for Mission Life?", "schEcoClubYn", "yn"),
        ("1.58.19", "Whether Teacher Identity Cards are issued to all teachers in the school?", "tchIcardYn", "yn"),
        ("1.58.20", "State School Standard Authority (SSSA) self-certification obtained?", "selfCertObtainedYn", "yn"),
    ]},
    {"key": "receipts", "dcf": "1.59 to 1.62", "title": "Section 1C Receipts and Expenditure", "path": "school-rec-exp",
     "fields": [
        *[(item, f"{name} (Samagra Shiksha): {what} (Rs.)", key + suffix, "money")
          for item, name, key in [("1.59.1", "Composite School Grant", "compoGrt"), ("1.59.2", "Library Grant", "libGrt"),
                                  ("1.59.3", "Grant for Major Repairs", "majorGrant"),
                                  ("1.59.4", "Grant for Sports and Physical Education", "sportGrt"),
                                  ("1.59.5", "Grant for Media and Community Mobilization", "mediaGrt"),
                                  ("1.59.6", "Grant for Training of SMC/SDMC", "smcGrt"),
                                  ("1.59.7", "Grant for support at Preschool Level (primary schools/sections only)", "preschGrt")]
          for what, suffix in (("Receipt", "R"), ("Expenditure", "E"))],
        *[f for item, who, key in [("1.60.1", "Non-Govt. Organization (NGO)", "ngoAsst"),
                                   ("1.60.2", "Public Sector Undertaking (PSU)", "psuAsst"),
                                   ("1.60.3", "Community", "commAsst"), ("1.60.4", "Other", "othAsst")]
          for f in ((item, f"Financial assistance received in previous academic year from {who}?", key + "Yn", "yn"),
                    (item, f"If Yes, name of the {who}", key + "Name", "text"),
                    (item, f"If Yes, amount received from {who} (Rs.)", key + "Rcvd", "money"))],
        ("1.61.1", "Is the school maintaining an Inventory Register on ICT Items? (previous academic year)", "ictRegYn", "yn"),
        ("1.61.2", "Is the school maintaining an Inventory Register on Sports Equipment?", "sportRegYn", "yn"),
        ("1.61.3", "Is the school maintaining an Inventory Register on Library Books?", "libRegYn", "yn"),
        ("1.62.1", "Annual expenditure in previous academic year: Maintenance/Housekeeping (Rs.)", "maintenanceGrant", "money"),
        ("1.62.2", "Annual expenditure in previous academic year: Teachers' gross salary (Rs.)", "teachersGrant", "money"),
        ("1.62.3", "Annual expenditure in previous academic year: Construction Works (Rs.)", "constructionGrant", "money"),
        ("1.62.4", "Annual expenditure in previous academic year: Other (Rs.)", "othersGrant", "money"),
    ]},
    {"key": "buildings", "dcf": "2.1 to 2.6", "title": "Physical Facilities: building, classrooms, electricity, rooms",
     "path": "facility/form1", "fields": [
        ("2.1", "Status of present School Building", "bldStatus", "opt:building"),
        ("2.2(i)", "Total number of active building blocks (used for instruction and administration)", "bldBlkTot", "num"),
        ("2.2(i)", "Of these: Pucca blocks", "bldBlk", "num"),
        ("2.2(i)", "Of these: Partially Pucca blocks (pucca walls and floor, no concrete roof)", "bldBlkPpu", "num"),
        ("2.2(i)", "Of these: Kuchcha blocks", "bldBlkKuc", "num"),
        ("2.2(i)", "Of these: Tent", "bldBlkTnt", "num"),
        ("2.2(i)", "Storey-wise: Single-Storey blocks", "noSingleStorey", "num"),
        ("2.2(i)", "Storey-wise: Double-Storey blocks", "noDoubleStorey", "num"),
        ("2.2(i)", "Storey-wise: Triple-Storey blocks", "noTripleStorey", "num"),
        ("2.2(i)", "Storey-wise: Multi-Storey blocks", "noMultiStorey", "num"),
        ("2.2(ii)", "Dilapidated building blocks (certified by authority)", "bldBlkDptd", "num"),
        ("2.2(iii)", "New building(s) under construction", "bldBlkUndcons", "num"),
        ("2.3(a)", "Classrooms (labs, library, staff room NOT included): Pre-Primary", "clsrmsPrePri", "num"),
        ("2.3(a)", "Classrooms: Primary", "clsrmsPri", "num"),
        ("2.3(a)", "Classrooms: Upper Primary", "clsrmsUpr", "num"),
        ("2.3(a)", "Classrooms: Secondary", "clsrmsSec", "num"),
        ("2.3(a)", "Classrooms: Higher Secondary", "clsrmsHsec", "num"),
        ("2.3(a)", "Classrooms currently not in use", "clsrmsNotInst", "num"),
        *[("2.3(b)", f"Classrooms used for instruction, {kind}: {cond}", key, "num")
          for kind, keys in [("Pucca", ("clsrmsGd", "clsrmsMin", "clsrmsMaj", "clsrmsDptdPucca")),
                             ("Partially Pucca", ("clsrmsGdPpu", "clsrmsMinPpu", "clsrmsMajPpu", "clsrmsDptdPpu")),
                             ("Kuchcha", ("clsrmsGdKuc", "clsrmsMinKun", "clsrmsMajKuc", "clsrmsDptdKuc")),
                             ("Tent", ("clsrmsGdTnt", "clsrmsMinTnt", "clsrmsMajTnt", "clsrmsDptdTnt"))]
          for cond, key in zip(("In good condition", "Need minor repair", "Need major repair", "Dilapidated"), keys)],
        *[("2.3(c)", f"Classrooms currently NOT in use, {kind}: {cond}", key, "num")
          for kind, keys in [("Pucca", ("clsrmsNuGdPucca", "clsrmsNuMin", "clsrmsNuMaj", "clsrmsNuDptdPucca")),
                             ("Partially Pucca", ("clsrmsNuGdPpu", "clsrmsNuMinPpu", "clsrmsNuMajPpu", "clsrmsNuDptdPpu")),
                             ("Kuchcha", ("clsrmsNuGdKuc", "clsrmsNuMinKun", "clsrmsNuMajKuc", "clsrmsNuDptdKuc")),
                             ("Tent", ("clsrmsNuGdTnt", "clsrmsNuMinTnt", "clsrmsNuMajTnt", "clsrmsNuDptdTnt"))]
          for cond, key in zip(("In good condition", "Need minor repair", "Need major repair", "Dilapidated"), keys)],
        ("2.3(d)", "Number of classrooms under construction", "clsrmsUndCons", "num"),
        ("2.3(d)", "Number of classrooms in dilapidated condition (total of the Dilapidated rows of 2.3(b) and 2.3(c))",
         "clsrmsDptd", "num"),
        ("2.4", "Type of Boundary Wall", "bndrywallType",
         {1: "Pucca", 2: "Pucca but Broken", 3: "Barbed wire fencing", 4: "Hedges", 5: "No boundary walls", 6: "Others",
          7: "Partial", 8: "Under Construction"}),
        ("2.5(a)", "Whether electricity connection is available in the school?", "electricityYn", "yn3"),
        ("2.5(a)(i)", "If electricity: number of classrooms having fans", "totFans", "num"),
        ("2.5(a)(ii)", "If electricity: number of classrooms having ACs", "totAcs", "num"),
        ("2.5(a)(iii)", "If electricity: number of classrooms having heaters/blowers", "totHeaters", "num"),
        ("2.5(b)", "Whether Solar Panel is available in school?", "solarpanelYn", "yn3"),
        ("2.6(a)", "Number of total other rooms (excluding classrooms and toilets)", "othrooms", "num"),
        ("2.6(b) I", "Separate room for Head of School/Head Teacher/Principal?", "hmRoomYn", "yn"),
        ("2.6(b) II", "Separate room for Library?", "libraryRoomYn", "yn"),
        ("2.6(b) III", "Separate room for Assistant Head Teacher/Vice Principal?", "ahmvpRoomYn", "yn"),
        ("2.6(b) IV", "Separate common room for girls?", "comroomGYn", "yn"),
        ("2.6(b) V", "Staffroom for teachers?", "staffRoomYn", "yn"),
        ("2.6(b) VI", "Co-curricular activity room/arts and crafts room?", "craftRoomYn", "yn"),
        ("2.6(b) VII", "Number of laboratory rooms including computer labs", "totLab", "num"),
    ]},
    {"key": "toilets", "dcf": "2.7 to 2.19", "title": "Toilet and Other Facilities", "path": "facility/form2",
     "note": "The sports list of 2.13 (sport, playground, coach, area) is kept as UDISE+ holds it: change it on the website.",
     "fields": [
        ("2.7", "Does the School have Toilet(s)/Urinal(s)?", "toiletYn", "yn"),
        *[("2.7(a)(i)" if "Cwsn" not in key else "2.7(a)(ii)", f"{what}", key, "num" if not key.endswith("Water") else "yn")
          for what, key in [
              ("Boys toilet seats (excluding CWSN friendly): Total", "toiletb"),
              ("Boys toilet seats (excluding CWSN friendly): Functional", "toiletbFun"),
              ("Boys toilet seats (excluding CWSN friendly): Running water available?", "toiletbFunWater"),
              ("Girls toilet seats (excluding CWSN friendly): Total", "toiletg"),
              ("Girls toilet seats (excluding CWSN friendly): Functional", "toiletgFun"),
              ("Girls toilet seats (excluding CWSN friendly): Running water available?", "toiletgFunWater"),
              ("Boys CWSN friendly toilet seats: Total", "toiletbCwsn"),
              ("Boys CWSN friendly toilet seats: Functional", "toiletbCwsnFun"),
              ("Boys CWSN friendly toilet seats: Running water available?", "toiletbCwsnWater"),
              ("Girls CWSN friendly toilet seats: Total", "toiletgCwsn"),
              ("Girls CWSN friendly toilet seats: Functional", "toiletgCwsnFun"),
              ("Girls CWSN friendly toilet seats: Running water available?", "toiletgCwsnWater")]],
        ("2.7(a)(iii)", "Boys urinals: Total", "urinalsb", "num"),
        ("2.7(a)(iii)", "Boys urinals: Functional", "urinalsbFun", "num"),
        ("2.7(a)(iii)", "Boys urinals: Running water available?", "urinalsbWater", "yn"),
        ("2.7(a)(iii)", "Girls urinals: Total", "urinalsg", "num"),
        ("2.7(a)(iii)", "Girls urinals: Functional", "urinalsgFun", "num"),
        ("2.7(a)(iii)", "Girls urinals: Running water available?", "urinalsgWater", "yn"),
        ("2.7(b)", "Number of boys' toilets under construction", "toiletbUnderConst", "num"),
        ("2.7(b)", "Number of girls' toilets under construction", "toiletgUnderConst", "num"),
        ("2.7(c)", "Is hand washing facility with soap available near toilets/urinals block?", "handwashYn", "yn"),
        ("2.7(d)", "Location of the toilet facility", "locationToilet",
         {1: "Inside the School Building", 2: "Outside the School Building but in the School Premises"}),
        ("2.7(e)", "Whether incinerator is available in girls' toilet?", "incineratorYn", "yn3"),
        ("2.7(f)", "Whether the school has Sanitary Pad vending machine available?", "sanitaryYn",
         {1: "Yes", 2: "No", 3: "Yes, but not functional", 4: "No, Pads available with Class Teachers"}),
        ("2.8", "Hand washing facility with soap for washing hands before and after meal?", "handwashMealYn", "yn"),
        ("2.8", "If Yes, number of wash points", "handwashMealTot", "num"),
        ("2.9(a)", "Drinking water source: Hand pumps/Bore well", "handPumpYn", "yn3"),
        ("2.9(a)", "Drinking water source: Protected Well", "wellProtYn", "yn3"),
        ("2.9(a)", "Drinking water source: Unprotected Well", "wellUnprotYn", "yn3"),
        ("2.9(a)", "Drinking water source: Tap water", "tapYn", "yn3"),
        ("2.9(a)", "Drinking water source: Packaged/Bottled Water", "packWaterYn", "yn3"),
        ("2.9(a)", "Drinking water source: Other", "othsrcYn", "yn3"),
        ("2.9(a)", "If Other: name of the source", "othsrcName", "text"),
        ("2.9(a)", "Whether overhead tank/sump facility is available for tap water?", "overheadTankYn", "yn"),
        ("2.9(b)", "Whether water purifier/RO is available in the school?", "waterPurifierYn", "yn3"),
        ("2.9(c)", "Whether drinking water quality is tested from a water testing lab?", "waterTestedYn", "yn"),
        ("2.10", "Does the school have provision for rain water harvesting?", "rainHarvestYn", "yn3"),
        ("2.11(a)", "Library available?", "libraryYn", "yn"),
        ("2.11(a)", "Library: total number of books", "libBooks", "num"),
        ("2.11(a)", "Book Bank available?", "bookbankYn", "yn"),
        ("2.11(a)", "Book Bank: total number of books", "bkbnkBooks", "num"),
        ("2.11(a)", "Reading Corner available?", "readcornerYn", "yn"),
        ("2.11(a)", "Reading Corner: total number of books", "readcornerBooks", "num"),
        ("2.11(b)", "Does the school have a full-time librarian?", "librarianYn", "yn"),
        ("2.11(c)", "Does the school subscribe to newspapers/magazines?", "newspaperYn", "yn"),
        ("2.11(d)", "Number of times library books have been borrowed/read by children", "booksBorrowed", "num"),
        ("2.12(a)", "Approximate land area of the school", "schLandArea", "dec"),
        ("2.12(a)", "Unit of the land area", "schLandUnit", {1: "Square Meter", 2: "Square Feet", 3: "Square Yard"}),
        ("2.12(b)", "Whether land is available for expansion of school facilities?", "landAvlYn", "yn"),
        ("2.12(b)", "If Yes, Horizontal or Vertical or Both", "schLandAvlHv", {1: "Horizontal", 2: "Vertical", 3: "Both"}),
        ("2.12(c)", "Number of additional classrooms and other rooms required", "additionalClassRoom", "num"),
        ("2.13", "Whether Playground facility is available in the School?", "playgroundYn", "yn"),
        ("2.13", "If No, adequate arrangements to play outdoor games in an adjoining playground/municipal park?",
         "playgroundAltYn", "yn"),
        ("2.14(a)", "Whether health check-up of students was conducted in previous academic year?", "medchkYn", "yn"),
        ("2.14(a)(i)", "Total number of health check-ups conducted during last session", "medchkTot", "num"),
        ("2.14(a)(ii)", "Health check-up parameter carried out: Height", "healthHeightYn", "yn"),
        ("2.14(a)(ii)", "Health check-up parameter carried out: Weight", "healthWeightYn", "yn"),
        ("2.14(a)(ii)", "Health check-up parameter carried out: Eyes", "healthEyesYn", "yn"),
        ("2.14(a)(ii)", "Health check-up parameter carried out: Dental", "healthDentalYn", "yn"),
        ("2.14(a)(ii)", "Health check-up parameter carried out: Throat", "healthThroatYn", "yn"),
        ("2.14(b)", "De-worming tablets given to children", "dewormtabYn",
         {1: "Complete (two doses)", 2: "Partially (one dose)", 3: "Not Given"}),
        ("2.14(c)", "Iron and Folic acid tablets given to children as per guidelines of WCD?", "irontabYn", "yn"),
        ("2.14(d)", "Whether school maintains Annual health records?", "annualHealthRecordYn", "yn"),
        ("2.14(e)", "Is thermal scanner available in the school?", "thermalYn", "yn"),
        ("2.14(f)", "Is First Aid facility available?", "firstAidYn", "yn"),
        ("2.14(g)", "Are essential medicines available?", "lifeSavingYn", "yn"),
        ("2.15", "Whether ramp for disabled children to access school building exists?", "rampsYn", "yn"),
        ("2.15", "If Yes, whether hand-rails for the ramp are available?", "handrailsYn", "yn"),
        ("2.16", "Whether School has special educator?", "splEducatorYn", {1: "Dedicated", 2: "At cluster level", 3: "No"}),
        ("2.17(a)", "Whether Kitchen Garden is available in school?", "kitchenGardenYn", "yn"),
        ("2.17(b)", "Whether Kitchen shed is available in school?", "kitchenShedYn", "yn"),
        ("2.18(a)", "Dustbins for collection of waste: each classroom", "dstbnClsrmsYn", {1: "Yes and all", 2: "No", 3: "Yes but some"}),
        ("2.18(b)", "Dustbins for collection of waste: toilets", "dstbnToiletYn", {1: "Yes and all", 2: "No", 3: "Yes but some"}),
        ("2.18(c)", "Dustbins for collection of waste: kitchen", "dstbnKitchenYn", "yn"),
        ("2.19", "Does the school have furniture for students?", "furnitutreYn",
         {1: "Yes for all", 2: "Partial", 3: "No Furniture Available"}),
        ("2.19", "If Yes for all or Partial: number of students for whom furniture is available", "stusHvFurnt", "num"),
    ]},
    {"key": "equipment", "dcf": "2.20 to 2.23", "title": "Physical Facilities and Equipments in Schools",
     "path": "facility/form3", "fields": [
        ("2.20(a)", "Staff quarters (including residential quarters for Head Teacher/Principal and Asst. Head/Vice Principal)?",
         "staffQtrYn", "yn"),
        ("2.20(b)", "Tinkering Lab?", "tinkeringLabYn", "yn"),
        ("2.20(c)", "Integrated science laboratory (Physics, Chemistry and Biology practicals in one lab)?", "integratedLabYn", "yn"),
        *[f for n, level, key in [("I", "Primary", "Pri"), ("II", "Upper Primary", "Upr"), ("III", "Secondary", "Sec"),
                                   ("IV", "Higher Secondary", "Hsec")]
          for f in ((f"2.21 {n}", f"Boarding/Hostel facility available for {level}?", f"boarding{key}Yn", "yn"),
                    (f"2.21 {n}", f"{level} boarding: seats for boys", f"boarding{key}B", "num"),
                    (f"2.21 {n}", f"{level} boarding: seats for girls", f"boarding{key}G", "num"))],
        *[f for letter, lab, key in [("a", "Physics", "phyLab"), ("b", "Chemistry", "chemLab"), ("c", "Biology", "bioLab"),
                                      ("d", "Mathematics", "mathLab"), ("e", "Language", "langLab"), ("f", "Geography", "geoLab"),
                                      ("g", "Home Science", "homeScLab"), ("h", "Psychology", "psychoLab"),
                                      ("i", "Computer Science", "compLab")]
          for f in ((f"2.22({letter})", f"{lab} lab (Higher Secondary only): condition", key + "Cond",
                     {1: "Fully equipped", 2: "Partially equipped", 3: "Not Equipped", 4: "Lab Not Available"}),
                    (f"2.22({letter})", f"{lab} lab: separate room available?", key + "Yn", "yn"))],
        ("2.23(a)", "Audio/Visual/Public Address System", "audioSystemYn", "yn3"),
        ("2.23(b)", "Science Kit", "sciencekitYn", "yn3"),
        ("2.23(c)", "Maths Kit", "mathkitYn", "yn3"),
        ("2.23(d)", "Biometric device", "biometricDevYn", "yn3"),
    ]},
    {"key": "computers", "dcf": "2.24 to 2.28", "title": "Computers and Digital Initiatives", "path": "facility/form4",
     "fields": [
        *[f for letter, item, key, fun in [
              ("a", "Desktop/PCs", "desktop", "Fun"), ("b", "Laptop/Notebook", "laptop", "Fun"), ("c", "Tablets", "tablets", "Fun"),
              ("d", "PCs with Integrated Teaching Learning Devices", "teachdev", "Fun"),
              ("e", "Digital Boards with CMS/LMS", "digiBoard", "Fun"), ("f", "Projector", "projector", "Fun"),
              ("g", "Printer", "printer", "Fun"), ("h", "Scanner", "scanner", "Fun"), ("i", "Server", "server", "Fun"),
              ("j", "Web Camera", "webcam", "Fun"), ("k", "Smart TV", "smarttv", "Fun"),
              ("l", "Smart Classrooms (digital/smart boards, virtual classrooms, smart TV, IFP)", "smartClassTv", "Func"),
              ("m", "Mobile phones used for teaching", "mobile", "Fun"),
              ("n", "Generator/Inverters/Power Backup/Big UPS (above 1KVA)", "generator", "Fun")]
          for f in ((f"2.24({letter})", f"{item}: total functional units", key + "Tot", "num"),
                    (f"2.24({letter})", f"{item}: functional units for teaching (out of total)", key + fun, "num"))],
        ("2.25", "Is Computer/ICT Lab available in school?", "compIctLabYn", "yn"),
        ("2.25(a)(i)", "Number of Computer/ICT labs", "noCompIctLab", "num"),
        ("2.25(a)(ii)", "Number of desktops/laptops in all Computer/ICT labs", "ictTotDeskLaptop", "num"),
        ("2.25(a)(iii)", "Separate room(s) available for Computer/ICT lab?", "isIctSeparateRoom", "yn"),
        ("2.25(b)", "Is the ICT Lab available in the school under Samagra Shiksha?", "ictLabYn", "yn"),
        ("2.25(b)", "Year of implementation of the ICT lab", "ictImplYear", "year"),
        ("2.25(b)", "Whether the ICT lab is functional?", "ictlabFunYn", "yn"),
        ("2.25(b)", "Model implemented in the school", "ictModelImpl", {1: "BOOT Model", 2: "BOO Model", 3: "Other"}),
        ("2.25(b)", "Type of the ICT Instructor in the school", "ictInstrType", {1: "Full Time", 2: "Part Time", 3: "Not Available"}),
        ("2.26", "Does the School have Internet Facility?", "internetYn", "yn"),
        ("2.26(a)", "Type of internet facility", "internetCategory",
         {1: "Broadband/Leased line", 2: "USB Modem/dongle/Portable Hotspot", 3: "Telephone Line with Modem",
          4: "Mobile Phone Internet", 5: "Any Other Type of connection", 6: "VSAT"}),
        ("2.26(b)", "Is the internet used for pedagogical (teaching) purposes?", "internetAccessPedagogyYn", "yn"),
        ("2.27(a)", "Whether ICT based tools are being used for teaching?", "ictToolsYn", "yn"),
        ("2.27(b)", "Access to e-Contents/Digital Contents/resources at school?", "digiResYn", "yn"),
        ("2.27(c)", "Assistive tech-based solutions for CWSN?", "techSolnYn", "yn"),
        ("2.27(d)", "Access to DTH/TV channels?", "accessDthYn", "yn"),
        ("2.28", "Does the School have a Digital Library?", "digitalLabYn", "yn"),
        ("2.28", "If Yes, number of e-Books/e-Contents available", "digitalTot", "num"),
    ]},
]

BY_KEY = {f["key"]: f for f in FORMS}


def options(kind: Any, lists: Optional[Dict[str, Dict[int, str]]] = None) -> Optional[Dict[int, str]]:
    """The code -> words list of a coded answer (None for numbers and words)."""
    if isinstance(kind, dict):
        return kind
    if kind == "yn":
        return YN
    if kind == "yn3":
        return YN3
    if isinstance(kind, str) and kind.startswith("opt:"):
        return (lists or {}).get(kind[4:]) or {}
    if isinstance(kind, str) and kind.startswith("multi:"):
        return {int(c): w for c, w in (p.split("=", 1) for p in kind[6:].split(";"))}
    return None


def questions(form: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every question of a form as rows: {id, item, question, kind}. A table form gives one row per (item, column);
    its id is "itemId:column"."""
    if form.get("table"):
        return [{"id": f"{item_id}:{col}", "item": item, "question": f"{q} - {header}", "kind": kind,
                 "row": item_id, "col": col, "level": level}
                for item_id, item, q, kind in form["rows"] for col, header, level in form["columns"]]
    return [{"id": key, "item": item, "question": q, "kind": kind} for item, q, key, kind in form["fields"]]


def applies(q: Dict[str, Any], levels: set) -> bool:
    """A table cell for a level/class the school does not have is left out (the page hides it as well)."""
    return "level" not in q or q["level"] in levels


# Questions only for schools with a level (the page hides them for other schools).
LEVEL = {
    "clsrmsPrePri": "pp", "clsrmsSec": "sec", "clsrmsHsec": "hsec", "noSec": "sec", "noHsec": "hsec",
    "boardingSecYn": "sec", "boardingSecB": "sec", "boardingSecG": "sec",
    "boardingHsecYn": "hsec", "boardingHsecB": "hsec", "boardingHsecG": "hsec",
    "preschGrtR": "pri", "preschGrtE": "pri", "prevocYn": "upr",
    **{f"{lab}{s}": "hsec" for lab in ("phyLab", "chemLab", "bioLab", "mathLab", "langLab", "geoLab", "homeScLab",
                                        "psychoLab", "compLab") for s in ("Cond", "Yn")},
}

# Questions only for some school categories (the number before the dash of the school's category, e.g. "2-Primary
# with Upper Primary"), as the page decides.
CATEGORY = {"staffQtrYn": {3, 5, 6, 7, 8, 10, 11}, "tinkeringLabYn": {3, 5, 6, 7, 8, 10, 11},
            "integratedLabYn": {3, 5, 6, 7, 8, 10}}


def for_school(qid: str, levels: set) -> bool:
    """Is this question on the school's form at all (its levels and category)?"""
    if LEVEL.get(qid) and LEVEL[qid] not in levels:
        return False
    cats = CATEGORY.get(qid)
    return not cats or any(f"cat{c}" in levels for c in cats) or not any(x.startswith("cat") for x in levels)


# "If ... then" questions: asked only when the answer they hang on is one of these (or above 0 for "pos").
_YES, _YES3 = {1}, {1, 3}
WHEN: Dict[str, Tuple[str, Any]] = {
    "resiSchType": ("resiSchYn", {1, 2}), "pcrMaintainedYn": ("cceYn", _YES), "pcrSharedYn": ("pcrMaintainedYn", _YES),
    "noColocAnganwadi": ("anganwadiYn", _YES),
    **{k: ("anganwadiYn", _YES) for k in ("anganwadiCode", "anganwadiName", "anganwadiStuB", "anganwadiStuG")},
    **{k: ("noColocAnganwadi", 2) for k in ("anganwadiCode2", "anganwadiName2", "anganwadiStuB2", "anganwadiStuG2")},
    **{k: ("noColocAnganwadi", 3) for k in ("anganwadiCode3", "anganwadiName3", "anganwadiStuB3", "anganwadiStuG3")},
    "oosceEnrYn": ("ooscYn", _YES), "smdcSdpYear": ("smdcSdpYn", _YES), "smdcPtaMeeting": ("smdcPtaYn", _YES),
    "ctt1": ("multiClassUnitsYn", _YES), "ctt2": ("multiClassUnitsYn", "never"), "ctt3": ("multiClassUnitsYn", "never"),
    **{k: ("hubSchoolYn", _YES) for k in ("noPrePri", "noPri", "noUpr", "noSec", "noHsec")},
    "totalFunctionalCctvCameras": ("cctvCamYn", _YES), "slfdefTrained": ("slfdefGrtYn", _YES),
    **{f"{p}{s}": (f"{p}Yn", _YES) for p in ("ngoAsst", "psuAsst", "commAsst", "othAsst") for s in ("Name", "Rcvd")},
    **{k: ("electricityYn", _YES3) for k in ("totFans", "totAcs", "totHeaters")},
    **{k: ("clsrmsNotInst", "pos") for k in ("clsrmsNuGdPucca", "clsrmsNuMin", "clsrmsNuMaj", "clsrmsNuDptdPucca",
                                             "clsrmsNuGdPpu", "clsrmsNuMinPpu", "clsrmsNuMajPpu", "clsrmsNuDptdPpu",
                                             "clsrmsNuGdKuc", "clsrmsNuMinKun", "clsrmsNuMajKuc", "clsrmsNuDptdKuc",
                                             "clsrmsNuGdTnt", "clsrmsNuMinTnt", "clsrmsNuMajTnt", "clsrmsNuDptdTnt")},
    "toiletbFunWater": ("toiletb", "pos"), "toiletgFunWater": ("toiletg", "pos"),
    "toiletbCwsnWater": ("toiletbCwsn", "pos"), "toiletgCwsnWater": ("toiletgCwsn", "pos"),
    "urinalsbWater": ("urinalsb", "pos"), "urinalsgWater": ("urinalsg", "pos"),
    **{k: ("toiletYn", _YES) for k in ("handwashYn", "locationToilet", "incineratorYn", "sanitaryYn")},
    "handwashMealTot": ("handwashMealYn", _YES), "othsrcName": ("othsrcYn", _YES3), "overheadTankYn": ("tapYn", _YES3),
    "schLandAvlHv": ("landAvlYn", _YES), "playgroundAltYn": ("playgroundYn", {2}),
    **{k: ("medchkYn", _YES) for k in ("medchkTot", "healthHeightYn", "healthWeightYn", "healthEyesYn", "healthDentalYn",
                                       "healthThroatYn")},
    "handrailsYn": ("rampsYn", _YES), "stusHvFurnt": ("furnitutreYn", {1, 2}),
    **{k: ("compIctLabYn", _YES) for k in ("noCompIctLab", "ictTotDeskLaptop", "isIctSeparateRoom")},
    **{k: ("ictLabYn", _YES) for k in ("ictImplYear", "ictlabFunYn", "ictModelImpl", "ictInstrType")},
    **{k: ("internetYn", _YES) for k in ("internetCategory", "internetAccessPedagogyYn")},
    "digitalTot": ("digitalLabYn", _YES),
}
# table forms: a row asked only when the row it hangs on says Yes in the same column
ROW_WHEN = {2: 1, 17: 6, 14: 13}


def asked(form: Dict[str, Any], q: Dict[str, Any], data: Any, levels: set) -> bool:
    """Is this question asked of this school, given its levels and its answers now?"""
    if not applies(q, levels) or not for_school(q["id"], levels):
        return False
    if form.get("table"):
        parent = ROW_WHEN.get(q["row"])
        if parent is None:
            return True
        row = next((r for r in data or [] if (r.get("id") or {}).get("itemId") == parent), {})
        return str(row.get(q["col"])) == "1"
    rule = WHEN.get(q["id"])
    if not rule or not isinstance(data, dict):
        return True
    parent, test = rule
    value = data.get(parent)
    if test == "never":
        return False
    if test == "pos" or isinstance(test, int):
        try:
            return float(value or 0) >= (test if isinstance(test, int) else 0.000001)
        except (TypeError, ValueError):
            return False
    try:
        return int(value) in test
    except (TypeError, ValueError):
        return False


def school_levels(school: Dict[str, Any]) -> set:
    """The levels and classes a school has, from its basic profile: classFrom/classTo and pre-primary."""
    out = set()
    try:
        lo, hi = int(school.get("classFrom") or 1), int(school.get("classTo") or 12)
    except (TypeError, ValueError):
        lo, hi = 1, 12
    for c in range(max(lo, 1), min(hi, 12) + 1):
        out.add(f"c{c}")
    if lo <= 5 and hi >= 1:
        out.add("pri")
    if lo <= 8 and hi >= 6:
        out.add("upr")
    if lo <= 10 and hi >= 9:
        out.add("sec")
    if hi >= 11:
        out.add("hsec")
    if str(school.get("isppsec") or "") == "1" or lo <= 0:
        out.add("pp")
    category = str(school.get("schCategoryId") or "").split("-")[0].strip()
    if category.isdigit():
        out.add(f"cat{int(category)}")
    return out
