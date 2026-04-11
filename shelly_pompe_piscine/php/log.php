<?php
// log.php - Endpoint de réception des évènements envoyés par le Shelly Pro EM
// Accepte un POST JSON, stocke en SQLite, répond en JSON.

header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/db.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'POST only']);
    exit;
}

$raw = file_get_contents('php://input');
$data = json_decode($raw, true);

if (!is_array($data) || !isset($data['type'])) {
    http_response_code(400);
    echo json_encode(['error' => 'invalid JSON payload', 'raw' => $raw]);
    exit;
}

try {
    $pdo = db();
    $stmt = $pdo->prepare("
        INSERT INTO events
            (ts, received_at, type, pump_on, grid_w, grid_avg_w, pv_w, mode, daily_sec, reason, raw)
        VALUES
            (:ts, :rx, :type, :pump_on, :grid, :gridavg, :pv, :mode, :daily, :reason, :raw)
    ");
    $stmt->execute([
        ':ts'      => isset($data['ts']) ? intval($data['ts']) : time(),
        ':rx'      => time(),
        ':type'    => substr((string)$data['type'], 0, 32),
        ':pump_on' => isset($data['pump_on']) ? ($data['pump_on'] ? 1 : 0) : null,
        ':grid'    => isset($data['grid_w'])     ? floatval($data['grid_w'])     : null,
        ':gridavg' => isset($data['grid_avg_w']) ? floatval($data['grid_avg_w']) : null,
        ':pv'      => isset($data['pv_w'])       ? floatval($data['pv_w'])       : null,
        ':mode'    => isset($data['mode'])       ? substr((string)$data['mode'], 0, 16) : null,
        ':daily'   => isset($data['daily_sec'])  ? intval($data['daily_sec'])    : null,
        ':reason'  => isset($data['reason'])     ? substr((string)$data['reason'], 0, 200) : null,
        ':raw'     => $raw,
    ]);
    echo json_encode(['ok' => true, 'id' => intval($pdo->lastInsertId())]);
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['error' => $e->getMessage()]);
}
