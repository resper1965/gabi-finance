import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { EventEmitter } from 'node:events';
import { conectar, decidirReconexao, instalarSaidaSegura } from '../src/ouvinte.js';

const RAZAO = { loggedOut: 401, forbidden: 403, connectionReplaced: 440, badSession: 500, restartRequired: 515 };

// Baileys falso: cada chamada a criar() devolve um socket com ev (EventEmitter) e end().
function falso() {
  const socks = [];
  const mod = {
    default: (opcoes) => {
      const s = { ev: new EventEmitter(), end() { s.fim = true; }, opcoes };
      socks.push(s);
      return s;
    },
    DisconnectReason: RAZAO,
    useMultiFileAuthState: async () => ({ state: { creds: {} }, saveCreds: async () => {} }),
    fetchLatestBaileysVersion: async () => ({ version: [2, 3000, 1] }),
    downloadMediaMessage: async () => { throw new Error('não usado'); },
  };
  return { mod, socks };
}
const dir = () => fs.mkdtempSync(path.join(os.tmpdir(), 'con-'));
const fecha = (s, codigo) => s.ev.emit('connection.update', { connection: 'close', lastDisconnect: { error: { output: { statusCode: codigo } } } });
const esperar = async (cond) => { for (let i = 0; i < 200 && !cond(); i++) await new Promise((r) => setTimeout(r, 5)); };

async function cenario(extra = {}) {
  const f = falso();
  const terminou = [];
  const esperas = [];
  const h = await conectar({
    pasta: dir(), authDir: path.join(dir(), 'auth'), carregarBaileys: async () => f.mod,
    dormir: async (ms) => { esperas.push(ms); }, aoTerminar: async (c) => { terminou.push(c); }, ...extra,
  });
  return { f, h, terminou, esperas };
}

test('decidirReconexao: terminais, badSession e backoff', () => {
  const est = { badSession: 0, tentativa: 0 };
  assert.equal(decidirReconexao(401, est, RAZAO).acao, 'terminal');
  assert.equal(decidirReconexao(403, est, RAZAO).acao, 'terminal');
  assert.equal(decidirReconexao(440, est, RAZAO).acao, 'terminal');
  assert.equal(decidirReconexao(500, est, RAZAO).acao, 'retry');
  assert.equal(decidirReconexao(500, est, RAZAO).acao, 'retry');
  assert.equal(decidirReconexao(500, est, RAZAO).acao, 'terminal');
  const e2 = { badSession: 0, tentativa: 0 };
  assert.deepEqual([1, 2, 3].map(() => decidirReconexao(428, e2, RAZAO).espera), [1000, 2000, 4000]);
  assert.equal(decidirReconexao(515, e2, RAZAO).espera, 0);
});

test('decidirReconexao: código desconhecido (undefined/null) nunca é terminal', () => {
  const bruta = { loggedOut: undefined, forbidden: undefined, connectionReplaced: undefined, badSession: undefined, restartRequired: undefined };
  for (const razao of [RAZAO, bruta, {}]) {
    for (const codigo of [undefined, null]) {
      const est = { badSession: 0, tentativa: 0 };
      assert.equal(decidirReconexao(codigo, est, razao).acao, 'retry');
      assert.equal(est.badSession, 0);
    }
  }
});

test('403 e 440 encerram sem religar (exit 78 no main)', async () => {
  for (const codigo of [401, 403, 440]) {
    const { f, terminou } = await cenario();
    fecha(f.socks[0], codigo);
    await esperar(() => terminou.length);
    assert.deepEqual(terminou, [codigo]);
    assert.equal(f.socks.length, 1);
  }
});

test('badSession: religa duas vezes e encerra na terceira seguida; open zera a contagem', async () => {
  const { f, terminou } = await cenario();
  fecha(f.socks[0], 500); await esperar(() => f.socks.length === 2);
  fecha(f.socks[1], 500); await esperar(() => f.socks.length === 3);
  f.socks[2].ev.emit('connection.update', { connection: 'open' });
  fecha(f.socks[2], 500); await esperar(() => f.socks.length === 4);
  fecha(f.socks[3], 500); await esperar(() => f.socks.length === 5);
  assert.deepEqual(terminou, []);
  fecha(f.socks[4], 500); await esperar(() => terminou.length);
  assert.deepEqual(terminou, [500]);
  assert.equal(f.socks.length, 5);
});

test('queda comum religa com backoff e restartRequired religa na hora', async () => {
  const { f, esperas } = await cenario();
  fecha(f.socks[0], 428); await esperar(() => f.socks.length === 2);
  fecha(f.socks[1], 515); await esperar(() => f.socks.length === 3);
  assert.deepEqual(esperas.slice(0, 2), [1000, 0]);
});

test('o socket é criado com as opções somente leitura', async () => {
  const { f } = await cenario();
  const o = f.socks[0].opcoes;
  assert.equal(o.markOnlineOnConnect, false);
  assert.equal(o.syncFullHistory, false);
});

// ---------- saída segura / log ----------
function procFalso() {
  const ev = new EventEmitter();
  const saidas = [];
  return { ev, on: (n, f) => ev.on(n, f), saidas, exit: (c) => saidas.push(`exit:${c}`) };
}
function consoleFalso() {
  const impr = [];
  const c = {};
  for (const k of ['log', 'info', 'warn', 'error', 'debug']) c[k] = (...a) => impr.push(a.map(String).join(' '));
  return { c, impr };
}

test('unhandledRejection/uncaughtException: mensagem genérica, sem payload, exit(1)', () => {
  const proc = procFalso();
  const { c, impr } = consoleFalso();
  instalarSaidaSegura({ proc, con: c, sair: (n) => proc.saidas.push(`exit:${n}`) });
  proc.ev.emit('unhandledRejection', new Error('segredo-5511912345678 texto'), Promise.resolve());
  proc.ev.emit('uncaughtException', Object.assign(new Error('outro-segredo'), { stack: 'pilha-secreta' }));
  assert.deepEqual(proc.saidas, ['exit:1', 'exit:1']);
  const tudo = impr.join('\n');
  for (const s of ['segredo', 'pilha', '5511912345678']) assert.ok(!tudo.includes(s));
  assert.ok(impr.length >= 1);
});

test('console.error/warn de biblioteca não chega ao journal; mensagens ouvinte: passam', () => {
  const proc = procFalso();
  const { c, impr } = consoleFalso();
  instalarSaidaSegura({ proc, con: c, sair: () => {} });
  c.error({ payload: 'segredo' }, 'texto da mensagem');
  c.warn('Closing session: SessionEntry { chave }');
  c.log('dump 5511912345678');
  c.error('ouvinte: sessão encerrada');
  assert.deepEqual(impr, ['ouvinte: sessão encerrada']);
});
