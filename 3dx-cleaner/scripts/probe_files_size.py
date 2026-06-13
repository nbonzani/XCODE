"""Probe live : capture le contrat REST de taille de fichier (jalon 3, étape 1).

Authentifie via le profil keyring enregistré, cherche des Documents, et appelle
``GET /resources/v1/modeler/documents/{physical_id}/files`` sur chacun jusqu'à
trouver un Document AVEC fichier physique attaché (``data[]`` non vide). Imprime
alors le JSON brut de la réponse pour identifier la clé exacte de la taille dans
``data[].dataelements``.

Usage (réseau Polytech requis) :
    .venv/Scripts/python.exe scripts/probe_files_size.py
    .venv/Scripts/python.exe scripts/probe_files_size.py 56A5898500000BFC6A2BABEF00000755 ...
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from threedx_mcp.client.endpoints import search  # noqa: E402
from threedx_mcp.client.session import ThreeDxClient  # noqa: E402

from threedx_cleaner.core.connection import who_am_i  # noqa: E402
from threedx_cleaner.credentials import profile_store, secret_store  # noqa: E402
from threedx_cleaner.credentials.settings_builder import build_settings  # noqa: E402

PROFILE_NAME = "UL on premise 2026X"
MAX_PROBE = 120  # nb max de Documents sondés avant d'abandonner


def _tenant(client: ThreeDxClient) -> str:
    return (
        getattr(client.settings, "platform_id", "")
        or getattr(client.settings, "tenant", "OnPremise")
        or "OnPremise"
    )


def _get_files(client: ThreeDxClient, pid: str) -> dict:
    url = (
        client.settings.space_url
        + f"/resources/v1/modeler/documents/{pid}/files"
    )
    return client.request("GET", url, params={"tenant": _tenant(client)})


def main() -> int:
    profile = profile_store.get(PROFILE_NAME)
    if profile is None:
        print(f"[ERREUR] Profil introuvable : {PROFILE_NAME!r}", file=sys.stderr)
        return 2
    password = secret_store.get_password(PROFILE_NAME)
    if not password:
        print("[ERREUR] Aucun mot de passe keyring pour ce profil.", file=sys.stderr)
        return 2

    settings = build_settings(profile, password)
    client = ThreeDxClient(settings)

    who = who_am_i(settings)
    print(who.one_line())
    print(f"space_url = {settings.space_url}")
    print(f"security_context = {settings.security_context!r}")
    print("-" * 70)

    # IDs explicites en argv, sinon recherche de Documents.
    explicit_ids = sys.argv[1:]
    if explicit_ids:
        candidates = [(pid, "(argv)", "(argv)") for pid in explicit_ids]
    else:
        print("Recherche de Documents (type=Document)…")
        res = search.search_advanced(
            client, query="*", types=["Document"], limit=MAX_PROBE, start=0
        )
        candidates = [
            (getattr(h, "physical_id", None), getattr(h, "title", None), getattr(h, "identifier", None))
            for h in res.hits
            if getattr(h, "physical_id", None)
        ]
        print(f"  {len(candidates)} Documents à sonder (nmatches serveur={res.nmatches}).")
    print("-" * 70)

    probed = 0
    empties = 0
    for pid, title, ident in candidates:
        probed += 1
        try:
            payload = _get_files(client, pid)
        except Exception as exc:  # noqa: BLE001 — on continue au suivant
            print(f"  [skip] {pid} : {type(exc).__name__}: {exc}")
            continue
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list) and data:
            print("\n" + "=" * 70)
            print(f"FICHIER TROUVÉ sur Document {pid}")
            print(f"  title={title!r} identifier={ident!r}")
            print("=" * 70)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            print("=" * 70)
            first = data[0]
            if isinstance(first, dict):
                de = first.get("dataelements")
                if isinstance(de, dict):
                    print("\nCLÉS data[0].dataelements :")
                    for k, v in de.items():
                        print(f"  {k!r:30} = {v!r}")
            # Dump brut pour archive d'analyse.
            out = Path(__file__).resolve().parent.parent / "docs" / "captures" / "size-files"
            out.mkdir(parents=True, exist_ok=True)
            (out / f"files-response-{pid}.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"\n[OK] Réponse brute écrite dans {out / ('files-response-' + pid + '.json')}")
            return 0
        else:
            empties += 1

    print(f"\n[VIDE] {probed} Documents sondés, {empties} sans fichier (data[]=[]).")
    print("Aucun Document avec fichier physique trouvé dans cet échantillon.")
    print("→ Fournis un physical_id connu (avec fichier) en argument, ou élargis la recherche.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
