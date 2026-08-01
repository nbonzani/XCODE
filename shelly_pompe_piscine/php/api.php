<?php
// api.php - API JSON consommée par index.php
// Calcule les cumuls journaliers/hebdomadaires/mensuels et renvoie les derniers évènements.

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
date_default_timezone_set('Europe/Paris');
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

    // Runtime du jour : MAX(daily_sec) parmi les événements survenus APRÈS le premier
    // reset (premier daily_sec=0 de la journée locale). Cela exclut les heartbeats
    // "queue de la veille" envoyés juste après minuit avec encore le cumul d'hier.
    // Si aucun reset n'a eu lieu aujourd'hui (pompe n'a pas encore tourné), on prend
    // simplement le MAX brut.
    $todayDate = date('Y-m-d');
    $stmt = $pdo->prepare("
        SELECT COALESCE(
            (SELECT MAX(e.daily_sec)
             FROM events e
             WHERE strftime('%Y-%m-%d', e.ts, 'unixepoch', 'localtime') = :today
               AND e.ts >= (
                   SELECT MIN(ts) FROM events
                   WHERE strftime('%Y-%m-%d', ts, 'unixepoch', 'localtime') = :today2
                     AND daily_sec = 0
               )
            ),
            (SELECT MAX(daily_sec) FROM events
             WHERE strftime('%Y-%m-%d', ts, 'unixepoch', 'localtime') = :today3
            ),
            0
        )
    ");
    $stmt->execute([':today' => $todayDate, ':today2' => $todayDate, ':today3' => $todayDate]);
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
               MAX(daily_sec) AS s,
               ROUND(SUM(COALESCE(pv_wh_5m, 0))) AS pv_wh,
               ROUND(SUM(COALESCE(pump_grid_wh_5m, 0))) AS pump_grid_wh
        FROM events
        WHERE ts >= :since
        GROUP BY day
        ORDER BY day DESC
    ");
    $stmt->execute([':since' => $now - 14 * 86400]);
    $out['daily'] = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Patch : remplacer le MAX(daily_sec) d'aujourd'hui par la valeur corrigée
    // (exclut les heartbeats "queue de la veille" envoyés juste après minuit)
    foreach ($out['daily'] as &$row) {
        if ($row['day'] === $todayDate) {
            $row['s'] = strval($out['today_sec']);
            break;
        }
    }
    unset($row);

    // Même correction pour week_sec et month_sec : soustraire l'écart sur aujourd'hui
    $rawTodayMax = 0;
    foreach ($out['daily'] as $row) {
        if ($row['day'] === $todayDate) { $rawTodayMax = intval($row['s']); break; }
    }
    // (déjà patché, pas d'écart à corriger sur week/month — sumDaily utilise ts >= since
    //  et prend MAX par jour ; on re-calcule proprement ci-dessous)
    $sumDailyFixed = function(PDO $pdo, int $since, string $todayDate, int $todaySec): int {
        $stmt = $pdo->prepare("
            SELECT strftime('%Y-%m-%d', ts, 'unixepoch', 'localtime') AS day,
                   MAX(daily_sec) AS s
            FROM events
            WHERE ts >= :since
            GROUP BY day
        ");
        $stmt->execute([':since' => $since]);
        $total = 0;
        foreach ($stmt as $row) {
            $s = ($row['day'] === $todayDate) ? $todaySec : intval($row['s']);
            $total += $s;
        }
        return $total;
    };
    $out['week_sec']  = $sumDailyFixed($pdo, $weekStart,  $todayDate, $out['today_sec']);
    $out['month_sec'] = $sumDailyFixed($pdo, $monthStart, $todayDate, $out['today_sec']);

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

    // Configuration (seuils)
    $cfgRows = $pdo->query("SELECT key, value FROM config")->fetchAll(PDO::FETCH_ASSOC);
    $cfgOut  = [];
    foreach ($cfgRows as $row) { $cfgOut[$row['key']] = intval($row['value']); }
    $out['config'] = $cfgOut;

    // Métadonnées
    $out['server_time'] = $now;
    $out['total_events'] = intval($pdo->query("SELECT COUNT(*) FROM events")->fetchColumn());

    echo json_encode($out);
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['error' => $e->getMessage()]);
}
