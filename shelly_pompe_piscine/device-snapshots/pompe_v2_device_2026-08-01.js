// ============================================================
//  Pilotage Pompe Piscine v2.2  -  Shelly Pro EM 50
//  (v2.2 : 3 saisons avec seuils et quotas differencies)
// ============================================================
//  - Mesure : em1:0 (arrivee generale, signe Shelly standard)
//        act_power > 0 : soutirage reseau
//        act_power < 0 : injection reseau (surplus solaire)
//
//  - HAUTE saison (1 juin -> 31 aout) :
//        Demarrage si export >= 300 W (grid <= -300)
//        Quota journalier : 4 h minimum, 8 h maximum
//
//  - MI-saison (2 mars -> 31 mai ET 1 sept -> 31 oct) :
//        Demarrage si export >= 600 W (grid <= -600)
//        Quota journalier : 1 h minimum, 8 h maximum
//
//  - BASSE saison (1 nov -> 1 mars) :
//        Demarrage si export >= 800 W (grid <= -800)
//        Aucun quota minimum (filtration opportuniste seulement)
//
//  - Forcage quota mini : entre 12h et 17h si quota non atteint
//        (ignore car pas de quota mini en basse saison)
//
//  - Conflit autre appareil (lave-linge, lave-vaisselle...) :
//        Si la pompe tourne et que le reseau redevient soutireur
//        pendant > 30 min, on arrete la pompe ;
//        elle redemarrera quand le surplus reapparaitra.
//        (Desactive pendant le forcage quota mini.)
//
//  - Securite materiel : 30 min mini entre 2 bascules ON/OFF.
//
//  - Detection commande manuelle : si l'etat reel de la pompe
//        differe de l'etat connu, le delai mini est etendu a 2 h.
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

  // Seuils et quotas par saison (grid en W, signe Shelly standard)
  // Calcules dynamiquement dans seasonInfo(comp) a partir du mois/jour
  // HAUTE : grid <= -300 W, mini 4 h
  // MI    : grid <= -600 W, mini 1 h
  // BASSE : grid <= -800 W, pas de mini
  conflictGrid: 50,              // grid > 50 W => on tire au reseau
  stopGrid: -50,                 // avg > -50 W => surplus insuffisant, on arrete

  // Temporisations (s)
  cycleSec: 30,                  // periode boucle
  minSwitchDelay: 30 * 60,       // 30 min entre 2 bascules
  manualSwitchDelay: 2 * 3600,   // 2 h apres une commande manuelle
  conflictHoldSec: 30 * 60,      // 30 min de conflit avant arret
  startAvgWindow: 5,             // moyenne glissante sur 5 mesures (2,5 min)

  // Quota max commun et creneau de forcage
  dailyMaxSec: 8 * 3600,         // 8 h maximum
  forceStartHour: 12,            // forcage si quota mini non atteint
  forceEndHour: 17,              // limite haute du forcage

  // Reporting NAS Synology
  reportUrl: "http://192.168.1.99/pompe/log.php",
  reportEnabled: true,
  heartbeatCycles: 10,           // 10 * cycleSec = 5 min
  configReloadCycles: 20,        // 20 * cycleSec = 10 min (rechargement config NAS)
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

// ---- ETAT GLOBAL ------------------------------------------
let st = {
  pumpIsOn: false,
  lastSwitchTime: 0,
  currentMinDelay: 30 * 60,
  history: [],                  // mesures grid recentes
  conflictStart: 0,             // 0 = pas de conflit en cours
  conflictReported: false,      // pour n'envoyer conflict_start qu'une fois
  dailyRunSec: 0,               // cumul ON deja consolide
  dayKey: 0,                    // jour julien local
  pumpOnStartTs: 0,             // debut de la session ON courante
  rpcBusy: false,               // garde anti-reentree Switch.Set
  tickCount: 0,                 // compteur de ticks pour heartbeat
  // Config dynamique chargee depuis le NAS au demarrage
  dynCfg: {
    h: { name: "HAUTE", startGrid: -300, stopGrid: -50, dailyMinSec: 4 * 3600, dailyMaxSec: 8 * 3600 },
    m: { name: "MI",    startGrid: -600, stopGrid: -50, dailyMinSec: 1 * 3600, dailyMaxSec: 8 * 3600 },
    b: { name: "BASSE", startGrid: -800, stopGrid: -50, dailyMinSec: 0,        dailyMaxSec: 8 * 3600 },
  },
};

// ---- REPORTING VERS NAS -----------------------------------
function reportCb(result, error_code, error_message) {
  if (error_code !== 0) {
    print("[RPT ] erreur code=" + error_code);
  }
}
function report(type, reason) {
  if (!CFG.reportEnabled) return;
  let now = Shelly.getComponentStatus("sys").unixtime;
  let s = Shelly.getComponentStatus(CFG.measureComponent + ":" + CFG.measureId);
  let pv = Shelly.getComponentStatus(CFG.pvComponent + ":" + CFG.pvId);
  let grid = (s && typeof s.act_power === "number") ? s.act_power : null;
  let pvW = (pv && typeof pv.act_power === "number") ? pv.act_power : null;
  let runningSec = st.dailyRunSec +
    (st.pumpIsOn && st.pumpOnStartTs > 0 ? (now - st.pumpOnStartTs) : 0);
  let comp = localComponents(now);

  // Energie sur la fenetre heartbeat (300 s) : uniquement pour type "heartbeat"
  let periodSec = CFG.heartbeatCycles * CFG.cycleSec;  // 300 s = 5 min
  let pvWh5m = null;
  let pumpGridWh5m = null;
  if (type === "heartbeat" && pvW !== null && grid !== null) {
    pvWh5m = pvW * periodSec / 3600;
    pumpGridWh5m = st.pumpIsOn ? Math.max(0, grid) * periodSec / 3600 : 0;
  }

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
    pv_wh_5m: pvWh5m,
    pump_grid_wh_5m: pumpGridWh5m,
  };
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
  let hour = Math.floor(secOfDay / 3600);
  return { year: year, month: month, day: day, hour: hour, dayKey: dayKey };
}

// Retourne les parametres de la saison courante depuis st.dynCfg
//   { name, startGrid, stopGrid, dailyMinSec }
function seasonInfo(comp) {
  let m = comp.month, d = comp.day;
  let key;
  if (m >= 6 && m <= 8) key = "h";
  else if ((m === 3 && d >= 2) || m === 4 || m === 5 || m === 9 || m === 10) key = "m";
  else key = "b";
  return st.dynCfg[key];
}

// Charge la config depuis le NAS (seuils et quotas)
function loadConfig(callback) {
  let url = CFG.reportUrl.replace("log.php", "config.php");
  Shelly.call("HTTP.GET", { url: url }, function(result, error_code) {
    if (error_code === 0 && result.code === 200) {
      try {
        let cfg = JSON.parse(result.body);
        let p = function(k) {
          return (cfg[k] !== undefined && cfg[k] !== null) ? parseInt(cfg[k]) : null;
        };
        if (p("seuil_mini_haute") !== null) st.dynCfg.h.startGrid    = p("seuil_mini_haute");
        if (p("seuil_maxi_haute") !== null) st.dynCfg.h.stopGrid     = p("seuil_maxi_haute");
        if (p("seuil_mini_mi")    !== null) st.dynCfg.m.startGrid    = p("seuil_mini_mi");
        if (p("seuil_maxi_mi")    !== null) st.dynCfg.m.stopGrid     = p("seuil_maxi_mi");
        if (p("seuil_mini_basse") !== null) st.dynCfg.b.startGrid    = p("seuil_mini_basse");
        if (p("seuil_maxi_basse") !== null) st.dynCfg.b.stopGrid     = p("seuil_maxi_basse");
        if (p("quota_mini_haute") !== null) st.dynCfg.h.dailyMinSec  = p("quota_mini_haute") * 3600;
        if (p("quota_mini_mi")    !== null) st.dynCfg.m.dailyMinSec  = p("quota_mini_mi")    * 3600;
        if (p("quota_mini_basse") !== null) st.dynCfg.b.dailyMinSec  = p("quota_mini_basse") * 3600;
        if (p("quota_max_haute")  !== null) st.dynCfg.h.dailyMaxSec  = p("quota_max_haute")  * 3600;
        if (p("quota_max_mi")     !== null) st.dynCfg.m.dailyMaxSec  = p("quota_max_mi")     * 3600;
        if (p("quota_max_basse")  !== null) st.dynCfg.b.dailyMaxSec  = p("quota_max_basse")  * 3600;
        print("[CFG] config chargee depuis NAS");
      } catch(e) { print("[CFG] erreur parsing: " + e); }
    } else {
      print("[CFG] NAS indisponible, valeurs par defaut");
    }
    if (callback) callback();
  });
}

// ---- HISTORIQUE MESURES -----------------------------------
function pushHistory(p) {
  st.history.push(p);
  while (st.history.length > CFG.startAvgWindow) st.history.splice(0, 1);
}
function avgHistory() {
  if (st.history.length === 0) return 0;
  let s = 0;
  for (let i = 0; i < st.history.length; i++) s += st.history[i];
  return s / st.history.length;
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
    st.conflictStart = 0;
    st.conflictReported = false;
    print((on ? "[ON ] " : "[OFF] ") + reason);
    report(on ? "on" : "off", reason);
  });
}

// ---- INIT ETAT POMPE --------------------------------------
function initPumpState(callback) {
  pump.call("Switch.GetStatus", { id: CFG.pumpId }, function (res, code) {
    let now = Shelly.getComponentStatus("sys").unixtime;
    st.lastSwitchTime = now;   // toujours initialise, meme en cas d'echec RPC
    if (code === 200) {
      st.pumpIsOn = res.output;
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

  // Rechargement periodique de la config NAS (toutes les 10 min)
  if ((st.tickCount % CFG.configReloadCycles) === 0) {
    loadConfig(function() {});
  }

  // Heartbeat periodique vers le NAS
  if ((st.tickCount % CFG.heartbeatCycles) === 0) {
    report("heartbeat", "");
  }

  // Reset compteur journalier
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

  // Lecture pompe (detection commande manuelle)
  pump.call("Switch.GetStatus", { id: CFG.pumpId }, function (res, code) {
    if (code !== 200) {
      print("[WARN] Lecture pompe KO code=" + code);
      return;
    }

    if (res.output !== st.pumpIsOn) {
      print("[MAN ] Commande manuelle detectee");
      if (res.output && !st.pumpIsOn) {
        st.pumpOnStartTs = now;
      } else if (!res.output && st.pumpIsOn && st.pumpOnStartTs > 0) {
        st.dailyRunSec += (now - st.pumpOnStartTs);
        st.pumpOnStartTs = 0;
      }
      st.pumpIsOn = res.output;
      st.lastSwitchTime = now;
      st.currentMinDelay = CFG.manualSwitchDelay;
      st.conflictStart = 0;
      st.conflictReported = false;
      report("manual", "etat reel: " + (res.output ? "ON" : "OFF"));
    }

    // Lecture grid
    let s = Shelly.getComponentStatus(CFG.measureComponent + ":" + CFG.measureId);
    if (!s || typeof s.act_power === "undefined") {
      print("[WARN] act_power indispo");
      return;
    }
    let grid = s.act_power;
    pushHistory(grid);
    let gridAvg = avgHistory();

    let season = seasonInfo(comp);
    let modeName = season.name;
    let startTh = season.startGrid;
    let dailyMin = season.dailyMinSec;
    let dailyMax = season.dailyMaxSec;

    // Cumul journalier en temps reel
    let runningSec = st.dailyRunSec +
      (st.pumpIsOn && st.pumpOnStartTs > 0 ? (now - st.pumpOnStartTs) : 0);

    print("[" + modeName + "] grid=" + Math.round(grid) +
          "W avg=" + Math.round(gridAvg) +
          "W pompe=" + (st.pumpIsOn ? "ON " : "OFF") +
          " jour=" + Math.floor(runningSec / 60) + "min" +
          " h=" + comp.hour);

    // ---------- Stop imperatif : quota max ----------
    if (st.pumpIsOn && runningSec >= dailyMax) {
      if ((now - st.lastSwitchTime) >= st.currentMinDelay) {
        setPump(false, "quota max " + Math.floor(dailyMax / 3600) + "h atteint (" + modeName + ")");
      }
      return;
    }

    // ---------- Conflit autre appareil ----------
    let inForceWindow = dailyMin > 0 &&
                        runningSec < dailyMin &&
                        comp.hour >= CFG.forceStartHour &&
                        comp.hour < CFG.forceEndHour;

    if (st.pumpIsOn && grid > CFG.conflictGrid) {
      if (st.conflictStart === 0) {
        st.conflictStart = now;
        st.conflictReported = false;
        print("[CONF] Debut conflit (grid>" + CFG.conflictGrid + "W)");
        report("conflict_start", "grid=" + Math.round(grid) + "W");
      } else {
        let confDur = now - st.conflictStart;
        if (confDur >= CFG.conflictHoldSec) {
          if (inForceWindow) {
            print("[CONF] " + Math.floor(confDur/60) +
                  "min mais forcage quota mini actif -> on garde ON");
          } else if ((now - st.lastSwitchTime) >= st.currentMinDelay) {
            setPump(false, "conflit autre appareil " +
                           Math.floor(confDur/60) + " min");
            return;
          }
        }
      }
    } else if (st.conflictStart !== 0) {
      print("[CONF] Conflit termine");
      report("conflict_end", "duree " +
             Math.floor((now - st.conflictStart) / 60) + " min");
      st.conflictStart = 0;
      st.conflictReported = false;
    }

    // ---------- Delai mini entre bascules ----------
    if ((now - st.lastSwitchTime) < st.currentMinDelay) {
      // delai actif : on ne peut ni demarrer ni arreter
      return;
    }

    // ---------- Fin surplus ----------
    if (st.pumpIsOn && !inForceWindow &&
        st.history.length >= CFG.startAvgWindow &&
        gridAvg > season.stopGrid) {
      setPump(false, "fin surplus " + modeName +
                     " (avg=" + Math.round(gridAvg) + "W > " + season.stopGrid + "W)");
      return;
    }

    // ---------- Forcage quota mini saison ----------
    if (!st.pumpIsOn && inForceWindow) {
      setPump(true, "forcage quota mini " +
                    Math.floor(dailyMin / 3600) + "h " +
                    modeName + " (h=" + comp.hour + ")");
      return;
    }

    // ---------- Demarrage normal sur surplus ----------
    if (!st.pumpIsOn &&
        st.history.length >= CFG.startAvgWindow &&
        gridAvg <= startTh) {
      setPump(true, "surplus solaire " + modeName +
                    " (avg=" + Math.round(gridAvg) + "W)");
      return;
    }
  });
}

// ---- DEMARRAGE --------------------------------------------
print("=== Pompe Piscine v2.3 ===");
loadConfig(function() {
  initPumpState(function () {
    Timer.set(CFG.cycleSec * 1000, true, tick);
    tick();
  });
});
