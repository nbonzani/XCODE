<?php
// db.php - Helpers SQLite pour le dashboard pompe piscine
// Le fichier SQLite est créé automatiquement au premier appel.

function db() {
    static $pdo = null;
    if ($pdo === null) {
        $dbPath = __DIR__ . '/pompe.db';
        $pdo = new PDO('sqlite:' . $dbPath);
        $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
        $pdo->exec('PRAGMA journal_mode=WAL');
        $pdo->exec('PRAGMA busy_timeout=3000');
        initSchema($pdo);
    }
    return $pdo;
}

function initSchema(PDO $pdo) {
    $pdo->exec("
        CREATE TABLE IF NOT EXISTS events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           INTEGER NOT NULL,
            received_at  INTEGER NOT NULL,
            type         TEXT    NOT NULL,
            pump_on      INTEGER,
            grid_w       REAL,
            grid_avg_w   REAL,
            pv_w         REAL,
            mode         TEXT,
            daily_sec    INTEGER,
            reason       TEXT,
            raw          TEXT
        );
    ");
    $pdo->exec("CREATE INDEX IF NOT EXISTS idx_events_ts   ON events(ts);");
    $pdo->exec("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);");
}
