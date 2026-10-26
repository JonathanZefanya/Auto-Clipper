"""F-10: subtitle otomatis dengan faster-whisper, hanya untuk rentang klip terpilih.

Catatan GPU (RTX 50 / Blackwell, sm_120):
- butuh CTranslate2 >= 4.6.3 (build CUDA 12.8) — diuji dengan 4.8.3 + cuBLAS 12.9 dari pip;
- INT8 dimatikan untuk sm_120 di CTranslate2 >= 4.6.2, jadi compute type GPU = float16;
- di Windows, DLL cuBLAS dari paket pip `nvidia-cublas-cu12` didaftarkan manual;
- jika CUDA gagal (DLL hilang, driver, OOM), otomatis fallback ke CPU int8.
"""
from __future__ import annotations

import gc
import glob
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.config import SubtitleConfig
from app.pipeline.audio import require_ffmpeg


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Line:
    start: float
    end: float
    text: str


# ---------------------------------------------------------------- audio segmen

def extract_audio_segment(
    source: Path, start: float, duration: float, sample_rate: int, audio_filter: str = "",
) -> np.ndarray:
    """Audio mono float32 hanya untuk rentang klip (≤ 60 dtk ≈ 4 MB), opsional dengan filter FFmpeg
    (mis. speechnorm agar suara streamer yang pelan terdengar oleh Whisper)."""
    af = ["-af", audio_filter] if audio_filter else []
    cmd = [
        require_ffmpeg(), "-nostdin", "-v", "error",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source),
        "-vn", *af, "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg gagal mengambil audio klip: {proc.stderr.decode(errors='replace').strip()}")
    return np.frombuffer(proc.stdout, dtype="<i2").astype(np.float32) / 32768.0


# ---------------------------------------------------------------- whisper

def is_hallucination(text: str, n_words: int, duration: float, no_speech_prob: float, cfg: SubtitleConfig) -> bool:
    """Segmen Whisper yang kemungkinan halusinasi di bagian musik/suara game.

    Tidak memakai no_speech_prob saja: ucapan asli yang pelan juga bisa bernilai ≥ 0.9 (uji nyata).
    - kata "direntang" (mis. 3 kata dalam 16 dtk) → hampir pasti bukan ucapan;
    - frasa penutup klasik ("terima kasih telah menonton", …) dengan no_speech tinggi.
    """
    if n_words and duration / n_words > cfg.hallucination_max_s_per_word:
        return True
    if no_speech_prob >= cfg.hallucination_min_no_speech:
        low = text.lower()
        if any(re.search(p, low) for p in cfg.hallucination_phrases):
            return True
    return False


def _register_cuda_dlls() -> None:
    """Windows: tambahkan site-packages/nvidia/*/bin (cuBLAS dari pip) ke pencarian DLL."""
    if sys.platform != "win32":
        return
    import site

    roots = [*site.getsitepackages(), site.getusersitepackages()]
    bundle = getattr(sys, "_MEIPASS", None)  # aplikasi desktop (PyInstaller, F-20)
    if bundle:
        roots.insert(0, bundle)
    for root in roots:
        for d in glob.glob(os.path.join(root, "nvidia", "*", "bin")):
            try:
                os.add_dll_directory(d)
            except OSError:
                continue
            if d not in os.environ.get("PATH", ""):
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def _cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


class Transcriber:
    """Context manager: muat model sekali untuk semua klip, lalu unload saat keluar."""

    def __init__(self, cfg: SubtitleConfig, log=print) -> None:
        self.cfg = cfg
        self.log = log
        self.model: Any = None
        self.device = ""

    def __enter__(self) -> Transcriber:
        _register_cuda_dlls()
        want = self.cfg.device
        if want == "auto":
            want = "cuda" if _cuda_available() else "cpu"
        if want == "cuda":
            try:
                self._load("cuda")
                return self
            except Exception as e:  # DLL, driver, arsitektur, OOM
                self.log(f"  [peringatan] Whisper di GPU gagal dimuat ({e}); fallback ke CPU.")
        self._load("cpu")
        return self

    def __exit__(self, *exc: object) -> None:
        self.unload()

    def _load(self, device: str) -> None:
        from faster_whisper import WhisperModel

        self.unload()
        if device == "cuda":
            name, compute = self.cfg.model, self.cfg.cuda_compute_type
        else:
            name, compute = self.cfg.cpu_model, self.cfg.cpu_compute_type
        self.log(f"  memuat model Whisper '{name}' di {device} ({compute}) ...")
        self.model = WhisperModel(name, device=device, compute_type=compute)
        self.device = device

    def unload(self) -> None:
        """Lepas model dari VRAM/RAM (CTranslate2 membebaskan memori saat objek dihapus)."""
        if self.model is not None:
            del self.model
            self.model = None
            gc.collect()

    def _transcribe(self, audio: np.ndarray) -> list[Word]:
        vad_params = dict(
            threshold=self.cfg.vad_threshold,
            min_silence_duration_ms=self.cfg.vad_min_silence_ms,
            speech_pad_ms=self.cfg.vad_speech_pad_ms,
        ) if self.cfg.vad_filter else None
        segments, _ = self.model.transcribe(
            audio,
            language=self.cfg.language,
            beam_size=self.cfg.beam_size,
            word_timestamps=True,
            vad_filter=self.cfg.vad_filter,
            vad_parameters=vad_params,
            condition_on_previous_text=False,  # kurangi halusinasi berulang di bagian berisik
        )
        words: list[Word] = []
        for seg in segments:  # generator: inferensi terjadi di sini
            n_words = len(seg.words or [])
            if is_hallucination(seg.text, n_words, seg.end - seg.start, seg.no_speech_prob, self.cfg):
                self.log(f"  segmen dibuang (halusinasi): {seg.text.strip()!r}")
                continue
            for w in seg.words or []:
                text = w.word.strip()
                if text:
                    words.append(Word(float(w.start), float(w.end), text))
        return words

    def transcribe(self, audio: np.ndarray) -> list[Word]:
        try:
            return self._transcribe(audio)
        except Exception as e:
            if self.device != "cuda":
                raise
            self.log(f"  [peringatan] transkripsi GPU gagal ({e}); ulang di CPU.")
            self._load("cpu")
            return self._transcribe(audio)


# ---------------------------------------------------------------- kata -> baris

_SENTENCE_END = re.compile(r"[.!?…,;:]$")


def join_words(parts) -> str:
    """Gabung token kata Whisper. Kata ulang/berimbuhan dipecah jadi 'teman' + '-teman', 'box' + '-nya'
    → disambung tanpa spasi ("teman-teman", "box-nya")."""
    out = ""
    for p in parts:
        out += p if (out and p.startswith("-")) or not out else f" {p}"
    return out


def cap_words(words: list[Word], max_word_s: float) -> list[Word]:
    """Batasi durasi kata: Whisper kadang memanjangkan kata sebelum jeda/musik sampai belasan detik."""
    return [Word(w.start, min(w.end, w.start + max_word_s), w.text) for w in words]


def cap_lines(lines: list[Line], max_s: float) -> list[Line]:
    """Batasi lama tampil baris (untuk subtitle otomatis yang tersimpan sebelum cap_words ada)."""
    return [Line(ln.start, min(ln.end, ln.start + max_s), ln.text) for ln in lines]


def group_words(words: list[Word], cfg: SubtitleConfig) -> list[Line]:
    """Kelompokkan 2–4 kata per baris; pisah pada jeda panjang atau akhir kalimat."""
    words = cap_words(words, cfg.max_word_s)
    groups: list[list[Word]] = []
    cur: list[Word] = []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt.start - w.end) if nxt else 0.0
        span = w.end - cur[0].start
        n = len(cur)
        if (
            nxt is None
            or n >= cfg.max_words
            or gap > cfg.max_word_gap_s
            or span >= cfg.max_line_s
            or (n >= cfg.min_words and _SENTENCE_END.search(w.text))
        ):
            groups.append(cur)
            cur = []

    # Baris 1 kata digabung ke baris sebelumnya bila masih muat & jedanya dekat.
    merged: list[list[Word]] = []
    for g in groups:
        if (
            len(g) < cfg.min_words and merged
            and len(merged[-1]) + len(g) <= cfg.max_words
            and g[0].start - merged[-1][-1].end <= cfg.max_word_gap_s
        ):
            merged[-1] = merged[-1] + g
        else:
            merged.append(g)

    lines: list[Line] = []
    for g in merged:
        text = join_words(w.text for w in g)
        lines.append(Line(g[0].start, g[-1].end, text.upper() if cfg.uppercase else text))

    # Tahan baris sampai baris berikut bila jedanya kecil (mencegah kedip).
    held: list[Line] = []
    for i, ln in enumerate(lines):
        end = ln.end
        if i + 1 < len(lines) and 0 <= lines[i + 1].start - ln.end <= cfg.hold_gap_s:
            end = lines[i + 1].start
        held.append(Line(ln.start, max(end, ln.start + 0.05), ln.text))
    return held


# ---------------------------------------------------------------- ASS

def _ass_time(t: float) -> str:
    cs = max(0, int(round(t * 100)))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(
    lines: list[Line], cfg: SubtitleConfig, width: int, height: int,
    gameplay_top: int, gameplay_height: int,
) -> str:
    """ASS gaya Shorts: font tebal, outline hitam, tengah-bawah area gameplay."""
    baseline_y = gameplay_top + gameplay_height * cfg.position_in_gameplay
    margin_v = max(0, int(round(height - baseline_y)))
    font_name = re.sub(r"[,\r\n{}]", "", cfg.font_name).strip() or "Arial Black"
    pop = r"{\fscx80\fscy80\t(0,90,\fscx100\fscy100)}" if cfg.pop_animation else ""
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Shorts,{font_name},{cfg.font_size},{cfg.primary_color},&H000000FF,"
        f"{cfg.outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,{cfg.outline},{cfg.shadow},"
        f"2,{cfg.side_margin},{cfg.side_margin},{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = [
        f"Dialogue: 0,{_ass_time(ln.start)},{_ass_time(ln.end)},Shorts,,0,0,0,,{pop}{_ass_escape(ln.text)}"
        for ln in lines
    ]
    return header + "\n".join(events) + ("\n" if events else "")


def clamp_words(words: list[Word], duration: float) -> list[Word]:
    out = []
    for w in words:
        s, e = max(0.0, w.start), min(duration, w.end)
        if e > s:
            out.append(Word(s, e, w.text))
    return out
