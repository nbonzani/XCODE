<?php
// deploy.php - endpoint de déploiement sécurisé (usage local uniquement)
// Supprimer ce fichier si le NAS est exposé sur internet.

require_once __DIR__ . '/env.php';

if (!isset($_SERVER['HTTP_X_DEPLOY_TOKEN']) ||
    $_SERVER['HTTP_X_DEPLOY_TOKEN'] !== env('DEPLOY_TOKEN')) {
    http_response_code(403);
    echo json_encode(['error' => 'unauthorized']);
    exit;
}

$allowed = ['index.php', 'api.php', 'log.php', 'db.php', 'purge.php', 'config.php',
            'env.php', 'mailer.php', 'watchdog.php', '.env'];
$filename = $_GET['file'] ?? '';
if (!in_array($filename, $allowed, true)) {
    http_response_code(400);
    echo json_encode(['error' => 'filename non autorise']);
    exit;
}

$dest = __DIR__ . '/' . $filename;
$content = file_get_contents('php://input');
if ($content === false || strlen($content) === 0) {
    http_response_code(400);
    echo json_encode(['error' => 'body vide']);
    exit;
}

file_put_contents($dest, $content);
echo json_encode(['ok' => true, 'file' => $filename, 'bytes' => strlen($content)]);
