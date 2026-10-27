// Préfiltrage des avis BOAMP avant l'IA : on n'envoie au modèle que des avis plausibles,
// pour garder un coût par jour prévisible (plafond `max_avis`).
// Entrée : réponses de l'API BOAMP (une ou plusieurs pages { total_count, results }).
// Contexte : params = nœud « Paramètres » (mots_cles, departements, max_avis).

function fold(s) {
  return String(s ?? '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
}

function asList(v) {
  if (v == null || v === '') return [];
  return Array.isArray(v) ? v.map(String) : String(v).split(/[,;]\s*/).filter(Boolean);
}

function isNewTender(r) {
  // avis de marché initiaux (pas les attributions ni les rectificatifs)
  const label = fold(r.nature_libelle || r.nature || '');
  if (!label) return true;
  return !label.includes('attribution') && !label.includes('rectificatif') && !label.includes('annulation');
}

function main(items, ctx) {
  const p = ctx.params || {};
  const keywords = asList(p.mots_cles).map(fold);
  const departments = asList(p.departements);
  const maxNotices = Number(p.max_avis || 40);

  const seen = new Set();
  const kept = [];
  for (const page of items) {
    for (const r of page.json.results || []) {
      if (!r.idweb || seen.has(r.idweb) || !isNewTender(r)) continue;
      seen.add(r.idweb);
      const deps = asList(r.code_departement);
      if (departments.length && !deps.some(d => departments.includes(d))) continue;
      const text = fold([r.objet, asList(r.descripteur_libelle).join(' ')].join(' '));
      const matched = keywords.filter(k => text.includes(k));
      if (keywords.length && !matched.length) continue;
      kept.push({
        idweb: r.idweb,
        objet: r.objet || '',
        acheteur: r.nomacheteur || '',
        departements: deps.join(', '),
        descripteurs: asList(r.descripteur_libelle).join(', '),
        type_marche: asList(r.type_marche).join(', '),
        date_parution: r.dateparution || '',
        date_limite: r.datelimitereponse || '',
        url: r.url_avis || `https://www.boamp.fr/pages/avis/?q=idweb:${r.idweb}`,
        mots_cles_trouves: matched.join(', '),
      });
    }
  }
  // les avis qui contiennent le plus de mots-clés passent en premier si on dépasse le plafond
  kept.sort((a, b) => b.mots_cles_trouves.split(',').length - a.mots_cles_trouves.split(',').length);
  return kept.slice(0, maxNotices).map(json => ({ json }));
}
