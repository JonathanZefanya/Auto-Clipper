// Tanpa jendela konsol di build rilis (Windows)
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    auto_clipper_desktop_lib::run()
}
