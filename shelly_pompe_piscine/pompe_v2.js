// ============================================================
//  Pilotage Pompe Piscine v2.6  -  Shelly Pro EM 50
//  (v2.6 : moyenne glissante sur fenetre temporelle de 10 min quand
//          la pompe est OFF ; moyenne depuis le dernier changement
//          d'etat conservee quand la pompe est ON)
// ============================================================
//  MATERIEL
//  - Script execute sur : Shelly Pro EM 50 SPEM-002CEBEU50
//                         IP 192.168.1.217
//  - em1:0  -> arrivee generale (grid)
//             act_power > 0 : soutirage reseau
//             act_power < 0 : injection reseau (surplus solaire)
//  - em1:1  -> panneaux solaires (PV)
//  - Pompe  -> Shelly 1 Mini Gen3 S3SW-001X8EU, IP 192.168.1.239
//
//  SAISONS ET QUOTAS
//  - HAUTE (1 juin -> 31 aout) :
//        Demarrage si gridMoy <= seuil_mini_haute (ex. -300 W)
//        Arret    si gridMoy >  seuil_maxi_haute (ex. -50 W)
//        Quota journalier : 4 h minimum, 8 h maximum
//
//  - MI-SAISON (2 mars -> 31 mai ET 1 sept -> 31 oct) :
//        Demarrage si gridMoy <= seuil_mini_mi (ex. -600 W)
//        Arret    si gridMoy >  seuil_maxi_mi  (ex. -50 W)
//        Quota journalier : 1 h minimum, 4 h maximum
//
//  - BASSE (1 nov -> 1 mars) :
//        Demarrage si gridMoy <= seuil_mini_basse (ex. -800 W)
//        Arret    si gridMoy >  seuil_maxi_basse  (ex. -50 W)
//        Quota journalier : 0 h minimum, 2 h maximum
//
//  LOGIQUE
//  - gridMoy : deux modes de calcul selon l'etat de la pompe -
//        * Pompe OFF : moyenne glissante sur une fenetre temporelle de
//          10 min (reactif, pour detecter un surplus qui apparait).
//        * Pompe ON  : moyenne de toutes les mesures depuis le dernier
//          changement d'etat (pas une fenetre fixe) : ca lisse l'appel
//          de puissance de la pompe elle-meme, qui sinon fait osciller
//          gridMoy au-dessus du seuil d'arret.
//        Dans les deux cas, minimum 5 mesures (2,5 min) avant de faire
//        confiance a la moyenne pour demarrer.
//
//  - Demarrage auto : pompe OFF + gridMoy <= seuil_mini + quota max
//        non atteint + delai 30 min ecoule
//
//  - Arret auto     : pompe ON  + gridMoy > seuil_maxi + delai 30 min ecoule
//        (arret immediat si quota max atteint, sans delai)
//
//  - Forcage quota mini : entre 12h et 17h si quota mini non atteint,
//        la pompe tourne (demarre si besoin) independamment du surplus -
//        prioritaire sur l'arret "fin de surplus" (mais pas sur le quota
//        max). Ignore en basse saison : pas de quota mini.
//
//  - Securite materiel : 30 min mini entre 2 bascules ON/OFF.
//
//  - Detection commande manuelle : si l'etat reel de la pompe
//        differe de l'etat connu, le delai mini est etendu a 2 h.
//
//  - Rafraichissement config NAS : au demarrage puis toutes les heures.
// ============================================================

// ---- CONFIGURATION ----------------------------------------
let CFG = {
  // Mesure
  measureComponent: "em1",
  measureId: 0,                  // canal "arrivee generale"

  // Pompe distante
  pumpAddr: "192.168.1.239",
  pumpId: 0,
  pumpPowerW: 800,

  // Seuils par saison - valeurs par defaut (ecrasees apres fetchConfig)
  // Demarrage (pompe OFF) : gridMoy <= seuilMini
  // Arret     (pompe ON)  : gridMoy >  seuilMaxi
  seuilMiniHaute: -300,
  seuilMaxiHaute: -50,
  seuilMiniMi:    -600,
  seuilMaxiMi:    -50,
  seuilMiniBasse: -800,
  seuilMaxiBasse: -50,

  // Temporisations (s)
  cycleSec: 30,                  // periode boucle
  minSwitchDelay: 30 * 60,       // 30 min entre 2 bascules
  manualSwitchDelay: 2 * 3600,   // 2 h apres une commande manuelle
  startAvgWindow: 5,             // nb mini de mesures avant de faire confiance a la moyenne (2,5 min)
  offAvgWindowSec: 10 * 60,      // fenetre glissante temporelle utilisee quand la pompe est OFF
  configRefreshCycles: 120,      // rafraichir config NAS toutes les heures (120 * 30s)

  // Quota max par defaut (HAUTE saison) et creneau de forcage
  dailyMaxSec: 8 * 3600,         // 8 h maximum (HAUTE)
  forceStartHour: 12,            // forcage si quota mini non atteint
  forceEndHour: 17,              // limite haute du forcage

  // Reporting NAS Synology
  reportUrl: "http://192.168.1.99/pompe/log.php",
  reportEnabled: true,
  heartbeatCycles: 10,           // 10 * cycleSec = 5 min
  pvComponent: "em1",            // canal PV pour enrichir le payload
  pvId: 1,
};

// ---- WRAPPER RPC SHELLY DISTANT ---------------------------
let RemoteShelly = {
  _cb: function (result, error_code, error_message, callback) {
    let body = JSON.parse(result.body || "{}");
    callback(body, result.code, result.message);
  },
  call: function (rpc, data, callback) {
    Shelly.call("HTTP.POST", {
      url: "http://" + this.address + "/rpc/" + rpc,
      body: data,
    }, RemoteShelly._cb, callback);
  },
  getInstance: function (address) {
    let r = Object.create(this);
    r.address = address;
    return r;
  },
};
let pump = RemoteShelly.getInstance(CFG.pumpAddr);

// ---- LECTURE CONFIG NAS -----------------------------------
function fetchConfig(callback) {
  let url = CFG.reportUrl.replace("log.php", "config.php");
  Shelly.call("HTTP.GET", { url: url }, function (result, error_code) {
    if (error_code === 0 && result && result.code === 200) {
      try {
        let c = JSON.parse(result.body);
        if (typeof c.seuil_mini_haute === "number") CFG.seuilMiniHaute = c.seuil_mini_haute;
        if (typeof c.seuil_maxi_haute === "number") CFG.seuilMaxiHaute = c.seuil_maxi_haute;
        if (typeof c.seuil_mini_mi    === "number") CFG.seuilMiniMi    = c.seuil_mini_mi;
        if (typeof c.seuil_maxi_mi    === "number") CFG.seuilMaxiMi    = c.seuil_maxi_mi;
        if (typeof c.seuil_mini_basse === "number") CFG.seuilMiniBasse = c.seuil_mini_basse;
        if (typeof c.seuil_maxi_basse === "number") CFG.seuilMaxiBasse = c.seuil_maxi_basse;
        print("[CFG ] mini(H/M/B)=" + CFG.seuilMiniHaute + "/" + CFG.seuilMiniMi + "/" + CFG.seuilMiniBasse +
              " maxi(H/M/B)=" + CFG.seuilMaxiHaute + "/" + CFG.seuilMaxiMi + "/" + CFG.seuilMaxiBasse);
      } catch (e) {
        print("[CFG ] erreur parsing: " + e);
      }
    } else {
      print("[CFG ] fetch KO code=" + (result ? result.code : error_code));
    }
    if (callback) callback();
  });
}

// ---- ETAT GLOBAL ------------------------------------------
let st = {
  pumpIsOn: false,
  lastSwitchTime: 0,
  currentMinDelay: 30 * 60,
  avgSum: 0,                     // somme des mesures grid depuis le dernier changement d'etat (utilise si ON)
  avgCount: 0,                   // nombre de mesures accumulees dans avgSum
  offHistory: [],                 // {t, g} des mesures des 10 dernieres min (utilise si OFF)
  dailyRunSec: 0,               // cumul ON deja consolide
  dayKey: 0,                    // jour julien local
  pumpOnStartTs: 0,             // debut de la session ON courante
  rpcBusy: false,               // garde anti-reentree Switch.Set
  tickCount: 0,                 // compteur de ticks pour heartbeat/config
  pvWhAccum: 0.0,               // energie PV accumulee depuis le dernier heartbeat (Wh)
  pumpGridWhAccum: 0.0,         // energie reseau pompe accumulee depuis le dernier heartbeat (Wh)
};

// ---- REPORTING VERS NAS -----------------------------------
function reportCb(result, error_code, error_message) {
  if (error_code !== 0) {
    print("[RPT ] erreur code=" + error_code);
  }
}
// extras : objet optionnel de champs supplementaires (ex: {pv_wh_5m, pump_grid_wh_5m})
function report(type, reason, extras) {
  if (!CFG.reportEnabled) return;
  let now = Shelly.getComponentStatus("sys").unixtime;
  let s = Shelly.getComponentStatus(CFG.measureComponent + ":" + CFG.measureId);
  let pv = Shelly.getComponentStatus(CFG.pvComponent + ":" + CFG.pvId);
  let grid = (s && typeof s.act_power === "number") ? s.act_power : null;
  let pvW = (pv && typeof pv.act_power === "number") ? pv.act_power : null;
  let runningSec = st.dailyRunSec +
    (st.pumpIsOn && st.pumpOnStartTs > 0 ? (now - st.pumpOnStartTs) : 0);
  let comp = localComponents(now);
  let payload = {
    ts: now,
    type: type,
    pump_on: st.pumpIsOn,
    grid_w: grid,
    grid_avg_w: avgHistory(),
    pv_w: pvW,
    mode: seasonInfo(comp).name,
    daily_sec: runningSec,
    reason: reason || "",
  };
  if (extras) {
    for (let k in extras) { payload[k] = extras[k]; }
  }
  Shelly.call("HTTP.POST", {
    url: CFG.reportUrl,
    body: JSON.stringify(payload),
  }, reportCb);
}

// ---- OUTILS DATE (sans Date()) ----------------------------
function localComponents(unixUtc) {
  let off = Shelly.getComponentStatus("sys").utc_offset;
  if (typeof off !== "number") off = 0;
  let t = unixUtc + off;
  let days = Math.floor(t / 86400);
  let secOfDay = t - days * 86400;
  let dayKey = days;
  let year = 1970;
  while (true) {
    let leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
    let yd = leap ? 366 : 365;
    if (days < yd) break;
    days -= yd;
    year += 1;
  }
  let leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  let mdays = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  let month = 1;
  for (let i = 0; i < 12; i++) {
    if (days < mdays[i]) { month = i + 1; break; }
    days -= mdays[i];
  }
  let day = days + 1;
  let hour   = Math.floor(secOfDay / 3600);
  let minute = Math.floor((secOfDay % 3600) / 60);
  let second = secOfDay % 60;
  return { year: year, month: month, day: day,
           hour: hour, minute: minute, second: second,
           dayKey: dayKey };
}

// Retourne les parametres de la saison courante :
//   { name, startGrid (seuil_mini), stopGrid (seuil_maxi), dailyMinSec, dailyMaxSec }
function seasonInfo(comp) {
  let m = comp.month;
  let d = comp.day;
  // HAUTE : 1 juin -> 31 aout
  if (m >= 6 && m <= 8) {
    return { name: "HAUTE",
             startGrid: CFG.seuilMiniHaute, stopGrid: CFG.seuilMaxiHaute,
             dailyMinSec: 4 * 3600, dailyMaxSec: 8 * 3600 };
  }
  // MI : 2 mars -> 31 mai  ET  1 sept -> 31 oct
  if ((m === 3 && d >= 2) || m === 4 || m === 5 ||
      m === 9 || m === 10) {
    return { name: "MI",
             startGrid: CFG.seuilMiniMi, stopGrid: CFG.seuilMaxiMi,
             dailyMinSec: 1 * 3600, dailyMaxSec: 4 * 3600 };
  }
  // BASSE : reste (1 nov -> 1 mars inclus)
  return { name: "BASSE",
           startGrid: CFG.seuilMiniBasse, stopGrid: CFG.seuilMaxiBasse,
           dailyMinSec: 0, dailyMaxSec: 2 * 3600 };
}

// ---- MOYENNE GLISSANTE --------------------------------------
// Pompe OFF : fenetre temporelle de 10 min (reactif, pour detecter un
//             surplus qui vient d'apparaitre).
// Pompe ON  : moyenne de TOUTES les mesures depuis la derniere bascule
//             (pas une fenetre fixe) : ca lisse correctement l'appel de
//             puissance de la pompe elle-meme, qui sinon fait osciller
//             gridAvg au-dessus du seuil d'arret des que le solaire ne
//             couvre pas tout a fait sa consommation.
function resetAvg() {
  st.avgSum = 0;
  st.avgCount = 0;
  // Vide aussi la fenetre OFF : sinon, juste apres un arret, elle contient
  // encore des mesures prises pendant que la pompe tournait (avg fausse
  // a la hausse pendant les 10 min suivantes).
  st.offHistory = [];
}
function pushHistory(now, p) {
  // Accumulateur "depuis le dernier changement d'etat" (pompe ON)
  st.avgSum += p;
  st.avgCount += 1;
  // Fenetre glissante temporelle des 10 dernieres minutes (pompe OFF)
  st.offHistory.push({ t: now, g: p });
  while (st.offHistory.length && (now - st.offHistory[0].t) > CFG.offAvgWindowSec) {
    st.offHistory.shift();
  }
}
function avgOffWindow() {
  if (st.offHistory.length === 0) return 0;
  let s = 0;
  for (let i = 0; i < st.offHistory.length; i++) s += st.offHistory[i].g;
  return s / st.offHistory.length;
}
function avgHistory() {
  if (st.pumpIsOn) return st.avgCount > 0 ? st.avgSum / st.avgCount : 0;
  return avgOffWindow();
}

// ---- COMMANDE POMPE ---------------------------------------
function setPump(on, reason) {
  if (st.rpcBusy) return;
  if (on === st.pumpIsOn) return;
  st.rpcBusy = true;
  pump.call("Switch.Set", { id: CFG.pumpId, on: on }, function (res, code) {
    st.rpcBusy = false;
    if (code !== 200) {
      print("[ERR] Switch.Set code=" + code);
      return;
    }
    let now = Shelly.getComponentStatus("sys").unixtime;
    if (on) {
      st.pumpOnStartTs = now;
    } else if (st.pumpOnStartTs > 0) {
      st.dailyRunSec += (now - st.pumpOnStartTs);
      st.pumpOnStartTs = 0;
    }
    st.pumpIsOn = on;
    st.lastSwitchTime = now;
    st.currentMinDelay = CFG.minSwitchDelay;
    resetAvg();
    print((on ? "[ON ] " : "[OFF] ") + reason);
    report(on ? "on" : "off", reason);
  });
}

// ---- INIT ETAT POMPE --------------------------------------
function initPumpState(callback) {
  pump.call("Switch.GetStatus", { id: CFG.pumpId }, function (res, code) {
    if (code === 200) {
      st.pumpIsOn = !!res.output;
      let now = Shelly.getComponentStatus("sys").unixtime;
      st.lastSwitchTime = now;
      if (st.pumpIsOn) st.pumpOnStartTs = now;
      print("[INIT] Pompe = " + (st.pumpIsOn ? "ON" : "OFF"));
      report("boot", "init " + (st.pumpIsOn ? "ON" : "OFF"));
    } else {
      print("[ERR ] Init pompe code=" + code);
    }
    if (callback) callback();
  });
}

// ---- BOUCLE PRINCIPALE ------------------------------------
function tick() {
  st.tickCount += 1;
  let sys = Shelly.getComponentStatus("sys");
  let now = sys.unixtime;
  let comp = localComponents(now);

  // Reset compteur journalier (avant le heartbeat pour ne pas envoyer le cumul de la veille)
  if (st.dayKey !== comp.dayKey) {
    if (st.dayKey !== 0) {
      let totalYesterday = st.dailyRunSec +
        (st.pumpIsOn && st.pumpOnStartTs > 0 ? (now - st.pumpOnStartTs) : 0);
      print("[DAY ] Cumul veille = " + Math.floor(totalYesterday / 60) + " min");
    }
    st.dayKey = comp.dayKey;
    st.dailyRunSec = 0;
    if (st.pumpIsOn) st.pumpOnStartTs = now;
  }

  // Marquer si ce tick doit emettre un heartbeat ou rafraichir la config
  let isHeartbeatTick = (st.tickCount % CFG.heartbeatCycles) === 0;
  let isConfigTick    = (st.tickCount % CFG.configRefreshCycles) === 0 && st.tickCount > 0;

  // Lecture pompe (detection commande manuelle)
  pump.call("Switch.GetStatus", { id: CFG.pumpId }, function (res, code) {
    if (code !== 200) {
      print("[WARN] Lecture pompe KO code=" + code);
      return;
    }

    // Normaliser en booleen strict pour eviter les comparaisons strictes
    // entre boolean (setPump) et integer (res.output du Shelly Mini)
    let realOn = !!res.output;
    if (realOn !== st.pumpIsOn) {
      print("[MAN ] Commande manuelle detectee");
      if (realOn && !st.pumpIsOn) {
        st.pumpOnStartTs = now;
      } else if (!realOn && st.pumpIsOn && st.pumpOnStartTs > 0) {
        st.dailyRunSec += (now - st.pumpOnStartTs);
        st.pumpOnStartTs = 0;
      }
      st.pumpIsOn = realOn;
      st.lastSwitchTime = now;
      st.currentMinDelay = CFG.manualSwitchDelay;
      resetAvg();
      report("manual", "etat reel: " + (realOn ? "ON" : "OFF"));
    }

    // Lecture grid et PV
    let s = Shelly.getComponentStatus(CFG.measureComponent + ":" + CFG.measureId);
    if (!s || typeof s.act_power === "undefined") {
      print("[WARN] act_power indispo");
      return;
    }
    let grid = s.act_power;
    let pvComp = Shelly.getComponentStatus(CFG.pvComponent + ":" + CFG.pvId);
    let pvW = (pvComp && typeof pvComp.act_power === "number") ? pvComp.act_power : null;
    pushHistory(now, grid);
    let gridAvg = avgHistory();

    // Accumulation energie sur 30 s (un tick)
    if (pvW !== null) { st.pvWhAccum += pvW * 30.0 / 3600.0; }
    if (st.pumpIsOn && grid > 0) { st.pumpGridWhAccum += grid * 30.0 / 3600.0; }

    // Heartbeat : envoyer les accumulations puis remettre a zero
    if (isHeartbeatTick) {
      report("heartbeat", "", {
        pv_wh_5m:        Math.round(st.pvWhAccum       * 10) / 10,
        pump_grid_wh_5m: Math.round(st.pumpGridWhAccum * 10) / 10,
      });
      st.pvWhAccum       = 0.0;
      st.pumpGridWhAccum = 0.0;
    }

    // Rafraichissement config NAS (toutes les heures, non bloquant)
    if (isConfigTick) {
      fetchConfig(null);
    }

    let season = seasonInfo(comp);
    let modeName = season.name;
    let startTh = season.startGrid;
    let stopTh  = season.stopGrid;
    let dailyMin = season.dailyMinSec;

    // Cumul journalier en temps reel
    let runningSec = st.dailyRunSec +
      (st.pumpIsOn && st.pumpOnStartTs > 0 ? (now - st.pumpOnStartTs) : 0);

    let hhmm = (comp.hour   < 10 ? "0" : "") + comp.hour   + ":" +
               (comp.minute < 10 ? "0" : "") + comp.minute + ":" +
               (comp.second < 10 ? "0" : "") + comp.second;
    print("[" + modeName + "|" + hhmm + "] grid=" + Math.round(grid) +
          "W avg=" + Math.round(gridAvg) +
          "W pompe=" + (st.pumpIsOn ? "ON " : "OFF") +
          " jour=" + Math.floor(runningSec / 60) + "min");

    // ---------- Stop imperatif : quota max par saison (sans delai) ----------
    if (st.pumpIsOn && runningSec >= season.dailyMaxSec) {
      setPump(false, "quota max " + Math.floor(season.dailyMaxSec / 3600) +
                     "h atteint (" + modeName + ")");
      return;
    }

    // ---------- Forcage quota mini saison ----------
    // Tant que le quota mini n'est pas atteint et qu'on est dans le creneau
    // horaire, la pompe tourne (ou demarre) independamment du surplus/grid :
    // le forcage a priorite sur la regle d'arret "fin de surplus" ci-dessous.
    let inForceWindow = dailyMin > 0 &&
                        runningSec < dailyMin &&
                        comp.hour >= CFG.forceStartHour &&
                        comp.hour < CFG.forceEndHour;

    // ---------- Delai mini entre bascules ----------
    let delayOk = (now - st.lastSwitchTime) >= st.currentMinDelay;

    // ---------- Arret : fin du surplus (seuil_maxi) ----------
    // Ignore si le forcage quota mini est actif : on ne coupe pas la pompe
    // en cours de forcage, elle tourne jusqu'a atteindre le quota mini.
    if (st.pumpIsOn && !inForceWindow && gridAvg > stopTh) {
      if (delayOk) {
        setPump(false, "fin surplus " + modeName +
                       " (avg=" + Math.round(gridAvg) + "W > " + stopTh + "W)");
      }
      return;
    }

    if (!delayOk) return;

    if (!st.pumpIsOn && inForceWindow) {
      setPump(true, "forcage quota mini " +
                    Math.floor(dailyMin / 3600) + "h " +
                    modeName + " (h=" + comp.hour + ")");
      return;
    }

    // ---------- Demarrage normal sur surplus (seuil_mini) ----------
    if (!st.pumpIsOn &&
        runningSec < season.dailyMaxSec &&
        st.offHistory.length >= CFG.startAvgWindow &&
        gridAvg <= startTh) {
      setPump(true, "surplus solaire " + modeName +
                    " (avg=" + Math.round(gridAvg) + "W <= " + startTh + "W)");
      return;
    }
  });
}

// ---- DEMARRAGE --------------------------------------------
print("=== Pompe Piscine v2.6 ===");
fetchConfig(function () {
  initPumpState(function () {
    Timer.set(CFG.cycleSec * 1000, true, tick);
    tick();
  });
});
