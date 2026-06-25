// ui/src-tauri/src/window.rs
// Window management — full implementation in Task 6

use tauri::Manager;

pub fn show(handle: &tauri::AppHandle) {
    if let Some(window) = handle.get_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

pub fn hide(handle: &tauri::AppHandle) {
    if let Some(window) = handle.get_window("main") {
        let _ = window.hide();
    }
}
