"""
Xtream Video Downloader
Application de téléchargement de vidéos depuis un serveur Xtream.
Les URLs sont lues depuis un fichier texte (une URL par ligne).
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import requests
import os
import re
from urllib.parse import urlparse, unquote


# ==============================================================================
# FONCTIONS UTILITAIRES
# ==============================================================================

def extraire_nom_fichier(url):
    """
    Extrait un nom de fichier lisible depuis une URL Xtream.
    Ex: http://serveur/serie/user/pass/12345.mp4 → 12345.mp4
    """
    chemin = urlparse(url).path          # Récupère la partie chemin de l'URL
    nom = os.path.basename(chemin)       # Prend le dernier segment (le nom de fichier)
    nom = unquote(nom)                   # Décode les caractères spéciaux (%20 → espace, etc.)
    if not nom or '.' not in nom:        # Si pas d'extension détectée, on force .mp4
        nom = f"video_{hash(url) % 100000}.mp4"
    return nom


def lire_urls_depuis_fichier(chemin_fichier):
    """
    Lit le fichier texte au format : nom;url (séparés par un point-virgule).
    Retourne une liste de tuples (nom, url).
    Les lignes vides ou commençant par # sont ignorées.
    Les lignes mal formées (sans point-virgule, ou sans URL valide) sont ignorées.
    """
    entrees = []
    with open(chemin_fichier, 'r', encoding='utf-8') as f:
        for numero_ligne, ligne in enumerate(f, start=1):
            ligne = ligne.strip()                        # Supprime espaces/retours à la ligne
            if not ligne or ligne.startswith('#'):       # Ignore lignes vides et commentaires
                continue
            if ';' not in ligne:                         # Ignore les lignes sans point-virgule
                print(f"Ligne {numero_ligne} ignorée (pas de ';') : {ligne}")
                continue
            # Sépare en deux parties sur le PREMIER point-virgule uniquement
            # Cela permet d'avoir des point-virgules dans le nom si nécessaire
            nom, url = ligne.split(';', maxsplit=1)
            nom = nom.strip()                            # Supprime les espaces autour du nom
            url = url.strip()                            # Supprime les espaces autour de l'URL
            if not (url.startswith('http://') or url.startswith('https://')):
                print(f"Ligne {numero_ligne} ignorée (URL invalide) : {url}")
                continue
            entrees.append((nom, url))
    return entrees


def construire_nom_fichier(nom_personnalise, url):
    """
    Construit le nom de fichier final en combinant :
    - le nom personnalisé fourni dans le fichier texte (ex: "Mon Film")
    - l'extension extraite de l'URL (ex: .mp4, .mkv, .ts)
    Résultat : "Mon Film.mp4"
    
    Si aucune extension n'est détectable dans l'URL, on utilise .mp4 par défaut.
    """
    chemin_url = urlparse(url).path              # Extrait le chemin de l'URL
    _, extension = os.path.splitext(chemin_url)  # Sépare le nom et l'extension (.mp4, .mkv...)
    extension = extension.lower()                # Normalise en minuscules
    if not extension:                            # Si pas d'extension détectée, on force .mp4
        extension = '.mp4'
    # Nettoie le nom personnalisé pour éviter les caractères interdits dans les noms de fichiers Windows
    nom_propre = re.sub(r'[\\/:*?"<>|]', '_', nom_personnalise)
    return f"{nom_propre}{extension}"
    """
    Télécharge une vidéo depuis une URL vers un dossier local.
    
    Paramètres :
    - url                  : l'adresse de la vidéo
    - dossier_destination  : dossier où enregistrer le fichier
    - nom_fichier          : nom du fichier de sortie
    - callback_progression : fonction appelée à chaque morceau téléchargé (pour la barre)
    - callback_fin         : fonction appelée à la fin (succès ou erreur)
    """
    chemin_complet = os.path.join(dossier_destination, nom_fichier)
    
    try:
        # stream=True permet de télécharger en morceaux (chunk) sans tout charger en RAM
        reponse = requests.get(url, stream=True, timeout=30)
        reponse.raise_for_status()  # Lève une erreur si le serveur répond avec un code d'erreur (404, 403, etc.)

        taille_totale = int(reponse.headers.get('content-length', 0))  # Taille totale en octets
        taille_telechargee = 0

        with open(chemin_complet, 'wb') as fichier:
            for morceau in reponse.iter_content(chunk_size=1024 * 1024):  # Morceaux de 1 Mo
                if morceau:
                    fichier.write(morceau)
                    taille_telechargee += len(morceau)
                    if taille_totale > 0:
                        pourcentage = (taille_telechargee / taille_totale) * 100
                    else:
                        pourcentage = 0
                    callback_progression(pourcentage, taille_telechargee, taille_totale)

        callback_fin(True, chemin_complet)

    except Exception as erreur:
        callback_fin(False, str(erreur))


# ==============================================================================
# INTERFACE GRAPHIQUE PRINCIPALE
# ==============================================================================

class ApplicationXtream:
    """
    Classe principale qui gère toute l'interface graphique de l'application.
    """

    def __init__(self, fenetre_principale):
        self.fenetre = fenetre_principale
        self.fenetre.title("Xtream Video Downloader")
        self.fenetre.geometry("900x700")
        self.fenetre.resizable(True, True)

        # Variables internes
        self.chemin_fichier = tk.StringVar()        # Chemin du fichier texte chargé
        self.dossier_sortie = tk.StringVar()        # Dossier de destination
        self.entrees_chargees = []                  # Liste de tuples (nom, url) lus depuis le fichier
        self.cases_cocher = []                      # Liste des variables BooleanVar (cases à cocher)
        self.en_cours = False                       # Indique si un téléchargement est en cours

        # Dossier de sortie par défaut = dossier Téléchargements de l'utilisateur
        dossier_defaut = os.path.join(os.path.expanduser("~"), "Downloads", "Xtream")
        self.dossier_sortie.set(dossier_defaut)

        self._construire_interface()

    # --------------------------------------------------------------------------
    # CONSTRUCTION DE L'INTERFACE
    # --------------------------------------------------------------------------

    def _construire_interface(self):
        """Construit tous les éléments visuels de la fenêtre."""

        # Couleurs et style
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Accent.TButton', foreground='white', background='#2563eb', font=('Helvetica', 10, 'bold'))

        # ── SECTION 1 : Chargement du fichier ──────────────────────────────────
        cadre_fichier = ttk.LabelFrame(self.fenetre, text=" 1. Fichier de liste ", padding=10)
        cadre_fichier.pack(fill='x', padx=15, pady=(15, 5))

        ttk.Entry(cadre_fichier, textvariable=self.chemin_fichier, state='readonly', width=70).pack(side='left', padx=(0, 10))
        ttk.Button(cadre_fichier, text="📂 Parcourir...", command=self._charger_fichier).pack(side='left')
        ttk.Button(cadre_fichier, text="↻ Recharger", command=self._recharger_fichier).pack(side='left', padx=(5, 0))

        # ── SECTION 2 : Dossier de destination ────────────────────────────────
        cadre_dossier = ttk.LabelFrame(self.fenetre, text=" 2. Dossier de destination ", padding=10)
        cadre_dossier.pack(fill='x', padx=15, pady=5)

        ttk.Entry(cadre_dossier, textvariable=self.dossier_sortie, width=70).pack(side='left', padx=(0, 10))
        ttk.Button(cadre_dossier, text="📂 Choisir...", command=self._choisir_dossier).pack(side='left')

        # ── SECTION 3 : Liste des vidéos ──────────────────────────────────────
        cadre_liste = ttk.LabelFrame(self.fenetre, text=" 3. Vidéos disponibles ", padding=10)
        cadre_liste.pack(fill='both', expand=True, padx=15, pady=5)

        # Boutons de sélection rapide
        cadre_boutons_selection = tk.Frame(cadre_liste)
        cadre_boutons_selection.pack(fill='x', pady=(0, 8))
        ttk.Button(cadre_boutons_selection, text="✅ Tout sélectionner", command=self._tout_selectionner).pack(side='left', padx=(0, 5))
        ttk.Button(cadre_boutons_selection, text="☐ Tout désélectionner", command=self._tout_deselectionner).pack(side='left')
        self.label_compteur = ttk.Label(cadre_boutons_selection, text="0 vidéo(s) chargée(s)")
        self.label_compteur.pack(side='right')

        # Zone scrollable pour la liste des vidéos
        cadre_scroll = tk.Frame(cadre_liste)
        cadre_scroll.pack(fill='both', expand=True)

        scrollbar_v = ttk.Scrollbar(cadre_scroll, orient='vertical')
        scrollbar_h = ttk.Scrollbar(cadre_scroll, orient='horizontal')

        self.canvas = tk.Canvas(cadre_scroll, yscrollcommand=scrollbar_v.set, xscrollcommand=scrollbar_h.set)
        scrollbar_v.config(command=self.canvas.yview)
        scrollbar_h.config(command=self.canvas.xview)

        scrollbar_v.pack(side='right', fill='y')
        scrollbar_h.pack(side='bottom', fill='x')
        self.canvas.pack(side='left', fill='both', expand=True)

        # Cadre intérieur du canvas (contiendra les cases à cocher)
        self.cadre_interieur = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.cadre_interieur, anchor='nw')
        self.cadre_interieur.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        # Molette de souris pour scroller
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # ── SECTION 4 : Progression et actions ────────────────────────────────
        cadre_bas = ttk.LabelFrame(self.fenetre, text=" 4. Téléchargement ", padding=10)
        cadre_bas.pack(fill='x', padx=15, pady=(5, 15))

        # Barre de progression globale
        self.label_progression = ttk.Label(cadre_bas, text="En attente...")
        self.label_progression.pack(anchor='w')

        self.barre_progression = ttk.Progressbar(cadre_bas, orient='horizontal', length=100, mode='determinate')
        self.barre_progression.pack(fill='x', pady=5)

        # Détail du fichier en cours
        self.label_detail = ttk.Label(cadre_bas, text="", foreground='gray')
        self.label_detail.pack(anchor='w')

        # Bouton de lancement
        self.bouton_telecharger = ttk.Button(
            cadre_bas, text="⬇  Télécharger la sélection",
            command=self._lancer_telechargements,
            style='Accent.TButton'
        )
        self.bouton_telecharger.pack(pady=(10, 0))

    # --------------------------------------------------------------------------
    # ACTIONS SUR LE FICHIER
    # --------------------------------------------------------------------------

    def _charger_fichier(self):
        """Ouvre un explorateur de fichiers pour choisir le fichier texte."""
        chemin = filedialog.askopenfilename(
            title="Sélectionner le fichier de liste",
            filetypes=[("Fichiers texte", "*.txt"), ("Tous les fichiers", "*.*")]
        )
        if chemin:
            self.chemin_fichier.set(chemin)
            self._charger_urls(chemin)

    def _recharger_fichier(self):
        """Recharge le fichier actuellement sélectionné."""
        chemin = self.chemin_fichier.get()
        if chemin:
            self._charger_urls(chemin)
        else:
            messagebox.showwarning("Attention", "Aucun fichier sélectionné.")

    def _charger_urls(self, chemin):
        """Lit le fichier et affiche la liste des vidéos dans l'interface."""
        try:
            entrees = lire_urls_depuis_fichier(chemin)
            self.entrees_chargees = entrees
            self._afficher_liste(entrees)
            self.label_compteur.config(text=f"{len(entrees)} vidéo(s) chargée(s)")
        except Exception as e:
            messagebox.showerror("Erreur de lecture", f"Impossible de lire le fichier :\n{e}")

    def _afficher_liste(self, entrees):
        """Efface et recrée la liste des cases à cocher dans l'interface."""
        # Supprime les anciens éléments
        for widget in self.cadre_interieur.winfo_children():
            widget.destroy()
        self.cases_cocher = []

        # Crée une case à cocher pour chaque entrée (nom, url)
        for i, (nom, url) in enumerate(entrees):
            var = tk.BooleanVar(value=True)   # Coché par défaut
            self.cases_cocher.append(var)

            cadre_ligne = tk.Frame(self.cadre_interieur)
            cadre_ligne.pack(fill='x', pady=1)

            nom_fichier_final = construire_nom_fichier(nom, url)

            # Case à cocher + nom personnalisé (avec extension finale)
            cb = tk.Checkbutton(cadre_ligne, variable=var, text=f" {i+1:03d}. {nom_fichier_final}", anchor='w', width=50)
            cb.pack(side='left')

            # URL en gris
            lbl_url = tk.Label(cadre_ligne, text=url, foreground='gray', font=('Courier', 8))
            lbl_url.pack(side='left', padx=(10, 0))

    # --------------------------------------------------------------------------
    # SÉLECTION
    # --------------------------------------------------------------------------

    def _tout_selectionner(self):
        for var in self.cases_cocher:
            var.set(True)

    def _tout_deselectionner(self):
        for var in self.cases_cocher:
            var.set(False)

    def _choisir_dossier(self):
        dossier = filedialog.askdirectory(title="Choisir le dossier de destination")
        if dossier:
            self.dossier_sortie.set(dossier)

    # --------------------------------------------------------------------------
    # TÉLÉCHARGEMENTS
    # --------------------------------------------------------------------------

    def _lancer_telechargements(self):
        """Prépare et lance les téléchargements dans un thread séparé."""
        if self.en_cours:
            messagebox.showinfo("En cours", "Un téléchargement est déjà en cours.")
            return

        # Récupère les entrées (nom, url) sélectionnées
        entrees_selectionnees = [
            entree for entree, var in zip(self.entrees_chargees, self.cases_cocher)
            if var.get()
        ]

        if not entrees_selectionnees:
            messagebox.showwarning("Attention", "Aucune vidéo sélectionnée.")
            return

        dossier = self.dossier_sortie.get()
        if not dossier:
            messagebox.showwarning("Attention", "Veuillez choisir un dossier de destination.")
            return

        # Crée le dossier s'il n'existe pas
        os.makedirs(dossier, exist_ok=True)

        # Lance les téléchargements dans un thread séparé pour ne pas bloquer l'interface
        self.en_cours = True
        self.bouton_telecharger.config(state='disabled')
        thread = threading.Thread(target=self._traiter_telechargements, args=(entrees_selectionnees, dossier), daemon=True)
        thread.start()

    def _traiter_telechargements(self, entrees, dossier):
        """
        Boucle principale de téléchargement (s'exécute dans un thread séparé).
        Traite les vidéos une par une.
        """
        total = len(entrees)
        resultats = []

        for index, (nom, url) in enumerate(entrees):
            # Construit le nom de fichier final : nom personnalisé + extension de l'URL
            nom_fichier = construire_nom_fichier(nom, url)

            # Mise à jour de l'interface (depuis le thread secondaire)
            self.fenetre.after(0, self._maj_label_progression,
                               f"Téléchargement {index+1}/{total} : {nom_fichier}")
            self.fenetre.after(0, self.barre_progression.config, {'value': 0})

            # Lancement du téléchargement
            succes = [None]
            message = [None]

            def cb_progression(pct, telecharg, total_octets):
                mb_dl = telecharg / (1024*1024)
                mb_total = total_octets / (1024*1024) if total_octets else 0
                detail = f"{mb_dl:.1f} Mo / {mb_total:.1f} Mo" if mb_total else f"{mb_dl:.1f} Mo"
                self.fenetre.after(0, self._maj_barre, pct, detail)

            def cb_fin(ok, msg):
                succes[0] = ok
                message[0] = msg

            telecharger_video(url, dossier, nom_fichier, cb_progression, cb_fin)
            resultats.append((nom_fichier, succes[0], message[0]))

        # Fin de tous les téléchargements
        self.fenetre.after(0, self._finaliser, resultats)

    def _maj_label_progression(self, texte):
        self.label_progression.config(text=texte)

    def _maj_barre(self, valeur, detail):
        self.barre_progression.config(value=valeur)
        self.label_detail.config(text=detail)

    def _finaliser(self, resultats):
        """Affiche le bilan des téléchargements et réactive l'interface."""
        self.en_cours = False
        self.bouton_telecharger.config(state='normal')
        self.barre_progression.config(value=100)

        succes = [r for r in resultats if r[1]]
        echecs = [r for r in resultats if not r[1]]

        bilan = f"Téléchargements terminés !\n\n✅ Succès : {len(succes)}\n❌ Échecs : {len(echecs)}"
        if echecs:
            bilan += "\n\nFichiers en erreur :"
            for nom, _, msg in echecs:
                bilan += f"\n  • {nom} : {msg}"

        self.label_progression.config(text="Terminé.")
        messagebox.showinfo("Bilan", bilan)


# ==============================================================================
# POINT D'ENTRÉE
# ==============================================================================

if __name__ == "__main__":
    fenetre = tk.Tk()
    app = ApplicationXtream(fenetre)
    fenetre.mainloop()
