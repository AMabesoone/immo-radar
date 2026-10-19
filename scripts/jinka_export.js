// Export d'une alerte Jinka vers le CSV attendu par Immo Radar (data/jinka/<nom>.csv).
// Usage : ouvrir https://www.jinka.fr/alerts/<id> connecte, ouvrir la console du navigateur (F12),
// coller ce script, Entree : un fichier CSV est telecharge. Le deposer dans data/jinka/ et commiter.
(async () => {
  const alertId = location.pathname.split('/alerts/')[1].split(/[/?]/)[0];
  const base = `${location.origin}/alerts/${alertId}`;
  const arrAt = (t, key) => { const k = t.indexOf(key); if (k < 0) return []; let s = k + key.length - 1, d = 0, e = s;
    for (; e < t.length; e++) { const c = t[e]; if (c === '"') { e++; while (e < t.length && t[e] !== '"') { if (t[e] === '\\') e++; e++; } continue; }
      if (c === '[' || c === '{') d++; else if (c === ']' || c === '}') { d--; if (d === 0) break; } } return JSON.parse(t.slice(s, e + 1)); };
  const rows = [["id","source","url","titre","prix","surface","pieces","type_bien","ville","code_postal","categorie_ville","dpe","charges_copro_annuelles","taxe_fonciere","loue","loyer_actuel","description","copro_en_procedure","nb_lots_copro","neuf","date_publication","quartier"]];
  const seen = new Set();
  for (let p = 1; p <= 20; p++) {
    const rsc = await fetch(`${base}?page=${p}`, { headers: { RSC: '1' } }).then(r => r.text());
    const ads = arrAt(rsc, '"alert_results":[');
    if (!ads.length) break;
    for (const a of ads) {
      if (seen.has(a.uuid)) continue; seen.add(a.uuid);
      const type = a.type === 'Maison' ? 'house' : (a.type === 'Immeuble' ? 'building' : 'flat');
      const titre = `${a.type} ${a.room || ''} pieces a ${a.city} via ${a.source_label || a.source}`;
      rows.push([a.uuid, 'jinka', `https://www.jinka.fr/ad/${a.uuid}`, titre, a.rent, a.area, a.room || 1, type, a.city, a.postal_code, 'a_determiner', a.energy_dpe || '',
        a.coduminium_charges ? Math.round(a.coduminium_charges * 12) : '', '', '', '', `Alerte Jinka, agence ${a.source_label || ''}, quartier ${a.quartier_name || 'n.c.'}`,
        a.coduminium_pending_prejudice ? 'oui' : '', a.coduminium_lots || '', a.buy_type === 'new' ? 'oui' : '', String(a.created_at || '').replace('$D', '').slice(0, 10), a.quartier_name || '']);
    }
    if (ads.length < 20) break;
  }
  const csv = rows.map(r => r.map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',')).join('\n');
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `jinka-${alertId.slice(0, 8)}.csv`; a.click();
  console.log(`${rows.length - 1} annonces exportees`);
})();
