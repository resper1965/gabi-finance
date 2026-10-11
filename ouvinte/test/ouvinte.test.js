import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { processarEvento } from '../src/ouvinte.js';

const PRIV = '5511912345678@s.whatsapp.net';
const GRUPO = '120363000000000000@g.us';
const PART = '5521987654321@s.whatsapp.net';
const TS = 1791720000; // 2026-10-11T12:00:00Z

const pasta = () => fs.mkdtempSync(path.join(os.tmpdir(), 'ouv-'));
const lista = (p) => fs.readdirSync(p).filter((n) => n.endsWith('.json')).map((n) => JSON.parse(fs.readFileSync(path.join(p, n), 'utf8')));
const msg = (message, key = {}, extra = {}) => ({
  key: { remoteJid: PRIV, fromMe: false, id: 'ID' + Math.random().toString(36).slice(2), ...key }, messageTimestamp: TS, message, ...extra,
});
const ev = (...ms) => ({ type: 'notify', messages: ms });
const deps = (p, o = {}) => ({ pasta: p, baixar: async () => Buffer.from('dados'), palavras: () => [], ...o });

test('texto de conversation vira mensagem com recebida_em com offset', async () => {
  const p = pasta();
  await processarEvento(ev(msg({ conversation: 'oi tudo bem' })), deps(p));
  const [j] = lista(p);
  assert.equal(j.texto, 'oi tudo bem');
  assert.equal(j.de, PRIV);
  assert.equal(j.grupo, false);
  assert.equal(j.id_grupo, null);
  assert.equal(j.anexo, null);
  assert.equal(j.recebida_em, '2026-10-11T12:00:00+00:00');
});

test('texto de extendedTextMessage e legenda de imagem', async () => {
  const p = pasta();
  await processarEvento(ev(
    msg({ extendedTextMessage: { text: 'link aqui' } }),
    msg({ imageMessage: { caption: 'foto da nota', mimetype: 'image/jpeg', fileLength: 10 } }),
  ), deps(p));
  const textos = lista(p).map((j) => j.texto).sort();
  assert.deepEqual(textos, ['foto da nota', 'link aqui']);
});

test('ignora fromMe, status, protocolo, reação, edição e vazio', async () => {
  const p = pasta();
  await processarEvento(ev(
    msg({ conversation: 'eu mesmo' }, { fromMe: true }),
    msg({ conversation: 'status' }, { remoteJid: 'status@broadcast' }),
    msg({ protocolMessage: { type: 0 } }),
    msg({ reactionMessage: { text: '👍' } }),
    msg({ editedMessage: { message: { conversation: 'editada' } } }),
    msg({ senderKeyDistributionMessage: {} }),
    msg(undefined),
  ), deps(p));
  assert.deepEqual(lista(p), []);
});

test('ignora type diferente de notify', async () => {
  const p = pasta();
  await processarEvento({ type: 'append', messages: [msg({ conversation: 'antiga' })] }, deps(p));
  assert.deepEqual(lista(p), []);
});

test('grupo: de é o participante, grupo true e id_grupo', async () => {
  const p = pasta();
  await processarEvento(ev(msg({ conversation: 'no grupo' }, { remoteJid: GRUPO, participant: PART })), deps(p));
  const [j] = lista(p);
  assert.equal(j.grupo, true);
  assert.equal(j.id_grupo, GRUPO);
  assert.equal(j.de, PART);
});

test('mensagem efêmera e visualização única são desembrulhadas', async () => {
  const p = pasta();
  await processarEvento(ev(msg({ ephemeralMessage: { message: { conversation: 'efemera' } } })), deps(p));
  assert.equal(lista(p)[0].texto, 'efemera');
});

test('documento: baixa, grava em anexos/ e referencia o nome', async () => {
  const p = pasta();
  let chamadas = 0;
  await processarEvento(ev(msg({ documentMessage: { mimetype: 'application/pdf', fileLength: 5, caption: 'boleto' } }, { id: 'DOC1' })),
    deps(p, { baixar: async () => { chamadas++; return Buffer.from('%PDF'); } }));
  const [j] = lista(p);
  assert.equal(chamadas, 1);
  assert.equal(j.anexo, 'DOC1.pdf');
  assert.equal(j.texto, 'boleto');
  assert.equal(fs.readFileSync(path.join(p, 'anexos', 'DOC1.pdf')).toString(), '%PDF');
});

test('acima do limite: grava sem anexo e nem baixa', async () => {
  const p = pasta();
  let chamadas = 0;
  const grande = 51 * 1024 * 1024;
  await processarEvento(ev(msg({ documentMessage: { mimetype: 'application/pdf', fileLength: grande, caption: 'enorme' } }, { id: 'BIG' })),
    deps(p, { anexoMaxBytes: 50 * 1024 * 1024, baixar: async () => { chamadas++; return Buffer.alloc(1); } }));
  const [j] = lista(p);
  assert.equal(chamadas, 0);
  assert.equal(j.anexo, null);
  assert.equal(j.texto, 'enorme');
  assert.equal(fs.existsSync(path.join(p, 'anexos')) ? fs.readdirSync(path.join(p, 'anexos')).length : 0, 0);
});

test('download acima do limite depois de baixar também descarta o anexo', async () => {
  const p = pasta();
  await processarEvento(ev(msg({ documentMessage: { mimetype: 'application/pdf' } }, { id: 'B2' })),
    deps(p, { anexoMaxBytes: 3, baixar: async () => Buffer.alloc(10) }));
  assert.equal(lista(p)[0].anexo, null);
});

test('falha no download grava a mensagem sem anexo', async () => {
  const p = pasta();
  await processarEvento(ev(msg({ imageMessage: { mimetype: 'image/png', caption: 'x' } }, { id: 'F1' })),
    deps(p, { baixar: async () => { throw new Error('expirou'); } }));
  assert.equal(lista(p)[0].anexo, null);
});

test('extensão por mimetype, resto vira .bin', async () => {
  const p = pasta();
  const casos = {
    'application/pdf': 'pdf', 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'audio/ogg; codecs=opus': 'ogg',
    'video/mp4': 'mp4', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx', 'text/plain': 'txt',
    'application/x-msdownload': 'bin', 'application/zip': 'bin', '': 'bin',
  };
  let i = 0;
  for (const [mime, ext] of Object.entries(casos)) {
    const id = `E${i++}`;
    await processarEvento(ev(msg({ documentMessage: { mimetype: mime } }, { id })), deps(p));
    assert.ok(fs.existsSync(path.join(p, 'anexos', `${id}.${ext}`)), `${mime} -> ${ext}`);
  }
});

test('palavra de risco toca o gatilho; mensagem comum não', async () => {
  const p = pasta();
  await processarEvento(ev(msg({ conversation: 'tudo certo hoje' })), deps(p, { palavras: () => ['matar'] }));
  assert.equal(fs.existsSync(path.join(p, 'gatilho')), false);
  await processarEvento(ev(msg({ conversation: 'Quero me MATAR' })), deps(p, { palavras: () => ['matar'] }));
  assert.equal(fs.existsSync(path.join(p, 'gatilho')), true);
  assert.equal(lista(p).length, 2);
});

test('mensagem repetida (mesmo id) gera um arquivo só', async () => {
  const p = pasta();
  const m = msg({ conversation: 'oi' }, { id: 'IGUAL' });
  await processarEvento(ev(m), deps(p));
  await processarEvento(ev(m), deps(p));
  assert.equal(lista(p).length, 1);
});

test('nada de texto, número ou nome vai para o console', async () => {
  const p = pasta();
  const saidas = [];
  const orig = {};
  for (const k of ['log', 'info', 'warn', 'error', 'debug']) {
    orig[k] = console[k];
    console[k] = (...a) => saidas.push(a.map(String).join(' '));
  }
  try {
    await processarEvento(ev(
      msg({ conversation: 'segredo-do-texto matar' }, { remoteJid: GRUPO, participant: PART }, { pushName: 'Fulano Secreto' }),
      msg({ documentMessage: { mimetype: 'application/pdf' } }, { id: 'LOGDOC' }),
    ), deps(p, { palavras: () => ['matar'], baixar: async () => { throw new Error('falhou 5511912345678'); } }));
  } finally { Object.assign(console, orig); }
  const tudo = saidas.join('\n');
  for (const s of ['segredo-do-texto', 'Fulano', '5521987654321', '5511912345678', GRUPO]) assert.ok(!tudo.includes(s), s);
});
