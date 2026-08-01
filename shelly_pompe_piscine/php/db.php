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
    // Colonnes ajoutées en v2.4 (ignorées si déjà présentes)
    foreach (['pv_wh_5m REAL', 'pump_grid_wh_5m REAL'] as $col) {
        try { $pdo->exec("ALTER TABLE events ADD COLUMN $col"); } catch (Exception $e) {}
    }

    // Table de configuration (seuils mini/maxi par saison)
    $pdo->exec("
        CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    ");
    // Valeurs par défaut (insérées seulement si la clé n'existe pas encore)
    $defaults = [
        'seuil_mini_haute' => '-300',
        'seuil_maxi_haute' => '-50',
        'seuil_mini_mi'    => '-600',
        'seuil_maxi_mi'    => '-50',
        'seuil_mini_basse' => '-800',
        'seuil_maxi_basse' => '-50',
        'quota_mini_haute' => '4',
        'quota_mini_mi'    => '1',
        'quota_mini_basse' => '0',
        'quota_max_haute'  => '8',
        'quota_max_mi'     => '8',
        'quota_max_basse'  => '8',
    ];
    $ins = $pdo->prepare("INSERT OR IGNORE INTO config (key, value) VALUES (:k, :v)");
    foreach ($defaults as $k => $v) {
        $ins->execute([':k' => $k, ':v' => $v]);
    }
}
