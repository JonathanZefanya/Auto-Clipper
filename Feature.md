# Feature — Auto Clipper (MVP)

Daftar fitur beserta kriteria penerimaan. Konteks produk ada di `PRD.md`.

**Prioritas:** `P0` wajib untuk MVP · `P1` diinginkan di MVP · `Later` setelah MVP

---

## Ringkasan

| ID | Fitur | Prioritas | Milestone |
|---|---|---|---|
| F-01 | Input link YouTube | P0 | M1 |
| F-02 | Unduh video & live chat | P0 | M1 |
| F-03 | Analisis lonjakan audio | P0 | M1 |
| F-04 | Analisis aktivitas chat | P0 | M1 |
| F-05 | Skoring & deteksi kandidat fleksibel | P0 | M1 |
| F-06 | Review kandidat (list, grafik, preview) | P0 | M4 |
| F-07 | Trim awal/akhir klip | P1 | M4 |
| F-08 | Template layout 9:16 | P0 | M2 |
| F-09 | Render klip (NVENC) | P0 | M2 |
| F-10 | Subtitle otomatis | P0 | M2 |
| F-11 | Thumbnail otomatis | P1 | M3 |
| F-12 | Unduh hasil & folder output | P0 | M4 |
| F-13 | Progres job real-time & riwayat | P0 | M4 |
| F-14 | Pengaturan | P1 | M4 |
| F-15 | Deteksi tawa/teriak (YAMNet) | P1 | M5 |
| F-16 | Edit subtitle sebelum render | P1 | M5 |
| F-17 | Auto-deteksi posisi facecam | P1 | M5 |

---

## F-01 — Input Link YouTube

User menempelkan link YouTube (video biasa atau bekas live) untuk memulai job.

**Kriteria penerimaan**
- Menerima format `youtube.com/watch?v=`, `youtu.be/`, dan `youtube.com/live/`.
- Link tidak valid ditolak dengan pesan error yang jelas.
- Menampilkan judul, channel, durasi, dan thumbnail sumber sebelum diproses (via metadata yt-dlp).
- User memilih template layout (F-08) sebelum klik **Proses**.

## F-02 — Unduh Video & Live Chat

**Kriteria penerimaan**
- Mengunduh video maksimal 1080p ke `data/jobs/<id>/source.mp4`.
- Mengunduh live chat replay (`--write-subs --sub-langs live_chat`) jika tersedia, disimpan sebagai `chat.json`.
- Jika chat tidak tersedia, job tetap lanjut dan menandai `has_chat = false`.
- Progres unduh (%) dikirim ke UI.
- Gagal unduh → status job `failed` beserta pesan error.

## F-03 — Analisis Lonjakan Audio

**Kriteria penerimaan**
- Ekstrak audio mono 16kHz dengan FFmpeg.
- Hitung RMS per detik, diproses per chunk agar hemat RAM.
- Normalisasi terhadap baseline bergerak (median 60 detik) sehingga yang terdeteksi adalah **lonjakan relatif**.
- Output: array skor audio per detik, disimpan di `scores.json`.

## F-04 — Analisis Aktivitas Chat

**Kriteria penerimaan**
- Parsing `chat.json` menjadi timestamp per pesan (offset terhadap awal video).
- Hitung jumlah pesan per detik dengan window 10 detik, lalu normalisasi.
- Geser mundur sinyal sesuai `chat_delay` (default 7 detik, bisa diatur).
- Dilewati otomatis jika `has_chat = false`.

## F-05 — Skoring & Deteksi Kandidat Fleksibel

Jumlah klip mengikuti isi video: bisa 1, bisa banyak.

**Kriteria penerimaan**
- Skor gabungan: `w_audio · audio + w_chat · chat` (tanpa chat → audio saja).
- Smoothing, lalu peak picking dengan:
  - ambang **sensitivitas** (bisa diatur),
  - jarak minimal antar puncak (default 60 detik).
- Setiap puncak → kandidat dengan `start = puncak − 20 detik`, `end = puncak + 15 detik`, durasi maksimal 60 detik.
- Kandidat yang overlap digabung jadi satu.
- Kandidat diurutkan berdasarkan skor dan ditampilkan dalam skala 0–100.
- Jika tidak ada puncak yang melewati ambang, ambil 1 puncak tertinggi.
- Bisa dijalankan via CLI di M1:
  `python -m clipper detect <url>` → mencetak tabel kandidat.

## F-06 — Review Kandidat

**Kriteria penerimaan**
- Grafik skor sepanjang durasi video, dengan penanda di setiap kandidat.
- Daftar kandidat berisi: nomor, timestamp, durasi, skor, dan checkbox.
- Klik kandidat → preview video sumber pada rentang tersebut (HTML5 video dengan range request dari backend).
- Tombol **Pilih semua** / **Hapus pilihan**.
- Tombol **Render** aktif jika minimal 1 kandidat dipilih.

## F-07 — Trim Awal/Akhir Klip

**Kriteria penerimaan**
- Geser `start` / `end` per kandidat dengan langkah ±1 detik dan ±5 detik.
- Durasi tidak boleh melebihi 60 detik (validasi di UI dan backend).
- Perubahan tersimpan ke database.

## F-08 — Template Layout 9:16

Output 1080×1920.

**Kriteria penerimaan**
- Template bawaan:
  - **Split**: area facecam (koordinat crop dari sumber) di atas, gameplay di bawah.
  - **Center crop**: crop tengah untuk video tanpa facecam.
- Template disimpan per nama (mis. "Windah", "MiawAug") dalam JSON, berisi koordinat crop facecam, crop gameplay, dan rasio tinggi atas/bawah.
- Editor template sederhana: user menggambar kotak facecam di atas satu frame video sumber.

## F-09 — Render Klip (NVENC)

**Kriteria penerimaan**
- Render setiap kandidat terpilih dengan FFmpeg: potong → crop/scale sesuai template → `vstack` → burn subtitle → encode `h264_nvenc` + AAC.
- Fallback ke `libx264` jika NVENC tidak tersedia.
- Output: `clips/clip_<nn>.mp4`.
- Progres per klip dikirim ke UI.

## F-10 — Subtitle Otomatis

**Kriteria penerimaan**
- Transkripsi dengan faster-whisper (Bahasa Indonesia), **hanya pada rentang klip terpilih**, bukan seluruh video.
- Timestamp per kata (`word_timestamps=True`), dikelompokkan 2–4 kata per baris ala Shorts.
- Gaya subtitle ASS: font tebal, outline hitam, posisi di tengah-bawah area gameplay.
- Model di-unload dari VRAM setelah selesai.
- Subtitle bisa dimatikan per job.

## F-11 — Thumbnail Otomatis

**Kriteria penerimaan**
- Ambil beberapa frame di sekitar puncak skor, deteksi wajah dengan MediaPipe, lalu pilih frame dengan wajah terbesar/paling jelas.
- Komposisi dengan Pillow: frame + teks besar (default dari potongan transkrip, bisa diedit) dengan outline.
- Ukuran 1080×1920 (Shorts) dan 1280×720 (opsional).
- Output: `thumbs/clip_<nn>.png`.
- Opsi menyisipkan thumbnail sebagai frame pembuka klip (±0,1 detik) agar mudah dipilih saat upload Shorts.

## F-12 — Unduh Hasil & Folder Output

**Kriteria penerimaan**
- Galeri hasil berisi preview klip dan thumbnail per kandidat.
- Unduh per file atau **semua sebagai ZIP**.
- Setiap klip disertai `clip_<nn>.txt` berisi judul sumber, link sumber + timestamp, dan nama channel (untuk kredit).
- Tombol **Buka folder output**.

## F-13 — Progres Job Real-time & Riwayat

**Kriteria penerimaan**
- Status job: `queued → downloading → analyzing → ready_for_review → rendering → done | failed`.
- Progres dikirim via SSE (`/api/jobs/{id}/events`).
- Riwayat job tersimpan di SQLite dan tetap ada setelah restart.
- Hapus job → hapus folder data terkait.
- Hanya satu job diproses dalam satu waktu; job lain masuk antrean.

## F-14 — Pengaturan

**Kriteria penerimaan**
- Sensitivitas deteksi, jarak minimal antar klip, padding sebelum/sesudah puncak.
- Bobot audio vs chat, `chat_delay`.
- Model Whisper (`medium` / `large-v3`), resolusi unduhan.
- Lokasi folder data.
- Disimpan di `config.json`.

## F-15 — Deteksi Tawa/Teriak (YAMNet)

Sinyal tambahan untuk skor momen: reaksi vokal yang khas momen seru.

**Kriteria penerimaan**
- Klasifikasi audio dengan YAMNet (MediaPipe AudioClassifier, CPU) pada aliran chunk yang sama dengan analisis RMS (tanpa decode ulang).
- Kelas reaksi (dapat diatur): tawa, teriak, sorak, dll.; skor per detik = probabilitas tertinggi kelas reaksi.
- Dinormalisasi sebagai lonjakan relatif (baseline median 60 detik) → `reaction_z`.
- Skor gabungan: `w_audio · audio_z + w_chat · chat_z + w_reaction · reaction_z` (bobot dinormalisasi; sinyal yang tidak tersedia dilewati).
- Bisa dimatikan dan bobotnya diatur di Pengaturan; jika model gagal dimuat, analisis tetap jalan tanpa sinyal ini.
- Disimpan di `scores.json` dan ditampilkan di grafik.

## F-16 — Edit Subtitle Sebelum Render

**Kriteria penerimaan**
- Tombol **Transkripsi** menjalankan faster-whisper untuk kandidat terpilih tanpa merender video.
- Editor per klip: daftar baris (waktu mulai/selesai + teks), bisa diubah, dihapus, ditambah; klik waktu → preview melompat ke titik itu.
- Hasil editan disimpan dan dipakai saat render (Whisper tidak dijalankan ulang untuk klip tersebut).
- Jika rentang klip di-trim setelah transkripsi, waktu baris disesuaikan otomatis dan UI memberi tanda bahwa transkripsi ulang mungkin diperlukan.
- **Reset** mengembalikan ke subtitle otomatis.

## F-17 — Auto-deteksi Posisi Facecam

**Kriteria penerimaan**
- Di editor template, tombol **Deteksi otomatis** menganalisis beberapa frame dari video sumber.
- Wajah dideteksi per frame (MediaPipe, dengan tiling agar wajah kecil di overlay facecam terdeteksi), lalu dikelompokkan; facecam = kelompok wajah yang posisinya stabil di banyak frame.
- Kotak facecam diperluas dari kotak wajah dan disesuaikan dengan rasio area atas layout split.
- Jika tidak ada wajah yang stabil, tampilkan pesan yang jelas (kotak bisa digambar manual).

---

## Rancangan API (Backend FastAPI)

| Method | Endpoint | Fungsi |
|---|---|---|
| `POST` | `/api/jobs/preview` | Ambil metadata link (F-01) |
| `POST` | `/api/jobs` | Buat job baru `{url, template}` |
| `GET` | `/api/jobs` | Riwayat job |
| `GET` | `/api/jobs/{id}` | Detail job + kandidat |
| `GET` | `/api/jobs/{id}/events` | SSE progres |
| `GET` | `/api/jobs/{id}/scores` | Data grafik skor |
| `GET` | `/api/jobs/{id}/source` | Stream video sumber (range request) |
| `PATCH` | `/api/candidates/{id}` | Ubah `selected` / `start` / `end` |
| `POST` | `/api/jobs/{id}/render` | Render kandidat terpilih |
| `GET` | `/api/jobs/{id}/download` | Unduh ZIP hasil |
| `DELETE` | `/api/jobs/{id}` | Hapus job dan file |
| `GET/POST` | `/api/templates` | Kelola template layout |
| `GET/PUT` | `/api/settings` | Pengaturan |
| `POST` | `/api/jobs/{id}/transcribe` | Transkripsi kandidat terpilih (F-16) |
| `GET/PUT/DELETE` | `/api/candidates/{id}/subtitles` | Baca / simpan / reset subtitle (F-16) |
| `POST` | `/api/jobs/{id}/detect-facecam` | Saran kotak facecam (F-17) |

## Model Data (SQLite)

- **Job**: `id, url, title, channel, duration, has_chat, template, status, progress, error, created_at`
- **Candidate**: `id, job_id, rank, peak_time, start, end, score, selected, clip_path, thumb_path, thumb_text`
- **Template**: `id, name, layout_type, facecam_box, gameplay_box, top_ratio`

## Struktur Proyek

```
auto-clipper/
├─ backend/
│  ├─ app/
│  │  ├─ main.py           # FastAPI app
│  │  ├─ api/              # routes
│  │  ├─ worker.py         # antrean job
│  │  ├─ pipeline/
│  │  │  ├─ download.py    # F-02
│  │  │  ├─ audio.py       # F-03
│  │  │  ├─ chat.py        # F-04
│  │  │  ├─ detect.py      # F-05
│  │  │  ├─ render.py      # F-08, F-09
│  │  │  ├─ subtitle.py    # F-10
│  │  │  └─ thumbnail.py   # F-11
│  │  ├─ models.py
│  │  └─ config.py
│  └─ pyproject.toml
├─ frontend/               # Vue 3 + Vite + Tailwind
├─ data/                   # jobs, templates, config (gitignored)
├─ docker-compose.yml
├─ PRD.md
└─ Feature.md
```

---

## Later (setelah MVP)

- ~~Deteksi tawa/teriak (YAMNet)~~ → F-15 (M5).
- Saran judul klip dengan LLM lokal (Ollama).
- ~~Edit teks subtitle sebelum render~~ → F-16 (M5).
- ~~Auto-deteksi posisi facecam~~ → F-17 (M5).
- Pembungkus aplikasi desktop (Tauri).
- Dukungan sumber Twitch VOD.
