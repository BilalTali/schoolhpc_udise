"""
A Field links one Excel column to one slot inside a part's portal formdata.

The portal stores each part as nested lists/dicts, e.g. Part A1 keeps mother tongue in
formdata["gen"][16]. A Field records that path plus how to show the value in Excel
(free text, a number, one choice from a list, or several choices).

Two kinds cover answers the portal stores as positions in a list of 0/1 values:
  onehot  one choice, stored as a single 1 among `span` slots (e.g. Yes / No / Don't know)
  flags   several choices, each stored as 1 or 0 in its own slot (tick boxes)
For both, options map a label to its offset inside the span.
  inlist  which of several comma-separated lists contains `member` (Foundational Part C keeps,
          per ability, one list of domains for each level); options map a label to a list index
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

Path = Tuple[Union[str, int], ...]


@dataclass
class Field:
    key: str                          # stable column id, e.g. "a1_mother_tongue"
    label: str                        # Excel header (portal wording)
    path: Path                        # where the value lives inside formdata
    kind: str = "text"                # text | int | choice | multi | onehot | flags | inlist
    options: Dict[str, Any] = field(default_factory=dict)  # Excel label -> stored value
    max_len: Optional[int] = None
    required: bool = False
    blank: Any = ""                   # value stored when the cell is empty
    span: Tuple[int, int] = (0, 0)    # onehot/flags: (first slot, number of slots) in the list at path
    member: str = ""                  # inlist: the code looked for in the lists

    # -- portal -> Excel -------------------------------------------------
    def read(self, formdata: Any) -> Any:
        value = get_path(formdata, self.path)
        if self.kind == "inlist":
            lists = list(value or [])
            return next((lbl for lbl, i in self.options.items()
                         if i < len(lists) and self.member in _members(lists[i])), "")
        if self.kind in ("onehot", "flags"):
            slots = list(value or [])
            on = [lbl for lbl, off in self.options.items()
                  if self.span[0] + off < len(slots) and str(slots[self.span[0] + off]) == "1"]
            return ", ".join(on) if self.kind == "flags" else (on[0] if on else "")
        if self.kind == "choice":
            return next((lbl for lbl, v in self.options.items() if str(v) == str(value)), "") if value not in (None, "") else ""
        if self.kind == "multi":
            chosen = {str(v) for v in (value or [])}
            return ", ".join(lbl for lbl, v in self.options.items() if str(v) in chosen)
        if value is None:
            return ""
        return value

    # -- Excel -> portal -------------------------------------------------
    def parse(self, cell: Any) -> Tuple[Any, Optional[str]]:
        """Converts an Excel cell to the stored value. Returns (value, error message or None)."""
        text = "" if cell is None else str(cell).strip()
        if text.endswith(".0") and text[:-2].isdigit():
            text = text[:-2]                       # Excel turns 22 into 22.0
        if not text:
            return self.blank, (f"{self.label}: required" if self.required else None)

        if self.kind == "int":
            if not text.lstrip("-").isdigit():
                return self.blank, f"{self.label}: '{text}' is not a whole number"
            return int(text), None
        if self.kind in ("choice", "onehot", "inlist"):
            match = _lookup(self.options, text)
            if match is None:
                return self.blank, _no_match(self.label, self.options, text)
            return match, None
        if self.kind in ("multi", "flags"):
            values, bad = [], []
            for part in (p.strip() for p in text.split(",")):
                if not part:
                    continue
                match = _lookup(self.options, part)
                (bad.append(part) if match is None else values.append(match))
            if bad:
                return values, f"{self.label}: unknown choice(s) {bad}"
            return values, None

        if self.max_len and len(text) > self.max_len:
            return text, f"{self.label}: {len(text)} characters, the portal allows {self.max_len}"
        return text, None

    def write(self, formdata: Any, cell: Any) -> Optional[str]:
        """Stores the cell into formdata. An unchanged cell leaves the stored value exactly as it was."""
        value, error = self.parse(cell)
        if error is not None:
            return error
        if self.kind == "multi":
            current = get_path(formdata, self.path) or []
            if {str(v) for v in current} == {str(v) for v in value}:
                return None                      # same choices: keep the portal's order
        elif self.kind == "inlist":
            if _cell_text(self.read(formdata)) == _cell_text(cell):
                return None
            lists = get_path(formdata, self.path)
            for i in range(len(lists)):
                kept = [m for m in _members(lists[i]) if m != self.member]
                if i == value:
                    kept.append(self.member)
                lists[i] = ",".join(kept)
            return None
        elif self.kind in ("onehot", "flags"):
            if {s.strip() for s in str(self.read(formdata)).split(",")} == {s.strip() for s in _cell_text(cell).split(",")}:
                return None
            slots = get_path(formdata, self.path)
            start, count = self.span
            chosen = set(value) if self.kind == "flags" else ({value} if value != self.blank else set())
            for off in range(count):
                if self.kind == "onehot" or off in self.options.values():
                    slots[start + off] = 1 if off in chosen else 0
            return None
        elif _cell_text(self.read(formdata)) == _cell_text(cell):
            return None
        set_path(formdata, self.path, value)
        return None

    def __post_init__(self):
        # Multi-choice cells are comma separated, so labels must not contain commas.
        if self.kind in ("multi", "flags"):
            self.options = {k.replace(",", " /"): v for k, v in self.options.items()}


def _members(text: Any) -> List[str]:
    return [m.strip() for m in str(text or "").split(",") if m.strip()]


def _cell_text(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return text[:-2] if text.endswith(".0") and text[:-2].isdigit() else text


def _lookup(options: Dict[str, Any], text: str):
    """The option a cell means: an exact label or stored value (any case), or else the only label that starts
    with what was typed - so "n" is No and "prof" is Proficient, as long as nothing else starts the same way."""
    low = text.lower()
    for label, value in options.items():
        if label.lower() == low or str(value).lower() == low:
            return value
    starts = [value for label, value in options.items() if label.lower().startswith(low)]
    return starts[0] if len(starts) == 1 else None


def _no_match(label: str, options: Dict[str, Any], text: str) -> str:
    starts = [o for o in options if o.lower().startswith(text.lower())]
    if len(starts) > 1:
        return f"{label}: '{text}' could be {' or '.join(starts)} - type a few more letters"
    return f"{label}: '{text}' is not one of {list(options)}"


def get_path(data: Any, path: Path) -> Any:
    for step in path:
        try:
            data = data[step]
        except (KeyError, IndexError, TypeError):
            return None
    return data


def set_path(data: Any, path: Path, value: Any) -> None:
    for step in path[:-1]:
        data = data[step]
    data[path[-1]] = value


def series(key: str, label: str, base: Path, labels: Sequence[str], **kwargs) -> List[Field]:
    """One Field per position of a list, e.g. 12 monthly attendance cells."""
    return [Field(f"{key}_{i + 1}", f"{label} - {item}", (*base, i), **kwargs) for i, item in enumerate(labels)]
