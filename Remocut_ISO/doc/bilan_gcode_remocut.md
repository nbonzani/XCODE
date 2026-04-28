# Bilan d'analyse GCode — REMOCUT II h2o / Contrôleur Eurosoft ECP1000

**Date d'analyse :** 11 avril 2026  
**Répertoire source :** `C:\Users\bonzani1.PNY-GM-NBO\Documents\CLAUDE\REMOCUT\Cfg-2020-11-25-17-02`  
**Générateur CN :** DrvEcp1000 by Eurosoft S.R.L. — Build MAR 18 2020

---

## 1. Inventaire des fichiers

### Répertoire racine `REMOCUT\`

| Nom | Extension | Taille | Catégorie | Chemin |
|-----|-----------|--------|-----------|--------|
| ACIER.docx | .docx | 13 299 o | Documentation | `REMOCUT\ACIER.docx` |
| Cfg-2020-11-25-17-02.tgz | .tgz | 75,3 Mo | Archive sauvegarde | `REMOCUT\Cfg-2020-11-25-17-02.tgz` |
| CutexpertSetupV4.exe | .exe | 325 Mo | Binaire installateur | `REMOCUT\CutexpertSetupV4.exe` |
| cutexpert.mdb | .mdb | 10,1 Mo | Base Access (technologie) | `REMOCUT\cutexpert.mdb` |

### Répertoire `Prog\` — Programmes de découpe

| Nom | Extension | Taille | Catégorie | Matériau associé |
|-----|-----------|--------|-----------|-----------------|
| 0.5_01.iso | .iso | 1 832 o | Programme GCode plasma | Acier-30A Fine Cut-Vitesse lente-0.5mm |
| 0.6_01.iso | .iso | 1 832 o | Programme GCode plasma | Acier-30A Fine Cut-Vitesse lente-0.6mm |
| 0.8_01.iso | .iso | 1 832 o | Programme GCode plasma | Acier-30A Fine Cut-Vitesse lente-0.8mm |
| 1.5_01.iso | .iso | 1 832 o | Programme GCode plasma | Acier-45A FineCut-Vitesse Rapide-1.5mm |
| 10_01.iso | .iso | 1 807 o | Programme GCode plasma | Acier-85A-10mm |
| 12_01.iso | .iso | 1 808 o | Programme GCode plasma | Acier-105A-12mm |
| 15_01.iso | .iso | 1 808 o | Programme GCode plasma | Acier-105A-15mm |

### Répertoire `Cfg-2020-11-25-17-02\settings\` — Configuration machine

| Nom | Extension | Taille | Catégorie |
|-----|-----------|--------|-----------|
| cnc.ini | .ini | 7 244 o | Config IHM (dernière session) |
| globals.ini | .ini | 10 574 o | Paramètres machine actifs |
| ioredir.ini | .ini | 2 321 o | Redirection E/S matériel |
| appconfig.js | .js | 1 047 o | Config application IHM |
| CustomVARS.DAT | .DAT | 1 o | Variables personnalisées (vide) |
| Custom_Ante | — | 0 o | Script pré-coupe personnalisé (vide) |
| Custom_Post | — | 0 o | Script post-coupe personnalisé (vide) |
| cnc.sav | .sav | 4 883 o | Sauvegarde config IHM (usine) |
| globals.sav | .sav | 5 803 o | Sauvegarde paramètres machine (usine) |
| ioredir.sav | .sav | 145 o | Sauvegarde redirection E/S (usine) |
| ALFA.png, remo.png, remocut.png, … | .png | divers | Ressources graphiques IHM |

### Répertoire `Cfg-2020-11-25-17-02\Databases\` — Bases de données

| Fichier .ini | Fichier .sqlite | Taille | Description |
|-------------|----------------|--------|-------------|
| 0c54ed5f…(pas d'ini) | 0c54ed5f….sqlite | 1,78 Mo | **Base principale** : paramètres matériaux (38 matériaux) |
| 1a133e8a….ini | 1a133e8a….sqlite | 2 048 o | CncDb — points zéro machine |
| 26a40bba….ini | 26a40bba….sqlite | 3 072 o | ModelDB — modèles paramétriques |
| 3225a10b….ini | 3225a10b….sqlite | 2 048 o | Parameters — paramètres lead-in/lead-out |
| 37a46cb8….ini | 37a46cb8….sqlite | 161 Ko | **HyperthermHPR** — procédés Hypertherm HPR (824 procédés) |
| 634a01a7….ini | 634a01a7….sqlite | 902 Ko | Td-AGC — base Thermadyne AGC |
| 6db435f3….ini | 6db435f3….sqlite | 2,37 Mo | Logger — journal d'erreurs |
| 955ce262….ini | 955ce262….sqlite | 10 240 o | thccfg — configuration THC |
| afd1532b….ini | afd1532b….sqlite | 41 Ko | **Powermax** — procédés Powermax ECP-1000 |
| ceffe753….ini | ceffe753….sqlite | 17,9 Mo | BatchModel — modèles de programmes par lots |
| oem-log.sqlite | — | 2 048 o | Journal OEM |

### Autres fichiers de configuration

| Nom | Extension | Taille | Catégorie |
|-----|-----------|--------|-----------|
| AvxInterface.h | .h | 188 835 o (binaire) | Interface applicative EtherCAT (bibliothèque partagée .so) |
| AvxInterface.so | .so | 188 835 o | Bibliothèque partagée Linux |
| CncPrestart.sh | .sh | 2 810 o | Script démarrage Linux (réseau, RTAI, EtherCAT) |
| CncStartup.sh | .sh | 891 o | Script boucle principale IHM |
| CncTools.sh | .sh | 56 095 o | Utilitaires CN (binaire Shell) |
| .runinfo | — | 45 o | Configuration modules RTAI |
| .chksum | — | 33 o | Somme de contrôle de la sauvegarde |
| EurosoftCN/qmldir | — | 21 o | Plugin QML (interface CN) |
| openvpn/ | — | — | Configuration VPN |
| app.enc/ | — | — | Application chiffrée (eCryptFS, illisible) |

---

## 2. Format GCode confirmé de l'ECP1000

### 2.1 Format de fichier

| Propriété | Valeur |
|-----------|--------|
| Extension | `.iso` |
| Encodage | ASCII (7 bits, confirmé par `file` et hexdump) |
| Délimiteurs de ligne | LF (`\n`, format Unix) |
| Séparateur décimal | `.` (point) |
| Unité | millimètres |
| Coordonnées | absolues (G90) |
| Précision | 6 décimales pour les coordonnées |

### 2.2 Structure générale d'un programme type

```
ZONE 1 — EN-TÊTE (commentaires + sélection matériau)
  ; [hash SHA256 du programme — signature Eurosoft]
  ; ( DrvEcp1000 BY EUROSOFT S.R.L. BUILD : MAR 18 2020 )
  ; ( PROGRAM NAME=NOM_DU_PROGRAMME )
  ; ( SHEET DIMENSION L x H )
  $material = "Nom-Matériau-dans-la-base"
  G90

ZONE 2 — SÉQUENCE DE COUPE (répétée pour chaque contour)
  G92 I1 T1             ← sélection outil 1 / torche 1
  G00                   ← passage en mode déplacement rapide
  F $vrapid             ← vitesse rapide
  G00 X... Y...         ← déplacement vers point de piquage

  M17.1                 ← descente torche (détection ohmique)
  G01                   ← passage en mode interpolation linéaire
  F $plasma.cut_feed[*0.500000]  ← vitesse lead-in (50 % de la vitesse de coupe)
  M20.1                 ← allumage arc plasma + délai de perçage
  M23.1                 ← début de lead-in (entrée dans la matière)
  [contour géométrique : G01 / G02 / G03]
  M19.1                 ← début séquence lead-out (sortie)
  [sortie géométrique]
  M21.1                 ← extinction arc plasma
  M24.1                 ← fin de séquence de coupe
  M18.1                 ← montée torche
  G92 I0                ← désélection outil

ZONE 3 — FIN DE PROGRAMME
  G90
  M30
```

### 2.3 G-codes utilisés

| Code | Rôle observé |
|------|-------------|
| `G90` | Coordonnées absolues (déclaré en en-tête et en fin de programme) |
| `G92 I1 T1` | **Non standard ISO** — Sélection outil n°1 / torche n°1 (syntaxe ECP1000) |
| `G92 I0` | **Non standard ISO** — Désélection outil courant |
| `G00` | Déplacement rapide (positionnement sans coupe) |
| `G01` | Interpolation linéaire (coupe ou lead-in/out en ligne droite) |
| `G03` | Interpolation circulaire sens antihoraire — utilisé pour les lead-in/out circulaires et les contours courbes |

> **Note :** `G02` (sens horaire) n'est pas présent dans ces 7 programmes mais est une commande standard que le contrôleur accepte.

### 2.4 M-codes utilisés

Le suffixe `.1` indique que la commande s'applique à la torche numéro 1 (en cas de machine multi-torche, `.2` désignerait la torche 2, etc.).

| Code | Rôle observé | Contexte dans le programme |
|------|-------------|---------------------------|
| `M17.1` | **Descente torche** — amorce la détection ohmique du contact avec la tôle | Avant `M20.1`, après positionnement XY |
| `M18.1` | **Montée torche** — dégagement de la tôle après extinction | Après `M24.1` à la fin de chaque contour |
| `M19.1` | **Début lead-out** — signal début de la sortie de coupe | Avant le dernier arc `G03` de fermeture |
| `M20.1` | **Allumage arc plasma + perçage** — déclenche la torche, attend le délai `PIERCING_TIME` | Avant `M23.1` |
| `M21.1` | **Extinction arc plasma** — coupe le courant torche | Après le lead-out, avant `M24.1` |
| `M23.1` | **Début lead-in** — signal de début d'entrée dans la matière | Après `M20.1`, avant le contour |
| `M24.1` | **Fin de séquence de coupe** — validation fin de pièce | Après `M21.1` |
| `M30` | **Fin de programme** — arrêt complet | Dernière ligne du fichier |

### 2.5 Paramètres F (vitesse) et autres lettres-adresses

| Syntaxe | Type | Rôle |
|---------|------|------|
| `F $vrapid` | Variable | Vitesse de déplacement rapide (valeur issue de `globals.ini` : 45 000 mm/min) |
| `F $plasma.cut_feed[*1.000000]` | Variable avec facteur | Vitesse de coupe nominale × 1,0 = 100 % |
| `F $plasma.cut_feed[*0.700000]` | Variable avec facteur | 70 % de la vitesse nominale (coins à 90°) |
| `F $plasma.cut_feed[*0.800000]` | Variable avec facteur | 80 % (coins intermédiaires) |
| `F $plasma.cut_feed[*0.500000]` | Variable avec facteur | 50 % (lead-in, ralentissement d'entrée) |
| `X`, `Y` | Coordonnées | Position absolue en mm (6 décimales) |
| `I`, `J` | Incréments | Centre de l'arc relatif au point courant (G02/G03) |
| `I1 T1` | Paramètre G92 | Sélection outil 1 (non standard) |

> **Important :** La syntaxe `$plasma.cut_feed[*N]` est propre à l'ECP1000. Elle ne peut pas être remplacée par une valeur numérique directe si l'on souhaite que le programme s'adapte automatiquement au matériau sélectionné dans l'IHM. Pour un générateur Python, il faudra utiliser cette syntaxe exacte.

---

## 3. Exemples de programmes annotés

### 3.1 Programme `0.5_01.iso` — Acier 0,5 mm / 30 A Fine Cut

Ce programme illustre la structure complète avec deux contours : un trou circulaire (lead-in avec M23) et un cadre rectangulaire.

```gcode
;0cf2779390e4e3475832aba24e3e91fd18022648…  ← Hash SHA256 (signature ECP1000, ne pas modifier)
; ( DrvEcp1000 BY EUROSOFT S.R.L. BUILD : MAR 18 2020 )   ← En-tête driver obligatoire
; ( PROGRAM NAME=0.5 )                                    ← Nom affiché dans l'IHM
; ( SHEET DIMENSION 3000 x 1500 )                         ← Dimension tôle (informatif)
$material = "Acier-30A Fine Cut-Vitesse lente-0.5mm"      ← Sélection matériau (clé dans la DB)
G90                                                       ← Mode absolu

;--- CONTOUR 1 : trou circulaire ---
G92 I1 T1                        ← Activation torche 1
G00                               ← Mode déplacement rapide
F $vrapid                         ← Vitesse rapide (45 000 mm/min)
G00 X59.724011 Y-55.662495        ← Positionnement au point de piquage (hors contour)
M17.1                             ← Descente torche / détection ohmique de la tôle
G01                               ← Mode interpolation
F $plasma.cut_feed[*0.500000]     ← Vitesse = 50 % de la vitesse de coupe (lead-in lent)
M20.1                             ← Allumage plasma + délai de perçage (THC_PIERCING_TIME)
M23.1                             ← Signal début lead-in
G03 X53.744058 Y-62.684588 I1.256779 J-7.127546   ← Arc lead-in circulaire (1er arc)
G03 X55.900524 Y-67.944875 I7.236732 J-0.105453   ← Continuation arc lead-in
G03 X60.350000 Y-70.000000 I5.080265 J5.154834    ← Arrivée sur le contour de la pièce
G03 X65.129264 Y-68.733384 I0.000000 J9.650000    ← Coupe du contour circulaire
G03 X61.843967 Y-50.816346 I-4.779264 J8.383384   ← Suite du contour
G03 X53.235377 Y-66.869558 I-1.493967 J-9.533654  ← Suite du contour
G03 X59.950115 Y-69.991711 I7.114623 J6.519558    ← Approche du lead-out
M19.1                                              ← Signal début lead-out
G03 X60.350000 Y-70.000000 I0.399885 J9.641711    ← Arc lead-out (fermeture de la coupe)
G03 X63.104815 Y-69.598432 I0.000000 J9.650000    ← Sortie définitive
M21.1                                              ← Extinction arc plasma
M24.1                                              ← Fin de séquence coupe
M18.1                                              ← Montée torche
G92 I0                                             ← Désactivation torche 1

;--- CONTOUR 2 : périmètre rectangulaire (cadre 100×100 mm) ---
G92 I1 T1
G00
F $vrapid
G00 X110.700000 Y-5.000000                         ← Positionnement à l'extérieur du cadre
M17.1                                              ← Descente torche
G01
F $plasma.cut_feed[*1.000000]                      ← Vitesse 100 % (mode nominal)
F $plasma.cut_feed[*0.700000]                      ← Réduit à 70 % pour lead-in angulaire
M20.1                                              ← Allumage plasma
G01 X110.700000 Y-10.000000                        ← Lead-in linéaire (entrée sur le coin)
G01 X110.700000 Y-15.000000                        ← Fin lead-in
F $plasma.cut_feed[*1.000000]                      ← Retour vitesse 100 %
M21.1                                              ← (Note : M21 ici = pause/détection – pas extinction)
G01 X110.700000 Y-105.700000                       ← Coupe côté droit (vertical)
M20.1                                              ← Reprise coupe (coin bas-droit)
G01 X110.700000 Y-106.700000                       ← Approche coin
F $plasma.cut_feed[*0.800000]                      ← Ralentissement à 80 % pour le coin
G01 X110.700000 Y-110.700000                       ← Coin bas-droit
G01 X106.700000 Y-110.700000                       ← 1 mm après le coin
F $plasma.cut_feed[*1.000000]                      ← Retour vitesse normale
G01 X105.700000 Y-110.700000
M21.1                                              ← Fin zone coin
G01 X15.000000 Y-110.700000                        ← Côté bas (horizontal)
M20.1                                              ← Coin bas-gauche
G01 X14.000000 Y-110.700000
F $plasma.cut_feed[*0.800000]
G01 X10.000000 Y-110.700000                        ← Coin bas-gauche
G01 X10.000000 Y-106.700000
F $plasma.cut_feed[*1.000000]
G01 X10.000000 Y-105.700000
M21.1
G01 X10.000000 Y-15.000000                         ← Côté gauche (vertical)
M20.1                                              ← Coin haut-gauche
G01 X10.000000 Y-14.000000
F $plasma.cut_feed[*0.800000]
G01 X10.000000 Y-10.000000
G01 X14.000000 Y-10.000000
F $plasma.cut_feed[*1.000000]
G01 X15.000000 Y-10.000000
M21.1
G01 X100.700000 Y-10.000000                        ← Côté haut (horizontal)
F $plasma.cut_feed[*0.700000]                      ← Ralentissement lead-out
M20.1
G01 X110.700000 Y-10.000000                        ← Retour point départ (fermeture)
G01 X115.700000 Y-10.000000                        ← Dépassement de 5 mm
M21.1
M18.1                                              ← Montée torche
G92 I0                                             ← Désactivation torche
G90
M30                                                ← Fin de programme
```

> **Observation sur M20/M21 aux coins :** Dans le périmètre rectangulaire, `M20.1` et `M21.1` sont utilisés conjointement pour délimiter les zones de ralentissement aux coins. Il ne s'agit **pas** d'extinction/rallumage de l'arc à chaque coin, mais d'un signal au contrôleur ECP1000 pour activer/désactiver la gestion de vitesse adaptative aux coins. Cette interprétation est cohérente avec la logique THC de l'ECP1000.

### 3.2 Programme `10_01.iso` — Acier 10 mm / 85 A (différences notables)

Les différences avec les programmes fine-cut sont :
- Rayon de lead-in plus grand (9 mm vs ~9,65 mm pour 0,5 mm — relatif au kerf plus large)
- Décalage du point de start plus éloigné du bord (Y=-10 au lieu de Y=-5)
- Zone de ralentissement aux coins plus étendue (5 mm au lieu de 1 mm)
- Matériau référencé : `"Acier-85A-10mm"` → THC_PIERCING_TIME_1 = 0,5 s

---

## 4. Paramètres machine identifiés

### 4.1 Paramètres globaux machine (source : `globals.ini` + base SQLite principale)

| Paramètre | Valeur | Unité | Description |
|-----------|--------|-------|-------------|
| `vrapid` | 45 000 | mm/min | Vitesse déplacement rapide G00 |
| `accel` | 2 000 | mm/s² | Accélération générale |
| `accel_g0` | 400 | mm/s² | Accélération en déplacement rapide |
| `accramp_g1` | 300 | mm/s² | Rampe d'accélération en G01 |
| `dim_plate_x` | 3 000 | mm | Largeur tôle par défaut |
| `dim_plate_y` | 1 500 | mm | Hauteur tôle par défaut |
| `HomeSpeedXY` | 1 500 | mm/min | Vitesse de retour origine XY |
| `HomeSpeedZ` | 500 | mm/min | Vitesse de retour origine Z |
| `POWERON_TIME` | 1 500 | ms | Délai mise en puissance |
| `JogSpeed` | 15 000 | mm/min | Vitesse de déplacement manuel |

### 4.2 Paramètres de coupe par matériau (acier)

Les paramètres ci-dessous proviennent de la base de données SQLite principale (`0c54ed5f….sqlite`, table `variables`). Le champ `cut_feed_1` est la vitesse effective de coupe lorsque le processus actif est le profil plasma 1 (Powermax Fine Cut ou standard).

#### Acier — Fine Cut (Powermax 30 A)

| Matériau | Épaisseur | Ampérage | cut_feed_1 (mm/min) | THC_PIERCING_TIME_1 (s) | THC_WORKING_HEIGHT_1 (mm) | THC_VOLTAGE_SET_POINT_1 (V) |
|---------|-----------|----------|---------------------|------------------------|--------------------------|----------------------------|
| Acier-30A Fine Cut-Vitesse lente | 0,5 mm | 30 A | 3 800 | 0,0 | 1,5 | 69 |
| Acier-30A Fine Cut-Vitesse lente | 0,6 mm | 30 A | 3 800 | 0,0 | 1,5 | 68 |
| Acier-30A Fine Cut-Vitesse lente | 0,8 mm | 30 A | 3 800 | 0,1 | 1,5 | 70 |
| Acier-45A FineCut-Vitesse Rapide | 1,5 mm | 45 A | 6 400 | 0,4 | 1,5 | 78 |

#### Acier — Coupe standard (Powermax 85 A)

| Matériau | Épaisseur | Ampérage | cut_feed_1 (mm/min) | THC_PIERCING_TIME_1 (s) | THC_PIERCING_HEIGHT_1 (mm) | THC_VOLTAGE_SET_POINT_1 (V) |
|---------|-----------|----------|---------------------|------------------------|---------------------------|----------------------------|
| Acier-85A | 6 mm | 85 A | — | — | — | — |
| Acier-85A | 8 mm | 85 A | — | — | — | — |
| Acier-85A | 10 mm | 85 A | 1 680 | 0,5 | 3,8 | 127 |
| Acier-85A | 12 mm | 85 A | 1 280 | 0,7 | 4,5 | 130 |
| Acier-85A | 15 mm | 85 A | 870 | 1,0 | 4,5 | 134 |
| Acier-85A | 20 mm | 85 A | — | — | — | — |

> **Note :** Les matériaux `Acier-105A-12mm` et `Acier-105A-15mm` (utilisés dans les fichiers `12_01.iso` et `15_01.iso`) ne figurent pas dans la base SQLite principale. Leurs paramètres proviennent probablement d'une version plus récente de la base Powermax ou de la base `cutexpert.mdb`.

#### Inox (extrait, pour référence)

| Matériau | Épaisseur | Ampérage | cut_feed_1 (mm/min) | THC_PIERCING_TIME_1 (s) | THC_VOLTAGE_SET_POINT_1 (V) |
|---------|-----------|----------|---------------------|------------------------|----------------------------|
| Inox-30A FineCut | 0,5 mm | 30 A | — | — | — |
| Inox-40A FineCut | 1,0 mm | 40 A | — | — | — |
| Inox-40A FineCut | 1,5 mm | 40 A | — | — | — |
| Inox-65A | 4 mm | 65 A | — | — | — |
| Inox-85A | 6 mm | 85 A | — | — | — |

#### Aluminium (extrait, pour référence)

| Matériau | Épaisseur | Ampérage | cut_feed_1 (mm/min) |
|---------|-----------|----------|---------------------|
| Alu-45A FineCut | 1,0 mm | 45 A | — |
| Alu-65A | 3 mm | 65 A | — |
| Alu-85A | 6 mm | 85 A | — |

> Pour les champs marqués `—` : les paramètres sont présents dans la base mais nécessitent une requête SQL spécifique (les valeurs `cut_feed_1` de ces matériaux n'ont pas toutes été extraites dans cette session d'analyse). Ils sont accessibles via `SELECT varvalue FROM variables WHERE material='NomMat' AND varname='cut_feed_1'`.

### 4.3 Paramètres THC (Torch Height Control)

| Paramètre | Valeur (globals.ini actif) | Rôle |
|-----------|--------------------------|------|
| `THC_DEAD_BAND` | 1,0 V | Bande morte pour la régulation de hauteur |
| `THC_SEARCH_SPEED` | 1 000 mm/min | Vitesse de descente lors de la détection ohmique |
| `THC_RAPID_SPEED` | 15 000 mm/min | Vitesse de déplacement Z rapide |
| `THC_RELEASING_SPEED` | 100 mm/min | Vitesse de décollage après contact |
| `THC_MOVEUP_DIST` | 10 mm | Distance de montée après chaque coupe |
| `THC_OPTIMIZATION` | 1 (activé) | Optimisation des trajectoires THC |
| `THC_V_FACT_SCALE` | 0,297 | Facteur d'échelle tension → hauteur |
| `THC_INITIAL_LOCK` | 400 ms | Verrouillage THC initial après allumage arc |
| `THC_AFTER_PIERCE_LOCK` | 200 ms | Verrouillage THC après perçage |

---

## 5. Conclusions pour le développement Python

### 5.1 Format exact du fichier à générer

| Propriété | Spécification |
|-----------|--------------|
| **Extension** | `.iso` (obligatoire pour la reconnaissance par l'IHM ECP1000) |
| **Encodage** | `ASCII` ou `UTF-8` sans BOM (les caractères sont exclusivement ASCII dans les programmes observés) |
| **Délimiteurs de ligne** | `\n` (LF uniquement, format Unix) — **ne pas utiliser `\r\n`** |
| **Séparateur décimal** | `.` (point) — **ne jamais utiliser la virgule** |
| **Précision coordonnées** | 6 décimales recommandées (format `{:.6f}`) |
| **Chemin de dépôt** | `/work/` sur la CN Linux, ou via clé USB (ex : `/media/CLE_POLYTEC/`) |
| **Commentaires** | Lignes commençant par `;` — la première ligne est le hash, ne doit pas être reproduite manuellement |

### 5.2 Séquence minimale valide pour un programme de découpe

```python
# Template Python pour générer un programme ISO ECP1000 minimal
# (un seul contour, coupe fermée)

template = """\
; ( DrvEcp1000 BY EUROSOFT S.R.L. )
; ( PROGRAM NAME={name} )
; ( SHEET DIMENSION {sheet_x} x {sheet_y} )
$material = "{material}"
G90
G92 I1 T1
G00
F $vrapid
G00 X{start_x:.6f} Y{start_y:.6f}
M17.1
G01
F $plasma.cut_feed[*0.500000]
M20.1
M23.1
{contour_lines}
M19.1
{leadin_out_lines}
M21.1
M24.1
M18.1
G92 I0
G90
M30
"""
```

**Variables à fournir :**
- `{name}` : nom du programme (sans espaces recommandé)
- `{sheet_x}`, `{sheet_y}` : dimensions de la tôle en mm
- `{material}` : chaîne exacte correspondant à un entrée dans la table `materials` de la base SQLite
- `{start_x}`, `{start_y}` : point de piquage en coordonnées absolues (mm)
- `{contour_lines}` : liste de commandes `G01`/`G02`/`G03` du contour
- `{leadin_out_lines}` : arcs de sortie (lead-out)

**Gestion des vitesses aux coins pour les contours rectangulaires :**
```python
# Avant chaque coin à 90° : encadrer avec M20.1/M21.1 + réduction de vitesse
corner_sequence = """\
M20.1
G01 X{x_approach:.6f} Y{y_approach:.6f}
F $plasma.cut_feed[*0.800000]
G01 X{x_corner:.6f} Y{y_corner:.6f}
G01 X{x_after:.6f} Y{y_after:.6f}
F $plasma.cut_feed[*1.000000]
G01 X{x_resume:.6f} Y{y_resume:.6f}
M21.1
"""
```

### 5.3 Noms de matériaux disponibles dans la base (38 entrées)

La liste complète des matériaux utilisables dans `$material = "..."` est :

**Acier :** Acier-30A Fine Cut-Vitesse lente-0.5mm, 0.6mm, 0.8mm, 1mm · Acier-45A Fine Cut- Vitesse lente-2mm, 3mm · Acier-45A FineCut-Vitesse Rapide-1mm, 1.5mm · Acier-65A-3mm, 4mm, 5mm · Acier-85A-6mm, 8mm, 10mm, 12mm, 15mm, 20mm

**Inox :** Inox-30A FineCut-Vitesse lente-0.5mm · Inox-40A FineCut-Vitesse lente-1mm, 1.5mm · Inox-45A FineCut-Vitesse lente-2mm, 3mm · Inox-65A-4mm, 5mm · Inox-85A-6mm, 8mm, 10mm, 12mm

**Aluminium :** Alu-45A FineCut-Vitesse Rapide-1mm, 2mm · Alu-65A-3mm, 4mm, 5mm · Alu-85A-6mm, 8mm, 10mm, 12mm

**Défaut :** Default

### 5.4 Points d'incertitude restants

| Point | Niveau d'incertitude | Commentaire |
|-------|---------------------|-------------|
| **Ligne de hash (ligne 1)** | Élevé | Le hash en première ligne est généré par le driver Eurosoft. Il n'est pas clair si le contrôleur le vérifie. Les programmes sans hash semblent acceptés (à confirmer sur machine) |
| **Signification précise de M20/M21 aux coins** | Moyen | D'après l'analyse, ces codes encadrent les zones de ralentissement de coin et ne représentent pas une extinction/rallumage de l'arc. Confirmation nécessaire dans la documentation Eurosoft |
| **Format `G92 I1 T1`** | Faible | Clairement spécifique à l'ECP1000. La syntaxe exacte est confirmée par tous les programmes. Ne pas utiliser `T1` seul ni `M06 T1` |
| **`$plasma.cut_feed` vs valeur numérique** | Moyen | Les programmes observés utilisent exclusivement la variable. Une valeur numérique directe (`F 3800`) pourrait fonctionner mais contournerait la gestion dynamique du matériau |
| **Matériaux 105A (12 et 15 mm)** | Élevé | Absents de la base SQLite principale — paramètres de coupe non disponibles dans cette analyse |
| **Sens des coordonnées Y négatif** | Faible | Toutes les coordonnées Y observées sont négatives. L'axe Y semble orienté vers le bas (Y croissant = direction négative dans le repère programme). À confirmer avec le zéro-pièce machine |
| **Encodage de la ligne `$material`** | Faible | Les espaces et tirets sont acceptés dans le nom de matériau. Les accents ne sont pas présents dans les noms actuels — à éviter par précaution |
| **Nombre de contours par programme** | Sans | Les 7 programmes contiennent exactement 2 contours. Il n'y a pas de limite documentée |

---

*Rapport généré automatiquement par analyse des fichiers sources — Polytech Nancy / Urbanloop — Avril 2026*
