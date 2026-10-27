"""Workflows de test exécutés dans un vrai n8n : les nœuds « Code » des workflows livrés tournent
avec des données d'entrée fictives, à la place des déclencheurs et des appels à l'IA.

Usage : python tests/build_test_workflows.py   → tests/workflows/*.json (puis `n8n execute`)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "workflows"


def load(name):
    return json.loads((ROOT / "workflows" / name).read_text())


def fake(name, pos, items):
    return {"id": name, "name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos,
            "parameters": {"jsCode": f"return {json.dumps(items, ensure_ascii=False)};"}}


def build(src_file, test_name, keep, fakes, chain):
    wf = load(src_file)
    nodes = [n for n in wf["nodes"] if n["name"] in keep]
    nodes.append({"id": "start", "name": "Start", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1,
                  "position": [-200, 0], "parameters": {}})
    nodes += [fake(n, [0, 0], items) for n, items in fakes.items()]
    conns = {}
    for a, b in zip(["Start"] + chain[:-1], chain):
        conns.setdefault(a, {"main": [[]]})["main"][0].append({"node": b, "type": "main", "index": 0})
    OUT.mkdir(parents=True, exist_ok=True)
    out = {"name": test_name, "nodes": nodes, "connections": conns, "settings": {"executionOrder": "v1"},
           "active": False, "pinData": {}}
    (OUT / f"{test_name}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))


PAGE = {"total_count": 3, "results": [
    {"idweb": "26-101", "objet": "Maintenance des bornes de recharge IRVE", "nomacheteur": "Ville de Lyon",
     "code_departement": ["69"], "descripteur_libelle": ["Électricité"], "nature_libelle": "Avis de marché",
     "url_avis": "https://www.boamp.fr/avis/26-101", "datelimitereponse": "2026-11-28"},
    {"idweb": "26-102", "objet": "Restauration scolaire", "code_departement": ["69"], "nature_libelle": "Avis de marché"},
    {"idweb": "26-103", "objet": "Supervision de la recharge électrique", "nomacheteur": "Métropole de Paris",
     "code_departement": ["75"], "nature_libelle": "Avis de marché"}]}

INVOICE = {"fournisseur": "Datalys Conseil", "siren": "552081317", "numero_facture": "DC-12",
           "date_facture": "2026-10-01", "date_echeance": "2026-10-31", "montant_ht": 1000, "montant_tva": 200,
           "montant_ttc": 1200, "iban": "FR7630006000011234567890189"}

if __name__ == "__main__":
    build("03_veille_appels_offres.json", "test_veille", {"Préfiltrage", "Synthèse"},
          {"Paramètres": [{"json": {"mots_cles": "recharge, IRVE", "departements": "69, 75", "score_minimum": 60, "max_avis": 10}}],
           "Avis BOAMP de la veille": [{"json": PAGE}],
           "Notation IA": [{"json": {"output": {"score": 88, "raison": "cœur de métier à Lyon"}}},
                           {"json": {"output": {"score": 40, "raison": "zone hors cible"}}}]},
          ["Paramètres", "Avis BOAMP de la veille", "Préfiltrage", "Notation IA", "Synthèse"])
    build("02_factures_controlees.json", "test_factures", {"Contrôles"},
          {"Une facture par élément": [{"json": {"from": "compta@datalys.fr", "subject": "Facture", "fileName": "DC-12.pdf"}}],
           "Extraction IA": [{"json": {"output": INVOICE}}],
           "Lire l'historique": [{"json": {"fournisseur": "Datalys Conseil", "siren": "552081317",
                                          "numero_facture": "DC-11", "iban": "FR1420041010050500013M02606"}}]},
          ["Une facture par élément", "Extraction IA", "Lire l'historique", "Contrôles"])
    print("workflows de test écrits dans", OUT, file=sys.stderr)
