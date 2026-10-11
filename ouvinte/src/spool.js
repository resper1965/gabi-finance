// Spool da escuta: um JSON por mensagem em <pasta>/<nome>.json, publicado de forma atômica.
// Contrato com o brain (gabi/escuta/caixa.py): o brain lê só `*.json`; anexo em <pasta>/anexos/<nome>.
// Ordem: anexo PRIMEIRO, json DEPOIS (o brain nunca vê json cujo anexo falta). Permissões 0660 / pastas 2770 (umask 0007).
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const MODO_ARQ = 0o660;
const MODO_DIR = 0o2770;

function recusarSeInseguro(valor, rotulo) {
  if (typeof valor !== 'string' || valor === '' || valor === '.' || valor === '..' || valor.includes('..')
    || /[\\/\0]/.test(valor) || valor !== path.basename(valor)) {
    throw new Error(`${rotulo} inválido`);
  }
}

const RESERVADOS = new Set(['palavras-risco', 'gatilho', 'lidos', 'invalidos', 'anexos']);
const MAX_BASE = 100;
const hash12 = (id) => crypto.createHash('sha256').update(id).digest('hex').slice(0, 12);

// Nome de arquivo determinístico a partir do id: [A-Za-z0-9._-] passam; o resto (inclusive separadores, "..", NUL) vira "_" e
// entra um sufixo de hash do id original, o mesmo vale para nome reservado, que começa com "." ou passa do limite.
// Nunca recusa por causa do conteúdo do id (a mensagem não pode ser perdida): só id vazio/não texto é erro.
export function nomeDoId(id) {
  if (typeof id !== 'string' || id === '') throw new Error('id_externo inválido');
  const limpo = id.replace(/[^A-Za-z0-9._-]/g, '_');
  const sujo = limpo !== id || id.includes('..') || id.startsWith('.') || id.length > MAX_BASE || RESERVADOS.has(id.toLowerCase());
  if (!sujo) return id;
  const base = limpo.replace(/\.{2,}/g, '_').replace(/^\.+/, '_').slice(0, MAX_BASE);
  return `${base}-${hash12(id)}`;
}

// Nome do anexo com a mesma regra do json (ext já vem da lista branca do chamador).
export function nomeAnexo(id, ext) {
  return `${nomeDoId(id)}.${ext}`;
}

function garantirPasta(d) {
  fs.mkdirSync(d, { recursive: true, mode: MODO_DIR });
  try { fs.chmodSync(d, MODO_DIR); } catch { /* sem dono da pasta: o instalador já criou 2770 */ }
}

function fsyncArquivo(caminho) {
  const fd = fs.openSync(caminho, 'r');
  try { fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
}

function fsyncPasta(dir) {
  try { fsyncArquivo(dir); } catch { /* melhor esforço */ }
}

// tmp aberto com wx (O_EXCL: não segue symlink plantado); fsync antes de publicar; tmp limpo em qualquer falha.
function gravarAtomico(destino, dados, { naoSobrescrever }) {
  const tmp = `${destino}.tmp`;
  try { fs.unlinkSync(tmp); } catch { /* sem sobra */ }
  try {
    fs.writeFileSync(tmp, dados, { mode: MODO_ARQ, flag: 'wx' });
    fs.chmodSync(tmp, MODO_ARQ); // não depende do umask
    fsyncArquivo(tmp);
    if (naoSobrescrever) fs.linkSync(tmp, destino); // falha com EEXIST: nunca sobrescreve
    else fs.renameSync(tmp, destino);
  } catch (e) {
    try { fs.unlinkSync(tmp); } catch { /* ignore */ }
    if (naoSobrescrever && e.code === 'EEXIST') return false;
    throw e;
  }
  if (naoSobrescrever) { try { fs.unlinkSync(tmp); } catch { /* ignore */ } }
  fsyncPasta(path.dirname(destino));
  return true;
}

// Só a raiz conta: o brain APAGA o json depois de gravar no banco (não há lidos/). Replay de um id já ingerido regrava o json
// e o brain deduplica por id_externo; o anexo que ainda existe não é regravado (naoSobrescrever).
function jaExiste(pasta, arquivo) {
  return fs.existsSync(path.join(pasta, arquivo));
}

/**
 * msg: {id_externo, de, grupo, id_grupo, recebida_em, texto, anexo}. opts.anexo: {nome, dados:Buffer} (nome === msg.anexo).
 * Devolve {gravado, arquivo}. Mesmo id_externo ainda na raiz do spool não regrava (o brain deduplica o replay de id já ingerido).
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
    gravarAtomico(path.join(dirAnexos, anexo.nome), anexo.dados, { naoSobrescrever: true }); // já existe: mesmo id, mesmo nome
  }
  const corpo = JSON.stringify({
    id_externo: msg.id_externo, de: msg.de, grupo: Boolean(msg.grupo), id_grupo: msg.id_grupo ?? null,
    recebida_em: msg.recebida_em, texto: msg.texto ?? null, anexo: msg.anexo ?? null,
    ...(msg.lid ? { lid: true } : {}),
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
