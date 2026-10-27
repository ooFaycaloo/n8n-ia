"""Assemble les 3 workflows n8n (JSON importable) à partir de leur définition et du code JS testé dans src/.

Le code des nœuds « Code » est copié tel quel depuis src/ : ce qui est testé (tests/logic.test.js)
est exactement ce qui tourne dans n8n.

Usage : python build_workflows.py   → workflows/*.json
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC, OUT = ROOT / "src", ROOT / "workflows"
MODEL = "claude-haiku-5-5"


def uid(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


class WF:
    def __init__(self, name: str, tags: list[str]):
        self.name, self.tags = name, tags
        self.nodes: list[dict] = []
        self.connections: dict = {}

    def node(self, name, type_, version, pos, params, **extra):
        self.nodes.append({"id": uid(self.name + name), "name": name, "type": type_, "typeVersion": version,
                           "position": list(pos), "parameters": params, **extra})
        return name

    def link(self, src, dst, out_index=0, kind="main"):
        outs = self.connections.setdefault(src, {}).setdefault(kind, [])
        while len(outs) <= out_index:
            outs.append([])
        outs[out_index].append({"node": dst, "type": kind, "index": 0})

    def note(self, name, pos, text, width=420, height=300, color=7):
        self.node(name, "n8n-nodes-base.stickyNote", 1, pos,
                  {"content": text, "width": width, "height": height, "color": color})

    def claude(self, name, pos, target, max_tokens=1024):
        self.node(name, "@n8n/n8n-nodes-langchain.lmChatAnthropic", 1.6, pos, {
            "model": {"__rl": True, "mode": "id", "value": MODEL},
            "options": {"maxTokensToSample": max_tokens, "temperature": 0}})
        self.link(name, target, kind="ai_languageModel")

    def code(self, name, pos, src_file, call):
        js = (SRC / src_file).read_text(encoding="utf-8")
        self.node(name, "n8n-nodes-base.code", 2, pos, {"jsCode": f"{js}\n\n{call}\n"})

    def settings(self, name, pos, values: dict):
        self.node(name, "n8n-nodes-base.set", 3.4, pos, {
            "assignments": {"assignments": [
                {"id": uid(name + k), "name": k, "value": v, "type": "number" if isinstance(v, (int, float)) else "string"}
                for k, v in values.items()]},
            "includeOtherFields": True, "options": {}})

    def save(self, filename):
        wf = {"name": self.name, "nodes": self.nodes, "connections": self.connections, "active": False,
              "settings": {"executionOrder": "v1", "timezone": "Europe/Paris"}, "pinData": {},
              "tags": [{"name": t} for t in self.tags]}
        OUT.mkdir(exist_ok=True)
        (OUT / filename).write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
        return wf


def sheet(doc_label: str, tab: str) -> tuple[dict, dict]:
    return ({"__rl": True, "mode": "url", "value": ""},
            {"__rl": True, "mode": "name", "value": tab})


def if_not_equal(left: str, right: str) -> dict:
    return {"conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
        "conditions": [{"id": uid(left + right), "leftValue": left, "rightValue": right,
                        "operator": {"type": "string", "operation": "notEquals"}}],
        "combinator": "and"}, "options": {}}


# ====================================================================== 1. tri des emails

def emails():
    w = WF("Tri des emails clients et brouillons de réponse", ["IA", "email"])
    w.note("Mode d'emploi", (-60, -520), (
        "## Tri des emails clients\n"
        "Chaque nouvel email non lu est classé par Claude, étiqueté dans Gmail. Les réclamations et "
        "demandes de support reçoivent un **brouillon** de réponse : rien n'est envoyé sans relecture.\n\n"
        "**À configurer**\n1. Identifiants Gmail (OAuth2) et Anthropic.\n"
        "2. Nœud *Paramètres* : nom de l'entreprise, ton, signature.\n"
        "3. Dans chaque nœud *Étiquette*, choisir le libellé Gmail.\n"
        "4. Nœud *Alerte Slack* : canal des réclamations.\n\n"
        "Coût indicatif : moins de 0,50 € pour 1 000 emails (Claude Haiku 5.5)."), width=480, height=360)
    w.node("Nouvel email", "n8n-nodes-base.gmailTrigger", 1.3, (0, 0), {
        "pollTimes": {"item": [{"mode": "everyMinute"}]}, "simple": False,
        "filters": {"readStatus": "unread", "q": "-category:promotions -category:social -from:me"}, "options": {}})
    w.settings("Paramètres", (220, 0), {
        "entreprise": "Corvelle Énergies", "ton": "cordial, précis, vouvoiement",
        "signature": "Le service client de Corvelle Énergies",
        "regles_reponse": "Ne jamais promettre de remboursement, de délai ni de geste commercial : proposer un rappel par un conseiller."})
    cats = [("Devis ou commande", "Demande de prix, de devis, de disponibilité ou passage de commande"),
            ("Réclamation", "Mécontentement, litige, produit défectueux, retard, demande de remboursement"),
            ("Facture ou comptabilité", "Facture, relance de paiement, avoir, question comptable"),
            ("Support technique", "Problème d'utilisation, panne, question technique sur un produit ou service"),
            ("Prospection ou spam", "Démarchage commercial, newsletter, message automatique, spam")]
    w.node("Classer l'email", "@n8n/n8n-nodes-langchain.textClassifier", 1.1, (460, 0), {
        "inputText": "=Objet : {{ $json.subject }}\nDe : {{ $json.from.text }}\n\n{{ ($json.text || '').slice(0, 4000) }}",
        "categories": {"categories": [{"category": c, "description": d} for c, d in cats]},
        "options": {"fallback": "other", "systemPromptTemplate":
                    "Classe l'email d'un client dans l'une des catégories suivantes : {categories}. "
                    "Suis les instructions de format ci-dessous. N'explique pas, réponds uniquement en JSON."}})
    w.link("Nouvel email", "Paramètres")
    w.link("Paramètres", "Classer l'email")
    w.claude("Claude (classement)", (460, 220), "Classer l'email", 256)

    y = -480
    for i, (cat, _) in enumerate(cats + [("Autre", "")]):
        name = f"Étiquette {cat.lower()}"
        w.node(name, "n8n-nodes-base.gmail", 2.2, (820, y + i * 190), {
            "operation": "addLabels", "messageId": "={{ $('Nouvel email').item.json.id }}", "labelIds": []})
        w.link("Classer l'email", name, out_index=i)

    w.node("Rédiger le brouillon", "@n8n/n8n-nodes-langchain.chainLlm", 1.7, (1160, -100), {
        "promptType": "define",
        "text": "=Email reçu\n"
                "Objet : {{ $('Nouvel email').item.json.subject }}\nDe : {{ $('Nouvel email').item.json.from.text }}\n\n"
                "{{ ($('Nouvel email').item.json.text || '').slice(0, 6000) }}",
        "messages": {"messageValues": [{"type": "SystemMessagePromptTemplate", "message":
            "=Tu rédiges des brouillons de réponse pour {{ $('Paramètres').item.json.entreprise }}, "
            "relus par un humain avant envoi. Ton : {{ $('Paramètres').item.json.ton }}. "
            "Réponds dans la langue du client, en 120 mots maximum, sans objet ni formule d'en-tête inventée. "
            "{{ $('Paramètres').item.json.regles_reponse }} Si une information manque pour répondre, "
            "pose une seule question précise. Termine par la signature : {{ $('Paramètres').item.json.signature }}"}]},
        "batching": {}})
    w.link("Étiquette réclamation", "Rédiger le brouillon")
    w.link("Étiquette support technique", "Rédiger le brouillon")
    w.claude("Claude (brouillon)", (1160, 120), "Rédiger le brouillon", 600)
    w.node("Créer le brouillon Gmail", "n8n-nodes-base.gmail", 2.2, (1460, -100), {
        "resource": "draft", "subject": "=Re: {{ $('Nouvel email').item.json.subject }}", "emailType": "text",
        "message": "={{ $json.text }}",
        "options": {"threadId": "={{ $('Nouvel email').item.json.threadId }}",
                    "sendTo": "={{ $('Nouvel email').item.json.from.value[0].address }}"}})
    w.link("Rédiger le brouillon", "Créer le brouillon Gmail")
    w.node("Alerte Slack réclamation", "n8n-nodes-base.slack", 2.3, (1160, -340), {
        "select": "channel", "channelId": {"__rl": True, "mode": "name", "value": "#service-client"},
        "text": "=:rotating_light: Réclamation de {{ $('Nouvel email').item.json.from.text }} : "
                "« {{ $('Nouvel email').item.json.subject }} ». Brouillon de réponse prêt dans Gmail.",
        "otherOptions": {}})
    w.link("Étiquette réclamation", "Alerte Slack réclamation")
    return w.save("01_tri_emails.json")


# ====================================================================== 2. factures

INVOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "fournisseur": {"type": "string", "description": "Raison sociale du vendeur (émetteur de la facture)"},
        "siren": {"type": "string", "description": "SIREN du vendeur : 9 chiffres, ou les 9 premiers chiffres du SIRET"},
        "numero_facture": {"type": "string"},
        "date_facture": {"type": "string", "description": "Date d'émission au format AAAA-MM-JJ"},
        "date_echeance": {"type": "string", "description": "Date d'échéance au format AAAA-MM-JJ, vide si absente"},
        "montant_ht": {"type": "number"},
        "montant_tva": {"type": "number"},
        "montant_ttc": {"type": "number"},
        "iban": {"type": "string", "description": "IBAN du vendeur pour le paiement, vide si absent"},
    },
    "required": ["fournisseur", "numero_facture", "date_facture", "montant_ttc"],
}


def invoices():
    w = WF("Factures fournisseurs reçues par email, contrôlées", ["IA", "comptabilité"])
    w.note("Mode d'emploi", (-60, -440), (
        "## Factures fournisseurs contrôlées\n"
        "Chaque PDF reçu par email est lu par Claude, contrôlé (SIREN, IBAN, totaux, délai légal de 60 jours, "
        "doublon, **changement d'IBAN par rapport à l'historique**) puis ajouté au tableau de suivi. "
        "Les factures suspectes sont signalées à la comptabilité.\n\n"
        "**À configurer**\n1. Identifiants Gmail, Google Sheets et Anthropic.\n"
        "2. Créer un Google Sheet avec un onglet *Factures* (la première ligne d'en-têtes est créée automatiquement).\n"
        "3. Coller son URL dans les deux nœuds Google Sheets.\n4. Nœud *Paramètres* : adresse de la comptabilité.\n\n"
        "Aucun paiement n'est déclenché : le workflow signale, la comptabilité décide."), width=500, height=380)
    w.node("Email avec facture", "n8n-nodes-base.gmailTrigger", 1.3, (0, 0), {
        "pollTimes": {"item": [{"mode": "everyX", "value": 10, "unit": "minutes"}]}, "simple": False,
        "filters": {"readStatus": "unread", "q": "has:attachment filename:pdf (facture OR invoice)"},
        "options": {"downloadAttachments": True}})
    w.settings("Paramètres", (220, 0), {"email_comptabilite": "comptabilite@exemple.fr"})
    w.code("Une facture par élément", (440, 0), "split_attachments.js", "return main($input.all());")
    w.node("Lire le PDF", "n8n-nodes-base.extractFromFile", 1.1, (660, 0),
           {"operation": "pdf", "binaryPropertyName": "data", "options": {}})
    w.node("Extraction IA", "@n8n/n8n-nodes-langchain.informationExtractor", 1.2, (880, 0), {
        "text": "={{ $json.text.slice(0, 15000) }}", "schemaType": "manual",
        "inputSchema": json.dumps(INVOICE_SCHEMA, ensure_ascii=False, indent=2),
        "options": {"systemPromptTemplate":
                    "Tu extrais les champs d'une facture française. Recopie exactement ce qui est écrit, "
                    "n'invente rien et laisse vide un champ absent. Les montants sont des nombres (point décimal)."}})
    w.claude("Claude (extraction)", (880, 220), "Extraction IA", 800)
    doc, tab = sheet("URL du Google Sheet de suivi", "Factures")
    w.node("Lire l'historique", "n8n-nodes-base.googleSheets", 4.7, (1160, 0),
           {"operation": "read", "documentId": doc, "sheetName": tab, "options": {}},
           executeOnce=True, alwaysOutputData=True)
    w.code("Contrôles", (1380, 0), "invoice_checks.js",
           "return main($('Extraction IA').all(), {\n"
           "  history: $('Lire l\\'historique').all().filter(i => i.json && i.json.numero_facture),\n"
           "  mails: $('Une facture par élément').all(),\n});")
    w.node("Ajouter au suivi", "n8n-nodes-base.googleSheets", 4.7, (1600, -100), {
        "operation": "append", "documentId": doc, "sheetName": tab,
        "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": []},
        "options": {}})
    w.node("Anomalie ?", "n8n-nodes-base.if", 2.2, (1600, 120), if_not_equal("={{ $json.statut }}", "OK"))
    w.node("Alerter la comptabilité", "n8n-nodes-base.gmail", 2.2, (1820, 100), {
        "sendTo": "={{ $('Paramètres').first().json.email_comptabilite }}",
        "subject": "={{ $json.statut }} : facture {{ $json.numero_facture }} de {{ $json.fournisseur }}",
        "message": "=<p>La facture <b>{{ $json.numero_facture }}</b> de <b>{{ $json.fournisseur }}</b> "
                   "({{ $json.montant_ttc }} € TTC) nécessite une vérification :</p>"
                   "<p>{{ $json.anomalies.split(' | ').join('<br>') }}</p>"
                   "<p>Fichier : {{ $json.fichier }} · reçu de {{ $json.expediteur }}</p>",
        "options": {"appendAttribution": False}})
    for a, b in [("Email avec facture", "Paramètres"), ("Paramètres", "Une facture par élément"),
                 ("Une facture par élément", "Lire le PDF"), ("Lire le PDF", "Extraction IA"),
                 ("Extraction IA", "Lire l'historique"), ("Lire l'historique", "Contrôles"),
                 ("Contrôles", "Ajouter au suivi"), ("Contrôles", "Anomalie ?")]:
        w.link(a, b)
    w.link("Anomalie ?", "Alerter la comptabilité", out_index=0)
    return w.save("02_factures_controlees.json")


# ====================================================================== 3. veille BOAMP

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "description": "Pertinence de 0 à 100 pour l'entreprise"},
        "raison": {"type": "string", "description": "Justification en 25 mots maximum"},
        "type_prestation": {"type": "string", "description": "Nature de la prestation demandée, en quelques mots"},
    },
    "required": ["score", "raison"],
}


def tenders():
    w = WF("Veille appels d'offres BOAMP qualifiée par IA", ["IA", "commercial"])
    w.note("Mode d'emploi", (-60, -440), (
        "## Veille appels d'offres\n"
        "Chaque matin de semaine, les avis publiés la veille au BOAMP (API ouverte, sans clé) sont filtrés "
        "par mots-clés et départements, notés par Claude selon le profil de l'entreprise, enregistrés dans "
        "Google Sheets et envoyés par email.\n\n"
        "**À configurer**\n1. Identifiants Gmail, Google Sheets et Anthropic.\n"
        "2. Nœud *Paramètres* : profil de l'entreprise, mots-clés, départements, seuil, destinataires.\n"
        "3. Google Sheet avec un onglet *Appels d'offres* (colonne *idweb* pour le dédoublonnage).\n\n"
        "Le plafond *max_avis* limite le nombre d'avis envoyés à l'IA chaque jour, donc le coût."),
        width=500, height=380)
    w.node("Chaque matin", "n8n-nodes-base.scheduleTrigger", 1.2, (0, 0),
           {"rule": {"interval": [{"field": "cronExpression", "expression": "0 30 7 * * 1-5"}]}})
    w.settings("Paramètres", (220, 0), {
        "profil_entreprise": "Bureau d'études de 25 personnes à Lyon spécialisé en infrastructures de recharge "
                             "pour véhicules électriques : études, installation, supervision et maintenance. "
                             "Marchés visés : 20 000 à 500 000 €, Auvergne-Rhône-Alpes et Île-de-France.",
        "mots_cles": "borne, recharge, IRVE, véhicule électrique, mobilité électrique, supervision, éclairage public",
        "departements": "69, 01, 38, 42, 73, 74, 75, 92, 93, 94",
        "score_minimum": 60, "max_avis": 40, "destinataires": "commercial@exemple.fr"})
    w.node("Avis BOAMP de la veille", "n8n-nodes-base.httpRequest", 4.2, (440, 0), {
        "url": "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/records",
        "sendQuery": True, "specifyQuery": "keypair",
        "queryParameters": {"parameters": [
            {"name": "where", "value": "=dateparution >= date'{{ $now.minus({ days: $now.weekday === 1 ? 3 : 1 }).toFormat('yyyy-MM-dd') }}'"},
            {"name": "order_by", "value": "idweb"},
            {"name": "limit", "value": "100"}]},
        "options": {"pagination": {"pagination": {
            "paginationMode": "updateAParameterInEachRequest",
            "parameters": {"parameters": [{"type": "qs", "name": "offset", "value": "={{ $pageCount * 100 }}"}]},
            "paginationCompleteWhen": "other",
            "completeExpression": "={{ $response.body.results.length < 100 }}",
            "limitPagesFetched": True, "maxRequests": 20}}}})
    w.code("Préfiltrage", (660, 0), "boamp_prefilter.js",
           "return main($input.all(), { params: $('Paramètres').first().json });")
    w.node("Notation IA", "@n8n/n8n-nodes-langchain.informationExtractor", 1.2, (880, 0), {
        "text": "=Avis : {{ $json.objet }}\nAcheteur : {{ $json.acheteur }}\nDépartements : {{ $json.departements }}\n"
                "Descripteurs : {{ $json.descripteurs }}\nType de marché : {{ $json.type_marche }}\n"
                "Date limite : {{ $json.date_limite }}",
        "schemaType": "manual", "inputSchema": json.dumps(SCORE_SCHEMA, ensure_ascii=False, indent=2),
        "options": {"systemPromptTemplate":
                    "=Tu qualifies des appels d'offres publics pour l'entreprise suivante : "
                    "{{ $('Paramètres').first().json.profil_entreprise }}\n"
                    "Note la pertinence de 0 (hors sujet) à 100 (cœur de métier, zone et taille adaptées). "
                    "Sois sévère : un avis seulement voisin du métier ne dépasse pas 50.",
                    "batching": {"batchSize": 5, "delayBetweenBatches": 0}}})
    w.claude("Claude (notation)", (880, 220), "Notation IA", 300)
    w.code("Synthèse", (1160, 0), "boamp_digest.js",
           "return main($input.all(), { notices: $('Préfiltrage').all(), params: $('Paramètres').first().json });")
    w.node("Envoyer la synthèse", "n8n-nodes-base.gmail", 2.2, (1400, -100), {
        "sendTo": "={{ $('Paramètres').first().json.destinataires }}", "subject": "={{ $json.subject }}",
        "message": "={{ $json.html }}", "options": {"appendAttribution": False}})
    w.node("Un avis par ligne", "n8n-nodes-base.splitOut", 1, (1400, 120),
           {"fieldToSplitOut": "rows", "include": "noOtherFields", "options": {}})
    doc, tab = sheet("URL du Google Sheet de veille", "Appels d'offres")
    w.node("Enregistrer les avis", "n8n-nodes-base.googleSheets", 4.7, (1620, 120), {
        "operation": "appendOrUpdate", "documentId": doc, "sheetName": tab,
        "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": ["idweb"], "schema": []},
        "options": {}})
    for a, b in [("Chaque matin", "Paramètres"), ("Paramètres", "Avis BOAMP de la veille"),
                 ("Avis BOAMP de la veille", "Préfiltrage"), ("Préfiltrage", "Notation IA"),
                 ("Notation IA", "Synthèse"), ("Synthèse", "Envoyer la synthèse"),
                 ("Synthèse", "Un avis par ligne"), ("Un avis par ligne", "Enregistrer les avis")]:
        w.link(a, b)
    return w.save("03_veille_appels_offres.json")


if __name__ == "__main__":
    for wf in (emails(), invoices(), tenders()):
        print(f"{wf['name']} : {len(wf['nodes'])} nœuds")
