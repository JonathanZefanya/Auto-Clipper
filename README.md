# Auto Clipper

Tool **lokal** untuk mengubah VOD / bekas live YouTube menjadi klip vertikal 9:16 siap upload ke YouTube Shorts, lengkap dengan subtitle dan thumbnail.

```
Tempel link YouTube → deteksi momen seru → review & pilih → render klip + thumbnail → unduh → upload manual
```

Semua proses berjalan di PC sendiri: tanpa API berbayar, tanpa upload otomatis. Momen seru dideteksi dari **lonjakan audio** (teriak, kaget, tertawa) dan **ledakan live chat**, bukan dari transkrip saja.

> Gunakan hanya untuk konten kreator yang program clipper-nya Anda ikuti, dan patuhi aturan program tersebut (durasi, kredit, watermark, dll.).

---

## Fitur

| Fitur | Keterangan |
|---|---|
| Input link | `youtube.com/watch?v=`, `youtu.be/`, `youtube.com/live/` + preview judul, channel, durasi |
| Unduh | Video maks 1080p + live chat replay (jika ada) via yt-dlp |
| Deteksi momen | Skor per detik dari audio + chat + **tawa/teriak (YAMNet)**, jumlah klip fleksibel (bisa 1, bisa banyak) |
| Review | Grafik skor, daftar kandidat, preview video per rentang, trim awal/akhir ±1/±5 dtk |
| Template 9:16 | **Split** (facecam atas + gameplay bawah) atau **center crop**, editor kotak facecam di UI + **deteksi facecam otomatis** |
| Render | FFmpeg `h264_nvenc` (fallback `libx264`), 1080×1920, maks 60 detik |
| Subtitle | faster-whisper Bahasa Indonesia, hanya pada klip terpilih, 2–4 kata per baris gaya Shorts; **bisa diedit sebelum render** |
| Thumbnail | Frame dengan wajah paling jelas (MediaPipe) + teks besar ber-outline; 1080×1920 dan opsional 1280×720; bisa disisipkan sebagai frame pembuka |
| Hasil | Galeri, unduh per file atau ZIP, file kredit `clip_<nn>.txt` (judul, channel, link + timestamp) |
| Job | Progres real-time (SSE), satu antrean, **batalkan** job yang antre/berjalan, riwayat tersimpan di SQLite, lanjut otomatis setelah restart |
| Pengaturan | Sensitivitas, jarak antar klip, padding, bobot audio/chat, chat delay, model Whisper, resolusi, folder data |

## Cara kerja deteksi

1. Audio diekstrak mono 16 kHz dan dibaca **per chunk 60 detik** (hemat RAM).
2. RMS per detik (dB) dibandingkan dengan **baseline median bergerak 60 detik** → yang terdeteksi lonjakan, bukan sekadar suara keras konstan (`audio_z`).
3. Jika ada live chat: jumlah pesan per detik (window 10 detik), dinormalisasi dengan cara yang sama, lalu digeser mundur `chat_delay` (default 7 detik) (`chat_z`).
4. Reaksi vokal: YAMNet mengklasifikasi audio yang sama (tawa, teriak, sorak, …) → probabilitas per detik, dinormalisasi sebagai lonjakan (`reaction_z`).
5. Skor = `w_audio · audio_z + w_chat · chat_z + w_reaction · reaction_z` (default 0.5 / 0.5 / 0.5; bobot dinormalisasi atas sinyal yang tersedia — tanpa chat, sinyal chat dilewati).
6. Smoothing → peak picking dengan ambang sensitivitas dan jarak minimal antar puncak (default 60 detik).
7. Tiap puncak → klip dari 20 detik sebelum sampai 15 detik sesudah puncak, maks 60 detik; klip yang overlap digabung.
8. Diurutkan dan diskalakan 0–100. Jika tidak ada yang melewati ambang, diambil 1 puncak tertinggi.

Semua angka di atas bisa diubah di halaman **Pengaturan** atau `data/config.json`.

---

## Kebutuhan

| | Minimal / diuji |
|---|---|
| OS | Windows 11 (Linux/WSL juga bisa) |
| Python | 3.11+ |
| Node.js | 20.19+ atau 22.12+ (untuk web UI) |
| FFmpeg | Build dengan NVENC + libass, mis. `winget install Gyan.FFmpeg` |
| GPU | Opsional. Diuji di RTX 5050 8GB (Blackwell). Tanpa GPU: Whisper di CPU, render `libx264` |
| RAM | 16 GB (32 GB disarankan) |

## Instalasi

```powershell
# Prasyarat (sekali saja), lalu buka ulang terminal
winget install Python.Python.3.11
winget install Gyan.FFmpeg
winget install OpenJS.NodeJS.LTS
winget install DenoLand.Deno        # JS runtime yang dibutuhkan yt-dlp untuk YouTube

# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # jika diblokir: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -e ".[dev,cuda]"        # tanpa GPU NVIDIA: pip install -e ".[dev]"
pytest -q

# Frontend
cd ..\frontend
npm install
npm run build
```

## Menjalankan

### Web UI

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m clipper serve
```

Buka **http://127.0.0.1:8000**. Dokumentasi API ada di http://127.0.0.1:8000/docs.

Untuk mengembangkan frontend (hot reload), jalankan juga di terminal kedua:

```powershell
cd frontend
npm run dev        # http://localhost:5173, /api di-proxy ke :8000
```

### Alur pemakaian

1. **Proses baru** → tempel link → **Cek link** → pilih template → **Proses**.
2. Tunggu unduh + analisis (progres tampil real-time).
3. **Review**: klik kandidat di daftar atau grafik untuk preview, geser awal/akhir bila perlu, centang yang mau dibuat.
4. *(Opsional)* **Transkripsi klip terpilih** → edit teks/waktu subtitle di panel **Subtitle** (klik waktu untuk memutar dari titik itu) → **Simpan**.
5. Atur opsi (subtitle, thumbnail, thumbnail 16:9, frame pembuka) → **Render**. Subtitle hasil edit dipakai apa adanya.
6. Di **Hasil**: preview klip, edit teks thumbnail, unduh per file atau **ZIP**, atau **Buka folder output**.

### CLI

Semua langkah juga bisa dijalankan tanpa UI:

```powershell
# Deteksi kandidat → tabel rank, start, end, peak, skor
python -m clipper detect "https://www.youtube.com/watch?v=VIDEO_ID"
python -m clipper detect "https://youtu.be/VIDEO_ID" --sensitivity 0.8 --min-gap 45

# Render kandidat (nomor rank dari tabel detect)
python -m clipper templates
python -m clipper render VIDEO_ID --ids 1,2,3 --template contoh-split
python -m clipper render VIDEO_ID --ids 1,2 --thumb-landscape --intro-frame

# Ganti teks thumbnail tanpa render ulang video
python -m clipper render VIDEO_ID --ids 1 --only-thumbs --thumb-text "WAH GILA!"
```

Pakai `--help` di setiap perintah untuk semua opsi (`--no-subtitle`, `--no-thumbnail`, `--whisper-model`, `--device`, `--encoder`, `--force-download`, ...). Job dari CLI otomatis muncul di riwayat web UI.

---

## Template layout

Template disimpan sebagai JSON di `data/templates/<nama>.json`. Koordinat kotak dinormalisasi 0..1 terhadap frame sumber, jadi berlaku untuk sumber 720p maupun 1080p:

```json
{
  "name": "contoh-split",
  "layout_type": "split",
  "facecam_box":  { "x": 0.74, "y": 0.62, "w": 0.26, "h": 0.38 },
  "gameplay_box": { "x": 0.12, "y": 0.0,  "w": 0.76, "h": 1.0 },
  "top_ratio": 0.4
}
```

- `split`: facecam di atas (`top_ratio` = porsi tinggi), gameplay di bawah.
- `center_crop`: crop tengah (opsional `gameplay_box`).
- Template bawaan `center` dan `contoh-split` dibuat otomatis. Buat template per streamer (mis. posisi facecam berbeda) lewat halaman **Template**, dengan menggambar kotak di atas frame video.

## Konfigurasi

Pengaturan disimpan di `data/config.json` (bisa diedit lewat halaman **Pengaturan**), dengan bagian `detect`, `render`, `subtitle`, `thumbnail`, dan `data_dir`. Cukup tulis nilai yang ingin diubah:

```json
{
  "detect":    { "sensitivity": 0.7, "min_peak_gap_s": 45, "chat_delay_s": 6 },
  "subtitle":  { "model": "medium" },
  "thumbnail": { "landscape": true, "intro_frame": true }
}
```

Daftar lengkap parameter beserta default ada di [backend/app/config.py](backend/app/config.py). Perubahan `data_dir` berlaku setelah server direstart.

## Struktur output

```
data/
├─ app.db                     # riwayat job & kandidat (SQLite)
├─ config.json
├─ templates/                 # template layout
├─ models/                    # model deteksi wajah MediaPipe (unduh otomatis)
└─ jobs/<job_id>/
   ├─ source.mp4, chat.json, meta.json
   ├─ scores.json             # skor per detik (grafik)
   ├─ candidates.json
   ├─ clips/clip_01.mp4       # klip 1080×1920
   ├─ clips/clip_01.ass       # subtitle (ASS)
   ├─ subs/clip_01.json       # subtitle yang bisa diedit (sumber .ass)
   ├─ clips/clip_01.txt       # kredit: judul, channel, link + timestamp
   ├─ thumbs/clip_01.png      # thumbnail 1080×1920
   ├─ thumbs/clip_01_16x9.png # opsional 1280×720
   └─ export/*.zip            # unduhan ZIP
```

---

## Catatan GPU (RTX 50 / Blackwell)

- Whisper memakai `ctranslate2>=4.6.3` (build CUDA 12.8, wajib untuk sm_120) + cuBLAS dari pip (`[cuda]`); cuDNN tidak diperlukan. Diuji dengan ctranslate2 4.8.3.
- Compute type GPU **`float16`**. INT8 dimatikan untuk Blackwell di CTranslate2, jadi jangan diubah ke `int8_float16`.
- Fallback otomatis: CUDA gagal → Whisper di CPU (`int8`); NVENC gagal → `libx264`.
- Urutan render menjaga VRAM: transkripsi semua klip → unload model → thumbnail (CPU) → encode NVENC.
- Render pertama mengunduh model Whisper dari Hugging Face (`large-v3` ±3 GB). Pakai `medium` jika ingin lebih cepat/ringan.

## Pengembangan

```
backend/
├─ app/
│  ├─ pipeline/      # download, audio, chat, detect, render, subtitle, thumbnail
│  ├─ runner.py      # orkestrasi detect/render (dipakai CLI & worker)
│  ├─ worker.py      # antrean job tunggal
│  ├─ api/           # route FastAPI
│  ├─ models.py, db.py, config.py, templates.py, main.py
├─ clipper/          # CLI
└─ tests/            # pytest (data sintetis, tanpa jaringan/GPU)
frontend/src/
├─ api.ts, stores/, components/, views/
```

```powershell
cd backend;  pytest -q                 # test backend
cd frontend; npm run typecheck         # typecheck frontend
```

Spesifikasi produk di [PRD.md](PRD.md) dan [Feature.md](Feature.md).

## Troubleshooting

| Masalah | Solusi |
|---|---|
| `py` / `python` tidak dikenali | Buka ulang terminal setelah instal Python, atau pakai path lengkap `%LOCALAPPDATA%\Programs\Python\Python311\python.exe` |
| `FFmpeg tidak ditemukan` | `winget install Gyan.FFmpeg`, lalu buka ulang terminal |
| yt-dlp gagal / format terbatas | Update: `pip install -U yt-dlp`, dan pastikan Deno terpasang |
| Whisper jatuh ke CPU | Pastikan `pip install -e ".[cuda]"` dan driver NVIDIA terbaru; lihat pesan peringatan di progres job |
| Wajah tidak terdeteksi di thumbnail | Model `short_range` cocok untuk facecam dekat; tanpa wajah dipilih frame paling tajam |
| Teks subtitle terpecah 2 baris | Turunkan `subtitle.font_size` di `config.json` |
| Folder data dipindah tapi tidak berlaku | Restart `python -m clipper serve` |

## Rencana berikutnya

Saran judul dengan LLM lokal (Ollama), aplikasi desktop (Tauri), dukungan Twitch VOD. Lihat bagian "Later" di [Feature.md](Feature.md).
