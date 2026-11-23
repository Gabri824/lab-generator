// Etichette delle interfacce sul disegno (Topologia ed editor), senza legami con la pagina:
// si possono provare anche con Node.
import { esc } from './comune.js';

export const largh = (testo, px) => testo.length * px * 0.62;

// etichetta di interfaccia: [eth0|1|c20] = nome dell'interfaccia + ultimo numero dell'IP +
// costo OSPF, solo se il costo è scritto nel frr.conf (il predefinito non si vede)
export const numIp = it => it.ip ? it.ip.split('/')[0].split('.')[3] : '';
export const testoCosto = it => it.costo != null && /^\d+$/.test(String(it.costo)) ? 'c' + it.costo : '';
const larghParti = it => {
  const num = numIp(it), c = testoCosto(it);
  return [largh(it.dev, 11) + 8, num ? largh(num, 11) + 9 : 0, c ? largh(c, 11) + 9 : 0];
};
export const largIface = it => larghParti(it).reduce((a, b) => a + b, 0);
export const largLan = l => largh(l.lan + '  ' + (l.subnet || ''), 11) + 10;
export function etichettaIface(it, x, y, colore) {
  const num = numIp(it), c = testoCosto(it);
  const [w1, w2, w3] = larghParti(it), w = w1 + w2 + w3, x0 = x - w / 2;
  let h = `<rect class="pill" x="${x0}" y="${y - 9}" width="${w}" height="18" rx="4"/>`;
  h += `<text class="pt" x="${x0 + w1 / 2}" y="${y + 4}" text-anchor="middle">${esc(it.dev)}</text>`;
  if (num) h += `<rect x="${x0 + w1}" y="${y - 9}" width="${w2}" height="18" rx="4" fill="${colore}"/><rect x="${x0 + w1}" y="${y - 9}" width="4" height="18" fill="${colore}"/>`
             + `<text class="nt" x="${x0 + w1 + w2 / 2}" y="${y + 4}" text-anchor="middle">${esc(num)}</text>`;
  if (c) {
    const xc = x0 + w1 + w2;
    h += `<rect class="cs" x="${xc}" y="${y - 9}" width="${w3}" height="18" rx="4"/><rect class="cs" x="${xc}" y="${y - 9}" width="4" height="18" stroke="none"/>`
       + `<text class="ct" x="${xc + w3 / 2}" y="${y + 4}" text-anchor="middle">${esc(c)}</text>`;
    h = `<g class="costo"><title>${esc(`${it.dev}: costo OSPF ${it.costo} (scritto nel frr.conf)`)}</title>${h}</g>`;
  }
  return h;
}

// solo il costo (livello "Costi OSPF" acceso e "Indirizzi" spento): [c20]
export const largCosto = it => largh(testoCosto(it), 11) + 10;
export function etichettaCosto(it, x, y) {
  const c = testoCosto(it), w = largCosto(it);
  return `<g class="costo"><title>${esc(`${it.dev}: costo OSPF ${it.costo} (scritto nel frr.conf)`)}</title>`
    + `<rect class="cs" x="${x - w / 2}" y="${y - 9}" width="${w}" height="18" rx="4"/><text class="ct" x="${x}" y="${y + 4}" text-anchor="middle">${esc(c)}</text></g>`;
}
