-- AP10 Belohnungssystem: Nachtraegliche Spalten fuer bereits existierende SQLite-Datenbanken.
-- Hintergrund: SQLAlchemy's Base.metadata.create_all() legt nur FEHLENDE TABELLEN an,
-- aendert aber niemals das Schema bereits bestehender Tabellen. Da "users" und
-- "queue_entries" schon vor AP10 existierten, fehlen die neuen Spalten schlicht.
-- Dieses Skript holt das nach, ohne bestehende Daten zu verlieren.

ALTER TABLE users ADD COLUMN reward_points INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN leaderboard_opt_in BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN avatar_path VARCHAR(255);

ALTER TABLE queue_entries ADD COLUMN benefactor_user_id VARCHAR(36);
ALTER TABLE queue_entries ADD COLUMN reward_points_pending INTEGER;
ALTER TABLE queue_entries ADD COLUMN reward_points_awarded BOOLEAN NOT NULL DEFAULT 0;

-- Die Tabelle "point_transactions" ist komplett neu und wird von create_all()
-- ganz normal automatisch angelegt, dafuer ist kein ALTER TABLE notwendig.
