// Une facture par élément : chaque pièce jointe PDF du courriel devient un élément séparé,
// avec les informations du courriel d'origine (expéditeur, objet, identifiant).

function main(items) {
  const out = [];
  for (const item of items) {
    const mail = item.json;
    const from = mail.from && mail.from.value && mail.from.value[0] ? mail.from.value[0].address : (mail.from || '');
    for (const [key, file] of Object.entries(item.binary || {})) {
      const isPdf = (file.mimeType || '').includes('pdf') || /\.pdf$/i.test(file.fileName || '');
      if (!isPdf) continue;
      out.push({
        json: { from, subject: mail.subject || '', messageId: mail.id || '', fileName: file.fileName || key },
        binary: { data: file },
      });
    }
  }
  return out;
}
