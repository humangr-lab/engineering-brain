mod adapters;
mod brain;
mod commands;
mod config;
mod git;
mod watcher;

use brain::BrainState;
use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .manage(BrainState::default())
        .invoke_handler(tauri::generate_handler![
            // Graph queries
            commands::get_graph,
            commands::get_graph_version,
            commands::get_stats,
            // Node queries
            commands::get_nodes,
            commands::get_node,
            // Edge queries
            commands::get_edges,
            // Epistemic queries
            commands::get_epistemic_stats,
            commands::get_contradictions,
            commands::get_at_risk_nodes,
            // Admin
            commands::trigger_reload,
            commands::get_reload_status,
            // Git
            commands::get_git_log,
            commands::get_changed_files,
            // Project
            commands::open_project,
            commands::analyze_project,
            // Health
            commands::get_health_score,
        ])
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // Start file watcher if seeds directory is configured via env
            if let Ok(dir) = std::env::var("BRAIN_SEEDS_DIR") {
                let path = std::path::PathBuf::from(&dir);
                if path.exists() {
                    let state: tauri::State<BrainState> = app.state();
                    match watcher::start_event_watcher(app.handle().clone(), path) {
                        Ok(debouncer) => {
                            if let Ok(mut handle) = state.watcher_handle.lock() {
                                *handle = Some(Box::new(debouncer));
                            }
                        }
                        Err(e) => {
                            log::warn!("Failed to start file watcher: {}", e);
                        }
                    }
                }
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
