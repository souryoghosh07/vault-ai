use tauri_plugin_shell::ShellExt;

// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init()) // <--- Required for sidecars
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            // 1. Boot the embedded Ollama engine in server mode
            // We ignore errors here so the app doesn't crash if the user already has Ollama running
            if let Ok(ollama_command) = app.shell().sidecar("ollama") {
                let _ = ollama_command.args(["serve"]).spawn(); 
            }

            // 2. Boot your compiled Python FastAPI backend
            if let Ok(api_command) = app.shell().sidecar("vault-api") {
                let _ = api_command.spawn();
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![greet])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}