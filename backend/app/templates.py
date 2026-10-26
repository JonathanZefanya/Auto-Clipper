"""F-08: template layout 9:16, disimpan sebagai JSON di data/templates/<nama>.json.

Koordinat box dinormalisasi 0..1 terhadap ukuran video sumber (x, y, w, h),
sehingga template yang sama berlaku untuk sumber 720p maupun 1080p.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

LAYOUT_TYPES = ("split", "center_crop")
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float

    def validate(self, label: str) -> None:
        for k, v in asdict(self).items():
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{label}.{k} harus di antara 0..1 (dapat {v})")
        if self.w <= 0 or self.h <= 0:
            raise ValueError(f"{label}: w dan h harus > 0")
        if self.x + self.w > 1.0 + 1e-6 or self.y + self.h > 1.0 + 1e-6:
            raise ValueError(f"{label} keluar dari frame (x+w / y+h > 1)")


@dataclass(frozen=True)
class Template:
    name: str
    layout_type: str
    facecam_box: Box | None = None
    gameplay_box: Box | None = None
    top_ratio: float = 0.4  # porsi tinggi facecam (atas) untuk layout split

    def validate(self) -> None:
        if not _NAME_RE.match(self.name):
            raise ValueError(f"Nama template tidak valid: {self.name!r} (pakai huruf, angka, - atau _)")
        if self.layout_type not in LAYOUT_TYPES:
            raise ValueError(f"layout_type harus salah satu dari {LAYOUT_TYPES}")
        if self.layout_type == "split":
            if self.facecam_box is None:
                raise ValueError("Template split wajib punya facecam_box")
            if not 0.1 <= self.top_ratio <= 0.9:
                raise ValueError("top_ratio harus di antara 0.1..0.9")
        if self.facecam_box:
            self.facecam_box.validate("facecam_box")
        if self.gameplay_box:
            self.gameplay_box.validate("gameplay_box")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Template:
        def box(v: Any) -> Box | None:
            return Box(**v) if v else None

        t = cls(
            name=d["name"],
            layout_type=d["layout_type"],
            facecam_box=box(d.get("facecam_box")),
            gameplay_box=box(d.get("gameplay_box")),
            top_ratio=float(d.get("top_ratio", 0.4)),
        )
        t.validate()
        return t


DEFAULT_TEMPLATES = [
    Template(name="center", layout_type="center_crop"),
    # Contoh: facecam di pojok kanan bawah sumber, gameplay bagian tengah.
    Template(
        name="contoh-split",
        layout_type="split",
        facecam_box=Box(x=0.74, y=0.62, w=0.26, h=0.38),
        gameplay_box=Box(x=0.12, y=0.0, w=0.76, h=1.0),
        top_ratio=0.4,
    ),
]


def ensure_default_templates(templates_dir: Path) -> None:
    templates_dir.mkdir(parents=True, exist_ok=True)
    for t in DEFAULT_TEMPLATES:
        path = templates_dir / f"{t.name}.json"
        if not path.exists():
            save_template(templates_dir, t)


def save_template(templates_dir: Path, template: Template) -> Path:
    template.validate()
    path = templates_dir / f"{template.name}.json"
    path.write_text(json.dumps(template.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_templates(templates_dir: Path) -> list[str]:
    return sorted(p.stem for p in templates_dir.glob("*.json"))


def load_template(templates_dir: Path, name: str) -> Template:
    if not _NAME_RE.match(name):
        raise ValueError(f"Nama template tidak valid: {name!r} (pakai huruf, angka, - atau _)")
    path = templates_dir / f"{name}.json"
    if not path.exists():
        available = ", ".join(list_templates(templates_dir)) or "(kosong)"
        raise ValueError(f"Template {name!r} tidak ditemukan di {templates_dir}. Tersedia: {available}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Template.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise ValueError(f"Template {path.name} tidak valid: {e}") from e
