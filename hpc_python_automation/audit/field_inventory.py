"""
Field inventory: extracts canonical form schema from browser audit data.

Generates:
  - config/stage_schemas.json (canonical field definitions, types, options, validation)
  - reports/field_inventory.json (detailed breakdown by stage and section)
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIT_FILE = ROOT / "hpc_field_audit.json"
CONFIG_SCHEMA = ROOT / "config" / "stage_schemas.json"
REPORTS_DIR = ROOT / "reports"


def clean_label(text: str) -> str:
    """Clean label string from extra spaces or unicode artifacts."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')


def derive_field_key(item: dict, index: int) -> str:
    """Generate a clean snake_case programmatic key for a field."""
    label = item.get("label", "").strip()
    section = item.get("section", "").strip()
    allowed = item.get("allowed_values", "").strip()
    control_type = item.get("control_type", "").strip()
    placeholder = item.get("placeholder", "").strip()
    url = item.get("page_url", "")

    # Competency checkbox in Part-B (e.g. VAC1.1, TC2.1)
    if allowed and re.match(r"^[A-Z0-9]+(\.[A-Z0-9]+)*$", allowed):
        return f"comp_{allowed.replace('.', '_')}"

    # Interests (e.g. STU_INTRST_READING)
    if allowed.startswith("STU_INTRST_"):
        return allowed.lower()

    # Part-A1 fields
    if "Student Name" in label:
        return "student_name"
    if "School Admission Number" in label:
        return "admission_number"
    if "Date of Birth" in label:
        return "dob"
    if "Gender" in label:
        return "gender"
    if "HPC Login ID" in label:
        return "hpc_login_id"
    if "Grade 3" in label:
        return "grade_3"
    if "Grade 4" in label:
        return "grade_4"
    if "Grade 5" in label:
        return "grade_5"
    if "Mother Tongue" in label:
        return "mother_tongue"
    if "Guardian" in label and "Name" in label:
        return "guardian_name"
    if "How many times" in label:
        return "absenteeism_frequency"
    if "Activity Name" in label:
        return "activity_name"

    # Part-B Rating scale
    if allowed in ("beginner", "proficient", "advance"):
        return f"rating_{allowed}"

    # Fallback using label or placeholder
    source = label or placeholder or section or f"field_{index}"
    clean = re.sub(r"[^a-zA-Z0-9_]+", "_", source.lower()).strip("_")
    return clean[:40] if clean else f"field_{index}"


def build_inventory(audit_path: Path = AUDIT_FILE) -> dict:
    if not audit_path.exists():
        raise FileNotFoundError(f"Audit file not found: {audit_path}")

    raw_data = json.loads(audit_path.read_text(encoding="utf-8"))

    schemas = {}
    stage = "Preparatory"
    sections = {}

    for i, item in enumerate(raw_data):
        url = item.get("page_url", "").split("?")[0]
        page_name = url.split("/")[-1] if "/" in url else "general"
        section_name = item.get("section") or page_name or "General"
        label = clean_label(item.get("label") or item.get("placeholder") or "")
        control_type = item.get("control_type", "text")
        allowed_values = [v.strip() for v in item.get("allowed_values", "").split(";") if v.strip()]

        key = derive_field_key(item, i)

        sec_entry = sections.setdefault(section_name, {})
        if key not in sec_entry:
            sec_entry[key] = {
                "key": key,
                "label": label or key,
                "control_type": control_type,
                "section": section_name,
                "page": page_name,
                "required": bool(item.get("required")),
                "readonly": bool(item.get("readonly")),
                "allowed_values": allowed_values,
                "maxlength": int(item["maxlength"]) if str(item.get("maxlength", "")).isdigit() else None,
                "minlength": int(item["minlength"]) if str(item.get("minlength", "")).isdigit() else None,
            }

    # Flatten into canonical stage schema
    stage_schema = {
        "stage": stage,
        "sections": {
            sec_name: list(fields.values())
            for sec_name, fields in sections.items()
        },
        "total_unique_fields": sum(len(fields) for fields in sections.values()),
    }

    schemas[stage] = stage_schema

    # Save to config/stage_schemas.json
    CONFIG_SCHEMA.parent.mkdir(exist_ok=True)
    CONFIG_SCHEMA.write_text(json.dumps(schemas, indent=2, ensure_ascii=False), encoding="utf-8")

    # Save detailed report
    REPORTS_DIR.mkdir(exist_ok=True)
    report_file = REPORTS_DIR / "field_inventory.json"
    report_file.write_text(json.dumps(schemas, indent=2, ensure_ascii=False), encoding="utf-8")

    return schemas


def main():
    print(f"Loading audit data from {AUDIT_FILE}...")
    schemas = build_inventory()
    prep = schemas["Preparatory"]
    print(f"\n[OK] Built Canonical Schema for '{prep['stage']}' Stage:")
    print(f"Total Unique Fields: {prep['total_unique_fields']}")
    for sec, fields in prep["sections"].items():
        print(f"  - {sec:35} : {len(fields):3d} fields")
    print(f"\nSaved to: {CONFIG_SCHEMA}")


if __name__ == "__main__":
    main()
