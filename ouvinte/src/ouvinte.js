// Ouvinte do WhatsApp: aparelho vinculado SOMENTE LEITURA. Grava cada mensagem recebida no spool da escuta; não envia nada,
// não marca como lida, não anuncia presença. Sem acesso a banco nem a segredos do brain.
// Log: só contadores e estado. Nunca texto, número, nome ou payload do QR (o QR só aparece no terminal em --parear).
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { gravarMensagem, tocarGatilho, nomeAnexo } from './spool.js';
import { criarRecarregador, temRisco } from './palavras.js';

const ANEXO_MAX_MB_PADRAO = 50;
const DOWNLOAD_TIMEOUT_S_PADRAO = 60;
const MIDIAS = ['documentMessage', 'imageMessage', 'audioMessage', 'videoMessage'];
const EMBRULHOS = ['ephemeralMessage', 'viewOnceMessage', 'viewOnceMessageV2', 'viewOnceMessageV2Extension', 'documentWithCaptionMessage'];
const IGNORADOS = ['protocolMessage', 'reactionMessage', 'editedMessage', 'pollUpdateMessage', 'keepInChatMessage'];
const EXTENSOES = {
  'application/pdf': 'pdf', 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'audio/ogg': 'ogg', 'video/mp4': 'mp4',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx', 'text/plain': 'txt',
};

export function extensaoDoMime(mime) {
  const base = String(mime ?? '').split(';')[0].trim().toLowerCase();
  return EXTENSOES[base] ?? 'bin';
}

export function downloadTimeoutMs(env = process.env) {
  const s = Number(env.OUVINTE_DOWNLOAD_TIMEOUT_S);
  return (Number.isFinite(s) && s > 0 ? s : DOWNLOAD_TIMEOUT_S_PADRAO) * 1000;
}

export function anexoMaxBytes(env = process.env) {
  const mb = Number(env.OUVINTE_ANEXO_MAX_MB);
  return (Number.isFinite(mb) && mb > 0 ? mb : ANEXO_MAX_MB_PADRAO) * 1024 * 1024;
}

function desembrulhar(message) {
  let m = message;
  for (let i = 0; i < 5 && m; i++) {
    const k = EMBRULHOS.find((e) => m[e]);
    if (!k) break;
    m = m[k].message;
  }
  return m ?? null;
}

function isoComOffset(ts) {
  const n = Number(ts?.toString?.() ?? ts);
  const ms = Number.isFinite(n) && n > 0 ? n * 1000 : Date.now();
  return new Date(ms).toISOString().replace(/\.\d{3}Z$/, '+00:00');
}

// Converte uma mensagem do Baileys no formato do spool. null = ignorar. Não faz E/S.
export function extrair(m) {
  const key = m?.key;
  if (!key || key.fromMe || !key.id || !key.remoteJid) return null;
  const remoto = key.remoteJid;
  if (remoto.endsWith('@broadcast') || remoto.endsWith('@newsletter')) return null;
  const conteudo = desembrulhar(m.message);
  if (!conteudo || IGNORADOS.some((k) => conteudo[k])) return null;
  const grupo = remoto.endsWith('@g.us');
  // Baileys 6.7.x preenche senderPn/participantPn quando o JID é @lid; remoteJidAlt/participantAlt são nomes da v7.
  const de = grupo
    ? (key.participantPn || key.participantAlt || key.participant || m.participant)
    : (key.senderPn || key.remoteJidAlt || remoto);
  if (!de || typeof de !== 'string') return null;
  const lid = de.endsWith('@lid');
  const midiaChave = MIDIAS.find((k) => conteudo[k]);
  const midia = midiaChave ? conteudo[midiaChave] : null;
  const texto = conteudo.conversation ?? conteudo.extendedTextMessage?.text ?? midia?.caption ?? null;
  if (texto == null && !midia) return null;
  return {
    msg: { id_externo: key.id, de, grupo, id_grupo: grupo ? remoto : null, ...(lid ? { lid: true } : {}), recebida_em: isoComOffset(m.messageTimestamp), texto: texto === '' ? null : texto, anexo: null },
    midia,
  };
}

// Lê o fluxo contando bytes: passou do teto ou do prazo, destrói o fluxo e desiste (nunca guarda o arquivo inteiro antes de checar).
// Devolve {dados} ou {motivo: 'teto'|'prazo'|'erro'}. Aceita Buffer pronto por compatibilidade.
export async function lerComTeto(fonte, max, prazoMs) {
  if (fonte == null) return { motivo: 'erro' };
  if (fonte instanceof Uint8Array) return fonte.length > 0 && fonte.length <= max ? { dados: Buffer.from(fonte) } : { motivo: 'teto' };
  const fim = Date.now() + prazoMs;
  const partes = [];
  let total = 0;
  let it;
  const desistir = () => {
    try { fonte.destroy?.(); } catch { /* ignore */ }
    try { it?.return?.()?.catch?.(() => {}); } catch { /* ignore */ }
  };
  let timer;
  try {
    it = fonte[Symbol.asyncIterator]();
    for (;;) {
      const restante = fim - Date.now();
      if (restante <= 0) { desistir(); return { motivo: 'prazo' }; }
      const prox = it.next();
      prox.catch(() => {}); // rejeição tardia depois de desistir não pode virar unhandledRejection
      const r = await Promise.race([prox, new Promise((resolve) => { timer = setTimeout(() => resolve(null), restante); })]);
      clearTimeout(timer);
      if (r === null) { desistir(); return { motivo: 'prazo' }; }
      if (r.done) break;
      total += r.value.length;
      if (total > max) { desistir(); return { motivo: 'teto' }; }
      partes.push(Buffer.from(r.value));
    }
  } catch {
    clearTimeout(timer);
    desistir();
    return { motivo: 'erro' };
  }
  return total > 0 ? { dados: Buffer.concat(partes) } : { motivo: 'teto' };
}

/**
 * ev: evento `messages.upsert` do Baileys. deps: {pasta, baixar(msg)->Readable|Buffer, palavras()->string[], anexoMaxBytes?,
 * downloadTimeoutMs?, contadores?, gravar?}. Só `notify` (mensagem nova). Erro em uma mensagem não impede as demais.
 */
export async function processarEvento(ev, deps) {
  const c = deps.contadores ?? {};
  const soma = (k) => { c[k] = (c[k] ?? 0) + 1; };
  if (ev?.type !== 'notify') return;
  const max = deps.anexoMaxBytes ?? anexoMaxBytes();
  const prazo = deps.downloadTimeoutMs ?? downloadTimeoutMs();
  const gravar = deps.gravar ?? gravarMensagem;
  for (const m of ev.messages ?? []) {
    try {
      const x = extrair(m);
      if (!x) { soma('ignoradas'); continue; }
      let anexo = null;
      if (x.midia) {
        const tam = Number(x.midia.fileLength?.toString?.() ?? x.midia.fileLength);
        if (Number.isFinite(tam) && tam > max) soma('anexo_grande'); // tamanho ausente/0/estranho = desconhecido: o fluxo limita
        else {
          let fonte = null;
          try { fonte = await deps.baixar(m); } catch { soma('anexo_falhou'); }
          if (fonte != null) {
            const r = await lerComTeto(fonte, max, prazo);
            if (r.dados) anexo = { nome: nomeAnexo(x.msg.id_externo, extensaoDoMime(x.midia.mimetype)), dados: r.dados };
            else soma({ teto: 'anexo_descartado', prazo: 'anexo_prazo' }[r.motivo] ?? 'anexo_falhou');
          }
        }
      }
      if (anexo) x.msg.anexo = anexo.nome;
      const r = gravar(x.msg, deps.pasta, { anexo });
      soma(r.gravado ? 'gravadas' : 'repetidas');
      if (x.msg.texto && temRisco(x.msg.texto, deps.palavras())) { tocarGatilho(deps.pasta); soma('gatilhos'); }
    } catch (e) { soma(e?.code === 'ENOSPC' || e?.code === 'EDQUOT' ? 'disco_cheio' : 'erros'); }
  }
}

// Opções do socket: nada de presença, histórico completo nem eco das próprias mensagens.
export function opcoesBaileys({ state, logger, version }) {
  return {
    auth: state, version, logger,
    markOnlineOnConnect: false,
    syncFullHistory: false,
    emitOwnEvents: false,
    printQRInTerminal: false,
    generateHighQualityLinkPreview: false,
    shouldSyncHistoryMessage: () => false,
    getMessage: async () => undefined,
  };
}

const loggerMudo = () => {
  const l = { level: 'silent', child: () => l };
  for (const k of ['trace', 'debug', 'info', 'warn', 'error', 'fatal']) l[k] = () => {};
  return l;
};

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));
const MAX_BAD_SESSION = 3;

/**
 * Política de reconexão. 401 (deslogado), 403 (proibido/banido) e 440 (substituído por outra sessão) são terminais; badSession
 * (500) é terminal na 3ª seguida; o resto religa com backoff 1s,2s,4s... até 60s; 515 (reinício pedido) religa na hora.
 * `est` ({badSession, tentativa}) é alterado. Devolve {acao:'terminal'} ou {acao:'retry', espera}.
 */
export function decidirReconexao(codigo, est, razao) {
  if (codigo === razao.loggedOut || codigo === razao.forbidden || codigo === razao.connectionReplaced) return { acao: 'terminal' };
  if (codigo === razao.badSession) {
    est.badSession += 1;
    if (est.badSession >= MAX_BAD_SESSION) return { acao: 'terminal' };
  }
  if (codigo === razao.restartRequired) return { acao: 'retry', espera: 0 };
  const espera = Math.min(60_000, 1000 * 2 ** est.tentativa);
  est.tentativa += 1;
  return { acao: 'retry', espera };
}

/** Liga ao WhatsApp (Baileys carregado só aqui). opts: {pasta, authDir, parear, env, carregarBaileys, dormir, aoPareado, aoTerminar}. */
export async function conectar(opts) {
  const env = opts.env ?? process.env;
  const pasta = opts.pasta ?? env.OUVINTE_SPOOL ?? '/var/lib/gabi-escuta-spool';
  const authDir = opts.authDir ?? env.OUVINTE_AUTH_DIR ?? '/var/lib/escuta-ouvinte/auth';
  const esperar = opts.dormir ?? dormir;
  const mod = await (opts.carregarBaileys ?? (() => import('@whiskeysockets/baileys')))();
  const criar = typeof mod.default === 'function' ? mod.default : mod.default?.default ?? mod.makeWASocket;
  const { useMultiFileAuthState, DisconnectReason, downloadMediaMessage, fetchLatestBaileysVersion } = mod;
  const fs = await import('node:fs');
  fs.mkdirSync(authDir, { recursive: true, mode: 0o700 });
  try { fs.chmodSync(authDir, 0o700); } catch { /* ignore */ }
  const { state, saveCreds } = await useMultiFileAuthState(authDir);
  let version;
  try { ({ version } = await fetchLatestBaileysVersion()); } catch { /* usa a versão embutida */ }
  const logger = loggerMudo();
  const contadores = {};
  const palavras = criarRecarregador(path.join(pasta, 'palavras-risco.json'));
  const prazo = downloadTimeoutMs(env);
  const deps = {
    pasta, palavras, contadores, anexoMaxBytes: anexoMaxBytes(env), downloadTimeoutMs: prazo,
    baixar: (m) => downloadMediaMessage(m, 'stream', { options: { timeout: prazo } }), // fluxo: o teto é aplicado durante a leitura
  };
  const est = { badSession: 0, tentativa: 0 };
  let parado = false;
  let sock = null;
  let fila = Promise.resolve();
  const resumo = setInterval(() => {
    if (Object.keys(contadores).length) console.log(`ouvinte: ${Object.entries(contadores).map(([k, v]) => `${k}=${v}`).join(' ')}`);
  }, 10 * 60 * 1000);
  resumo.unref?.();

  const ligar = async () => {
    sock = criar(opcoesBaileys({ state, logger, version }));
    sock.ev.on('creds.update', saveCreds);
    sock.ev.on('messages.upsert', (ev) => {
      if (opts.parear) return; // pareando: não grava nada no spool
      fila = fila.then(() => processarEvento(ev, deps)).catch(() => { contadores.erros = (contadores.erros ?? 0) + 1; });
    });
    sock.ev.on('connection.update', async (u) => {
      if (u.qr && opts.parear) {
        const qr = await import('qrcode-terminal'); // só no terminal do pareamento
        (qr.default ?? qr).generate(u.qr, { small: true });
      }
      if (u.connection === 'open') {
        est.badSession = 0; est.tentativa = 0;
        console.log('ouvinte: conectado');
        if (opts.parear) { await esperar(3000); console.log('ouvinte: pareado'); await opts.aoPareado?.(); }
      }
      if (u.connection === 'close' && !parado) {
        const codigo = u.lastDisconnect?.error?.output?.statusCode;
        const d = decidirReconexao(codigo, est, DisconnectReason);
        if (d.acao === 'terminal') {
          parado = true;
          console.error(`ouvinte: conexão encerrada sem nova tentativa (codigo=${codigo ?? 'desconhecido'}); ver runbook #escuta`);
          await opts.aoTerminar?.(codigo);
          return;
        }
        console.log(`ouvinte: conexão fechada (codigo=${codigo ?? 'desconhecido'}), nova tentativa em ${Math.round(d.espera / 1000)}s`);
        await esperar(d.espera);
        if (!parado) await ligar();
      }
    });
  };
  await ligar();
  return { contadores, parar: () => { parado = true; clearInterval(resumo); try { sock?.end?.(undefined); } catch { /* ignore */ } } };
}

const SAIDA_TERMINAL = 78; // a unit tem RestartPreventExitStatus=78: não fica religando sessão encerrada/banida/substituída

/**
 * Modo servidor: erro não tratado vira mensagem genérica (sem pilha nem payload) e exit(1); console.* de bibliotecas é
 * descartado (só passa uma linha única que comece com "ouvinte:"), para nada de mensagem chegar ao journal.
 */
export function instalarSaidaSegura({ proc = process, con = console, sair = process.exit } = {}) {
  const originais = {};
  for (const k of ['log', 'info', 'warn', 'error', 'debug']) originais[k] = con[k].bind(con);
  const emitir = originais.error;
  const falhar = () => { emitir('ouvinte: erro inesperado, encerrando'); sair(1); };
  proc.on('unhandledRejection', falhar);
  proc.on('uncaughtException', falhar);
  for (const k of Object.keys(originais)) {
    con[k] = (...a) => { if (a.length === 1 && typeof a[0] === 'string' && a[0].startsWith('ouvinte:')) originais[k](a[0]); };
  }
}

export async function main(argv = process.argv.slice(2)) {
  const parear = argv.includes('--parear');
  if (!parear) instalarSaidaSegura(); // no --parear o QR sai por console.log e precisa aparecer
  const h = await conectar({
    parear,
    aoPareado: async () => process.exit(0),
    aoTerminar: async () => process.exit(SAIDA_TERMINAL),
  });
  for (const s of ['SIGINT', 'SIGTERM']) process.on(s, () => { h.parar(); process.exit(0); });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(() => { console.error('ouvinte: falha ao iniciar'); process.exit(1); });
}
