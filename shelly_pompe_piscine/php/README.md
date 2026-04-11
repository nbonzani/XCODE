# Dashboard Pompe Piscine — Installation sur Synology

## Fichiers

- `db.php`    — helpers SQLite (crée la base automatiquement)
- `log.php`   — endpoint POST JSON appelé par le Shelly
- `api.php`   — API JSON lue par le dashboard
- `index.php` — dashboard HTML/JS (rafraîchi toutes les 30 s)
- `pompe.db`  — créé automatiquement au premier appel de `log.php`

## Installation

### 1. Activer Web Station et PHP sur le Synology

DSM → Package Center → installer **Web Station** si ce n'est pas déjà fait.
DSM → Web Station → Web Service Portal → vérifier qu'un **profil PHP** est actif
(PHP 7.4 ou 8.x) pour le site par défaut.

### 2. Activer l'extension SQLite (PDO_SQLite)

DSM → Web Station → PHP Settings → éditer le profil PHP utilisé → onglet
**Extensions** → cocher **pdo_sqlite** → Appliquer.

### 3. Copier les fichiers

Via **File Station** ou un partage SMB, créer le dossier :

    /volume1/web/pompe/

et y déposer `db.php`, `log.php`, `api.php`, `index.php`.

### 4. Droits d'écriture pour SQLite

Le dossier `/volume1/web/pompe/` doit être inscriptible par l'utilisateur qui
fait tourner Apache/Nginx (souvent `http`). Via File Station → clic droit sur
le dossier → Propriétés → Permissions → ajouter `http` en lecture+écriture
(ou positionner le dossier avec `chmod 775` via SSH).

### 5. Tester

Dans un navigateur :

    http://192.168.1.99/pompe/

→ doit afficher « Chargement… » puis une page vide (aucun évènement tant
que le Shelly n'a rien envoyé).

Test manuel de `log.php` depuis la ligne de commande :

```bash
curl -s -X POST "http://192.168.1.99/pompe/log.php" \
     -H "Content-Type: application/json" \
     -d '{"ts":1775568000,"type":"boot","pump_on":true,"grid_w":-320,"mode":"HORS","daily_sec":0,"reason":"test"}'
```

→ doit répondre `{"ok":true,"id":1}` et créer `pompe.db` dans le dossier.

### 6. Activer l'envoi depuis le Shelly

Le script Shelly v2.1 enverra automatiquement :
- au démarrage (`boot`)
- à chaque bascule ON/OFF (`on` / `off`)
- en cas de commande manuelle détectée (`manual`)
- début / fin de conflit avec un autre appareil (`conflict_start` / `conflict_end`)
- toutes les 5 min : un heartbeat avec la puissance courante (`heartbeat`)

## Schéma de la table `events`

| Colonne       | Type    | Description                                   |
|---------------|---------|-----------------------------------------------|
| id            | INTEGER | Clé primaire                                  |
| ts            | INTEGER | Timestamp Shelly (Unix UTC)                   |
| received_at   | INTEGER | Timestamp de réception côté serveur           |
| type          | TEXT    | boot / on / off / manual / heartbeat / ...    |
| pump_on       | INTEGER | 0 ou 1, état de la pompe au moment de l'évènement |
| grid_w        | REAL    | Puissance arrivée générale (W), signe Shelly  |
| grid_avg_w    | REAL    | Moyenne glissante sur 5 mesures (W)           |
| pv_w          | REAL    | Puissance PV (W, canal em1:1)                 |
| mode          | TEXT    | "ETE" ou "HORS"                               |
| daily_sec     | INTEGER | Cumul de fonctionnement du jour (secondes)    |
| reason        | TEXT    | Motif lisible de l'évènement                  |
| raw           | TEXT    | Payload JSON brut reçu                        |

## Maintenance

- La base grossit d'environ **290 lignes/jour** (288 heartbeats + évènements).
  ≈ 100 MB après 5 ans → pas un souci. Si besoin, nettoyage périodique :

  ```sql
  DELETE FROM events WHERE ts < strftime('%s', 'now', '-90 days');
  VACUUM;
  ```

- Sauvegarde : copier simplement `pompe.db`.
