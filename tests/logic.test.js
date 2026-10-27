// Tests de la logique des nœuds Code (exactement le code embarqué dans les workflows).
// Lancement : node --test tests/
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function load(name) {
  const ctx = {};
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'src', name), 'utf8'), ctx);
  // les objets créés dans le contexte isolé sont recopiés pour être comparables avec deepEqual
  return { main: (items, c) => JSON.parse(JSON.stringify(ctx.main(items, c))) };
}

// ------------------------------------------------------------------ BOAMP
const page = { json: { total_count: 5, results: [
  { idweb: '26-1', objet: 'Maintenance des bornes de recharge pour véhicules électriques', nomacheteur: 'Ville de Lyon',
    code_departement: ['69'], descripteur_libelle: ['Électricité'], nature_libelle: 'Avis de marché',
    url_avis: 'https://www.boamp.fr/x/26-1', datelimitereponse: '2026-11-20' },
  { idweb: '26-2', objet: 'Fourniture de repas scolaires', nomacheteur: 'Commune A', code_departement: ['69'],
    descripteur_libelle: ['Restauration'], nature_libelle: 'Avis de marché' },
  { idweb: '26-3', objet: 'Supervision et data des infrastructures de recharge', nomacheteur: 'Métropole B',
    code_departement: ['13'], nature_libelle: 'Avis de marché' },
  { idweb: '26-4', objet: 'Bornes de recharge - attribution', code_departement: ['69'], nature_libelle: "Avis d'attribution" },
  { idweb: '26-1', objet: 'doublon', code_departement: ['69'], nature_libelle: 'Avis de marché' },
] } };

test('préfiltrage BOAMP : mots-clés, départements, nature, doublons', () => {
  const { main } = load('boamp_prefilter.js');
  const out = main([page], { params: { mots_cles: 'recharge, borne, supervision', departements: '69, 75', max_avis: 10 } });
  assert.deepEqual(out.map(o => o.json.idweb), ['26-1']);
  assert.match(out[0].json.mots_cles_trouves, /recharge/);
});

test('préfiltrage BOAMP : sans filtre de département et plafond respecté', () => {
  const { main } = load('boamp_prefilter.js');
  const all = main([page], { params: { mots_cles: 'recharge', departements: '', max_avis: 1 } });
  assert.equal(all.length, 1);
  const noCap = main([page], { params: { mots_cles: 'recharge', departements: '' } });
  assert.deepEqual(noCap.map(o => o.json.idweb).sort(), ['26-1', '26-3']);
});

test('synthèse BOAMP : fusion par position, seuil, tri et échappement HTML', () => {
  const { main } = load('boamp_digest.js');
  const notices = [{ json: { idweb: 'a', objet: 'Bornes <IRVE>', acheteur: 'X', url: 'u' } },
                   { json: { idweb: 'b', objet: 'Repas', acheteur: 'Y', url: 'u' } },
                   { json: { idweb: 'c', objet: 'Supervision', acheteur: 'Z', url: 'u' } }];
  const scored = [{ json: { output: { score: 72, raison: 'cœur de métier' } } },
                  { json: { output: { score: 10, raison: 'hors sujet' } } },
                  { json: { output: { score: 91, raison: 'très pertinent' } } }];
  const [d] = main(scored, { notices, params: { score_minimum: 60 } });
  assert.equal(d.json.count, 2);
  assert.deepEqual(d.json.rows.map(r => r.idweb), ['c', 'a']);
  assert.ok(d.json.html.includes('Bornes &lt;IRVE&gt;'));
  assert.match(d.json.subject, /2 avis pertinent/);
});

// ------------------------------------------------------------------ factures
const goodInvoice = { fournisseur: 'Datalys Conseil', siren: '552 081 317', numero_facture: 'DC-12',
  date_facture: '2026-10-01', date_echeance: '2026-10-31', montant_ht: '1 000,00', montant_tva: '200,00',
  montant_ttc: '1 200,00', iban: 'FR76 3000 6000 0112 3456 7890 189' };

test('facture conforme', () => {
  const { main } = load('invoice_checks.js');
  const [r] = main([{ json: { output: goodInvoice } }], { history: [] });
  assert.equal(r.json.statut, 'OK');
  assert.equal(r.json.montant_ttc, 1200);
  assert.equal(r.json.iban, 'FR7630006000011234567890189');
});

test('facture : totaux, SIREN, IBAN et délai', () => {
  const { main } = load('invoice_checks.js');
  const bad = { ...goodInvoice, siren: '552081318', montant_ttc: '1 300,00', iban: 'FR7630006000011234567890188',
                date_echeance: '2027-01-15' };
  const [r] = main([{ json: { output: bad } }], { history: [] });
  assert.equal(r.json.statut, 'À BLOQUER');
  for (const s of ['HT + TVA', 'SIREN invalide', 'IBAN invalide', 'Délai de paiement']) assert.ok(r.json.anomalies.includes(s), s);
});

test("facture : changement d'IBAN et doublon par rapport à l'historique", () => {
  const { main } = load('invoice_checks.js');
  const history = [{ json: { fournisseur: 'Datalys Conseil', siren: '552081317', numero_facture: 'DC-11',
                             iban: 'FR1420041010050500013M02606' } }];
  const [r] = main([{ json: { output: goodInvoice } }], { history });
  assert.equal(r.json.statut, 'À BLOQUER');
  assert.match(r.json.anomalies, /IBAN différent/);
  const [dup] = main([{ json: { output: { ...goodInvoice, numero_facture: 'DC-11', iban: 'FR1420041010050500013M02606' } } }], { history });
  assert.match(dup.json.anomalies, /Doublon/);
});

test('facture : deux pièces jointes identiques dans le même courriel', () => {
  const { main } = load('invoice_checks.js');
  const out = main([{ json: { output: goodInvoice } }, { json: { output: goodInvoice } }], { history: [] });
  assert.equal(out[0].json.statut, 'OK');
  assert.match(out[1].json.anomalies, /Doublon/);
});

test('pièces jointes : seuls les PDF sont gardés, un élément par fichier', () => {
  const { main } = load('split_attachments.js');
  const out = main([{ json: { id: 'm1', subject: 'Factures octobre', from: { value: [{ address: 'compta@fournisseur.fr' }] } },
    binary: { attachment_0: { mimeType: 'application/pdf', fileName: 'F-1.pdf' },
              attachment_1: { mimeType: 'image/png', fileName: 'logo.png' },
              attachment_2: { mimeType: 'application/octet-stream', fileName: 'F-2.PDF' } } }]);
  assert.deepEqual(out.map(o => o.json.fileName), ['F-1.pdf', 'F-2.PDF']);
  assert.equal(out[0].json.from, 'compta@fournisseur.fr');
  assert.equal(out[1].binary.data.fileName, 'F-2.PDF');
});

test('facture : les métadonnées du courriel suivent chaque facture', () => {
  const { main } = load('invoice_checks.js');
  const [r] = main([{ json: { output: goodInvoice } }], { history: [], mails: [{ json: { from: 'a@b.fr', subject: 'Facture', fileName: 'F.pdf' } }] });
  assert.equal(r.json.expediteur, 'a@b.fr');
  assert.equal(r.json.fichier, 'F.pdf');
});
