"""
core/database.py
----------------
Gestion complète de la base de données SQLite pour VoiceNotes.

Tables :
  - notes        : métadonnées + transcription de chaque note vocale
  - themes       : catalogue des thèmes (libellés configurables)
  - notes_themes : liaison many-to-many entre notes et thèmes

Toutes les fonctions ouvrent et ferment leur propre connexion pour
rester thread-safe sans connexion persistante globale.
"""

import sqlite3
import os
from datetime import datetime
from utils.config import DB_PATH, THEMES_PAR_DEFAUT


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def init_database():
    """
    Crée les tables si elles n'existent pas encore et insère les thèmes par défaut.
    À appeler une seule fois au démarrage de l'application.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = _get_conn()
    cur = conn.cursor()

    # Activation des clés étrangères (désactivées par défaut dans SQLite)
    cur.execute("PRAGMA foreign_keys = ON")

    # --- Table des notes ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            titre             TEXT,
            transcription     TEXT,
            chemin_audio      TEXT,
            duree_secondes    REAL DEFAULT 0,
            date_creation     TEXT NOT NULL,
            date_modification TEXT NOT NULL
        )
    """)

    # --- Table des thèmes ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS themes (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            nom            TEXT NOT NULL UNIQUE,
            date_creation  TEXT NOT NULL
        )
    """)

    # --- Table de liaison notes ↔ thèmes ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notes_themes (
            note_id  INTEGER NOT NULL,
            theme_id INTEGER NOT NULL,
            PRIMARY KEY (note_id, theme_id),
            FOREIGN KEY (note_id)  REFERENCES notes(id)  ON DELETE CASCADE,
            FOREIGN KEY (theme_id) REFERENCES themes(id) ON DELETE CASCADE
        )
    """)

    conn.commit()

    # Insérer les thèmes par défaut s'ils n'existent pas encore
    for nom in THEMES_PAR_DEFAUT:
        _inserer_theme_si_absent(conn, nom)

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    """Retourne une connexion avec row_factory pour accès par nom de colonne."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _inserer_theme_si_absent(conn, nom: str):
    """Insère un thème uniquement s'il n'existe pas déjà (sans lever d'exception)."""
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO themes (nom, date_creation) VALUES (?, ?)",
        (nom, now)
    )


# ---------------------------------------------------------------------------
# CRUD — Notes
# ---------------------------------------------------------------------------

def inserer_note(titre: str, transcription: str, chemin_audio: str,
                 duree_secondes: float) -> int:
    """
    Insère une nouvelle note dans la base.
    Retourne l'ID de la note créée.
    """
    now = datetime.now().isoformat()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO notes (titre, transcription, chemin_audio, duree_secondes,
                           date_creation, date_modification)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (titre, transcription, chemin_audio, duree_secondes, now, now))
    note_id = cur.lastrowid
    conn.commit()
    conn.close()
    return note_id


def mettre_a_jour_note(note_id: int, titre: str = None, transcription: str = None):
    """Met à jour le titre et/ou la transcription d'une note existante."""
    now = datetime.now().isoformat()
    conn = _get_conn()
    cur = conn.cursor()
    if titre is not None:
        cur.execute("UPDATE notes SET titre=?, date_modification=? WHERE id=?",
                    (titre, now, note_id))
    if transcription is not None:
        cur.execute("UPDATE notes SET transcription=?, date_modification=? WHERE id=?",
                    (transcription, now, note_id))
    conn.commit()
    conn.close()


def supprimer_note(note_id: int):
    """Supprime une note et toutes ses associations de thèmes (CASCADE)."""
    conn = _get_conn()
    conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
    conn.commit()
    conn.close()


def get_note_par_id(note_id: int) -> dict | None:
    """Retourne une note complète (avec ses thèmes) sous forme de dict, ou None."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT n.*, GROUP_CONCAT(t.nom, ', ') AS themes
        FROM notes n
        LEFT JOIN notes_themes nt ON n.id = nt.note_id
        LEFT JOIN themes t        ON nt.theme_id = t.id
        WHERE n.id = ?
        GROUP BY n.id
    """, (note_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_toutes_notes(theme_filtre: str = None, recherche: str = None) -> list[dict]:
    """
    Récupère toutes les notes, avec filtres optionnels :
      - theme_filtre : nom exact du thème (ex: "Réunion")
      - recherche    : chaîne à rechercher dans la transcription (LIKE)
    Retourne une liste de dict triée par date décroissante.
    """
    conn = _get_conn()
    cur = conn.cursor()

    base = """
        SELECT n.*, GROUP_CONCAT(t.nom, ', ') AS themes
        FROM notes n
        LEFT JOIN notes_themes nt ON n.id = nt.note_id
        LEFT JOIN themes t        ON nt.theme_id = t.id
    """
    conditions = []
    params = []

    if theme_filtre:
        conditions.append("""
            n.id IN (
                SELECT nt2.note_id FROM notes_themes nt2
                JOIN themes t2 ON nt2.theme_id = t2.id
                WHERE t2.nom = ?
            )
        """)
        params.append(theme_filtre)

    if recherche:
        conditions.append("n.transcription LIKE ?")
        params.append(f"%{recherche}%")

    if conditions:
        base += " WHERE " + " AND ".join(conditions)

    base += " GROUP BY n.id ORDER BY n.date_creation DESC"

    cur.execute(base, params)
    notes = [dict(row) for row in cur.fetchall()]
    conn.close()
    return notes


# ---------------------------------------------------------------------------
# CRUD — Thèmes
# ---------------------------------------------------------------------------

def get_tous_themes() -> list[dict]:
    """Retourne tous les thèmes triés alphabétiquement."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM themes ORDER BY nom")
    themes = [dict(row) for row in cur.fetchall()]
    conn.close()
    return themes


def get_noms_themes() -> list[str]:
    """Retourne uniquement les noms des thèmes (pratique pour l'UI)."""
    return [t["nom"] for t in get_tous_themes()]


def get_ou_creer_theme(nom: str) -> int:
    """
    Retourne l'ID du thème si il existe, sinon le crée.
    Retourne l'ID dans tous les cas.
    """
    nom = nom.strip()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM themes WHERE nom = ?", (nom,))
    row = cur.fetchone()
    if row:
        theme_id = row["id"]
        conn.close()
        return theme_id
    # Création
    now = datetime.now().isoformat()
    cur.execute("INSERT INTO themes (nom, date_creation) VALUES (?, ?)", (nom, now))
    theme_id = cur.lastrowid
    conn.commit()
    conn.close()
    return theme_id


def supprimer_theme(theme_id: int):
    """Supprime un thème et toutes ses associations avec les notes."""
    conn = _get_conn()
    conn.execute("DELETE FROM themes WHERE id=?", (theme_id,))
    conn.commit()
    conn.close()


def renommer_theme(theme_id: int, nouveau_nom: str):
    """Renomme un thème existant."""
    conn = _get_conn()
    conn.execute("UPDATE themes SET nom=? WHERE id=?", (nouveau_nom.strip(), theme_id))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Association notes ↔ thèmes
# ---------------------------------------------------------------------------

def assigner_themes_a_note(note_id: int, noms_themes: list[str]):
    """
    Remplace les thèmes d'une note par la liste fournie.
    Crée les thèmes manquants automatiquement.
    Les thèmes vides ou en doublon sont ignorés.
    """
    # Supprime les anciennes associations
    conn = _get_conn()
    conn.execute("DELETE FROM notes_themes WHERE note_id=?", (note_id,))
    conn.commit()
    conn.close()

    # Ajoute les nouvelles
    noms_uniques = list({n.strip() for n in noms_themes if n.strip()})
    for nom in noms_uniques:
        theme_id = get_ou_creer_theme(nom)
        conn = _get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO notes_themes (note_id, theme_id) VALUES (?, ?)",
            (note_id, theme_id)
        )
        conn.commit()
        conn.close()


def get_themes_de_note(note_id: int) -> list[str]:
    """Retourne la liste des noms de thèmes associés à une note."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.nom FROM themes t
        JOIN notes_themes nt ON t.id = nt.theme_id
        WHERE nt.note_id = ?
        ORDER BY t.nom
    """, (note_id,))
    noms = [row["nom"] for row in cur.fetchall()]
    conn.close()
    return noms
