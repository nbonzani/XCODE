<?php
// watchdog.php - Verifie que le Shelly envoie toujours des donnees au NAS.
// A appeler periodiquement (Planificateur de taches DSM, toutes les 5 min).
// GET watchdog.php?token=...         -> verifie et alerte si besoin
// GET watchdog.php?token=...&test=1  -> envoie un mail de test (sans toucher a l'etat)

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
date_default_timezone_set('Europe/Paris');
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/env.php';
require_once __DIR__ . '/mailer.php';

$token = $_GET['token'] ?? ($_SERVER['HTTP_X_DEPLOY_TOKEN'] ?? '');
if ($token !== env('DEPLOY_TOKEN')) {
    http_response_code(403);
    echo json_encode(['error' => 'unauthorized']);
    exit;
}

$to        = env('ALERT_TO', '');
$threshold = intval(env('WATCHDOG_THRESHOLD_SEC', '900')); // 15 min par defaut

if ($to === '') {
    http_response_code(500);
    echo json_encode(['error' => 'ALERT_TO non configure dans .env']);
    exit;
}

try {
    $pdo = db();

    if (isset($_GET['test'])) {
        $res = send_alert_mail($to, '[Pompe Piscine] Test watchdog',
            "Ceci est un mail de test envoye manuellement depuis watchdog.php.\n" .
            "Si tu le recois, la configuration SMTP est correcte.");
        echo json_encode(['ok' => $res['ok'], 'error' => $res['error']]);
        exit;
    }

    $lastReceived = intval($pdo->query("SELECT COALESCE(MAX(received_at), 0) FROM events")->fetchColumn());
    $now = time();
    $gap = $now - $lastReceived;

    $cfg = $pdo->query("SELECT key, value FROM config WHERE key LIKE 'watchdog_%'")
                ->fetchAll(PDO::FETCH_KEY_PAIR);
    $alertActive = ($cfg['watchdog_alert_active'] ?? '0') === '1';

    $set = function (string $k, string $v) use ($pdo) {
        $stmt = $pdo->prepare("INSERT OR REPLACE INTO config (key, value) VALUES (:k, :v)");
        $stmt->execute([':k' => $k, ':v' => $v]);
    };

    $result = ['gap_sec' => $gap, 'threshold_sec' => $threshold, 'alert_active' => $alertActive];

    if ($gap > $threshold && !$alertActive) {
        // Nouvelle panne detectee : on alerte
        $mins = intval($gap / 60);
        $res = send_alert_mail($to, '[Pompe Piscine] Plus de donnees du Shelly',
            "Le NAS n'a plus recu de donnees du Shelly depuis {$mins} min " .
            "(derniere reception : " . date('d/m/Y H:i:s', $lastReceived) . ").\n\n" .
            "Le programme de pilotage de la pompe s'est probablement arrete. " .
            "Verifie le Shelly Pro EM50 (192.168.1.217) et sa connexion WiFi.");
        $set('watchdog_alert_active', '1');
        $set('watchdog_alert_since', strval($now));
        $result['action'] = 'alert_sent';
        $result['mail_ok'] = $res['ok'];
        $result['mail_error'] = $res['error'];

    } elseif ($gap <= $threshold && $alertActive) {
        // Reprise des donnees apres une panne : on previent que c'est resolu
        $since = intval($cfg['watchdog_alert_since'] ?? $now);
        $downMin = intval(($now - $since) / 60);
        $res = send_alert_mail($to, '[Pompe Piscine] Reprise des donnees',
            "Le NAS recoit a nouveau des donnees du Shelly.\n" .
            "Duree de la coupure : environ {$downMin} min.");
        $set('watchdog_alert_active', '0');
        $result['action'] = 'resolved_sent';
        $result['mail_ok'] = $res['ok'];
        $result['mail_error'] = $res['error'];

    } else {
        $result['action'] = 'none';
    }

    $result['ok'] = true;
    echo json_encode($result);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['error' => $e->getMessage()]);
}
