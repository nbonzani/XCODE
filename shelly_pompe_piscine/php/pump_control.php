<?php
// pump_control.php - Proxy POST vers Shelly Switch.Set (contournement CORS)
// Appelé par le dashboard : POST {"on": true|false}
// Répercute la commande sur le Shelly 192.168.1.239

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

$SHELLY_IP = '192.168.1.239';
$SWITCH_ID = 0;

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'method not allowed']);
    exit;
}

$raw  = file_get_contents('php://input');
$data = json_decode($raw, true);

if (!is_array($data) || !isset($data['on'])) {
    http_response_code(400);
    echo json_encode(['error' => 'invalid body, expected {"on": true|false}']);
    exit;
}

$on      = $data['on'] ? true : false;
$payload = json_encode(['id' => $SWITCH_ID, 'on' => $on]);

$ctx = stream_context_create([
    'http' => [
        'method'  => 'POST',
        'header'  => "Content-Type: application/json\r\n",
        'content' => $payload,
        'timeout' => 5,
    ],
]);

$url  = "http://{$SHELLY_IP}/rpc/Switch.Set";
$resp = @file_get_contents($url, false, $ctx);

if ($resp === false) {
    http_response_code(502);
    echo json_encode(['error' => 'Shelly unreachable', 'url' => $url]);
    exit;
}

// Retransmet la réponse du Shelly telle quelle
echo $resp;
