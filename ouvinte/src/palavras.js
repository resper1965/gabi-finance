// Palavras de risco: lista publicada pelo brain em <spool>/palavras-risco.json (parametro escuta.palavras_risco).
// Mesma regra de gabi/escuta/crise.py: sem acento, sem caixa, palavra inteira, aceita expressão de várias palavras.
import fs from 'node:fs';

export function normalizar(s) {
  const sem = String(s ?? '').normalize('NFD').replace(/\p{Mn}/gu, '');
  return (sem.toLowerCase().match(/[\p{L}\p{N}_]+/gu) ?? []).join(' ');
}

export function temRisco(texto, palavras) {
  const alvo = ` ${normalizar(texto)} `;
  return (palavras ?? []).some((p) => {
    const n = normalizar(p);
    return n !== '' && alvo.includes(` ${n} `);
  });
}

export function carregarPalavras(caminho) {
  try {
    const l = JSON.parse(fs.readFileSync(caminho, 'utf8'));
    return Array.isArray(l) ? l.filter((p) => typeof p === 'string') : [];
  } catch {
    return [];
  }
}

// Devolve uma função que entrega a lista, relida no máximo a cada `intervaloMs` e só se o mtime mudou.
export function criarRecarregador(caminho, { agora = Date.now, intervaloMs = 60_000 } = {}) {
  let lista = [];
  let mtime = null;
  let ultima = -Infinity;
  return () => {
    const t = agora();
    if (t - ultima < intervaloMs) return lista;
    ultima = t;
    try {
      const m = fs.statSync(caminho).mtimeMs;
      if (m !== mtime) { lista = carregarPalavras(caminho); mtime = m; }
    } catch {
      lista = []; mtime = null;
    }
    return lista;
  };
}
