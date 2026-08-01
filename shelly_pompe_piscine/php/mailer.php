<?php
// mailer.php - client SMTP minimal (sans dependance) pour envoyer une alerte
// par mail via un compte Gmail (ou tout serveur SMTP+STARTTLS+AUTH LOGIN).
// Configuration attendue dans .env : SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS.

function smtp_read(&$fp) {
    $data = '';
    while (($line = fgets($fp, 515)) !== false) {
        $data .= $line;
        // Derniere ligne de la reponse : "250 ..." (espace en 4e position)
        // Les lignes intermediaires ont un tiret : "250-..."
        if (isset($line[3]) && $line[3] === ' ') break;
    }
    return $data;
}

function smtp_expect(&$fp, string $prefix): array {
    $resp = smtp_read($fp);
    if (strpos($resp, $prefix) !== 0) {
        return [false, $resp];
    }
    return [true, $resp];
}

// Retourne ['ok' => bool, 'error' => string|null]
function send_alert_mail(string $to, string $subject, string $body): array {
    $host = env('SMTP_HOST', 'smtp.gmail.com');
    $port = intval(env('SMTP_PORT', '587'));
    $user = env('SMTP_USER', '');
    $pass = str_replace(' ', '', env('SMTP_PASS', ''));
    $from = env('ALERT_FROM', $user);

    if ($user === '' || $pass === '') {
        return ['ok' => false, 'error' => 'SMTP_USER/SMTP_PASS non configures dans .env'];
    }

    $fp = @stream_socket_client("tcp://{$host}:{$port}", $errno, $errstr, 10);
    if (!$fp) {
        return ['ok' => false, 'error' => "connexion SMTP echouee: $errstr ($errno)"];
    }
    stream_set_timeout($fp, 10);

    try {
        [$ok, $resp] = smtp_expect($fp, '220');
        if (!$ok) return ['ok' => false, 'error' => "greeting KO: $resp"];

        fwrite($fp, "EHLO localhost\r\n");
        [$ok, $resp] = smtp_expect($fp, '250');
        if (!$ok) return ['ok' => false, 'error' => "EHLO KO: $resp"];

        fwrite($fp, "STARTTLS\r\n");
        [$ok, $resp] = smtp_expect($fp, '220');
        if (!$ok) return ['ok' => false, 'error' => "STARTTLS KO: $resp"];

        if (!@stream_socket_enable_crypto($fp, true, STREAM_CRYPTO_METHOD_TLS_CLIENT)) {
            return ['ok' => false, 'error' => 'negociation TLS echouee'];
        }

        fwrite($fp, "EHLO localhost\r\n");
        [$ok, $resp] = smtp_expect($fp, '250');
        if (!$ok) return ['ok' => false, 'error' => "EHLO (TLS) KO: $resp"];

        fwrite($fp, "AUTH LOGIN\r\n");
        [$ok, $resp] = smtp_expect($fp, '334');
        if (!$ok) return ['ok' => false, 'error' => "AUTH LOGIN KO: $resp"];

        fwrite($fp, base64_encode($user) . "\r\n");
        [$ok, $resp] = smtp_expect($fp, '334');
        if (!$ok) return ['ok' => false, 'error' => "AUTH user KO: $resp"];

        fwrite($fp, base64_encode($pass) . "\r\n");
        [$ok, $resp] = smtp_expect($fp, '235');
        if (!$ok) return ['ok' => false, 'error' => "AUTH pass KO (identifiants ?): $resp"];

        fwrite($fp, "MAIL FROM:<{$from}>\r\n");
        [$ok, $resp] = smtp_expect($fp, '250');
        if (!$ok) return ['ok' => false, 'error' => "MAIL FROM KO: $resp"];

        fwrite($fp, "RCPT TO:<{$to}>\r\n");
        [$ok, $resp] = smtp_expect($fp, '250');
        if (!$ok) return ['ok' => false, 'error' => "RCPT TO KO: $resp"];

        fwrite($fp, "DATA\r\n");
        [$ok, $resp] = smtp_expect($fp, '354');
        if (!$ok) return ['ok' => false, 'error' => "DATA KO: $resp"];

        $headers = "From: {$from}\r\n" .
                   "To: {$to}\r\n" .
                   "Subject: {$subject}\r\n" .
                   "Date: " . date('r') . "\r\n" .
                   "Content-Type: text/plain; charset=utf-8\r\n";
        // Echappement des lignes commencant par un point (RFC 5321)
        $escaped = preg_replace('/^\./m', '..', $body);
        fwrite($fp, $headers . "\r\n" . $escaped . "\r\n.\r\n");
        [$ok, $resp] = smtp_expect($fp, '250');
        if (!$ok) return ['ok' => false, 'error' => "envoi KO: $resp"];

        fwrite($fp, "QUIT\r\n");
        return ['ok' => true, 'error' => null];
    } finally {
        fclose($fp);
    }
}
