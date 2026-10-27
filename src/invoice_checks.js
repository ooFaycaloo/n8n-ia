// Contrôles d'une facture extraite par l'IA, avant enregistrement dans le tableau de suivi.
// Entrée : sorties du nœud d'extraction ({ output: { fournisseur, siren, numero_facture, ... } }).
// Contexte : history = lignes déjà présentes dans le tableau ;
//            mails = métadonnées du courriel source de chaque facture (même ordre que les entrées).

function digits(s) { return String(s ?? '').replace(/\D/g, ''); }

function isValidSiren(s) {
  const d = digits(s);
  if (d.length !== 9) return false;
  let sum = 0;
  for (let i = 0; i < 9; i++) {
    let n = Number(d[8 - i]);
    if (i % 2 === 1) { n *= 2; if (n > 9) n -= 9; }
    sum += n;
  }
  return sum % 10 === 0;
}

function normalizeIban(s) { return String(s ?? '').replace(/\s+/g, '').toUpperCase(); }

function isValidIban(s) {
  const iban = normalizeIban(s);
  if (!/^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$/.test(iban)) return false;
  const rearranged = iban.slice(4) + iban.slice(0, 4);
  const numeric = rearranged.replace(/[A-Z]/g, c => String(c.charCodeAt(0) - 55));
  return BigInt(numeric) % 97n === 1n;
}

function toNumber(v) {
  if (typeof v === 'number') return v;
  const s = String(v ?? '').replace(/[\s  €]/g, '');
  if (!s) return NaN;
  const normalized = s.includes(',') && s.lastIndexOf(',') > s.lastIndexOf('.')
    ? s.replace(/\./g, '').replace(',', '.') : s.replace(/,/g, '');
  return Number(normalized);
}

function daysBetween(a, b) { return Math.round((new Date(b) - new Date(a)) / 86400000); }

function check(inv, history) {
  const issues = [];
  const ht = toNumber(inv.montant_ht), tva = toNumber(inv.montant_tva), ttc = toNumber(inv.montant_ttc);
  if ([ht, tva, ttc].some(Number.isNaN)) issues.push('Montants illisibles');
  else if (Math.abs(ht + tva - ttc) > 0.02) issues.push(`HT + TVA ≠ TTC (${ht} + ${tva} ≠ ${ttc})`);
  if (!inv.siren) issues.push('SIREN absent');
  else if (!isValidSiren(inv.siren)) issues.push(`SIREN invalide (${inv.siren})`);
  if (inv.iban && !isValidIban(inv.iban)) issues.push('IBAN invalide');
  if (inv.date_echeance && inv.date_facture) {
    const d = daysBetween(inv.date_facture, inv.date_echeance);
    if (d < 0) issues.push('Échéance antérieure à la date de facture');
    else if (d > 60) issues.push(`Délai de paiement de ${d} jours (> 60 jours légaux)`);
  }
  const sameSupplier = history.filter(h => (inv.siren && digits(h.siren) === digits(inv.siren))
    || (h.fournisseur && String(h.fournisseur).toLowerCase() === String(inv.fournisseur ?? '').toLowerCase()));
  if (sameSupplier.some(h => String(h.numero_facture) === String(inv.numero_facture))) {
    issues.push('Doublon : facture déjà enregistrée');
  }
  const knownIbans = new Set(sameSupplier.map(h => normalizeIban(h.iban)).filter(Boolean));
  if (inv.iban && knownIbans.size && !knownIbans.has(normalizeIban(inv.iban))) {
    issues.push('IBAN différent de celui connu pour ce fournisseur : vérifier par téléphone avant tout paiement');
  }
  return issues;
}

function main(items, ctx) {
  const history = (ctx.history || []).map(h => h.json || h);
  return items.map((it, idx) => {
    const mail = ((ctx.mails || [])[idx] || {}).json || {};
    const inv = it.json.output || it.json;
    const issues = check(inv, history);
    const blocking = issues.some(i => /IBAN|Doublon|SIREN invalide|≠/.test(i));
    const row = {
      recu_le: new Date().toISOString().slice(0, 10),
      fournisseur: inv.fournisseur || '',
      siren: digits(inv.siren),
      numero_facture: inv.numero_facture || '',
      date_facture: inv.date_facture || '',
      date_echeance: inv.date_echeance || '',
      montant_ht: toNumber(inv.montant_ht),
      montant_tva: toNumber(inv.montant_tva),
      montant_ttc: toNumber(inv.montant_ttc),
      iban: normalizeIban(inv.iban),
      statut: blocking ? 'À BLOQUER' : issues.length ? 'À vérifier' : 'OK',
      anomalies: issues.join(' | '),
      expediteur: mail.from || '',
      objet_mail: mail.subject || '',
      fichier: mail.fileName || '',
    };
    history.push(row); // deux factures du même courriel se contrôlent aussi entre elles
    return { json: row };
  });
}
