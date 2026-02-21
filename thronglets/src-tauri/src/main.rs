#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

#[tauri::command]
fn get_claude_agents() -> Result<String, String> {
    let db_path = dirs::home_dir()
        .unwrap_or_default()
        .join(".claude/ccnotify/ccnotify.db");

    if !db_path.exists() {
        return Ok("[]".to_string());
    }

    let conn = rusqlite::Connection::open(&db_path)
        .map_err(|e| e.to_string())?;

    let mut stmt = conn.prepare(
        "SELECT agent_id, agent_type, session_id, cwd, started_at, stopped_at
         FROM agent
         WHERE started_at > datetime('now', '-30 minutes')
         ORDER BY started_at DESC LIMIT 20"
    ).map_err(|e| e.to_string())?;

    let agents: Vec<serde_json::Value> = stmt.query_map([], |row| {
        Ok(serde_json::json!({
            "agent_id": row.get::<_, String>(0).unwrap_or_default(),
            "agent_type": row.get::<_, String>(1).unwrap_or_default(),
            "session_id": row.get::<_, String>(2).unwrap_or_default(),
            "cwd": row.get::<_, String>(3).unwrap_or_default(),
            "started_at": row.get::<_, String>(4).unwrap_or_default(),
            "stopped_at": row.get::<_, Option<String>>(5).unwrap_or(None)
        }))
    }).map_err(|e| e.to_string())?
    .filter_map(|r| r.ok())
    .collect();

    serde_json::to_string(&agents).map_err(|e| e.to_string())
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![get_claude_agents])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
