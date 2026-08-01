<?php
// config.php - GET : retourne la config JSON pour le Shelly et le dashboard
//              POST : sauvegarde les cles autorisees (dashboard uniquement)

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/env.php';

$ALLOWED = [
    'seuil_mini_haute', 'seuil_maxi_haute',
    'seuil_mini_mi',    'seuil_maxi_mi',
    'seuil_mini_basse', 'seuil_maxi_basse',
    'quota_mini_haute', 'quota_mini_mi', 'quota_mini_basse',
    'quota_max_haute',  'quota_max_mi',  'quota_max_basse',
];

try {
    $pdo = db();

    if ($_SERVER['REQUEST_METHOD'] === 'GET') {
        // Retourne toute la config (consomme par le Shelly et le dashboard)
        $rows = $pdo->query("SELECT key, value FROM config")->fetchAll(PDO::FETCH_ASSOC);
        $out  = [];
        foreach ($rows as $row) { $out[$row['key']] = intval($row['value']); }
        echo json_encode($out);

    } elseif ($_SERVER['REQUEST_METHOD'] === 'POST') {
        // Sauvegarde depuis le dashboard (token requis)
        $token = $_SERVER['HTTP_X_DEPLOY_TOKEN'] ?? '';
        if ($token !== env('DEPLOY_TOKEN')) {
            http_response_code(403);
            echo json_encode(['error' => 'forbidden']);
            exit;
        }
        $raw  = file_get_contents('php://input');
        $data = json_decode($raw, true);
        if (!is_array($data)) {
            http_response_code(400);
            echo json_encode(['error' => 'invalid JSON']);
            exit;
        }
        $stmt  = $pdo->prepare("INSERT OR REPLACE INTO config (key, value) VALUES (:k, :v)");
        $saved = 0;
        foreach ($data as $k => $v) {
            if (in_array($k, $ALLOWED, true)) {
                $stmt->execute([':k' => $k, ':v' => strval(intval($v))]);
                $saved++;
            }
        }
        echo json_encode(['ok' => true, 'saved' => $saved]);

    } else {
        http_response_code(405);
        echo json_encode(['error' => 'method not allowed']);
    }

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['error' => $e->getMessage()]);
}
