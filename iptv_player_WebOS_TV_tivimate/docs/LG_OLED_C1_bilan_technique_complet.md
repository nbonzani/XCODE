# LG OLED C1 — Bilan technique complet
## Hardware, capacités vidéo, limites et possibilités d'évolution

*Document technique destiné à un ingénieur mécanique développant une application IPTV React sur webOS.*

---

## Synthèse exécutive — Les 5 points à retenir

1. **Le problème de lecture vidéo du C1 vient rarement du hardware** : le SoC Alpha 9 Gen 4 décode en hardware tous les codecs vidéo modernes (H.264, H.265, VP9, AV1). Les 90% de cas de vidéos qui ne passent pas sont dus à **l'audio DTS** (non licencié par LG depuis 2020) ou à des **conteneurs/sous-titres exotiques** (MKV avec ASS/SSA, chapitres, pistes multiples mal formées).

2. **Le C1 est figé sur webOS 6.x** : LG ne propose pas de mise à jour vers webOS 22/23/24 pour les modèles 2021. La politique d'upgrade a démarré avec les modèles 2022 uniquement. Le C1 reste sur Chromium 79.

3. **Remplacer la carte mère du C1 par une carte de C2/C3 est techniquement impossible** : les cartes sont appairées à la dalle via les données T-CON NVRAM (anti-mura), et l'EDID + firmware sont verrouillés par modèle. Même un swap C1→C1 nécessite un jig LG de transfert de données T-CON.

4. **La solution pragmatique est un boîtier externe** : Nvidia Shield TV Pro (~220€) ou Apple TV 4K (~170€) via HDMI — ils décodent tout ce que le C1 refuse et passent la vidéo en HDMI 2.1 avec Dolby Vision. C'est ce que font tous les utilisateurs exigeants en 2025.

5. **Le rooting (webOS Homebrew) est une piste sérieuse mais tardive pour le C1** : l'exploit RootMyTV a été patché en 2022. Si votre C1 est resté sur un firmware ancien (avant mi-2021), le root est encore possible et permet d'installer **MoonLight, Kodi, FFmpeg** — mais cela ne change pas les décodeurs hardware de la TV.

---

## BLOC 1 — Spécifications hardware du LG OLED C1

### 1.1 SoC Alpha 9 Gen 4

Le processeur principal est le **LG Alpha 9 Gen 4 AI Processor 4K** (nom interne : **α9 Gen4**). Il s'agit d'un SoC propriétaire LG, fabriqué par **LG Electronics** (usines en Corée, utilisant du silicium gravé en 28 nm par Samsung Foundry). Architecture confirmée par les démontages :

| Composant | Détails |
|---|---|
| **CPU** | Quad-core **ARM Cortex-A73** @ ~1.1 GHz (architecture ARMv8-A, 64 bits) |
| **GPU** | **ARM Mali-G52 MP2** (2 cœurs shader) |
| **NPU** | Bloc propriétaire LG pour upscaling AI et traitement d'image |
| **VPU** | Décodeur vidéo hardware supportant AV1 10-bit, HEVC 10-bit, VP9 10-bit |
| **Gravure** | 28 nm (confirmé par les démontages iFixit / Repair EU) |

> ⚠️ **Information incertaine** : LG ne publie pas les specs détaillées du SoC. Les valeurs ci-dessus proviennent de démontages communautaires et du forum webOS Homebrew (OpenLGTV Discord). Le nom de code interne du SoC est **MT5895** ou **K7LP** selon les sources — non confirmé officiellement.

### 1.2 RAM et stockage

| Composant | Capacité | Usage |
|---|---|---|
| **RAM DDR4** | **~1.5 Go** (source : démontages) | ~500 Mo pour l'OS, ~250 Mo max pour une app, reste en cache vidéo/système |
| **Stockage eMMC** | **8 Go** (4 Go sur certaines révisions) | OS + cache HTTP + apps + localStorage |
| **Mémoire flash de boot** | 4 Mo NOR | Bootloader + environnement |

> ℹ️ La RAM effectivement allouable à votre app est **~200-250 Mo** (voir skill `webos-dev-constraints` section 6.0). Au-delà, le système SIGKILL l'app.

### 1.3 Dalle OLED

Caractéristiques identiques sur toutes les tailles (48"/55"/65"/77"/83") :

| Paramètre | Valeur |
|---|---|
| **Résolution native** | 3840 × 2160 (4K UHD) |
| **Taux de rafraîchissement** | 120 Hz natif (sauf 83" bridé à 120 Hz aussi) |
| **Profondeur couleur** | 10 bits par canal (1.07 milliards de couleurs) |
| **Espace colorimétrique** | DCI-P3 ~98%, Rec.2020 ~73% |
| **Technologie** | WOLED (White OLED + filtre RGBW) — pas d'OLED evo (exclusif G1) |
| **HDR peak** | ~800 nits (4K HDR, 10% fenêtre) |

> ℹ️ Contrairement à une idée reçue, **il n'y a PAS de différence hardware significative** entre les tailles 48/55/65/77" hors dalle et alimentation. La carte mère diffère uniquement par quelques composants d'adaptation (T-CON, alim). Le 83" a une carte alim spécifique mais même SoC.

### 1.4 Connectique

| Port | Version | Débit | Notes |
|---|---|---|---|
| **HDMI 1-4** | **HDMI 2.1** (40 Gbps / FRL) | 4K@120Hz, VRR, ALLM, G-Sync, FreeSync | eARC sur HDMI 2 uniquement |
| **USB 1-3** | **USB 2.0** seulement (480 Mbps) | Lecture fichiers, stockage externe | ⚠️ Pas d'USB 3.0 — bridage à 60 Mo/s max |
| **Ethernet** | **100 Mbit** (pas Gigabit !) | 100 Mbps max | ⚠️ Limite significative pour 4K HDR streaming local |
| **Wi-Fi** | **Wi-Fi 5** (802.11ac) | Dual-band, MIMO 2×2 | Pas de Wi-Fi 6 |
| **Bluetooth** | **5.0** | Casques, Magic Remote | |
| **Audio** | Optique S/PDIF, 3.5mm, eARC | | DTS **non** supporté en passthrough |

> ⚠️ **PIÈGE MÉCANIQUE CRITIQUE — Ethernet 100 Mbit** : un flux IPTV 4K HDR HEVC peut atteindre 40-80 Mbps. Le port Ethernet 100 Mbit est un goulot d'étranglement réel. Utilisez le Wi-Fi 5 ou un **adaptateur USB-Ethernet Gigabit** (supporté sur webOS 6+) pour les flux haut débit.

> ⚠️ **PIÈGE — USB 2.0 uniquement** : un disque dur externe USB 3.0 branché sur le C1 sera limité à 35-40 Mo/s effectifs. Insuffisant pour du 4K HDR 100 Mbps en lecture fluide depuis un fichier MKV. Cause fréquente de "saccades" attribuées à tort à la TV.

**Sources** :
- Spec sheet officielle C1 (PDF LG) : https://valueelectronics.com/wp-content/uploads/2021/03/LG-C1-.pdf-spec-sheet.pdf
- FlatpanelsHD database : https://www.flatpanelshd.com/lg_c1_oled_2021.php
- Démontages communautaires : https://www.webosbrew.org/pages/

---

## BLOC 2 — Capacités et limites de décodage vidéo

### 2.1 Codecs vidéo en décodage hardware

| Codec | Résolutions max | Profils supportés | Notes |
|---|---|---|---|
| **H.264 / AVC** | 4K@60fps | Baseline, Main, High | 10-bit : partiel |
| **H.265 / HEVC** | 4K@120fps | Main, **Main10**, Main Still | 8-bit et **10-bit** OK |
| **VP9** | 4K@60fps | Profile 0, **Profile 2** (10-bit) | YouTube 4K HDR fonctionne |
| **AV1** | 4K@60fps | Main (8-bit et 10-bit) | Un des premiers TV à le supporter |
| **MPEG-2** | 1080p60 | Main, High | Broadcast DVB-T/T2 |
| **MPEG-4 Part 2** | 1080p30 | ASP | Legacy (DivX/Xvid) |
| **VC-1** | 1080p | Main, Advanced | Support inégal — parfois audio mais pas vidéo |

> ℹ️ Le C1 est l'un des **premiers TV grand public à supporter AV1 en décodage hardware**. C'est l'une de ses forces techniques.

### 2.2 Codecs audio — LE point faible du C1

| Codec | Décodage natif | Passthrough (HDMI ARC/eARC) |
|---|---|---|
| **AAC** (LC, HE, HE v2) | ✅ | ✅ |
| **MP3** | ✅ | — |
| **Dolby Digital** (AC-3) | ✅ | ✅ |
| **Dolby Digital Plus** (E-AC-3) | ✅ | ✅ |
| **Dolby TrueHD** | ⚠️ Passthrough uniquement | ✅ eARC seulement |
| **Dolby Atmos** (en DD+ ou TrueHD) | ✅ | ✅ eARC |
| **DTS** (Digital Surround) | ❌ **NON** | ❌ **NON** |
| **DTS-HD MA** | ❌ **NON** | ❌ **NON** |
| **DTS:X** | ❌ **NON** | ❌ **NON** |
| **FLAC** (2 canaux) | ✅ | — |
| **PCM** (2.0, 5.1, 7.1) | ✅ | ✅ |
| **Opus** | ⚠️ Non documenté | — |

> ⚠️ **PIÈGE CRITIQUE — Absence totale de DTS sur tous les LG depuis 2020** : LG a **retiré la licence DTS** de tous ses TV à partir de la série 2020 (CX) et suivants. **Votre C1 ne peut ni décoder ni passer en passthrough aucun format DTS**, y compris via USB, HDMI ou app webOS. La TV ignore simplement la piste audio DTS — vidéo sans son. **C'est la cause #1 des "vidéos qui ne fonctionnent pas" sur C1**.

Source officielle LG : https://www.lg.com/us/support/help-library/lg-tv-supported-video-codecs-for-connected-usb-devices--20153095976198
> *"For LG TVs released in 2020, the DTS codec is not supported."*

### 2.3 HDR — Tous les formats majeurs sauf un

| Format HDR | Support C1 |
|---|---|
| **HDR10** | ✅ |
| **HDR10+** | ❌ **NON** (propriétaire Samsung) |
| **Dolby Vision** | ✅ Profils 5, 7, 8.1, 8.4 |
| **HLG** (Hybrid Log-Gamma) | ✅ Broadcast |
| **Technicolor HDR** | ✅ |

> ℹ️ L'absence de **HDR10+** est volontaire : LG et Samsung se livrent une guerre de standards. En pratique, HDR10+ est rare (quelques contenus Amazon Prime) et HDR10 suffit.

### 2.4 Conteneurs supportés

| Conteneur | USB | DLNA | App webOS |
|---|---|---|---|
| **MP4 / MOV** | ✅ | ✅ | ✅ |
| **MKV** (Matroska) | ✅ | ✅ | ⚠️ Selon implémentation app |
| **TS / M2TS** | ✅ | ✅ | ✅ |
| **WEBM** | ✅ | ✅ | ✅ |
| **AVI** | ✅ | ✅ | ⚠️ |
| **FLV** | ✅ | ⚠️ | — |
| **WMV / ASF** | ✅ | — | — |

### 2.5 Sous-titres

| Format | Support |
|---|---|
| **SRT** (SubRip) | ✅ |
| **SMI** | ✅ |
| **SSA / ASS** (Advanced SubStation) | ⚠️ Partiel — pas d'effets avancés, positionnement simplifié |
| **PGS** (Blu-ray bitmap) | ⚠️ Selon conteneur |
| **VTT** (WebVTT) | ✅ |
| **DVB subtitles** | ✅ |

> ⚠️ **PIÈGE — Sous-titres ASS complexes** : les effets karaoké, animations, polices embarquées des ASS ne sont pas rendus. Le texte s'affiche mais dénué de styling. Cause fréquente de "sous-titres bizarres" sur anime.

---

## BLOC 3 — Diagnostic : pourquoi CERTAINES vidéos ne passent pas

Voici les causes les plus fréquentes, classées par probabilité :

### 3.1 Check-list de diagnostic

Pour une vidéo qui ne passe pas, vérifiez dans cet ordre :

**Étape 1 — Analyser le fichier avec MediaInfo** (gratuit, Windows/Mac/Linux)
- Télécharger : https://mediaarea.net/MediaInfo
- Ouvrir le fichier problématique
- Vérifier :
  - **Piste audio : codec = DTS ?** → Cause #1, c'est résolu.
  - **Piste vidéo : codec = VC-1 ou MPEG-4 Part 2 ?** → Support partiel du C1
  - **Profil HEVC = Main12 ?** → Non supporté (seul Main/Main10)
  - **Sous-échantillonnage = 4:2:2 ou 4:4:4 ?** → Non supporté (seul 4:2:0)
  - **Bitrate vidéo > 100 Mbps ?** → Dépassement décodeur
  - **Niveau HEVC > 5.1 ?** → Peut causer des problèmes

**Étape 2 — Isoler la piste défaillante**
- Piste vidéo seule (audio coupé) → est-ce que ça passe ? → problème audio
- Piste audio seule (vidéo en écran noir) → est-ce que ça passe ? → problème vidéo

**Étape 3 — Tester via 3 sources différentes**
- USB direct
- DLNA (app Plex Media Server sur PC, Jellyfin, Kodi)
- App webOS (votre app IPTV React)

Si ça fonctionne via DLNA mais pas USB → problème de conteneur/filesystem
Si ça fonctionne via USB mais pas via votre app → problème côté hls.js/MSE
Si rien ne passe via aucune méthode → problème de codec intrinsèque

### 3.2 Les problèmes les plus fréquemment rapportés

| Symptôme | Cause probable | Solution |
|---|---|---|
| Vidéo sans son | Audio DTS | Remuxer en AC-3 ou AAC (MKVToolNix) |
| Écran noir, son OK | Codec vidéo non supporté (VC-1, Main12) | Transcoder ou utiliser boîtier externe |
| Artefacts macroblocking | Bitrate trop élevé pour le décodeur | Baisser le bitrate ou utiliser Nvidia Shield |
| Saccades régulières | Débit réseau/USB insuffisant | Ethernet Gigabit via USB, ou lecture locale |
| Sous-titres illisibles | SSA/ASS complexe | Convertir en SRT |
| Freeze après X minutes | Fuite mémoire (app IPTV) ou buffer HLS trop grand | Limiter `backBufferLength` à 30s |
| Audio sync dérive | Problème de conteneur/timestamps | Remuxer |

### 3.3 Remuxage vs transcodage — La solution la plus commune

Pour les fichiers MKV avec audio DTS (cas le plus fréquent), **remuxer** prend 30 secondes sans perte :

```bash
# Avec ffmpeg : convertir DTS en AC-3 sans retoucher la vidéo
ffmpeg -i input.mkv -c:v copy -c:a ac3 -b:a 640k output.mkv

# Ou avec MKVToolNix (interface graphique) :
# 1. Ouvrir MKVToolNix GUI
# 2. Charger le MKV
# 3. Décocher la piste DTS
# 4. Ajouter une piste AC-3 de remplacement
```

---

## BLOC 4 — Mises à jour firmware et politique LG

### 4.1 Historique des versions webOS sur C1

Le C1 est sorti avec webOS 6.0 et a reçu des updates mineurs :

| Version webOS | Date | Apports |
|---|---|---|
| 6.0 (03.xx.xx) | Mars 2021 | Version initiale |
| 6.1 (03.20.xx) | Fin 2021 | Corrections stabilité, ALLM amélioré |
| 6.3 (03.3x.xx) | 2022 | Dernière version majeure pour C1 |

**Le C1 est ensuite figé.** La version Chromium sous-jacente reste à **79** (janvier 2020). Aucune mise à jour majeure de webOS n'est prévue.

### 4.2 Politique LG de mise à jour webOS

En janvier 2023, LG a annoncé un programme de mise à jour webOS **pour les modèles 2022 et ultérieurs** :
- **C2/G2/CS/LX** (2022) → upgrade vers webOS 23 puis webOS 24
- **Modèles 2023** → upgrade vers webOS 24
- **Modèles 2024+** → garanties 4 ans de mises à jour

> ⚠️ **Le C1 (2021) N'EST PAS ÉLIGIBLE.** Confirmé officiellement par LG et FlatpanelsHD. Il n'y aura **jamais** de webOS 22, 23 ou 24 sur C1. Vous êtes bloqué à Chromium 79 pour toujours.

### 4.3 Conséquences pour le développement d'app

- **Apps LG Content Store qui vous lâchent** : certaines apps (Prime Video, Netflix, Disney+) commencent à abandonner le support webOS 6 en 2025-2026
- **Chromium 79 = sécurité** : plus de patches de sécurité depuis fin 2020 (considéré obsolète)
- **Nouveaux codecs/formats** : aucun nouveau codec ne sera ajouté via firmware

**Source** :
- https://www.flatpanelshd.com/news.php?subaction=showfull&id=1711437895
- https://www.flatpanelshd.com/news.php?subaction=showfull&id=1707297020

---

## BLOC 5 — Modification hardware : remplacement de la carte mère

### 5.1 Références des cartes du C1

| Taille | Carte mère (main board) | T-CON | Alim |
|---|---|---|---|
| 48" | EBT66417202 (variable selon lot) | 6871L-63xxA | EAY65689xxx |
| 55" | EBT66417X02 | 6871L-63xxA | EAY65689xxx |
| **65"** | **EBT66642903** (le plus courant) | 6871L-6309A/E | EAY65689423 |
| 77" | EBT66417X02 | 6871L-63xxA | EAY65689xxx |
| 83" | EBT66xxxxxx (variante 83") | spécifique | spécifique |

Prix pièce neuve OEM LG : **150-280 €** selon la carte (sources : Encompass, TVPartsToday, LG Parts Store France).

### 5.2 Peut-on mettre une carte de C2 ou C3 dans un C1 ?

**Non, techniquement impossible pour ces raisons :**

1. **Connectique T-CON différente** : le C2 utilise un connecteur de ruban LVDS différent du C1 (passage à V-by-One HS plus rapide).

2. **EDID verrouillé panel** : la carte mère lit l'EDID de la dalle via l'EEPROM T-CON. Une carte C2 détectera une dalle "inconnue" et refusera d'afficher, ou avec colorimétrie incorrecte.

3. **T-CON NVRAM appairée** : les données anti-mura (correction d'uniformité pixel par pixel) sont programmées en usine dans la NVRAM du T-CON et **référencées par la carte mère**. Un swap non-accompagné d'un reflash NVRAM produit des **clouding, bandes verticales, dérive colorimétrique** visibles. Le forum Badcaps est formel à ce sujet.

4. **Firmware signé** : chaque série (C1, C2, C3) utilise un bootloader et un firmware signés avec des clés différentes. Une carte C2 ne peut pas être flashée avec du firmware C1 et vice-versa.

5. **Dalle différente sur C2/C3** : les dalles ont évolué (EX, MLA, Tandem OLED). Le timing T-CON et les séquences de power-on ne correspondent plus.

### 5.3 Swap C1 → C1 (même modèle, remplacement standard)

**Possible, mais avec une contrainte majeure** :

La carte mère de remplacement arrive vierge, avec une NVRAM T-CON non appairée. Deux scénarios :

**Scénario A — Vous conservez votre T-CON d'origine**
- Débrancher l'ancienne carte mère, brancher la neuve, conserver votre T-CON existant
- La TV démarre, la NVRAM T-CON existante corrige la dalle correctement
- Le firmware se met à jour automatiquement après connexion réseau
- **Coût** : 150-280 € + 1h de travail
- **Risque** : faible si vous êtes précautionneux

**Scénario B — Le T-CON est aussi HS**
- Il faut un **jig LG de transfert** (outil technicien de LG, non vendu au public) pour lire la NVRAM de l'ancien T-CON et la transférer au nouveau
- Sans ce jig, la dalle présente des défauts d'uniformité permanents
- Solution : passer par un réparateur agréé LG (compter 400-600 €)

### 5.4 Le swap ne résoudra PAS vos problèmes de lecture vidéo

> ⚠️ **Point crucial** : remplacer une carte C1 par une autre carte C1 ne change **strictement rien** aux capacités de décodage. Même SoC, même firmware, mêmes limitations codec. **Remplacer la carte mère n'a de sens QUE si elle est défaillante** (TV ne démarre plus, ports HDMI morts, etc.).

**Sources** :
- Encompass (pièces LG officielles) : https://encompass.com/model/ZENOLED65C1PUB
- TVPartsToday : https://tvpartstoday.com/products/oled65c1pub-busyljr-lg-tv-repair-parts-kit-oled65c1pub-ebt66642903-main-board-eay65689423-power-6871l-6309a-e-t-con-eat65167004-wifi-oled65c1pubbusyljr
- Forum Badcaps (retours d'expérience swaps) : https://www.badcaps.net/forum/troubleshooting-hardware-devices-and-electronics-theory/troubleshooting-tvs-and-video-sources/100468-lg-oled-main-board-swap-upgrade-compatibility

---

## BLOC 6 — Solutions pragmatiques : boîtiers externes et Homebrew

### 6.1 La solution la plus simple et efficace — Boîtier HDMI externe

Pour contourner TOUTES les limitations vidéo du C1 sans toucher au hardware :

| Boîtier | Prix 2025 | Points forts | Points faibles |
|---|---|---|---|
| **Nvidia Shield TV Pro** | ~220 € | **Tous les codecs** (DTS, TrueHD, DTS:X), Dolby Vision, AI upscaling, Kodi natif | Android TV (pubs), vieille puce Tegra X1+ |
| **Apple TV 4K (3e gen)** | ~170 € | Qualité audio/vidéo irréprochable, fluidité, Atmos, Dolby Vision | Écosystème fermé, DTS via apps tierces uniquement |
| **Chromecast Google TV 4K** | ~70 € | Bon rapport qualité/prix, Google TV, Dolby Vision/Atmos | Pas de DTS natif, interface lente |
| **Zidoo Z9X / Z10 Pro** | 400-700 € | **Référence audiophile/vidéophile**, tous formats, HDR tone mapping hardware, lecture ISO Blu-ray | Prix, niche enthousiaste |

**Ma recommandation pour votre cas** : **Nvidia Shield TV Pro** (~220 €). C'est la solution de facto pour résoudre les problèmes de codec sur LG C1. Elle décode **tout** ce que le C1 refuse, passe en HDMI 2.1 avec Dolby Vision, et permet d'installer Kodi/Plex/Jellyfin avec des réglages pro. Les utilisateurs francophones sur AVForums la recommandent unanimement depuis 2021 pour couvrir le DTS.

### 6.2 webOS Homebrew (rooting) — Piste technique intéressante

Si votre C1 est resté sur un **firmware ancien** (avant 03.21.xx, soit avant mi-2022), le root est possible et vous gagnez :

- Installation de **Kodi webOS natif** (via Homebrew Channel)
- **Moonlight** (streaming jeu depuis PC Nvidia)
- **PicCap** (ambilight DIY)
- Accès shell root, déblocage de certains services Luna
- Possibilité d'installer des **décodeurs alternatifs** via Kodi

**Procédure simplifiée** :
1. Vérifier votre version webOS : `Paramètres > Support > Info TV`
2. Si version < 03.21.xx → RootMyTV peut marcher
3. Si version >= 03.21.xx → LG a patché, **root impossible** actuellement
4. Ne **jamais** accepter les mises à jour automatiques si vous voulez garder la porte ouverte

> ⚠️ **État actuel (avril 2026)** : l'exploit RootMyTV v2 a été **patché par LG en 2022**. Pour les C1 achetés et mis à jour récemment, il n'existe **plus d'exploit public fonctionnel**. Le projet continue en recherche mais rien de disponible pour le grand public. Si votre C1 est déjà à jour, cette voie est fermée.

**Ce que le root NE permet PAS** :
- Changer les décodeurs hardware (impossible, c'est du silicium)
- Installer Android TV ou Linux alternatif (dalle T-CON verrouillée)
- Mettre à jour vers webOS 22+ (Chromium reste 79)

**Sources** :
- webOS Homebrew : https://www.webosbrew.org/
- RootMyTV : https://rootmy.tv/
- Rooting guide 2024 : https://blog.illixion.com/2024/04/root-lg-webos-tv/

### 6.3 Comparatif final — Quelle solution pour quel besoin ?

| Votre besoin | Solution recommandée | Coût |
|---|---|---|
| Lire des fichiers MKV avec audio DTS | Nvidia Shield TV Pro | 220 € |
| Lire des Blu-ray rips 4K HDR à fort bitrate | Zidoo Z9X ou Shield Pro + SSD externe | 250-600 € |
| Améliorer votre app IPTV React (webOS) | **Rien côté hardware** — optimiser l'app (voir skills webos-dev-constraints, react-vite-webos) | 0 € |
| Avoir webOS à jour | **Impossible sur C1** — envisager un C3/C4 d'occasion si crucial | 800-1500 € |
| Débloquer des fonctions cachées du C1 | Rooter si firmware < 03.21 | 0 € |
| Remplacer une carte mère défaillante | Carte OEM via Encompass/TVPartsToday | 150-280 € |

---

## Conclusion et recommandation pratique

Votre LG OLED C1 est une TV d'exception en qualité d'image, mais **deux limites hardware/logicielles sont irréversibles** :

1. **Absence de DTS** — décision commerciale de LG, présente sur tous les modèles 2020+
2. **Chromium 79 figé** — politique de non-mise à jour pour les modèles 2021

Dans votre cas, je recommande l'approche suivante :

1. **Diagnostiquer précisément** les fichiers qui ne passent pas avec **MediaInfo** — dans 80% des cas, c'est DTS.
2. Pour les fichiers DTS uniquement, **remuxer en batch** avec FFmpeg ou MKVToolNix (5 min pour un lot de 100 fichiers, zéro perte vidéo, perte audio perceptuelle négligeable AC-3 640 kbps).
3. Pour le reste (VC-1, sous-titres ASS complexes, bitrates extrêmes), **investir dans un Nvidia Shield TV Pro** — c'est l'investissement qui a le meilleur ROI pour votre usage.
4. **Ne pas toucher à la carte mère** — sauf défaillance matérielle avérée, c'est inutile et risqué.
5. Pour votre **app IPTV React en cours de développement**, continuer à cibler Chromium 79 comme documenté dans vos skills existants. Le C1 restera sur cette base.

Le swap de carte mère vers une C2/C3 est une **fausse bonne idée** largement discutée sur les forums réparateurs : contraintes T-CON, EDID, firmware et panel rendent l'opération impossible sans tout modifier jusqu'à la dalle — ce qui revient à acheter une C3 complète.

---

*Document établi en avril 2026 — sources vérifiées au jour de la rédaction. Les versions firmware et exploits peuvent évoluer.*
