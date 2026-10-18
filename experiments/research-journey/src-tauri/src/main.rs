#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::webview::NewWindowResponse;
use tauri::{AppHandle, Runtime, Url, WebviewWindowBuilder};
use tauri_plugin_opener::OpenerExt;

/// Opens an https link in the default browser; any other scheme is ignored.
fn open_in_browser<R: Runtime>(app: &AppHandle<R>, url: &Url) {
    if url.scheme() == "https" {
        if let Err(error) = app.opener().open_url(url.as_str(), None::<&str>) {
            eprintln!("could not open {url} in the default browser: {error}");
        }
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let for_tabs = app.handle().clone();
            let for_links = app.handle().clone();
            let config = app.config().app.windows.first().cloned().ok_or("tauri.conf.json defines no window")?;
            WebviewWindowBuilder::from_config(app, &config)?
                // Pages come only from the app itself (the dev server while developing); a link
                // that would leave it opens in the default browser instead of replacing the page.
                .on_navigation(move |url| {
                    let own = url.scheme() == "tauri" || (cfg!(dev) && url.host_str() == Some("127.0.0.1"));
                    if !own {
                        open_in_browser(&for_links, url);
                    }
                    own
                })
                // Source links open in a new tab; send them to the default browser instead.
                .on_new_window(move |url, _| {
                    open_in_browser(&for_tabs, &url);
                    NewWindowResponse::Deny
                })
                .build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running the research journey");
}
