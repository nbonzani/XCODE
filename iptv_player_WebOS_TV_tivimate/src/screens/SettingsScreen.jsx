/**
 * SettingsScreen.jsx
 * Tous les champs texte fonctionnent comme le champ recherche :
 *   - Bouton focusable avec halo visible à la télécommande
 *   - OK → ouvre l'input et le clavier virtuel
 *   - Blur (validation clavier) → ferme l'input, focus sur le champ suivant
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppStore } from '../store/appStore.js';
import { XtreamClient } from '../services/xtreamApi.js';
import { KEY, isBackKey } from '../constants/keyCodes.js';
import { detectUsbDevices, readFileContent, parseM3u, USB_PATHS } from '../services/usbService.js';
import './SettingsScreen.css';

// ── Champ texte : bouton → input sur OK ───────────────────────────────────────

const FocusableField = React.forwardRef(function FocusableField(
  { id, label, value, onChange, placeholder, isFocused, onNext, isPassword },
  ref
) {
  const [editing, setEditing] = useState(false);
  const inputRef = useRef(null);

  const openInput = useCallback(() => {
    setEditing(true);
    setTimeout(() => inputRef.current?.focus(), 50);
  }, []);

  const closeInput = useCallback(() => {
    setEditing(false);
    setTimeout(() => {
      ref?.current?.focus();
      if (onNext) setTimeout(onNext, 3000);
    }, 50);
  }, [ref, onNext]);

  const handleInputKeyDown = useCallback((e) => {
    if (e.keyCode === KEY.OK || e.keyCode === 461) {
      // OK ou BACK télécommande → valider et fermer
      e.preventDefault();
      e.stopPropagation();
      closeInput();
    } else if (e.keyCode === 8) {
      // Touche ⌫ clavier virtuel → laisser l'input supprimer le caractère
      e.stopPropagation();
    }
  }, [closeInput]);

  const displayValue = value || placeholder;

  return (
    <div className="settings-field">
      <label htmlFor={id} className="settings-label">{label}</label>

      {editing ? (
        <input
          ref={inputRef}
          id={id}
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={closeInput}
          onKeyDown={handleInputKeyDown}
          className="settings-input focusable-input"
          autoComplete="off"
          spellCheck={false}
        />
      ) : (
        <button
          ref={ref}
          className={`settings-field-btn ${isFocused ? 'focused' : ''} ${value ? 'settings-field-btn--filled' : 'settings-field-btn--empty'}`}
          tabIndex={0}
          onClick={openInput}
          onKeyDown={(e) => {
            if (e.keyCode === KEY.OK) { e.preventDefault(); openInput(); }
          }}
        >
          {displayValue}
          <span className="settings-field-btn__edit">✏️</span>
        </button>
      )}
    </div>
  );
});

// ── Toggle FR ─────────────────────────────────────────────────────────────────

function ToggleSwitch({ checked, onChange, divRef, isFocused }) {
  return (
    <div
      ref={divRef}
      className={`toggle-switch ${checked ? 'toggle-switch--on' : ''} ${isFocused ? 'focused' : ''}`}
      tabIndex={0}
      role="checkbox"
      aria-checked={checked}
      onKeyDown={(e) => {
        if (e.keyCode === KEY.OK || e.keyCode === 32) {
          e.preventDefault();
          onChange(!checked);
        }
      }}
      onClick={() => onChange(!checked)}
    >
      <div className="toggle-switch__track">
        <div className="toggle-switch__thumb" />
      </div>
      <span className="toggle-switch__label">
        Afficher uniquement le contenu en français (catégories commençant par "FR")
      </span>
    </div>
  );
}

// ── Résultat test connexion ───────────────────────────────────────────────────

function ConnectionStatus({ status }) {
  if (!status) return null;
  return (
    <div className={`connection-status connection-status--${status.type}`}>
      {status.type === 'loading' && <div className="spinner" style={{ width: 32, height: 32, flexShrink: 0 }} />}
      {status.type === 'success' && <span className="connection-status__icon">✅</span>}
      {status.type === 'error'   && <span className="connection-status__icon">❌</span>}
      <div className="connection-status__content">
        <p className="connection-status__message">{status.message}</p>
        {status.type === 'success' && status.details && (
          <ul className="connection-status__details">
            {status.details.map((line, i) => <li key={i}>{line}</li>)}
          </ul>
        )}
      </div>
    </div>
  );
}

// ── Écran principal ───────────────────────────────────────────────────────────

export default function SettingsScreen() {
  const navigate = useNavigate();
  const { config, isConfigured, saveConfig } = useAppStore();

  const [serverUrl,  setServerUrl]  = useState(config.serverUrl  || '');
  const [username,   setUsername]   = useState(config.username   || '');
  const [password,   setPassword]   = useState(config.password   || '');

  const [connectionStatus,   setConnectionStatus]   = useState(null);
  const [validationError,    setValidationError]     = useState('');
  const [isTesting,          setIsTesting]           = useState(false);
  const [focusedIdx,         setFocusedIdx]          = useState(0);
  const [showLangPicker,     setShowLangPicker]      = useState(false);
  const [langFocusedIdx,     setLangFocusedIdx]      = useState(0);
  const [isLoadingCats,      setIsLoadingCats]       = useState(false);
  const [inLangArea,         setInLangArea]          = useState(false);
  const langButtonRefs = useRef([]);

  // ── Import M3U ──────────────────────────────────────────────────────────
  const [m3uStatus, setM3uStatus]     = useState(null);  // { type, message, files? }
  const [m3uPath, setM3uPath]         = useState('');
  const [isScanning, setIsScanning]   = useState(false);

  const urlRef      = useRef(null);
  const usernameRef = useRef(null);
  const passwordRef = useRef(null);
  const testBtnRef  = useRef(null);
  const saveBtnRef  = useRef(null);
  const m3uScanRef  = useRef(null);
  const m3uPathRef  = useRef(null);
  const m3uLoadRef  = useRef(null);

  // Ordre : 0=url 1=username 2=password 3=test 4=save 5=scanUSB 6=m3uPath 7=loadM3U
  const fieldOrder = [urlRef, usernameRef, passwordRef, testBtnRef, saveBtnRef, m3uScanRef, m3uPathRef, m3uLoadRef];

  const applyFocus = useCallback((idx) => {
    const i = Math.max(0, Math.min(idx, fieldOrder.length - 1));
    setFocusedIdx(i);
    fieldOrder[i].current?.focus();
  }, []);

  // Focus initial
  useEffect(() => {
    const t = setTimeout(() => applyFocus(0), 150);
    return () => clearTimeout(t);
  }, []);

  // Navigation globale ↑/↓/←/→
  useEffect(() => {
    const handler = (e) => {
      // Ignorer si un input est actif (clavier virtuel ouvert)
      if (document.activeElement?.tagName === 'INPUT') return;

      // Zone langue : navigation horizontale parmi les 5 boutons
      if (inLangArea) {
        if (e.keyCode === KEY.LEFT) {
          e.preventDefault();
          const next = Math.max(0, langFocusedIdx - 1);
          setLangFocusedIdx(next);
          langButtonRefs.current[next]?.focus();
        } else if (e.keyCode === KEY.RIGHT) {
          e.preventDefault();
          const next = Math.min(4, langFocusedIdx + 1);
          setLangFocusedIdx(next);
          langButtonRefs.current[next]?.focus();
        } else if (e.keyCode === KEY.UP) {
          e.preventDefault();
          setInLangArea(false);
          applyFocus(3);
        } else if (e.keyCode === KEY.DOWN) {
          e.preventDefault();
          setInLangArea(false);
          applyFocus(4);
        } else if (e.keyCode === KEY.OK) {
          const el = document.activeElement;
          if (el && el.tagName === 'BUTTON') { e.preventDefault(); el.click(); }
        } else if (isBackKey(e.keyCode) && isConfigured) {
          e.preventDefault();
          navigate('/');
        }
        return;
      }

      if (isBackKey(e.keyCode) && isConfigured) {
        e.preventDefault();
        navigate('/');
      } else if (e.keyCode === KEY.DOWN) {
        e.preventDefault();
        if (showLangPicker && focusedIdx === 3) {
          // Descendre vers zone langue (bouton Test = idx 3)
          setInLangArea(true);
          setLangFocusedIdx(0);
          langButtonRefs.current[0]?.focus();
        } else {
          applyFocus(focusedIdx + 1);
        }
      } else if (e.keyCode === KEY.UP) {
        e.preventDefault();
        applyFocus(focusedIdx - 1);
      } else if (e.keyCode === KEY.RIGHT && focusedIdx === 3) {
        e.preventDefault();
        applyFocus(4);
      } else if (e.keyCode === KEY.LEFT && focusedIdx === 4) {
        e.preventDefault();
        applyFocus(3);
      } else if (e.keyCode === KEY.RIGHT && focusedIdx === 5) {
        e.preventDefault();
        applyFocus(7);
      } else if (e.keyCode === KEY.LEFT && focusedIdx === 7) {
        e.preventDefault();
        applyFocus(5);
      } else if (e.keyCode === KEY.OK) {
        const el = document.activeElement;
        if (el && el.tagName === 'BUTTON') {
          e.preventDefault();
          el.click();
        }
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isConfigured, navigate, focusedIdx, applyFocus, inLangArea, langFocusedIdx, showLangPicker]);

  const normalizeUrl = (url) => {
    const t = url.trim();
    return t.startsWith('http://') || t.startsWith('https://') ? t : 'http://' + t;
  };

  const validate = useCallback(() => {
    if (!serverUrl.trim()) { setValidationError("Veuillez saisir l'URL du serveur."); applyFocus(0); return false; }
    if (!username.trim())  { setValidationError("Veuillez saisir le nom d'utilisateur."); applyFocus(1); return false; }
    if (!password.trim())  { setValidationError('Veuillez saisir le mot de passe.'); applyFocus(2); return false; }
    setValidationError('');
    return true;
  }, [serverUrl, username, password, applyFocus]);

  const handleTestConnection = useCallback(async () => {
    if (!validate() || isTesting) return;
    setIsTesting(true);
    setConnectionStatus({ type: 'loading', message: 'Test de connexion en cours…' });
    let success = false;
    try {
      const client = new XtreamClient(normalizeUrl(serverUrl), '', username.trim(), password.trim());
      const data   = await client.authenticate();
      const u      = data.user_info || {};
      let expDate  = 'N/A';
      if (u.exp_date) {
        try { expDate = new Date(parseInt(u.exp_date) * 1000).toLocaleDateString('fr-FR'); } catch { expDate = String(u.exp_date); }
      }
      setConnectionStatus({
        type: 'success', message: 'Connexion réussie !',
        details: [`Compte : ${u.username || 'N/A'}`, `Statut : ${u.status || 'N/A'}`, `Expire le : ${expDate}`, `Connexions : ${u.active_cons || 0} / ${u.max_connections || 'N/A'}`],
      });
      success = true;
      setShowLangPicker(true);
      setLangFocusedIdx(0);
      setTimeout(() => {
        setInLangArea(true);
        langButtonRefs.current[0]?.focus();
      }, 200);
    } catch (err) {
      setConnectionStatus({ type: 'error', message: `Échec : ${err.message}` });
      setShowLangPicker(false);
    } finally {
      setIsTesting(false);
      if (!success) setTimeout(() => applyFocus(4), 200);
    }
  }, [serverUrl, username, password, validate, isTesting, applyFocus]);

  const handleSave = useCallback(() => {
    if (!validate()) return;
    try {
      const existing = useAppStore.getState().config;
      saveConfig({
        serverUrl: normalizeUrl(serverUrl), port: '', username: username.trim(), password: password.trim(),
        frenchOnly: false,
        filterLanguage: existing.filterLanguage || '',
        selectedMovieCategories: existing.selectedMovieCategories || [],
        selectedSeriesCategories: existing.selectedSeriesCategories || [],
      });
      navigate('/');
    } catch {
      setValidationError('Erreur lors de la sauvegarde. Réessayez.');
    }
  }, [serverUrl, username, password, validate, saveConfig, navigate]);

  const handleLanguageSelect = useCallback(async (lang) => {
    if (isLoadingCats) return;
    const baseConfig = {
      serverUrl: normalizeUrl(serverUrl), port: '', username: username.trim(),
      password: password.trim(), frenchOnly: false,
    };

    if (lang === '') {
      // "Tout" : pas de filtre catégorie
      try {
        saveConfig({ ...baseConfig, filterLanguage: '', selectedMovieCategories: [], selectedSeriesCategories: [] });
        navigate('/');
      } catch {
        setValidationError('Erreur lors de la sauvegarde.');
      }
      return;
    }

    // Langue sélectionnée → charger les catégories et ouvrir l'écran de filtre
    setIsLoadingCats(true);
    try {
      const client = new XtreamClient(normalizeUrl(serverUrl), '', username.trim(), password.trim());
      const [movieCats, seriesCats] = await Promise.all([
        client.getVodCategories(),
        client.getSeriesCategories(),
      ]);
      // Pré-sauvegarder la config sans sélection de catégories (sera mis à jour dans CatalogFilterScreen)
      saveConfig({ ...baseConfig, filterLanguage: lang, selectedMovieCategories: [], selectedSeriesCategories: [] });
      navigate('/catalog-filter', { state: { language: lang, movieCategories: movieCats, seriesCategories: seriesCats } });
    } catch (err) {
      setValidationError(`Erreur chargement catégories : ${err.message}`);
    } finally {
      setIsLoadingCats(false);
    }
  }, [serverUrl, username, password, frenchOnly, isLoadingCats, saveConfig, navigate]);

  // ── Import M3U : scan USB ──────────────────────────────────────────────
  const handleScanUsb = useCallback(async () => {
    if (isScanning) return;
    setIsScanning(true);
    setM3uStatus({ type: 'loading', message: 'Recherche de clés USB…' });

    try {
      const devices = await detectUsbDevices();

      if (devices.length > 0) {
        // Luna a trouvé des devices — lister les infos
        setM3uStatus({
          type: 'success',
          message: `${devices.length} périphérique(s) USB détecté(s)`,
          files: devices.map((d) => d.uri),
        });
      } else {
        // Fallback : tester les chemins courants
        setM3uStatus({ type: 'loading', message: 'Test des chemins USB courants…' });
        const found = [];
        for (const basePath of USB_PATHS) {
          try {
            const content = await readFileContent(basePath + '/');
            if (content) found.push(basePath);
          } catch { /* chemin inaccessible */ }
        }
        if (found.length > 0) {
          setM3uStatus({
            type: 'success',
            message: `USB trouvé : ${found.join(', ')}`,
            files: found,
          });
          setM3uPath(found[0]);
        } else {
          setM3uStatus({
            type: 'error',
            message: 'Aucune clé USB détectée. Saisissez le chemin manuellement (ex: /tmp/usb/sda/sda1/playlist.m3u)',
          });
        }
      }
    } catch (err) {
      setM3uStatus({ type: 'error', message: `Erreur : ${err.message}` });
    } finally {
      setIsScanning(false);
    }
  }, [isScanning]);

  // ── Import M3U : charger le fichier ──────────────────────────────────
  const handleLoadM3u = useCallback(async () => {
    if (!m3uPath.trim()) {
      setM3uStatus({ type: 'error', message: 'Saisissez le chemin du fichier M3U.' });
      return;
    }

    setM3uStatus({ type: 'loading', message: 'Lecture du fichier M3U…' });

    try {
      const content = await readFileContent(m3uPath.trim());
      if (!content || content.length < 10) {
        setM3uStatus({ type: 'error', message: 'Fichier vide ou illisible.' });
        return;
      }

      const result = parseM3u(content);
      setM3uStatus({
        type: 'success',
        message: `Import réussi : ${result.movies.length} films, ${result.series.length} séries, ${result.categories.length} catégories`,
      });

      // Sauvegarder le chemin dans le localStorage pour la prochaine fois
      try { localStorage.setItem('iptv_last_m3u_path', m3uPath.trim()); } catch {}

    } catch (err) {
      setM3uStatus({ type: 'error', message: `Erreur : ${err.message}` });
    }
  }, [m3uPath]);

  // Restaurer le dernier chemin M3U utilisé
  useEffect(() => {
    try {
      const lastPath = localStorage.getItem('iptv_last_m3u_path');
      if (lastPath) setM3uPath(lastPath);
    } catch {}
  }, []);

  const fc = (idx) => focusedIdx === idx ? 'focused' : '';

  return (
    <div className="settings-screen">
      <div className="settings-header">
        <h1 className="settings-title">Paramètres de connexion</h1>
        <p className="settings-subtitle">Configurez votre serveur IPTV compatible Xtream Codes</p>
      </div>

      <div className="settings-body">
        {/* ── Panneau gauche : Paramètres serveur ── */}
        <div className="settings-panel">

          <section className="settings-group">
            <h2 className="settings-group__title">Serveur Xtream Codes</h2>
            <FocusableField ref={urlRef}      id="url"      label="URL du serveur"    value={serverUrl} onChange={setServerUrl} placeholder="http://serveur.com ou http://serveur.com:port" isFocused={focusedIdx===0} onNext={() => applyFocus(1)} />
            <FocusableField ref={usernameRef} id="username" label="Nom d'utilisateur" value={username}  onChange={setUsername}  placeholder="Appuyez sur OK pour saisir…" isFocused={focusedIdx===1} onNext={() => applyFocus(2)} />
            <FocusableField ref={passwordRef} id="password" label="Mot de passe"      value={password}  onChange={setPassword}  placeholder="Appuyez sur OK pour saisir…" isFocused={focusedIdx===2} onNext={() => applyFocus(3)} />
          </section>

          {validationError && <p className="settings-error">⚠ {validationError}</p>}
          <ConnectionStatus status={connectionStatus} />

          {showLangPicker && (
            <div className="settings-lang-picker">
              <p className="settings-lang-picker__title">
                {isLoadingCats ? 'Chargement des catégories…' : 'Choisissez une langue pour filtrer le catalogue :'}
              </p>
              {isLoadingCats ? (
                <div className="spinner" style={{ width: 40, height: 40, margin: '0 auto' }} />
              ) : (
                <div className="settings-lang-picker__buttons">
                  {[
                    { lang: 'FR', label: 'Français' },
                    { lang: 'IT', label: 'Italien' },
                    { lang: 'EN', label: 'Anglais' },
                    { lang: 'DE', label: 'Allemand' },
                    { lang: '',   label: 'Tout' },
                  ].map(({ lang, label }, i) => (
                    <button
                      key={lang || 'all'}
                      ref={(el) => { langButtonRefs.current[i] = el; }}
                      className={`settings-lang-btn ${inLangArea && langFocusedIdx === i ? 'focused' : ''}`}
                      tabIndex={0}
                      onFocus={() => { setInLangArea(true); setLangFocusedIdx(i); }}
                      onClick={() => handleLanguageSelect(lang)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="settings-actions">
            <button
              ref={testBtnRef}
              className={`settings-btn settings-btn--test action-button ${fc(3)}`}
              tabIndex={0}
              onClick={handleTestConnection}
              disabled={isTesting}
              onFocus={() => setFocusedIdx(3)}
            >
              🔌 Tester la connexion
            </button>
            <div className="settings-actions__right">
              <button
                ref={saveBtnRef}
                className={`settings-btn settings-btn--save action-button ${fc(4)}`}
                tabIndex={0}
                onClick={handleSave}
                onFocus={() => setFocusedIdx(4)}
              >
                Enregistrer
              </button>
            </div>
          </div>
          {isConfigured && (
            <p className="settings-back-hint">← Appuyez sur BACK pour annuler et revenir</p>
          )}

        </div>

        {/* ── Panneau droit : Import M3U ── */}
        <div className="settings-panel settings-panel--m3u">

          <section className="settings-group">
            <h2 className="settings-group__title">Importer une playlist M3U</h2>
            <p className="settings-info">ℹ Branchez une clé USB contenant un fichier .m3u sur votre TV</p>

            <div className="settings-m3u-row">
              <button
                ref={m3uScanRef}
                className={`settings-btn settings-btn--scan action-button ${fc(5)}`}
                tabIndex={0}
                onClick={handleScanUsb}
                disabled={isScanning}
                onFocus={() => setFocusedIdx(5)}
              >
                🔍 Rechercher sur USB
              </button>
            </div>

            <FocusableField
              ref={m3uPathRef}
              id="m3u-path"
              label="Chemin du fichier M3U"
              value={m3uPath}
              onChange={setM3uPath}
              placeholder="/tmp/usb/sda/sda1/playlist.m3u"
              isFocused={focusedIdx===6}
              onNext={() => applyFocus(7)}
            />

            <div className="settings-m3u-row">
              <button
                ref={m3uLoadRef}
                className={`settings-btn settings-btn--load action-button ${fc(7)}`}
                tabIndex={0}
                onClick={handleLoadM3u}
                onFocus={() => setFocusedIdx(7)}
              >
                📂 Charger le fichier M3U
              </button>
            </div>

            {m3uStatus && (
              <div className={`connection-status connection-status--${m3uStatus.type}`}>
                {m3uStatus.type === 'loading' && <div className="spinner" style={{ width: 32, height: 32, flexShrink: 0 }} />}
                {m3uStatus.type === 'success' && <span className="connection-status__icon">✅</span>}
                {m3uStatus.type === 'error'   && <span className="connection-status__icon">❌</span>}
                <p className="connection-status__message">{m3uStatus.message}</p>
              </div>
            )}
          </section>

        </div>
      </div>
    </div>
  );
}
