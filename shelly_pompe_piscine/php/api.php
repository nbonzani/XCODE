<?php
// api.php - API JSON consommée par index.php
// Calcule les cumuls journaliers/hebdomadaires/mensuels et renvoie les derniers évènements.

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
require_once __DIR__ . '/db.php';

try {
    $pdo = db();
    $now = time();

    // Bornes de période en heure locale
    $todayStart = strtotime('today');
    $weekStart  = strtotime('monday this week 00:00:00');
    if ($weekStart > $now) { $weekStart = strtotime('-1 week monday 00:00:00'); }
    $monthStart = strtotime('first day of this month 00:00:00');

    $out = [];

    // Dernier évènement reçu (utilisé pour l'état "live")
    $last = $pdo->query("SELECT * FROM events ORDER BY id DESC LIMIT 1")
                ->fetch(PDO::FETCH_ASSOC);
    $out['last_event'] = $last ?: null;

    // Runtime du jour : max(daily_sec) parmi les évènements depuis minuit
    $stmt = $pdo->prepare("SELECT COALESCE(MAX(daily_sec),0) FROM events WHERE ts >= :since");
    $stmt->execute([':since' => $todayStart]);
    $out['today_sec'] = intval($stmt->fetchColumn());

    // Runtime semaine/mois : somme des max quotidiens
    $sumDaily = function(PDO $pdo, int $since): int {
        $stmt = $pdo->prepare("
            SELECT strftime('%Y-%m-%d', ts, 'unixepoch', 'localtime') AS day,
                   MAX(daily_sec) AS s
            FROM events
            WHERE ts >= :since
            GROUP BY day
        ");
        $stmt->execute([':since' => $since]);
        $total = 0;
        foreach ($stmt as $row) { $total += intval($row['s']); }
        return $total;
    };
    $out['week_sec']  = $sumDaily($pdo, $weekStart);
    $out['month_sec'] = $sumDaily($pdo, $monthStart);

    // Ventilation quotidienne sur 14 jours
    $stmt = $pdo->prepare("
        SELECT strftime('%Y-%m-%d', ts, 'unixepoch', 'localtime') AS day,
               MAX(daily_sec) AS s
        FROM events
        WHERE ts >= :since
        GROUP BY day
        ORDER BY day DESC
    ");
    $stmt->execute([':since' => $now - 14 * 86400]);
    $out['daily'] = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // 50 derniers évènements (tous types)
    $stmt = $pdo->query("
        SELECT id, ts, type, pump_on, grid_w, grid_avg_w, pv_w, mode, daily_sec, reason
        FROM events
        ORDER BY id DESC
        LIMIT 50
    ");
    $out['recent'] = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // 20 derniers évènements non-heartbeat (bascules, conflits, boots, manuel…)
    $stmt = $pdo->query("
        SELECT id, ts, type, pump_on, grid_w, mode, daily_sec, reason
        FROM events
        WHERE type != 'heartbeat'
        ORDER BY id DESC
        LIMIT 20
    ");
    $out['events'] = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Métadonnées
    $out['server_time'] = $now;
    $out['total_events'] = intval($pdo->query("SELECT COUNT(*) FROM events")->fetchColumn());

    echo json_encode($out);
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['error' => $e->getMessage()]);
}
