"""Stage definitions: which parts a stage has and how each one is filled."""
from types import ModuleType

from backend.hpc.portal import stage_code


def get_stage(stage: str) -> ModuleType:
    code = stage_code(stage)
    if code == "FOUNDATIONAL":
        from backend.hpc.stages import foundational
        return foundational
    if code == "PREPARATORY":
        from backend.hpc.stages import preparatory
        return preparatory
    if code == "MIDDLE":
        from backend.hpc.stages import middle
        return middle
    raise ValueError(f"No stage definition for {stage!r}")
