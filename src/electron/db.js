import Database from 'better-sqlite3';
import path from 'node:path';

const SCHEMA_VERSION = 1;

export const ALLOWED_TABLES = new Set([
  'characters', 'scenes', 'chapters', 'timeline_events',
  'timeline_branches', 'world_items', 'world_containers', 'manuscript_nodes',
  'graph_boards', 'graph_relationships', 'tags', 'todos', 'script_shots',
]);

function validateTable(table) {
  if (!ALLOWED_TABLES.has(table)) throw new Error(`Invalid table: ${table}`);
}

const SCHEMA_SQL = `
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS characters (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS scenes (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS chapters (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS timeline_events (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS timeline_branches (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS world_items (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS world_containers (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS manuscript_nodes (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS graph_boards (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS graph_relationships (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS tags (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS todos (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS script_shots (
  id TEXT PRIMARY KEY,
  storyboard_id TEXT NOT NULL,
  data TEXT NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

-- FTS5 for search
CREATE VIRTUAL TABLE IF NOT EXISTS fts_entities USING fts5(
  entity_type,
  entity_id UNINDEXED,
  title,
  content
);
`;

// Map of open DB connections keyed by projectRoot
const openDbs = new Map();

/**
 * Open (or return cached) DB for a project root.
 * Creates schema on first open.
 */
export function openDb(projectRoot) {
  if (openDbs.has(projectRoot)) return openDbs.get(projectRoot);

  const dbPath = path.join(projectRoot, 'project.db');
  const db = new Database(dbPath);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');

  // Apply schema
  db.exec(SCHEMA_SQL);

  // Check / set schema version
  const versionRow = db.prepare('SELECT value FROM meta WHERE key = ?').get('schema_version');
  if (!versionRow) {
    db.prepare('INSERT INTO meta (key, value) VALUES (?, ?)').run('schema_version', String(SCHEMA_VERSION));
  }

  openDbs.set(projectRoot, db);
  return db;
}

/**
 * Close DB for a project root.
 */
export function closeDb(projectRoot) {
  const db = openDbs.get(projectRoot);
  if (db) {
    db.close();
    openDbs.delete(projectRoot);
  }
}

/**
 * Close all open DB connections cleanly (call on app quit).
 */
export function closeAllDbs() {
  for (const [projectRoot, db] of openDbs) {
    try { db.close(); } catch {}
    openDbs.delete(projectRoot);
  }
}

/**
 * Upsert a single entity row.
 */
export function upsertEntity(db, table, id, data) {
  validateTable(table);
  db.prepare(
    `INSERT INTO ${table} (id, data, updated_at) VALUES (?, ?, unixepoch())
     ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at`
  ).run(id, JSON.stringify(data));
}

/**
 * Get all entities from a table as parsed objects.
 */
export function getAllEntities(db, table) {
  validateTable(table);
  return db.prepare(`SELECT data FROM ${table}`).all().map((row) => JSON.parse(row.data));
}

/**
 * Delete an entity by id.
 */
export function deleteEntity(db, table, id) {
  validateTable(table);
  db.prepare(`DELETE FROM ${table} WHERE id = ?`).run(id);
}

/**
 * Migrate a JSON-based project to SQLite.
 * Reads all entity arrays from projectJson and writes them to SQLite.
 * This is idempotent — safe to call multiple times.
 */
export async function migrateFromJson(projectRoot, projectJson) {
  const db = openDb(projectRoot);

  const alreadyMigrated = db.prepare('SELECT value FROM meta WHERE key = ?').get('migrated_from_json');
  if (alreadyMigrated) return; // already done

  const tableMap = {
    characters: 'characters',
    scenes: 'scenes',
    chapters: 'chapters',
    timelineEvents: 'timeline_events',
    timelineBranches: 'timeline_branches',
    worldItems: 'world_items',
    worldContainers: 'world_containers',
    manuscriptNodes: 'manuscript_nodes',
    graphBoards: 'graph_boards',
    relationships: 'graph_relationships',
    tags: 'tags',
    todos: 'todos',
  };

  const migrate = db.transaction(() => {
    for (const [jsonKey, table] of Object.entries(tableMap)) {
      const entities = projectJson[jsonKey] ?? [];
      for (const entity of entities) {
        if (entity?.id) {
          upsertEntity(db, table, entity.id, entity);
        }
      }
    }
    db.prepare('INSERT INTO meta (key, value) VALUES (?, ?)').run('migrated_from_json', '1');
  });

  migrate();
}

/**
 * FTS index update for an entity.
 */
export function indexEntity(db, entityType, entityId, title, content = '') {
  // Delete old entry if exists
  db.prepare('DELETE FROM fts_entities WHERE entity_id = ?').run(entityId);
  // Insert new
  db.prepare('INSERT INTO fts_entities (entity_type, entity_id, title, content) VALUES (?, ?, ?, ?)')
    .run(entityType, entityId, title ?? '', content ?? '');
}

/**
 * Full-text search across all entities.
 * Returns array of { entityType, entityId, title }.
 */
export function searchEntities(db, query) {
  if (!query?.trim()) return [];
  return db
    .prepare(
      `SELECT entity_type, entity_id, title
       FROM fts_entities
       WHERE fts_entities MATCH ?
       ORDER BY rank
       LIMIT 50`
    )
    .all(query.trim() + '*');
}
