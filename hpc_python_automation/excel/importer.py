"""
Importer: reads populated HPC Excel workbooks and parses them into normalized student records.
Supports:
  1. Multi-sheet workbooks (e.g. HPC_Preparatory_Blank, Sample_Filled_Student).
  2. Global Class Seeder ('Global_Class_Config'): automatically seeds class-wide defaults
     (12-month working days, max marks, grade, section, activity name) into student records.
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
import openpyxl

DEFAULT_WORKING_DAYS = {
    "apr_working_days": "22",
    "may_working_days": "23",
    "jun_working_days": "23",
    "jul_working_days": "22",
    "aug_working_days": "23",
    "sep_working_days": "22",
    "oct_working_days": "23",
    "nov_working_days": "23",
    "dec_working_days": "22",
    "jan_working_days": "23",
    "feb_working_days": "22",
    "mar_working_days": "23",
    "max_summative_marks": "33",
}


CANONICAL_KEY_ALIASES = {
    "apr_working_days": "apr_working_days",
    "apr": "apr_working_days",
    "april": "apr_working_days",
    "may_working_days": "may_working_days",
    "may": "may_working_days",
    "jun_working_days": "jun_working_days",
    "june": "jun_working_days",
    "jul_working_days": "jul_working_days",
    "july": "jul_working_days",
    "aug_working_days": "aug_working_days",
    "aug": "aug_working_days",
    "august": "aug_working_days",
    "sep_working_days": "sep_working_days",
    "sep": "sep_working_days",
    "september": "sep_working_days",
    "oct_working_days": "oct_working_days",
    "oct": "oct_working_days",
    "october": "oct_working_days",
    "nov_working_days": "nov_working_days",
    "nov": "nov_working_days",
    "november": "nov_working_days",
    "dec_working_days": "dec_working_days",
    "dec": "dec_working_days",
    "december": "dec_working_days",
    "jan_working_days": "jan_working_days",
    "jan": "jan_working_days",
    "january": "jan_working_days",
    "feb_working_days": "feb_working_days",
    "feb": "feb_working_days",
    "february": "feb_working_days",
    "mar_working_days": "mar_working_days",
    "mar": "mar_working_days",
    "march": "mar_working_days",
    "max_summative_marks": "max_summative_marks",
    "max_marks": "max_summative_marks",
    "max_marks_per_subject": "max_summative_marks",
    "max_marks_per_subject_(summative)": "max_summative_marks",
    "summative_max_marks": "max_summative_marks",
    "academic_year": "academic_year",
    "grade": "grade",
    "section": "section",
    "medium_of_instruction": "medium_of_instruction",
    "rural_urban": "rural_urban",
    "activity_name": "activity_name",
    "activity_subject": "activity_subject",
    "credits_earned": "credits_earned",
    "declaration_agreed": "declaration_agreed",
}

GLOBAL_SEEDER_AUTHORITATIVE_KEYS = {
    "apr_working_days", "may_working_days", "jun_working_days", "jul_working_days",
    "aug_working_days", "sep_working_days", "oct_working_days", "nov_working_days",
    "dec_working_days", "jan_working_days", "feb_working_days", "mar_working_days",
    "max_summative_marks", "activity_name", "activity_subject", "credits_earned",
    "declaration_agreed", "academic_year"
}


def _find_seeder_sheet(wb: openpyxl.Workbook) -> Optional[Any]:
    """Finds the Global Class Configuration / Seeder sheet by name or content inspection."""
    # 1. Check by explicit name pattern
    for name in wb.sheetnames:
        low = name.lower()
        if any(w in low for w in ("config", "seeder", "settings", "global")):
            return wb[name]

    # 2. Check Sheet 1 / first worksheet by inspecting cell content
    if wb.worksheets:
        first_ws = wb.worksheets[0]
        for r in range(1, min(30, first_ws.max_row + 1)):
            for c in range(1, min(10, first_ws.max_column + 1)):
                v = str(first_ws.cell(row=r, column=c).value or "").strip().lower()
                if "working_days" in v or "max_summative" in v or "parameter key" in v:
                    return first_ws

    # 3. Check any remaining sheet
    for ws in wb.worksheets:
        for r in range(1, min(15, ws.max_row + 1)):
            for c in range(1, min(6, ws.max_column + 1)):
                v = str(ws.cell(row=r, column=c).value or "").strip().lower()
                if "working_days" in v or "max_summative" in v or "parameter key" in v:
                    return ws
    return None


def _read_global_seeder(wb: openpyxl.Workbook) -> Dict[str, str]:
    """Extracts class-wide defaults from the Global_Class_Config or Sheet 1 seeder."""
    defaults = dict(DEFAULT_WORKING_DAYS)
    ws = _find_seeder_sheet(wb)
    if not ws:
        return defaults

    for r in range(1, ws.max_row + 1):
        row_cells = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]
        if not any(row_cells):
            continue

        matched_key = None
        key_col = -1
        for col_idx, cell_val in enumerate(row_cells):
            if cell_val is None:
                continue
            clean_s = str(cell_val).strip().lower().replace(" ", "_").replace(":", "").replace("-", "_")
            if clean_s in CANONICAL_KEY_ALIASES:
                matched_key = CANONICAL_KEY_ALIASES[clean_s]
                key_col = col_idx
                break
            for alias_k, canonical in CANONICAL_KEY_ALIASES.items():
                if alias_k in clean_s or clean_s in alias_k:
                    matched_key = canonical
                    key_col = col_idx
                    break
            if matched_key:
                break

        if matched_key and key_col >= 0:
            val = None
            # Standard template has value in column 3 (index 2)
            if len(row_cells) > 2 and row_cells[2] is not None and str(row_cells[2]).strip() != "":
                val = row_cells[2]
            else:
                # Scan for next non-empty cell in row
                for next_col in range(key_col + 1, len(row_cells)):
                    candidate = row_cells[next_col]
                    if candidate is not None and str(candidate).strip() != "":
                        val = candidate
                        break

            if val is not None:
                val_str = str(val).strip()
                try:
                    num_f = float(val_str)
                    if num_f.is_integer():
                        val_str = str(int(num_f))
                except (ValueError, TypeError):
                    pass
                if val_str:
                    defaults[matched_key] = val_str

    return defaults


def import_preparatory_workbook(file_path: Path, sheet_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Reads an HPC Preparatory workbook and returns a list of student records.
    Assumes:
      - Row 2: Human-readable labels
      - Row 3: Technical keys (snake_case)
      - Row 4+: Student data records
    
    Automatically incorporates class defaults from the Global_Class_Config / Sheet 1 seeder.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Workbook not found: {path}")

    wb = openpyxl.load_workbook(path, data_only=True)
    seeder_ws = _find_seeder_sheet(wb)
    global_defaults = _read_global_seeder(wb)

    target_sheets = []
    if sheet_name and sheet_name in wb.sheetnames:
        target_sheets = [wb[sheet_name]]
    else:
        seeder_title = seeder_ws.title if seeder_ws else ""
        data_sheet_names = [
            s for s in wb.sheetnames 
            if s != seeder_title and not any(w in s.lower() for w in ("config", "seeder", "settings"))
        ]
        target_sheets = [wb[s] for s in data_sheet_names]

    records = []
    for ws in target_sheets:
        keys = []
        labels = []
        for col in range(1, ws.max_column + 1):
            key = ws.cell(row=3, column=col).value
            label = ws.cell(row=2, column=col).value
            keys.append(str(key).strip() if key else f"col_{col}")
            labels.append(str(label).strip() if label else "")

        sheet_records = []
        for row_idx in range(4, ws.max_row + 1):
            row_vals = [ws.cell(row=row_idx, column=c).value for c in range(1, ws.max_column + 1)]
            if not any(row_vals):
                continue  # empty row

            record = {
                "_row_number": row_idx,
                "_sheet_name": ws.title,
                "data": {},
            }
            for col_idx, key in enumerate(keys):
                raw_val = row_vals[col_idx]
                val_str = str(raw_val).strip() if raw_val is not None else ""
                record["data"][key] = val_str

            # Apply Global Seeder defaults:
            # Authoritative class-wide parameters (working days, max marks, academic year, etc.)
            # from Sheet 1 OVERRIDE any stale defaults in student rows.
            for def_k, def_v in global_defaults.items():
                if def_k in GLOBAL_SEEDER_AUTHORITATIVE_KEYS:
                    record["data"][def_k] = def_v
                else:
                    if def_k not in record["data"] or not record["data"][def_k]:
                        record["data"][def_k] = def_v

            # Recalculate total working_days as sum of the 12 months
            months = ["apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec", "jan", "feb", "mar"]
            try:
                total_working = sum(int(record["data"].get(f"{m}_working_days", 0)) for m in months)
                if total_working > 0:
                    record["data"]["working_days"] = str(total_working)
            except Exception:
                pass

            # Only add if at least admission_number or student_name is present
            adm = record["data"].get("admission_number", "")
            name = record["data"].get("student_name", "")
            if adm or name:
                sheet_records.append(record)

        if sheet_records:
            records = sheet_records
            break

    return records
