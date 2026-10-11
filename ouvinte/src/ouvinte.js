// Ouvinte do WhatsApp: aparelho vinculado SOMENTE LEITURA. Grava cada mensagem recebida no spool da escuta; não envia nada,
// não marca como lida, não anuncia presença. Sem acesso a banco nem a segredos do brain.
// Log: só contadores e estado. Nunca texto, número, nome ou payload do QR (o QR só aparece no terminal em --parear).
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { gravarMensagem, tocarGatilho } from './spool.js';
import { criarRecarregador, temRisco } from './palavras.js';

const ANEXO_MAX_MB_PADRAO = 50;
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

const ehTelefone = (j) => typeof j === 'string' && j.endsWith('@s.whatsapp.net');

// Converte uma mensagem do Baileys no formato do spool. null = ignorar. Não faz E/S.
export function extrair(m) {
  const key = m?.key;
  if (!key || key.fromMe || !key.id || !key.remoteJid) return null;
  const remoto = key.remoteJid;
  if (remoto.endsWith('@broadcast') || remoto.endsWith('@newsletter')) return null;
  const conteudo = desembrulhar(m.message);
  if (!conteudo || IGNORADOS.some((k) => conteudo[k])) return null;
  const grupo = remoto.endsWith('@g.us');
  const alvo = grupo ? (key.participant ?? m.participant) : remoto;
  const alt = grupo ? key.participantAlt : key.remoteJidAlt; // quando o JID é um LID, prefere o telefone
  const de = ehTelefone(alvo) ? alvo : (ehTelefone(alt) ? alt : alvo);
  if (!de) return null;
  const midiaChave = MIDIAS.find((k) => conteudo[k]);
  const midia = midiaChave ? conteudo[midiaChave] : null;
  const texto = conteudo.conversation ?? conteudo.extendedTextMessage?.text ?? midia?.caption ?? null;
  if (texto == null && !midia) return null;
  return {
    msg: { id_externo: key.id, de, grupo, id_grupo: grupo ? remoto : null, recebida_em: isoComOffset(m.messageTimestamp), texto: texto === '' ? null : texto, anexo: null },
    midia,
  };
}

/**
 * ev: evento `messages.upsert` do Baileys. deps: {pasta, baixar(msg)->Buffer, palavras()->string[], anexoMaxBytes?, contadores?}.
 * Só `notify` (mensagem nova). Erro em uma mensagem não impede as demais; só entra no contador.
 */
export async function processarEvento(ev, deps) {
  const c = deps.contadores ?? {};
  const soma = (k) => { c[k] = (c[k] ?? 0) + 1; };
  if (ev?.type !== 'notify') return;
  const max = deps.anexoMaxBytes ?? anexoMaxBytes();
  for (const m of ev.messages ?? []) {
    try {
      const x = extrair(m);
      if (!x) { soma('ignoradas'); continue; }
      let anexo = null;
      if (x.midia) {
        const tam = Number(x.midia.fileLength?.toString?.() ?? x.midia.fileLength ?? 0);
        if (tam > max) soma('anexo_grande');
        else {
          try {
            const dados = await deps.baixar(m);
            if (dados && dados.length > 0 && dados.length <= max) anexo = { nome: `${x.msg.id_externo.replace(/[^A-Za-z0-9._-]/g, '_')}.${extensaoDoMime(x.midia.mimetype)}`, dados };
            else soma('anexo_descartado');
          } catch { soma('anexo_falhou'); }
        }
      }
      if (anexo) x.msg.anexo = anexo.nome;
      const r = gravarMensagem(x.msg, deps.pasta, { anexo });
      soma(r.gravado ? 'gravadas' : 'repetidas');
      if (x.msg.texto && temRisco(x.msg.texto, deps.palavras())) { tocarGatilho(deps.pasta); soma('gatilhos'); }
    } catch { soma('erros'); }
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

/** Liga ao WhatsApp (Baileys carregado só aqui). opts: {pasta, authDir, parear, env}. Resolve com {parar()}. */
export async function conectar(opts) {
  const env = opts.env ?? process.env;
  const pasta = opts.pasta ?? env.OUVINTE_SPOOL ?? '/var/lib/gabi-escuta-spool';
  const authDir = opts.authDir ?? env.OUVINTE_AUTH_DIR ?? '/var/lib/escuta-ouvinte/auth';
  const mod = await import('@whiskeysockets/baileys');
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
  const deps = { pasta, palavras, contadores, anexoMaxBytes: anexoMaxBytes(env), baixar: (m) => downloadMediaMessage(m, 'buffer', {}, { logger }) };
  let parado = false;
  let tentativa = 0;
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
        tentativa = 0;
        console.log('ouvinte: conectado');
        if (opts.parear) { await dormir(3000); console.log('ouvinte: pareado'); await opts.aoPareado?.(); }
      }
      if (u.connection === 'close' && !parado) {
        const codigo = u.lastDisconnect?.error?.output?.statusCode;
        if (codigo === DisconnectReason.loggedOut) {
          console.error('ouvinte: sessão encerrada pelo WhatsApp; refazer o pareamento (--parear)');
          await opts.aoDeslogar?.();
          return;
        }
        const espera = codigo === DisconnectReason.restartRequired ? 0 : Math.min(60_000, 1000 * 2 ** tentativa++);
        console.log(`ouvinte: conexão fechada (codigo=${codigo ?? 'desconhecido'}), nova tentativa em ${Math.round(espera / 1000)}s`);
        await dormir(espera);
        if (!parado) await ligar();
      }
    });
  };
  await ligar();
  return { parar: () => { parado = true; clearInterval(resumo); try { sock?.end?.(undefined); } catch { /* ignore */ } } };
}

const SAIDA_DESLOGADO = 78; // a unit tem RestartPreventExitStatus=78: não fica religando sessão encerrada

export async function main(argv = process.argv.slice(2)) {
  const parear = argv.includes('--parear');
  const h = await conectar({
    parear,
    aoPareado: async () => process.exit(0),
    aoDeslogar: async () => process.exit(SAIDA_DESLOGADO),
  });
  for (const s of ['SIGINT', 'SIGTERM']) process.on(s, () => { h.parar(); process.exit(0); });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(() => { console.error('ouvinte: falha ao iniciar'); process.exit(1); });
}
