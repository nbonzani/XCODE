"""Orchestration — appelle la couche endpoints de ``threedx_mcp``.

Modules par jalon :
- ``connection``       : test de connexion / who_am_i + probe contextes (jalon 0-1).
- ``document_query``   : F3 recherche filtree + pagination (jalon 2).
- ``collabspace_query``: F3 listing des collabspaces pour le filtre (jalon 2).
- ``size_resolver``    : F3 architecture taille (stub tant que contrat non capture).
- ``normalize``    : F4 unreserve + demote In Work (jalon 3).
- ``preflight``    : F5 checkDeleteAccess, locks, where-used (jalon 3).
- ``executor``     : batch + progression + agregation d'erreurs (jalon 3).
- ``report``       : F6 rapport post-vol (jalon 3).
- ``space_purge``  : F1 (jalon 4).
- ``owner_purge``  : F2 (jalon 4).
"""

from __future__ import annotations
