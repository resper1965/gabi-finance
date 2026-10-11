// Spool da escuta: um JSON por mensagem em <pasta>/<nome>.json, publicado de forma atômica.
// Contrato com o brain (gabi/escuta/caixa.py): o brain lê só `*.json`; anexo em <pasta>/anexos/<nome>.
// Ordem: anexo PRIMEIRO, json DEPOIS (o brain nunca vê json cujo anexo falta). Permissões 0660 / pastas 2770 (umask 0007).
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const MODO_ARQ = 0o660;
const MODO_DIR = 0o2770;
const SUBPASTAS_CONSUMIDAS = ['lidos', 'invalidos'];

function recusarSeInseguro(valor, rotulo) {
  if (typeof valor !== 'string' || valor === '' || valor === '.' || valor === '..' || valor.includes('..')
    || /[\\/\0]/.test(valor) || valor !== path.basename(valor)) {
    throw new Error(`${rotulo} inválido`);
  }
}

// Nome de arquivo determinístico: caracteres fora de [A-Za-z0-9._-] viram "_" e, nesse caso, entra um sufixo de hash
// do id original (ids diferentes nunca colidem no mesmo nome).
export function nomeDoId(id) {
  recusarSeInseguro(id, 'id_externo');
  const limpo = id.replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 120);
  if (limpo === id && id.length <= 120) return id;
  return `${limpo}-${crypto.createHash('sha256').update(id).digest('hex').slice(0, 12)}`;
}

function garantirPasta(d) {
  fs.mkdirSync(d, { recursive: true, mode: MODO_DIR });
  try { fs.chmodSync(d, MODO_DIR); } catch { /* sem dono da pasta: o instalador já criou 2770 */ }
}

function gravarAtomico(destino, dados, { naoSobrescrever }) {
  const tmp = `${destino}.tmp`;
  try { fs.unlinkSync(tmp); } catch { /* sem sobra */ }
  fs.writeFileSync(tmp, dados, { mode: MODO_ARQ });
  fs.chmodSync(tmp, MODO_ARQ); // não depende do umask
  try {
    if (naoSobrescrever) fs.linkSync(tmp, destino); // falha com EEXIST: nunca sobrescreve
    else fs.renameSync(tmp, destino);
  } catch (e) {
    try { fs.unlinkSync(tmp); } catch { /* ignore */ }
    if (naoSobrescrever && e.code === 'EEXIST') return false;
    throw e;
  }
  if (naoSobrescrever) { try { fs.unlinkSync(tmp); } catch { /* ignore */ } }
  return true;
}

function jaExiste(pasta, arquivo) {
  return [pasta, ...SUBPASTAS_CONSUMIDAS.map((s) => path.join(pasta, s))].some((d) => fs.existsSync(path.join(d, arquivo)));
}

/**
 * msg: {id_externo, de, grupo, id_grupo, recebida_em, texto, anexo}. opts.anexo: {nome, dados:Buffer} (nome === msg.anexo).
 * Devolve {gravado, arquivo}. Mesmo id_externo (inclusive já consumido pelo brain em lidos/) não regrava.
 */
export function gravarMensagem(msg, pasta, opts = {}) {
  const arquivo = `${nomeDoId(msg.id_externo)}.json`;
  const anexo = opts.anexo ?? null;
  if (msg.anexo != null || anexo) {
    recusarSeInseguro(msg.anexo, 'anexo');
    if (anexo && anexo.nome !== msg.anexo) throw new Error('anexo diferente do nome informado');
  }
  if (anexo) recusarSeInseguro(anexo.nome, 'anexo');
  garantirPasta(pasta);
  if (jaExiste(pasta, arquivo)) return { gravado: false, arquivo };
  if (anexo) {
    const dirAnexos = path.join(pasta, 'anexos');
    garantirPasta(dirAnexos);
    gravarAtomico(path.join(dirAnexos, anexo.nome), anexo.dados, { naoSobrescrever: false });
  }
  const corpo = JSON.stringify({
    id_externo: msg.id_externo, de: msg.de, grupo: Boolean(msg.grupo), id_grupo: msg.id_grupo ?? null,
    recebida_em: msg.recebida_em, texto: msg.texto ?? null, anexo: msg.anexo ?? null,
  });
  const gravado = gravarAtomico(path.join(pasta, arquivo), corpo, { naoSobrescrever: true });
  return { gravado, arquivo };
}

// Acorda o gabi-brain-escuta.path (PathChanged=<pasta>/gatilho): abre para escrita (close-write) e atualiza o mtime.
export function tocarGatilho(pasta) {
  const g = path.join(pasta, 'gatilho');
  fs.closeSync(fs.openSync(g, 'a', MODO_ARQ));
  const agora = new Date();
  fs.utimesSync(g, agora, agora);
}
