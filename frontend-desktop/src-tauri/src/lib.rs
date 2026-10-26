//! F-20: shell desktop Auto Clipper.
//!
//! Alur: jendela menampilkan splash (aset lokal) → backend Python dijalankan di 127.0.0.1 port bebas
//! → setelah `/api/health` OK, jendela pindah ke `http://127.0.0.1:<port>/` (backend menyajikan UI web
//! yang sama, sehingga `/api`, SSE, video Range & unduhan ZIP bekerja tanpa perubahan UI).
//! Menutup aplikasi menghentikan backend beserta proses anaknya (FFmpeg).
//!
//! Backend: bundel PyInstaller di `<resources>/backend/autoclip-backend.exe` (installer), atau
//! `backend/.venv` repo saat `tauri dev` (data tetap di folder `data/` repo).

use std::fs::{self, File};
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager, RunEvent, Url, WebviewWindow};

#[cfg(windows)]
use std::os::windows::process::CommandExt;
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// Waktu maksimal menunggu backend siap (start pertama memuat numpy/scipy/mediapipe).
const BOOT_TIMEOUT: Duration = Duration::from_secs(120);

struct Backend(Mutex<Option<Child>>);

fn free_port() -> std::io::Result<u16> {
    Ok(TcpListener::bind(("127.0.0.1", 0))?.local_addr()?.port())
}

/// GET /api/health tanpa dependensi HTTP tambahan.
fn health_ok(port: u16) -> bool {
    let addr: std::net::SocketAddr = ([127, 0, 0, 1], port).into();
    let Ok(mut s) = TcpStream::connect_timeout(&addr, Duration::from_millis(500)) else {
        return false;
    };
    let _ = s.set_read_timeout(Some(Duration::from_secs(2)));
    let req = format!("GET /api/health HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n");
    if s.write_all(req.as_bytes()).is_err() {
        return false;
    }
    let mut buf = [0u8; 32];
    matches!(s.read(&mut buf), Ok(n) if n >= 12 && buf[..n].starts_with(b"HTTP/1.1 200"))
}

fn bundled_backend(app: &AppHandle) -> Option<PathBuf> {
    let exe = app.path().resource_dir().ok()?.join("backend").join("autoclip-backend.exe");
    exe.exists().then_some(exe)
}

fn dev_backend_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..").join("backend")
}

/// Bangun perintah backend + kembalikan lokasi file log.
fn spawn_backend(app: &AppHandle, port: u16) -> Result<(Child, PathBuf), String> {
    let log_dir = app.path().app_log_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&log_dir).map_err(|e| e.to_string())?;
    let log_path = log_dir.join("backend.log");
    let log = File::create(&log_path).map_err(|e| format!("Tidak bisa membuat log {}: {e}", log_path.display()))?;

    let mut cmd = if let Some(exe) = bundled_backend(app) {
        let dir = exe.parent().map(Path::to_path_buf).unwrap_or_default();
        // data job di %APPDATA%\<identifier>\data — bukan di folder instalasi
        let data = app.path().app_data_dir().map_err(|e| e.to_string())?.join("data");
        fs::create_dir_all(&data).map_err(|e| e.to_string())?;
        let mut c = Command::new(&exe);
        c.current_dir(&dir).env("AUTOCLIP_DATA_DIR", &data);
        // FFmpeg/FFprobe/Deno yang ikut dibundel didahulukan di PATH
        let bin = dir.join("bin");
        if bin.exists() {
            let mut paths = vec![bin];
            paths.extend(std::env::split_paths(&std::env::var_os("PATH").unwrap_or_default()));
            if let Ok(joined) = std::env::join_paths(paths) {
                c.env("PATH", joined);
            }
        }
        c
    } else {
        let dir = dev_backend_dir();
        let py = dir.join(".venv").join("Scripts").join("python.exe");
        if !py.exists() {
            return Err(format!(
                "Backend tidak ditemukan.\nBundel: build dengan `npm run build`.\nDev: buat venv di {}",
                py.display()
            ));
        }
        let mut c = Command::new(py);
        c.current_dir(&dir).args(["-m", "clipper"]);
        c
    };

    cmd.args(["serve", "--host", "127.0.0.1", "--port", &port.to_string()])
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(Stdio::null())
        .stdout(log.try_clone().map_err(|e| e.to_string())?)
        .stderr(log);
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);

    let child = cmd.spawn().map_err(|e| format!("Gagal menjalankan backend: {e}"))?;
    Ok((child, log_path))
}

/// Hentikan backend + seluruh proses anaknya (FFmpeg yang sedang render, dll.).
fn stop_backend(app: &AppHandle) {
    let Some(state) = app.try_state::<Backend>() else { return };
    let Some(mut child) = state.0.lock().ok().and_then(|mut g| g.take()) else { return };
    #[cfg(windows)]
    {
        let _ = Command::new("taskkill")
            .args(["/PID", &child.id().to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();
    }
    let _ = child.kill();
    let _ = child.wait();
}

fn js_str(s: &str) -> String {
    serde_json::to_string(s).unwrap_or_else(|_| "\"\"".into())
}

fn splash_status(win: &WebviewWindow, msg: &str) {
    let _ = win.eval(&format!("window.setStatus && window.setStatus({})", js_str(msg)));
}

fn splash_error(win: &WebviewWindow, msg: &str, log: Option<&Path>) {
    let log = log.map(|p| p.display().to_string()).unwrap_or_default();
    let _ = win.eval(&format!("window.showError && window.showError({}, {})", js_str(msg), js_str(&log)));
}

fn boot(app: AppHandle) {
    let Some(win) = app.get_webview_window("main") else { return };
    let port = match free_port() {
        Ok(p) => p,
        Err(e) => return splash_error(&win, &format!("Tidak ada port bebas: {e}"), None),
    };
    splash_status(&win, "Menyalakan backend…");
    let (child, log_path) = match spawn_backend(&app, port) {
        Ok(v) => v,
        Err(e) => return splash_error(&win, &e, None),
    };
    if let Ok(mut g) = app.state::<Backend>().0.lock() {
        *g = Some(child);
    }

    let started = Instant::now();
    loop {
        if health_ok(port) {
            if let Ok(url) = Url::parse(&format!("http://127.0.0.1:{port}/")) {
                let _ = win.navigate(url);
            }
            return;
        }
        // backend mati sebelum siap → tampilkan error + log
        let exited = app.state::<Backend>().0.lock().ok().and_then(|mut g| {
            let code = g.as_mut().and_then(|c| c.try_wait().ok().flatten());
            if code.is_some() {
                *g = None;
            }
            code
        });
        if let Some(code) = exited {
            return splash_error(&win, &format!("Backend berhenti ({code})."), Some(&log_path));
        }
        if started.elapsed() > BOOT_TIMEOUT {
            return splash_error(&win, "Backend tidak merespons dalam 120 detik.", Some(&log_path));
        }
        if started.elapsed() > Duration::from_secs(8) {
            splash_status(&win, "Memuat library analisis… (start pertama bisa lebih lama)");
        }
        thread::sleep(Duration::from_millis(300));
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // satu instance saja: membuka lagi → fokus ke jendela yang ada (mencegah dua backend)
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.set_focus();
            }
        }))
        .manage(Backend(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            thread::spawn(move || boot(handle));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("gagal membangun aplikasi Tauri")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                stop_backend(app);
            }
        });
}
