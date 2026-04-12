/**
 * src/constants/keyCodes.js
 * Codes de touches de la télécommande Samsung Tizen TV.
 *
 * Ces constantes correspondent aux valeurs de `event.keyCode` reçues
 * dans les écouteurs `document.addEventListener('keydown', handler)`.
 *
 * Usage recommandé :
 *   import { KEY } from '../constants/keyCodes';
 *   if (event.keyCode === KEY.OK) { ... }
 *
 * Référence officielle Samsung :
 *   https://developer.samsung.com/smarttv/develop/guides/user-interaction/remote-control.html
 */

// =============================================================================
// Navigation directionnelle
// =============================================================================

/** Flèche gauche */
export const VK_LEFT = 37;

/** Flèche haut */
export const VK_UP = 38;

/** Flèche droite */
export const VK_RIGHT = 39;

/** Flèche bas */
export const VK_DOWN = 40;

// =============================================================================
// Touches de validation et navigation système
// =============================================================================

/** Touche OK / Entrée (centre du pavé directionnel) */
export const VK_ENTER = 13;

/** Alias sémantique pour la touche OK */
export const VK_OK = 13;

/**
 * Touche Retour (bouton "Return/Back" de la télécommande Samsung).
 * Valeur spécifique Samsung Tizen TV.
 */
export const VK_BACK = 10009;

/**
 * Valeur alternative pour VK_BACK (Escape sur certains appareils).
 */
export const VK_BACK_ALT = 27;

/**
 * Touche Home / Smart Hub (ramène au lanceur d'applications Samsung).
 * Valeur spécifique Samsung Tizen TV.
 */
export const VK_EXIT = 10182;

// =============================================================================
// Contrôles de lecture multimédia
// =============================================================================

/** Touche Lecture (▶) */
export const VK_PLAY = 415;

/** Touche Pause (⏸) */
export const VK_PAUSE = 19;

/**
 * Touche Lecture/Pause combinée (▶⏸).
 * Valeur spécifique Samsung Tizen TV.
 */
export const VK_PLAY_PAUSE = 10252;

/** Touche Stop (⏹) */
export const VK_STOP = 413;

/**
 * Touche Avance rapide (⏩).
 */
export const VK_FF = 417;

/**
 * Touche Retour rapide (⏪).
 */
export const VK_REW = 412;

// =============================================================================
// Touches couleur
// =============================================================================

/** Touche rouge */
export const VK_RED = 403;

/** Touche verte */
export const VK_GREEN = 404;

/** Touche jaune */
export const VK_YELLOW = 405;

/** Touche bleue */
export const VK_BLUE = 406;

// =============================================================================
// Touches numériques
// =============================================================================

export const VK_0 = 48;
export const VK_1 = 49;
export const VK_2 = 50;
export const VK_3 = 51;
export const VK_4 = 52;
export const VK_5 = 53;
export const VK_6 = 54;
export const VK_7 = 55;
export const VK_8 = 56;
export const VK_9 = 57;

// =============================================================================
// Objet agrégé KEY — permet l'import nommé unique
// =============================================================================

/**
 * Objet regroupant toutes les constantes de touches.
 * Permet d'utiliser : import { KEY } from '../constants/keyCodes';
 * puis : event.keyCode === KEY.OK
 */
export const KEY = {
  // Navigation
  LEFT: VK_LEFT,
  UP: VK_UP,
  RIGHT: VK_RIGHT,
  DOWN: VK_DOWN,

  // Validation / système
  ENTER: VK_ENTER,
  OK: VK_OK,
  BACK: VK_BACK,
  BACK_ALT: VK_BACK_ALT,
  EXIT: VK_EXIT,

  // Lecture
  PLAY: VK_PLAY,
  PAUSE: VK_PAUSE,
  PLAY_PAUSE: VK_PLAY_PAUSE,
  STOP: VK_STOP,
  FF: VK_FF,
  REW: VK_REW,

  // Couleurs
  RED: VK_RED,
  GREEN: VK_GREEN,
  YELLOW: VK_YELLOW,
  BLUE: VK_BLUE,

  // Chiffres
  NUM_0: VK_0,
  NUM_1: VK_1,
  NUM_2: VK_2,
  NUM_3: VK_3,
  NUM_4: VK_4,
  NUM_5: VK_5,
  NUM_6: VK_6,
  NUM_7: VK_7,
  NUM_8: VK_8,
  NUM_9: VK_9,
};

// =============================================================================
// Utilitaires
// =============================================================================

/**
 * Vérifie si un keyCode correspond à la touche BACK (en gérant les variantes).
 * Usage : if (isBackKey(event.keyCode)) { navigateBack(); }
 *
 * @param {number} keyCode - La valeur event.keyCode reçue
 * @returns {boolean}
 */
export function isBackKey(keyCode) {
  return keyCode === VK_BACK || keyCode === VK_BACK_ALT;
}

/**
 * Vérifie si un keyCode correspond à une touche de validation (OK/Entrée).
 *
 * @param {number} keyCode - La valeur event.keyCode reçue
 * @returns {boolean}
 */
export function isOkKey(keyCode) {
  return keyCode === VK_ENTER;
}

/**
 * Vérifie si un keyCode correspond à une touche directionnelle.
 *
 * @param {number} keyCode - La valeur event.keyCode reçue
 * @returns {boolean}
 */
export function isDirectionalKey(keyCode) {
  return keyCode >= VK_LEFT && keyCode <= VK_DOWN;
}

/**
 * Vérifie si un keyCode correspond à une touche de lecture multimédia.
 *
 * @param {number} keyCode - La valeur event.keyCode reçue
 * @returns {boolean}
 */
export function isMediaKey(keyCode) {
  return [VK_PLAY, VK_PAUSE, VK_PLAY_PAUSE, VK_STOP, VK_FF, VK_REW].includes(keyCode);
}
