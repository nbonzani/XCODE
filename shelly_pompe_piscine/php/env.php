<?php
// env.php - Charge les variables depuis .env (non versionné) dans $_ENV.
// Usage : require_once __DIR__ . '/env.php'; env('DEPLOY_TOKEN');

function env(string $key, ?string $default = null): ?string {
    static $loaded = false;
    if (!$loaded) {
        $path = __DIR__ . '/.env';
        if (is_file($path)) {
            foreach (file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
                $line = trim($line);
                if ($line === '' || $line[0] === '#' || !str_contains($line, '=')) continue;
                [$k, $v] = explode('=', $line, 2);
                $_ENV[trim($k)] = trim($v);
            }
        }
        $loaded = true;
    }
    return $_ENV[$key] ?? $default;
}
