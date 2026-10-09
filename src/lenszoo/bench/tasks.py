"""Benchmark task format and loader."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Task:
    id: str
    title: str
    prompt: str
    spec: dict            # efl, fno, hfov_deg, ttl_max, wavelengths_um, object ("inf")
    constraints: dict = field(default_factory=dict)   # efl_tol_rel, min_center_thickness, max_distortion_pct, max_elements
    scoring: dict = field(default_factory=dict)       # fields, freq_lpmm
    reference: dict = field(default_factory=dict)     # {"design_id":..., "spec_source":..., "exclude_patents":[...]}
    tags: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "Task":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**d)

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")

    # defaults ------------------------------------------------------------
    @property
    def efl_tol(self) -> float:
        return self.constraints.get("efl_tol_rel", 0.02)

    @property
    def fields(self) -> list[float]:
        return self.scoring.get("fields", [0.0, 0.5, 0.7, 0.85, 1.0])

    @property
    def freq(self) -> float:
        # default: quarter of the incoherent cutoff at 587.6 nm
        return self.scoring.get("freq_lpmm") or 0.25 / (0.5876e-3 * self.spec["fno"])


def load_tasks(folder: str | Path) -> list[Task]:
    return [Task.load(p) for p in sorted(Path(folder).glob("*.json"))]


def render_prompt(task: Task) -> str:
    """Natural-language prompt handed to an agent."""
    s = task.spec
    c = task.constraints
    return (f"{task.prompt}\nSpec: EFL = {s['efl']} mm (±{task.efl_tol*100:.0f}%), F/# = {s['fno']}, "
            f"half-FOV = {s['hfov_deg']} deg, TTL <= {s['ttl_max']} mm, object at infinity, visible F/d/C. "
            f"Constraints: at most {c.get('max_elements', 'any')} elements, center thickness >= "
            f"{c.get('min_center_thickness', 0.2)} mm, |distortion| <= {c.get('max_distortion_pct', 'n/a')}%. "
            f"Return a LensZoo JSON prescription.")
