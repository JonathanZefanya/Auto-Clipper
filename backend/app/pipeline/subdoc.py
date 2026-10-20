"""F-16: dokumen subtitle yang bisa diedit, disimpan di <job>/subs/clip_<nn>.json.

Waktu baris relatif terhadap awal klip saat dokumen dibuat (`clip_start`). Jika klip di-trim,
`shift_lines` menggeser waktu ke rentang baru dan membuang bagian di luar klip.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.pipeline.subtitle import Line, Word

MIN_LINE_S = 0.05


@dataclass
class SubDoc:
    clip_start: float
    clip_end: float
    lines: list[Line] = field(default_factory=list)
    edited: bool = False

    def to_dict(self) -> dict:
        return {
            "clip_start": self.clip_start,
            "clip_end": self.clip_end,
            "edited": self.edited,
            "lines": [{"start": round(ln.start, 3), "end": round(ln.end, 3), "text": ln.text} for ln in self.lines],
        }

    @classmethod
    def from_dict(cls, d: dict) -> SubDoc:
        return cls(
            clip_start=float(d["clip_start"]),
            clip_end=float(d["clip_end"]),
            edited=bool(d.get("edited", False)),
            lines=[Line(float(x["start"]), float(x["end"]), str(x["text"])) for x in d.get("lines", [])],
        )


def subs_path(job_dir: Path, rank: int) -> Path:
    return job_dir / "subs" / f"clip_{rank:02d}.json"


def load_doc(job_dir: Path, rank: int) -> SubDoc | None:
    path = subs_path(job_dir, rank)
    if not path.exists():
        return None
    try:
        return SubDoc.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_doc(job_dir: Path, rank: int, doc: SubDoc) -> Path:
    path = subs_path(job_dir, rank)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def delete_doc(job_dir: Path, rank: int) -> None:
    subs_path(job_dir, rank).unlink(missing_ok=True)


def shift_lines(doc: SubDoc, start: float, end: float) -> list[Line]:
    """Waktu baris untuk rentang klip [start, end] (detik sumber) → relatif terhadap `start`."""
    offset = doc.clip_start - start
    dur = end - start
    out: list[Line] = []
    for ln in doc.lines:
        s = max(0.0, ln.start + offset)
        e = min(dur, ln.end + offset)
        if e - s >= MIN_LINE_S:
            out.append(Line(round(s, 3), round(e, 3), ln.text))
    return out


def is_stale(doc: SubDoc, start: float, end: float) -> bool:
    """Rentang klip berubah sejak transkripsi (bagian baru mungkin belum bersubtitle)."""
    return abs(doc.clip_start - start) > 1e-3 or abs(doc.clip_end - end) > 1e-3


def lines_to_words(lines: list[Line]) -> list[Word]:
    """Perkiraan waktu per kata (dibagi rata) — untuk teks thumbnail dari subtitle hasil edit."""
    words: list[Word] = []
    for ln in lines:
        parts = ln.text.split()
        if not parts:
            continue
        step = (ln.end - ln.start) / len(parts)
        for i, p in enumerate(parts):
            words.append(Word(ln.start + i * step, ln.start + (i + 1) * step, p))
    return words


def validate_lines(raw: list[dict], duration: float) -> list[Line]:
    """Validasi input editor: 0 ≤ start < end ≤ durasi klip, teks tidak kosong; diurutkan."""
    lines: list[Line] = []
    for i, x in enumerate(raw, start=1):
        try:
            s, e, text = float(x["start"]), float(x["end"]), str(x["text"]).strip()
        except (KeyError, TypeError, ValueError) as err:
            raise ValueError(f"Baris {i} tidak valid") from err
        if not text:
            raise ValueError(f"Baris {i}: teks kosong")
        if s < 0 or e > duration + 1e-3 or e - s < MIN_LINE_S:
            raise ValueError(f"Baris {i}: waktu harus 0 ≤ mulai < selesai ≤ {duration:g} dtk")
        lines.append(Line(round(s, 3), round(min(e, duration), 3), text))
    return sorted(lines, key=lambda ln: (ln.start, ln.end))
