// ui/src-tauri/src/ws.rs
// WebSocket client — connects to Python backend, relays events to Vue3

use std::time::Duration;
use tauri::{AppHandle, Manager};
use tokio::sync::mpsc;
use tokio::time::sleep;
use tokio_tungstenite::connect_async;
use futures_util::SinkExt;
use futures_util::StreamExt;

pub fn connect(url: String, handle: AppHandle) {
    // Channel for frontend → backend messages (e.g. keyboard input)
    let (tx, mut rx) = mpsc::channel::<String>(256);

    // Store sender in Tauri state so commands can access it
    handle.manage(WsState { tx: tx.clone() });

    tokio::spawn(async move {
        let mut retries = 0;
        let max_retries = 10;

        loop {
            match connect_async(&url).await {
                Ok((ws_stream, _)) => {
                    println!("[WS] Connected to {}", url);
                    retries = 0;
                    let (mut write, mut read) = ws_stream.split();

                    // Send handshake
                    let _ = write.send(tokio_tungstenite::tungstenite::Message::Text(
                        r#"{"event":"hello","version":"1.0"}"#.into(),
                    )).await;

                    loop {
                        tokio::select! {
                            // WS → Tauri event
                            msg = read.next() => {
                                match msg {
                                    Some(Ok(tokio_tungstenite::tungstenite::Message::Text(text))) => {
                                        if let Ok(event) = serde_json::from_str::<serde_json::Value>(&text) {
                                            let event_type = event["event"].as_str().unwrap_or("");
                                            let payload = text.clone();

                                            match event_type {
                                                "wake" => {
                                                    if let Some(window) = handle.get_window("main") {
                                                        if let Err(e) = window.show() {
                                                            eprintln!("[WS] Failed to show window: {}", e);
                                                        }
                                                        if let Err(e) = window.set_focus() {
                                                            eprintln!("[WS] Failed to focus window: {}", e);
                                                        }
                                                    } else {
                                                        eprintln!("[WS] 'main' window not found on wake");
                                                    }
                                                    let _ = handle.emit_all("tauri://wake", &payload);
                                                }
                                                "stt"          => { let _ = handle.emit_all("tauri://stt", &payload); }
                                                "thinking"     => { let _ = handle.emit_all("tauri://thinking", &payload); }
                                                "text_chunk"   => { let _ = handle.emit_all("tauri://text-chunk", &payload); }
                                                "data"         => { let _ = handle.emit_all("tauri://data", &payload); }
                                                "amplitude"    => { let _ = handle.emit_all("tauri://amplitude", &payload); }
                                                "tts_start"    => { let _ = handle.emit_all("tauri://tts-start", &payload); }
                                                "tts_end"      => { let _ = handle.emit_all("tauri://tts-end", &payload); }
                                                "idle"         => { let _ = handle.emit_all("tauri://idle", &payload); }
                                                "error"        => { let _ = handle.emit_all("tauri://error", &payload); }
                                                _ => {}
                                            }
                                        }
                                    }
                                    Some(Ok(tokio_tungstenite::tungstenite::Message::Close(_))) => {
                                        println!("[WS] Server closed connection");
                                        break;
                                    }
                                    Some(Err(e)) => {
                                        println!("[WS] Error: {}", e);
                                        break;
                                    }
                                    None => {
                                        println!("[WS] Stream ended");
                                        break;
                                    }
                                    _ => {} // ping/pong handled by tungstenite
                                }
                            }
                            // Frontend → WS (keyboard input)
                            text = rx.recv() => {
                                if let Some(text) = text {
                                    let _ = write.send(tokio_tungstenite::tungstenite::Message::Text(text.into())).await;
                                }
                            }
                        }
                    }
                }
                Err(e) => {
                    println!("[WS] Connection failed: {}", e);
                }
            }

            // Reconnect with exponential backoff
            if retries >= max_retries {
                println!("[WS] Max retries reached, giving up");
                break;
            }
            retries += 1;
            let delay = Duration::from_millis(std::cmp::min(500 * 2u64.pow(retries), 10000));
            println!("[WS] Reconnecting in {:?} (attempt {}/{})", delay, retries, max_retries);
            sleep(delay).await;
        }
    });
}

pub struct WsState {
    pub tx: mpsc::Sender<String>,
}
