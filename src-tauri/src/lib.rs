use tauri_plugin_shell::ShellExt;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            // 1. Boot embedded Ollama engine
            if let Ok(ollama_command) = app.shell().sidecar("ollama") {
                let _ = ollama_command.args(["serve"]).spawn(); 
            }

            // 2. Boot compiled Python FastAPI backend
            if let Ok(api_command) = app.shell().sidecar("vault-api") {
                let _ = api_command.spawn();
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}