"""Semua parameter aplikasi. Default di sini, bisa ditimpa via data/config.json lalu flag CLI."""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data"
_ASS_COLOR_RE = re.compile(r"^&H[0-9A-Fa-f]{8}$")
_SAFE_MODEL_URL_PREFIX = "https://storage.googleapis.com/mediapipe-models/"
_WHISPER_MODELS = ("medium", "large-v3")
# F-19: Ollama hanya di mesin ini (cegah pengaturan diarahkan ke server lain)
_LOCAL_URL_RE = re.compile(r"^http://(127\.0\.0\.1|localhost|\[::1\])(:\d{1,5})?/?$")
_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/]{0,80}(:[A-Za-z0-9._\-]{1,40})?$")


class _Overridable:
    def with_overrides(self, **overrides: Any):
        known = {f.name for f in fields(self)}  # type: ignore[arg-type]
        return replace(self, **{k: v for k, v in overrides.items() if k in known and v is not None})  # type: ignore[type-var]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)  # type: ignore[call-overload]


@dataclass(frozen=True)
class DetectConfig(_Overridable):
    # Peak picking (F-05)
    sensitivity: float = 0.5          # 0..1, makin besar makin banyak klip
    threshold_z_max: float = 3.5      # ambang z-score saat sensitivity = 0
    threshold_z_min: float = 1.0      # ambang z-score saat sensitivity = 1
    min_peak_gap_s: int = 60
    pad_before_s: int = 20
    pad_after_s: int = 15
    max_clip_s: int = 60
    smooth_window_s: int = 5
    # Puncak di awal (intro/sapaan) & akhir video (outro "sampai jumpa") tidak dijadikan kandidat
    exclude_start_s: int = 30
    exclude_end_s: int = 45

    # Bobot skor gabungan (PRD §12.4); tanpa chat -> audio saja
    w_audio: float = 0.5
    w_chat: float = 0.5

    # Chat (F-04)
    chat_delay_s: int = 7
    chat_window_s: int = 10
    chat_baseline_s: int = 60

    # Audio (F-03)
    audio_sample_rate: int = 16000
    audio_chunk_s: int = 60
    audio_baseline_s: int = 60
    audio_floor_db: float = -100.0

    # Reaksi tawa/teriak (F-15): YAMNet via MediaPipe AudioClassifier
    reaction_enabled: bool = True
    w_reaction: float = 0.5
    reaction_baseline_s: int = 60
    reaction_model_url: str = (
        "https://storage.googleapis.com/mediapipe-models/audio_classifier/"
        "yamnet/float32/1/yamnet.tflite"
    )
    reaction_classes: tuple[str, ...] = (
        "Laughter", "Giggle", "Snicker", "Belly laugh", "Chuckle, chortle",
        "Shout", "Bellow", "Whoop", "Yell", "Screaming", "Cheering", "Children shouting",
    )

    # Reaksi wajah (F-18): MediaPipe Face Landmarker (blendshapes) di area facecam
    face_enabled: bool = True
    w_face: float = 0.5
    face_fps: float = 2.0               # frame per detik yang dibaca (decode CPU ±25× realtime untuk 1080p60)
    face_size: int = 256                # area facecam di-scale ke ukuran ini sebelum dibaca
    face_baseline_s: int = 60
    face_min_detect_frac: float = 0.3   # wajah harus terdeteksi di ≥ 30% frame (avatar VTuber sering gagal)
    face_model_url: str = (
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
        "face_landmarker/float16/1/face_landmarker.task"
    )

    # Unduhan (F-02)
    download_max_height: int = 1080

    @property
    def threshold_z(self) -> float:
        s = min(max(self.sensitivity, 0.0), 1.0)
        return self.threshold_z_max - s * (self.threshold_z_max - self.threshold_z_min)


@dataclass(frozen=True)
class RenderConfig(_Overridable):
    # F-08 / F-09
    width: int = 1080
    height: int = 1920
    fps: int = 30
    default_template: str = "center"
    video_encoder: str = "auto"       # auto | h264_nvenc | libx264
    nvenc_preset: str = "p5"
    nvenc_cq: int = 21
    x264_preset: str = "veryfast"
    x264_crf: int = 20
    audio_bitrate: str = "160k"


@dataclass(frozen=True)
class SubtitleConfig(_Overridable):
    # F-10
    enabled: bool = True
    model: str = "large-v3"           # medium | large-v3
    cpu_model: str = "medium"         # dipakai bila fallback ke CPU
    language: str = "id"
    device: str = "auto"              # auto | cuda | cpu
    # Blackwell (RTX 50, sm_120): INT8 dimatikan di CTranslate2 >= 4.6.2 -> pakai float16
    cuda_compute_type: str = "float16"
    cpu_compute_type: str = "int8"
    beam_size: int = 5
    vad_filter: bool = True
    # VAD lebih longgar dari default Silero (0.5): teriakan bercampur suara game tetap tertangkap
    vad_threshold: float = 0.3
    vad_min_silence_ms: int = 1000
    vad_speech_pad_ms: int = 500
    sample_rate: int = 16000
    # Pra-proses audio sebelum Whisper: suara streamer sering pelan di bawah suara game.
    # speechnorm menaikkan volume ucapan (uji nyata: kalimat yang terlewat jadi tertranskripsi). Kosong = mati.
    audio_filter: str = "highpass=f=150,lowpass=f=4000,speechnorm=e=12.5:r=0.0001:l=1"

    # Saring halusinasi Whisper di bagian musik/suara game
    hallucination_max_s_per_word: float = 3.0   # segmen dgn kata "direntang" > ini dibuang
    hallucination_min_no_speech: float = 0.5    # frasa klasik dibuang bila no_speech_prob ≥ ini
    hallucination_phrases: tuple[str, ...] = (
        r"terima kasih (telah|sudah|udah) menonton",
        r"sampai jumpa (lagi )?di video (selanjutnya|berikutnya)",
        r"jangan lupa (like|subscribe|komen)",
        r"subtitle(s)? (oleh|by)",
        r"thanks? for watching",
    )

    # Pengelompokan kata ala Shorts
    min_words: int = 2
    max_words: int = 4
    max_word_gap_s: float = 0.6       # jeda lebih panjang -> baris baru
    max_line_s: float = 2.5
    # Whisper kadang memanjangkan kata terakhir sampai melewati jeda panjang (baris "menggantung")
    max_word_s: float = 1.2
    hold_gap_s: float = 0.3           # tahan baris sampai baris berikut jika jedanya sekecil ini
    uppercase: bool = True

    # Gaya ASS
    font_name: str = "Arial Black"
    font_size: int = 86
    outline: int = 6
    shadow: int = 0
    primary_color: str = "&H00FFFFFF"   # ASS &HAABBGGRR (putih)
    outline_color: str = "&H00000000"   # hitam
    pop_animation: bool = True
    # Posisi baseline teks, sebagai fraksi tinggi area gameplay dari atas (tengah-bawah)
    position_in_gameplay: float = 0.78
    side_margin: int = 60


@dataclass(frozen=True)
class ThumbnailConfig(_Overridable):
    # F-11
    enabled: bool = True
    landscape: bool = False             # juga buat 1280x720
    landscape_width: int = 1280
    landscape_height: int = 720
    intro_frame: bool = False           # sisipkan thumbnail sebagai frame pembuka klip
    intro_duration_s: float = 0.1

    # Kandidat frame di sekitar puncak
    n_frames: int = 9
    window_before_s: float = 3.0
    window_after_s: float = 2.0

    # Deteksi wajah (MediaPipe Tasks FaceDetector)
    face_model_url: str = (
        "https://storage.googleapis.com/mediapipe-models/face_detector/"
        "blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
    )
    face_min_confidence: float = 0.5
    sharpness_ref: float = 150.0        # variance of Laplacian dianggap "tajam penuh"

    # Teks
    text_max_words: int = 5
    text_window_s: float = 3.0          # kata di sekitar puncak (± detik) untuk teks default
    fallback_text: str = "MOMEN SERU!"
    uppercase: bool = True
    font_path: str = ""                 # kosong = cari font tebal bawaan sistem
    font_size_ratio: float = 0.12       # ukuran font awal relatif lebar gambar
    min_font_size_ratio: float = 0.05
    max_lines: int = 3
    line_spacing: float = 1.05
    margin_ratio: float = 0.06
    text_color: str = "#FFFFFF"
    highlight_color: str = "#FFE600"    # warna kata terakhir; kosong = tanpa highlight
    stroke_color: str = "#000000"
    stroke_ratio: float = 0.09          # tebal outline relatif ukuran font
    # Posisi pusat teks (fraksi tinggi), dipilih yang menjauhi wajah
    text_y_top: float = 0.2
    text_y_bottom: float = 0.72


@dataclass(frozen=True)
class FacecamConfig(_Overridable):
    # F-17: auto-deteksi facecam
    frames: int = 12                    # jumlah frame sampel di sepanjang video
    sample_from: float = 0.05           # rentang sampel (fraksi durasi), hindari intro/outro
    sample_to: float = 0.95
    frame_width: int = 1280
    frame_height: int = 720
    tile_grid: int = 3                  # tiling N×N (overlap 50%) agar wajah kecil terdeteksi
    min_confidence: float = 0.5
    nms_iou: float = 0.4
    cluster_dist: float = 0.6           # jarak pusat maks (× lebar wajah) untuk satu kelompok
    min_frame_frac: float = 0.3         # wajah facecam harus muncul di ≥ 30% frame
    expand_w: float = 2.8               # lebar kotak facecam = lebar wajah × ini
    min_expand_h: float = 1.8           # tinggi kotak minimal = tinggi wajah × ini
    face_y_in_box: float = 0.42         # posisi pusat wajah di dalam kotak (dari atas)


@dataclass(frozen=True)
class TitleConfig(_Overridable):
    # F-19: saran judul klip via LLM lokal (Ollama)
    enabled: bool = True
    ollama_url: str = "http://127.0.0.1:11434"   # hanya localhost (lihat validate_settings)
    model: str = "qwen2.5:7b"
    count: int = 3                      # jumlah opsi judul
    hashtags: int = 5
    max_title_chars: int = 80           # batas aman judul Shorts (YouTube maks 100)
    max_transcript_chars: int = 2000
    temperature: float = 0.8
    timeout_s: int = 180                # termasuk waktu memuat model ke VRAM
    keep_alive: str = "0"               # "0" = unload segera → VRAM bebas untuk Whisper/NVENC


SECTIONS: dict[str, type] = {
    "detect": DetectConfig,
    "render": RenderConfig,
    "subtitle": SubtitleConfig,
    "thumbnail": ThumbnailConfig,
    "facecam": FacecamConfig,
    "title": TitleConfig,
}


@dataclass(frozen=True)
class AppConfig:
    data_dir: Path = DEFAULT_DATA_DIR
    detect: DetectConfig = field(default_factory=DetectConfig)
    render: RenderConfig = field(default_factory=RenderConfig)
    subtitle: SubtitleConfig = field(default_factory=SubtitleConfig)
    thumbnail: ThumbnailConfig = field(default_factory=ThumbnailConfig)
    facecam: FacecamConfig = field(default_factory=FacecamConfig)
    title: TitleConfig = field(default_factory=TitleConfig)
    config_file: Path = DEFAULT_DATA_DIR / "config.json"

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def templates_dir(self) -> Path:
        return self.data_dir / "templates"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    def to_settings(self) -> dict[str, Any]:
        return {
            "data_dir": str(self.data_dir),
            **{name: getattr(self, name).to_dict() for name in SECTIONS},
        }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"config.json tidak valid ({path}): {e}") from e


def resolve_config_file(data_dir: Path | None = None) -> tuple[Path, Path | None]:
    """(lokasi config.json, data_dir eksplisit). Tanpa argumen/env, config.json selalu di
    <repo>/data sehingga pengaturan `data_dir` (F-14) bisa menunjuk ke folder lain."""
    if data_dir is not None:
        return data_dir / "config.json", data_dir
    env = os.environ.get("AUTOCLIP_DATA_DIR")
    if env:
        return Path(env) / "config.json", Path(env)
    return DEFAULT_DATA_DIR / "config.json", None


def load_config(data_dir: Path | None = None) -> AppConfig:
    """Muat config: default -> config.json (kunci `data_dir`, `detect`, `render`, `subtitle`,
    `thumbnail`; boleh parsial). Prioritas data_dir: argumen > env AUTOCLIP_DATA_DIR > config.json."""
    config_file, explicit = resolve_config_file(data_dir)
    raw = _read_json(config_file)
    resolved = explicit or (Path(raw["data_dir"]) if raw.get("data_dir") else DEFAULT_DATA_DIR)
    sections = {name: cls().with_overrides(**raw.get(name, {})) for name, cls in SECTIONS.items()}
    return AppConfig(data_dir=resolved, config_file=config_file, **sections)


def _coerce(value: Any, default: Any, key: str) -> Any:
    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise ValueError(f"{key} harus boolean")
        return value
    if isinstance(default, int):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
            raise ValueError(f"{key} harus bilangan bulat")
        return int(value)
    if isinstance(default, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} harus angka")
        return float(value)
    if isinstance(default, str):
        if not isinstance(value, str):
            raise ValueError(f"{key} harus teks")
        return value
    return value


def validate_settings(cfg: AppConfig) -> None:
    d, s = cfg.detect, cfg.subtitle
    checks = [
        (0.0 <= d.sensitivity <= 1.0, "detect.sensitivity harus 0..1"),
        (d.min_peak_gap_s >= 1, "detect.min_peak_gap_s harus ≥ 1"),
        (d.pad_before_s >= 0 and d.pad_after_s >= 0, "padding tidak boleh negatif"),
        (1 <= d.max_clip_s <= 60, "detect.max_clip_s harus 1..60"),
        (0 <= d.exclude_start_s <= 600 and 0 <= d.exclude_end_s <= 600, "pengecualian intro/outro harus 0..600 dtk"),
        (min(d.w_audio, d.w_chat, d.w_reaction, d.w_face) >= 0
         and d.w_audio + d.w_chat + d.w_reaction + d.w_face > 0,
         "bobot harus ≥ 0 dan tidak semuanya 0"),
        (0.25 <= d.face_fps <= 10, "detect.face_fps harus 0.25..10"),
        (0 <= d.chat_delay_s <= 60, "detect.chat_delay_s harus 0..60"),
        (d.download_max_height in (360, 480, 720, 1080, 1440, 2160), "resolusi unduhan tidak didukung"),
        (s.device in ("auto", "cuda", "cpu"), "subtitle.device harus auto|cuda|cpu"),
        (s.model in _WHISPER_MODELS and s.cpu_model in _WHISPER_MODELS, "subtitle.model tidak didukung"),
        (not any(tok in s.audio_filter.lower() for tok in (";", "movie", "\r", "\n")),
         "subtitle.audio_filter tidak valid"),
        (bool(s.font_name.strip()) and not any(ch in s.font_name for ch in ",\r\n{}"),
         "subtitle.font_name tidak valid"),
        (bool(_ASS_COLOR_RE.match(s.primary_color)) and bool(_ASS_COLOR_RE.match(s.outline_color)),
         "warna subtitle ASS harus berformat &HAABBGGRR"),
        (all(u.startswith(_SAFE_MODEL_URL_PREFIX)
             for u in (d.reaction_model_url, d.face_model_url, cfg.thumbnail.face_model_url)),
         "URL model harus berasal dari repositori resmi MediaPipe"),
        (cfg.render.video_encoder in ("auto", "h264_nvenc", "libx264"), "render.video_encoder tidak dikenal"),
        (bool(_LOCAL_URL_RE.match(cfg.title.ollama_url)), "title.ollama_url hanya boleh localhost (http://127.0.0.1:PORT)"),
        (bool(_MODEL_NAME_RE.match(cfg.title.model)), "title.model tidak valid (mis. qwen2.5:7b)"),
        (1 <= cfg.title.count <= 10 and 0 <= cfg.title.hashtags <= 15, "title.count 1..10, title.hashtags 0..15"),
        (20 <= cfg.title.max_title_chars <= 100, "title.max_title_chars harus 20..100"),
        (0.0 <= cfg.title.temperature <= 2.0, "title.temperature harus 0..2"),
        (5 <= cfg.title.timeout_s <= 900, "title.timeout_s harus 5..900"),
    ]
    for ok, msg in checks:
        if not ok:
            raise ValueError(msg)


def save_settings(current: AppConfig, updates: dict[str, Any]) -> AppConfig:
    """Gabungkan perubahan parsial (F-14) ke config.json lalu kembalikan config baru.

    Perubahan `data_dir` baru berlaku setelah aplikasi direstart.
    """
    raw = _read_json(current.config_file)
    for key, value in updates.items():
        if key == "data_dir":
            if value in (None, ""):
                raw.pop("data_dir", None)
            elif not isinstance(value, str):
                raise ValueError("data_dir harus teks")
            else:
                raw["data_dir"] = value
            continue
        if key not in SECTIONS:
            raise ValueError(f"Bagian pengaturan tidak dikenal: {key}")
        if not isinstance(value, dict):
            raise ValueError(f"{key} harus objek")
        defaults = SECTIONS[key]().to_dict()
        section = dict(raw.get(key, {}))
        for k, v in value.items():
            if k not in defaults:
                raise ValueError(f"Pengaturan tidak dikenal: {key}.{k}")
            section[k] = _coerce(v, defaults[k], f"{key}.{k}")
        raw[key] = section

    sections = {name: cls().with_overrides(**raw.get(name, {})) for name, cls in SECTIONS.items()}
    candidate = AppConfig(data_dir=current.data_dir, config_file=current.config_file, **sections)
    validate_settings(candidate)
    current.config_file.parent.mkdir(parents=True, exist_ok=True)
    current.config_file.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return candidate
