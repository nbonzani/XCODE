/**
 * src/store/appStore.js
 * Store Zustand — état global de l'application.
 *
 * Correction clé : la configuration est lue de façon SYNCHRONE au chargement
 * du module JS (readInitialConfig), avant le premier rendu React.
 * Cela garantit que isConfigured et isReady sont corrects dès le premier rendu
 * de RequireConfig, sans flash de redirection vers /settings.
 */

import { create } from 'zustand';

const CONFIG_STORAGE_KEY = 'iptv_config';

const DEFAULT_CONFIG = {
  serverUrl:  '',
  port:       '',
  username:   '',
  password:   '',
  frenchOnly: true,
  filterLanguage:           [],  // ['FR','IT',...] | [] (tout)
  selectedMovieCategories:  [],  // [] = toutes, [id, ...] = filtrées
  selectedSeriesCategories: [],  // [] = toutes, [id, ...] = filtrées
};

// Lecture synchrone du localStorage au chargement du module.
// S'exécute UNE SEULE FOIS avant que React ne monte quoi que ce soit.
function readInitialConfig() {
  try {
    const raw = localStorage.getItem(CONFIG_STORAGE_KEY);
    if (!raw) {
      return { isConfigured: false, config: { ...DEFAULT_CONFIG }, lastSyncDate: null };
    }
    const saved   = JSON.parse(raw);
    const isValid = Boolean(saved.serverUrl && saved.serverUrl.trim()) &&
                    Boolean(saved.username  && saved.username.trim());
    return {
      isConfigured: isValid,
      config:       { ...DEFAULT_CONFIG, ...saved },
      lastSyncDate: saved.lastSyncDate || null,
    };
  } catch {
    return { isConfigured: false, config: { ...DEFAULT_CONFIG }, lastSyncDate: null };
  }
}

const INITIAL = readInitialConfig();

export const useAppStore = create((set, get) => ({

  isConfigured: INITIAL.isConfigured,
  isReady:      true,   // toujours true : lecture synchrone au dessus
  config:       INITIAL.config,

  isSyncing:     false,
  syncStatus:    '',
  syncProgress:  { done: 0, total: 0 },
  lastSyncDate:  INITIAL.lastSyncDate,

  activeTab:     'movies',
  selectedMovie: null,

  // No-op : conservé pour compatibilité avec App.jsx
  initConfig: () => {},

  saveConfig: (newConfig) => {
    try {
      const toSave = { ...newConfig, lastSyncDate: get().lastSyncDate };
      localStorage.setItem(CONFIG_STORAGE_KEY, JSON.stringify(toSave));
      set({ config: { ...newConfig }, isConfigured: true });
    } catch (error) {
      console.error('[AppStore] Erreur écriture localStorage:', error);
      throw error;
    }
  },

  startSync: () => set({ isSyncing: true, syncStatus: 'Synchronisation en cours…', syncProgress: { done: 0, total: 0 } }),

  setSyncProgress: (done, total) => set({ syncProgress: { done, total } }),

  finishSync: (count) => {
    const now = new Date().toISOString();
    set({ isSyncing: false, syncStatus: `✅ Synchronisation terminée (${count} contenus)`, lastSyncDate: now });
    try {
      const raw = localStorage.getItem(CONFIG_STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw);
        localStorage.setItem(CONFIG_STORAGE_KEY, JSON.stringify({ ...saved, lastSyncDate: now }));
      }
    } catch { /* non bloquant */ }
  },

  failSync: (message) => set({ isSyncing: false, syncStatus: `Erreur : ${message}`, syncProgress: { done: 0, total: 0 } }),

  setActiveTab: (tab) => set({ activeTab: tab }),

  openMovieDetail:  (movie) => set({ selectedMovie: movie }),
  closeMovieDetail: ()      => set({ selectedMovie: null }),
}));
