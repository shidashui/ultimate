#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod ws;
mod window;

use tauri::{
    CustomMenuItem, Manager, SystemTray, SystemTrayEvent, SystemTrayMenu,
    SystemTrayMenuItem,
};

#[tauri::command]
fn close_window(window: tauri::Window) {
    let _ = window.hide();
}

#[tauri::command]
fn send_input(text: String, handle: tauri::AppHandle) {
    println!("[Input] {}", text);
    let _ = handle.emit_all("tauri://user-input", &text);
}

fn main() {
    let show_item = CustomMenuItem::new("show".to_string(), "显示/隐藏窗口");
    let quit_item = CustomMenuItem::new("quit".to_string(), "退出");
    let tray_menu = SystemTrayMenu::new()
        .add_item(show_item)
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(quit_item);

    tauri::Builder::default()
        .system_tray(SystemTray::new().with_menu(tray_menu))
        .on_system_tray_event(|app, event| match event {
            SystemTrayEvent::MenuItemClick { id, .. } => match id.as_str() {
                "show" => {
                    let window = app.get_window("main").unwrap();
                    if window.is_visible().unwrap_or(false) {
                        let _ = window.hide();
                    } else {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                }
                "quit" => {
                    app.exit(0);
                }
                _ => {}
            },
            _ => {}
        })
        .setup(|app| {
            let handle = app.handle();
            ws::connect("ws://127.0.0.1:18765/ws".to_string(), handle.clone());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![close_window, send_input])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
