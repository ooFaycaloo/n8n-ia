// Fusionne les avis préfiltrés avec la note donnée par l'IA, garde les avis pertinents
// et prépare le courriel de synthèse quotidien.
// Entrée : sorties du nœud d'extraction IA ({ output: { score, raison, type_prestation } }), dans le même ordre.
// Contexte : notices = sorties du préfiltrage ; params = nœud « Paramètres » (score_minimum).

function esc(s) {
  return String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function main(items, ctx) {
  const notices = ctx.notices || [];
  const minScore = Number((ctx.params || {}).score_minimum ?? 60);
  const rows = items.map((it, i) => {
    const o = it.json.output || it.json || {};
    return { ...notices[i].json, score: Math.round(Number(o.score) || 0), raison: o.raison || '',
             type_prestation: o.type_prestation || '' };
  });
  const retained = rows.filter(r => r.score >= minScore).sort((a, b) => b.score - a.score);

  const date = new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
  const cards = retained.map(r => `
    <tr><td style="padding:14px 0;border-bottom:1px solid #e5e7eb">
      <div style="font:600 15px Arial,sans-serif;color:#111827">${esc(r.objet)}</div>
      <div style="font:13px Arial,sans-serif;color:#4b5563;margin-top:2px">${esc(r.acheteur)} · dép. ${esc(r.departements)} · réponse avant le ${esc(r.date_limite || 'non précisé')}</div>
      <div style="font:13px Arial,sans-serif;color:#111827;margin-top:6px"><b>Pertinence ${r.score}/100</b> — ${esc(r.raison)}</div>
      <a href="${esc(r.url)}" style="font:13px Arial,sans-serif;color:#0d6a73">Lire l'avis sur le BOAMP</a>
    </td></tr>`).join('');
  const html = `<div style="max-width:640px">
    <p style="font:15px Arial,sans-serif;color:#111827">${retained.length} appel(s) d'offres pertinent(s) sur ${rows.length} avis analysés.</p>
    <table style="width:100%;border-collapse:collapse">${cards || '<tr><td style="font:14px Arial,sans-serif">Aucun avis au-dessus du seuil aujourd\'hui.</td></tr>'}</table>
    <p style="font:12px Arial,sans-serif;color:#6b7280">Note de pertinence calculée par IA à partir du profil de l'entreprise : à vérifier avant toute décision de réponse.</p></div>`;

  return [{ json: {
    subject: `Veille appels d'offres — ${retained.length} avis pertinent(s) — ${date}`,
    html,
    count: retained.length,
    analysed: rows.length,
    rows: retained,
  } }];
}
