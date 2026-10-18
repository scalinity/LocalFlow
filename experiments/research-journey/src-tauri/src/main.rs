#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::webview::NewWindowResponse;
use tauri::WebviewWindowBuilder;
use tauri_plugin_opener::OpenerExt;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let handle = app.handle().clone();
            let config = app.config().app.windows.first().cloned().ok_or("tauri.conf.json defines no window")?;
            WebviewWindowBuilder::from_config(app, &config)?
                // Source links open in a new tab; send them to the default browser instead.
                .on_new_window(move |url, _| {
                    if url.scheme() == "https" {
                        if let Err(error) = handle.opener().open_url(url.as_str(), None::<&str>) {
                            eprintln!("could not open {url} in the default browser: {error}");
                        }
                    }
                    NewWindowResponse::Deny
                })
                .build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running the research journey");
}
