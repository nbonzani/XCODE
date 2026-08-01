<?php
// purge.php - Supprime tous les évènements antérieurs à une date choisie.
// Usage local uniquement — même token que deploy.php.

header('Content-Type: application/json; charset=utf-8');
date_default_timezone_set('Europe/Paris');
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/env.php';

if (!isset($_SERVER['HTTP_X_DEPLOY_TOKEN']) ||
    $_SERVER['HTTP_X_DEPLOY_TOKEN'] !== env('DEPLOY_TOKEN')) {
    http_response_code(403);
    echo json_encode(['error' => 'unauthorized']);
    exit;
}

$before = $_GET['before'] ?? '';
if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $before)) {
    http_response_code(400);
    echo json_encode(['error' => 'paramètre before invalide (format YYYY-MM-DD attendu)']);
    exit;
}

// Convertir la date en timestamp Unix (début de journée, heure locale)
$ts = strtotime($before . ' 00:00:00');
if ($ts === false) {
    http_response_code(400);
    echo json_encode(['error' => 'date invalide']);
    exit;
}

try {
    $pdo = db();
    $count_before = intval($pdo->query("SELECT COUNT(*) FROM events")->fetchColumn());
    $stmt = $pdo->prepare("DELETE FROM events WHERE ts < :ts");
    $stmt->execute([':ts' => $ts]);
    $deleted = $stmt->rowCount();
    $count_after = intval($pdo->query("SELECT COUNT(*) FROM events")->fetchColumn());
    // Compacter la base
    $pdo->exec("VACUUM");
    echo json_encode([
        'ok'           => true,
        'before_date'  => $before,
        'deleted'      => $deleted,
        'remaining'    => $count_after,
    ]);
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['error' => $e->getMessage()]);
}
