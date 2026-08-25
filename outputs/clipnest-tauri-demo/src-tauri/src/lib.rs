#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use arboard::Clipboard;
use rusqlite::{params, Connection};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::path::PathBuf;

#[derive(Debug, Serialize)]
pub struct ClipRecord {
    pub id: i64,
    pub kind: String,
    pub title: String,
    pub preview: String,
    pub metadata: String,
    pub captured_at: i64,
}

fn database_path() -> Result<PathBuf, String> {
    let base = std::env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .ok_or("Cannot resolve Windows local app data directory")?;
    let dir = base.join("ClipNest");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir.join("clipnest.db"))
}

fn open_database() -> Result<Connection, String> {
    let connection = Connection::open(database_path()?).map_err(|e| e.to_string())?;
    connection.execute_batch(
        "PRAGMA journal_mode=WAL;
         CREATE TABLE IF NOT EXISTS clips(
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           kind TEXT NOT NULL,
           title TEXT NOT NULL,
           preview TEXT NOT NULL,
           metadata TEXT NOT NULL,
           content TEXT NOT NULL,
           content_hash TEXT NOT NULL UNIQUE,
           captured_at INTEGER NOT NULL
         );
         CREATE INDEX IF NOT EXISTS idx_clips_captured_at ON clips(captured_at DESC);",
    ).map_err(|e| e.to_string())?;
    Ok(connection)
}

#[tauri::command]
fn read_clipboard_text() -> Result<Option<String>, String> {
    let mut clipboard = Clipboard::new().map_err(|e| e.to_string())?;
    Ok(clipboard.get_text().ok())
}

#[tauri::command]
fn save_clipboard_text(text: String) -> Result<(), String> {
    let normalized = text.trim().to_string();
    if normalized.is_empty() { return Ok(()); }
    let hash = format!("{:x}", Sha256::digest(normalized.as_bytes()));
    let title = normalized.lines().next().unwrap_or("文本片段").chars().take(80).collect::<String>();
    let metadata = format!("纯文本 · {} 字", normalized.chars().count());
    let connection = open_database()?;
    connection.execute(
        "INSERT OR IGNORE INTO clips(kind,title,preview,metadata,content,content_hash,captured_at)
         VALUES('text',?1,?2,?3,?4,?5,strftime('%s','now'))",
        params![title, title, metadata, normalized, hash],
    ).map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
fn recent_clips(limit: i64) -> Result<Vec<ClipRecord>, String> {
    let connection = open_database()?;
    let mut statement = connection.prepare(
        "SELECT id,kind,title,preview,metadata,captured_at FROM clips
         ORDER BY captured_at DESC LIMIT ?1",
    ).map_err(|e| e.to_string())?;
    let rows = statement.query_map(params![limit.clamp(1, 2000)], |row| Ok(ClipRecord {
        id: row.get(0)?,
        kind: row.get(1)?,
        title: row.get(2)?,
        preview: row.get(3)?,
        metadata: row.get(4)?,
        captured_at: row.get(5)?,
    })).map_err(|e| e.to_string())?;
    rows.collect::<Result<Vec<_>, _>>().map_err(|e| e.to_string())
}

#[tauri::command]
fn app_info() -> serde_json::Value {
    serde_json::json!({ "name": "ClipNest", "backend": "Tauri 2 + Rust", "storage": "SQLite WAL" })
}

pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![read_clipboard_text, save_clipboard_text, recent_clips, app_info])
        .run(tauri::generate_context!())
        .expect("error while running ClipNest");
}

