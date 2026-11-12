"""Einmaliges Migrations-Skript fuer AP10 (Belohnungssystem) inkl. Erweiterung um
Spitzname, Auto-Verwaltung und Leaderboard-Anzeige-Auswahl (Nutzer oder Auto).

Verwendung (im Projekt-Root, mit aktivierter venv bzw. im Container):
    python migrate_ap10.py

Idempotent: bereits vorhandene Spalten/Tabellen werden uebersprungen.
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data/ladeplatz.db")

COLUMN_STATEMENTS = [
    ("users", "reward_points", "ALTER TABLE users ADD COLUMN reward_points INTEGER NOT NULL DEFAULT 0"),
    ("users", "leaderboard_opt_in", "ALTER TABLE users ADD COLUMN leaderboard_opt_in BOOLEAN NOT NULL DEFAULT 0"),
    ("users", "avatar_path", "ALTER TABLE users ADD COLUMN avatar_path VARCHAR(255)"),
    ("users", "nickname", "ALTER TABLE users ADD COLUMN nickname VARCHAR(100)"),
    ("users", "leaderboard_display", "ALTER TABLE users ADD COLUMN leaderboard_display VARCHAR(10) NOT NULL DEFAULT 'user'"),
    ("queue_entries", "benefactor_user_id", "ALTER TABLE queue_entries ADD COLUMN benefactor_user_id VARCHAR(36)"),
    ("queue_entries", "reward_points_pending", "ALTER TABLE queue_entries ADD COLUMN reward_points_pending INTEGER"),
    ("queue_entries", "reward_points_awarded", "ALTER TABLE queue_entries ADD COLUMN reward_points_awarded BOOLEAN NOT NULL DEFAULT 0"),
]

CREATE_CARS_TABLE = """
CREATE TABLE IF NOT EXISTS cars (
    id VARCHAR(36) PRIMARY KEY,
    owner_id VARCHAR(36) NOT NULL REFERENCES users(id),
    name VARCHAR(100) NOT NULL,
    brand VARCHAR(100),
    model VARCHAR(100),
    photo_path VARCHAR(255),
    is_primary BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL
)
"""


def column_exists(cursor, table, column) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def main():
    if not DB_PATH.exists():
        print(f"Keine bestehende Datenbank unter {DB_PATH} gefunden. "
              f"Nichts zu migrieren, die App legt beim Start ein frisches Schema an.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    applied = 0
    for table, column, statement in COLUMN_STATEMENTS:
        if column_exists(cursor, table, column):
            print(f"Uebersprungen: {table}.{column} existiert bereits.")
            continue
        cursor.execute(statement)
        applied += 1
        print(f"Angewendet: {table}.{column}")

    cursor.execute(CREATE_CARS_TABLE)
    print("Sichergestellt: Tabelle 'cars' existiert.")

    conn.commit()
    conn.close()
    print(f"\nFertig. {applied} Spalte(n) ergaenzt, Tabelle 'cars' sichergestellt.")


if __name__ == "__main__":
    sys.exit(main())
