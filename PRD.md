# PRD — Auto Clipper (MVP)

> Product Requirements Document
> Versi: 0.1 (MVP) · Tanggal: 20 Oktober 2026 · Pemilik: Jonathan

---

## 1. Ringkasan

Auto Clipper adalah aplikasi web **lokal** untuk mengubah video panjang YouTube (VOD/bekas live gameplay maupun video biasa) menjadi beberapa klip vertikal 9:16 siap upload ke YouTube Shorts, lengkap dengan subtitle dan thumbnail.

Alur inti:

```
Tempel link YouTube → program mendeteksi momen seru → user review & pilih → render klip + thumbnail → unduh → upload manual
```

Seluruh pemrosesan berjalan di PC pengguna. Tidak ada API berbayar, tidak ada upload otomatis.

## 2. Latar Belakang & Masalah

- Streamer seperti Windah Basudara atau MiawAug punya **program clipper berbayar**.
- Clipper harus menonton VOD berjam-jam secara manual untuk mencari momen seru, lalu memotong, me-reframe ke 9:16, memberi subtitle, dan membuat thumbnail. Prosesnya lama dan repetitif.
- Momen seru pada konten gameplay umumnya berupa **reaksi** (teriak, kaget, tertawa, chat meledak), bukan sekadar omongan, sehingga pendekatan "transkrip saja" tidak cukup.

## 3. Tujuan

1. Memangkas waktu mencari momen dari menonton seluruh VOD menjadi **review ±20–30 kandidat**.
2. Mengotomatiskan render klip 9:16 dengan layout facecam + gameplay, subtitle, dan thumbnail.
3. Berjalan **100% lokal dan gratis** di hardware pengguna.

## 4. Non-Goals (di luar cakupan MVP)

- Upload otomatis ke YouTube (upload dilakukan manual).
- Multi-user, login, SaaS, atau hosting di server.
- Installer/aplikasi desktop (MVP berupa web lokal di `localhost`).
- Penguncian jumlah klip ("selalu N klip").
- Judul/caption otomatis berbasis LLM.
- Sumber selain YouTube (Twitch, TikTok, dll.).

## 5. Target Pengguna

Pengguna tunggal: clipper yang tergabung dalam program clipper resmi kreator, nyaman menjalankan aplikasi lokal, dan memiliki PC dengan GPU NVIDIA.

## 6. Lingkungan Target (Hardware Acuan)

| Komponen | Spesifikasi |
|---|---|
| CPU | AMD Ryzen 5 8600G |
| GPU | NVIDIA RTX 5050 8GB (CUDA + NVENC) |
| RAM | 16GB DDR5 (disarankan 32GB) |
| Storage | NVMe 500GB (+1TB) |
| OS | Windows + WSL 2 / Docker Desktop |

Batasan desain: VRAM 8GB → model dijalankan **berurutan**, tidak paralel.

## 7. User Flow

1. User membuka `http://localhost:5173`.
2. User menempelkan link YouTube, memilih **template layout** (mis. "Windah", "MiawAug", "Tanpa facecam"), lalu klik **Proses**.
3. Sistem mengunduh video + live chat replay (jika ada), lalu menganalisis. Progres tampil real-time.
4. Sistem menampilkan **daftar kandidat momen** terurut berdasarkan skor, dengan grafik skor sepanjang video.
5. User mem-preview kandidat, mencentang yang dipilih, dan bisa menggeser titik awal/akhir.
6. User klik **Render**. Sistem membuat klip 9:16 + subtitle + thumbnail untuk setiap kandidat terpilih.
7. User mengunduh hasil (per klip atau ZIP), lalu meng-upload manual ke YouTube.

## 8. Kebutuhan Fungsional (ringkas)

Detail tiap fitur ada di `Feature.md`.

| ID | Kebutuhan |
|---|---|
| FR-1 | Menerima input link YouTube (video biasa atau VOD live) |
| FR-2 | Mengunduh video dan live chat replay (jika tersedia) |
| FR-3 | Menghitung skor momen per detik dari sinyal audio dan chat |
| FR-4 | Mendeteksi banyak puncak secara fleksibel (0..N klip) dengan jarak minimal dan tanpa overlap; fallback minimal 1 klip |
| FR-5 | Menampilkan kandidat untuk direview, dipreview, dan di-trim |
| FR-6 | Merender klip 9:16 (≤ 60 detik) dengan layout template |
| FR-7 | Membuat subtitle otomatis (Bahasa Indonesia) hanya untuk klip terpilih |
| FR-8 | Membuat thumbnail otomatis dengan teks yang bisa diedit |
| FR-9 | Menyediakan unduhan hasil dan menyimpannya ke folder output |
| FR-10 | Menampilkan progres job secara real-time |

## 9. Kebutuhan Non-Fungsional

| ID | Kebutuhan |
|---|---|
| NFR-1 | Berjalan sepenuhnya lokal; internet hanya untuk mengunduh video dan model pertama kali |
| NFR-2 | VOD 4 jam selesai dianalisis (tanpa transkripsi penuh) dalam waktu yang wajar, target < 15 menit setelah unduhan selesai |
| NFR-3 | Render 1 klip 60 detik dengan NVENC, target < 30 detik |
| NFR-4 | Penggunaan VRAM ≤ 7GB pada satu waktu |
| NFR-5 | Job tetap bisa dilanjutkan/dilihat hasilnya setelah aplikasi direstart (state disimpan di SQLite) |
| NFR-6 | File sementara dibersihkan otomatis setelah job selesai/dihapus |

## 10. Arsitektur

```
┌──────────────────────┐   HTTP/REST + SSE   ┌──────────────────────────────┐
│  Frontend (Vue 3)    │ ◄─────────────────► │  Backend (FastAPI, Python)    │
│  Vite + Tailwind     │                     │  ├─ API & SSE progress        │
│  localhost:5173      │                     │  ├─ Job worker (1 antrean)    │
└──────────────────────┘                     │  └─ SQLite (jobs, candidates) │
                                             └──────────────┬───────────────┘
                                                            │
                        ┌───────────────────────────────────┼─────────────────────────────┐
                        ▼                 ▼                 ▼                 ▼           ▼
                     yt-dlp          librosa/FFmpeg   faster-whisper     FFmpeg+NVENC   Pillow +
                  (video + chat)    (analisis audio)  (subtitle, GPU)   (render 9:16)  MediaPipe
                                                                                       (thumbnail)
```

- **Worker**: satu antrean, satu job aktif pada satu waktu (menjaga VRAM).
- **Penyimpanan**: `data/jobs/<job_id>/` berisi `source.mp4`, `chat.json`, `scores.json`, `clips/`, `thumbs/`.

## 11. Tech Stack

| Lapisan | Teknologi |
|---|---|
| Frontend | Vue 3, Vite, TypeScript, Tailwind CSS, Pinia, chart sederhana (Chart.js) |
| Backend | Python 3.11+, FastAPI, Uvicorn, SQLModel + SQLite |
| Progres | Server-Sent Events (SSE) |
| Unduh | yt-dlp (video + `live_chat` subtitle) |
| Analisis audio | FFmpeg (ekstraksi audio), librosa / numpy (RMS, onset) |
| Transkripsi | faster-whisper (`large-v3` int8 / `medium`), CUDA |
| Render | FFmpeg dengan `h264_nvenc`, filter crop/scale/vstack, subtitle ASS |
| Thumbnail | MediaPipe Face Detection + Pillow |
| Deploy | Docker Compose (GPU via WSL 2) atau jalan langsung dengan venv |

## 12. Algoritma Deteksi Momen (MVP)

1. Ekstrak audio mono 16kHz.
2. Hitung **energi audio (RMS)** per detik dan normalisasi terhadap baseline bergerak (mis. median 60 detik), sehingga yang terdeteksi adalah **lonjakan**, bukan sekadar suara keras konstan.
3. Jika chat tersedia: hitung **jumlah pesan per detik** (window 10 detik), normalisasi dengan cara yang sama. Geser mundur ±5–10 detik untuk mengompensasi delay chat.
4. Skor gabungan: `skor = w_audio · audio_z + w_chat · chat_z`. Default `w_audio = 0.5`, `w_chat = 0.5`. Tanpa chat → `w_audio = 1.0`.
5. Smoothing, lalu **peak picking** dengan ambang sensitivitas dan jarak minimal antar puncak (default 60 detik).
6. Setiap puncak → klip: mulai 20 detik sebelum puncak, selesai 15 detik setelahnya, dibatasi maksimal 60 detik. Klip yang overlap digabung.
7. Urutkan berdasarkan skor dan skalakan ke 0–100. Jika tidak ada yang melewati ambang, ambil 1 puncak tertinggi.

## 13. Risiko & Mitigasi

| Risiko | Mitigasi |
|---|---|
| Chat replay tidak tersedia | Fallback ke skor audio saja |
| Whisper berhalusinasi di bagian teriakan/berisik | Transkripsi hanya pada klip terpilih; subtitle bisa diedit sebelum render (later) |
| VRAM penuh | Jalankan model berurutan, unload model setelah dipakai |
| RAM 16GB mepet (Docker + browser) | Proses audio per chunk, bukan sekaligus |
| Perubahan yt-dlp akibat update YouTube | Pin versi, sediakan perintah update yt-dlp |
| Aturan program clipper (format/kredit) | Template layout + file teks kredit sumber di output |

## 14. Kepatuhan

Tool ini hanya digunakan untuk konten dari kreator yang programnya diikuti pengguna, dengan mengikuti aturan program masing-masing (durasi, kredit, watermark, dll.).

## 15. Milestone

| Tahap | Lingkup | Fitur |
|---|---|---|
| M1 | Deteksi momen (CLI) | F-01, F-02, F-03, F-04, F-05 |
| M2 | Render klip | F-08, F-09, F-10 |
| M3 | Thumbnail | F-11 |
| M4 | Web UI | F-06, F-07, F-12, F-13 |

## 16. Indikator Keberhasilan

- Dari 10 kandidat teratas, minimal 5 layak diupload menurut penilaian user.
- Waktu dari tempel link sampai klip siap unduh < 30 menit untuk VOD 4 jam.
- Tidak perlu membuka editor video eksternal untuk klip standar.