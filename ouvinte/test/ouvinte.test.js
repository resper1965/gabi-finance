import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Readable } from 'node:stream';
import { processarEvento, criarGatilho } from '../src/ouvinte.js';

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

// ---------- @lid ----------
test('privado com remoteJid @lid e senderPn: de é o telefone, sem lid', async () => {
  const p = pasta();
  await processarEvento(ev(msg({ conversation: 'oi' }, { remoteJid: '123456789@lid', senderPn: PRIV })), deps(p));
  const [j] = lista(p);
  assert.equal(j.de, PRIV);
  assert.equal('lid' in j, false);
});

test('privado: remoteJidAlt (v7) quando não há senderPn', async () => {
  const p = pasta();
  await processarEvento(ev(msg({ conversation: 'oi' }, { remoteJid: '123456789@lid', remoteJidAlt: PRIV })), deps(p));
  assert.equal(lista(p)[0].de, PRIV);
});

test('grupo: participantPn vence participant @lid', async () => {
  const p = pasta();
  await processarEvento(ev(msg({ conversation: 'g' }, { remoteJid: GRUPO, participant: '999@lid', participantPn: PART })), deps(p));
  const [j] = lista(p);
  assert.equal(j.de, PART);
  assert.equal(j.id_grupo, GRUPO);
  assert.equal('lid' in j, false);
});

test('só @lid: guarda como veio com lid:true (privado e grupo)', async () => {
  const p = pasta();
  await processarEvento(ev(
    msg({ conversation: 'a' }, { remoteJid: '123456789@lid', id: 'L1' }),
    msg({ conversation: 'b' }, { remoteJid: GRUPO, participant: '999@lid', id: 'L2' }),
  ), deps(p));
  const por = Object.fromEntries(lista(p).map((j) => [j.id_externo, j]));
  assert.equal(por.L1.de, '123456789@lid');
  assert.equal(por.L1.lid, true);
  assert.equal(por.L2.de, '999@lid');
  assert.equal(por.L2.lid, true);
});

// ---------- download em fluxo com teto ----------
const doc = (extra = {}) => ({ documentMessage: { mimetype: 'application/pdf', ...extra } });
const MB = 1024 * 1024;

test('declarou pequeno mas o fluxo é grande: corta no teto, sem bufferizar tudo e sem anexo', async () => {
  const p = pasta();
  let puxados = 0;
  let fonte;
  const baixar = async () => {
    fonte = Readable.from((async function* () { for (let i = 0; i < 1000; i++) { puxados++; yield Buffer.alloc(MB); } })());
    return fonte;
  };
  const c = {};
  await processarEvento(ev(msg(doc({ fileLength: 10 }), { id: 'S1' }), msg({ conversation: 'depois' }, { id: 'S2' })),
    deps(p, { baixar, anexoMaxBytes: 3 * MB, contadores: c }));
  const por = Object.fromEntries(lista(p).map((j) => [j.id_externo, j]));
  assert.equal(por.S1.anexo, null);
  assert.equal(por.S2.texto, 'depois');
  assert.ok(puxados <= 10, `puxou ${puxados} MB`);
  assert.equal(fonte.destroyed, true);
  assert.equal(c.anexo_descartado, 1);
});

test('fluxo parado: estoura o prazo, grava sem anexo e a fila segue', async () => {
  const p = pasta();
  let fonte;
  const baixar = async () => { fonte = new Readable({ read() {} }); return fonte; };
  const t0 = Date.now();
  await processarEvento(ev(msg(doc(), { id: 'P1' }), msg({ conversation: 'proxima' }, { id: 'P2' })),
    deps(p, { baixar, downloadTimeoutMs: 80 }));
  assert.ok(Date.now() - t0 < 2000);
  const por = Object.fromEntries(lista(p).map((j) => [j.id_externo, j]));
  assert.equal(por.P1.anexo, null);
  assert.equal(por.P2.texto, 'proxima');
  assert.equal(fonte.destroyed, true);
});

test('fileLength ausente, 0 ou estranho: tamanho desconhecido, o fluxo é que limita', async () => {
  const p = pasta();
  const baixar = async () => Readable.from([Buffer.from('%PDF-ok')]);
  let i = 0;
  for (const fl of [undefined, 0, 'abc', null, -5, { low: 7, high: 0 }]) {
    const id = `FL${i++}`;
    await processarEvento(ev(msg(doc(fl === undefined ? {} : { fileLength: fl }), { id })), deps(p, { baixar }));
  }
  const l = lista(p);
  assert.equal(l.length, 6);
  for (const j of l) assert.match(j.anexo, /\.pdf$/);
});

test('fluxo parado acima do teto declarado nem é aberto', async () => {
  const p = pasta();
  let abriu = 0;
  await processarEvento(ev(msg(doc({ fileLength: 100 * MB }), { id: 'G1' })), deps(p, { anexoMaxBytes: 50 * MB, baixar: async () => { abriu++; return Readable.from([]); } }));
  assert.equal(abriu, 0);
});

// ---------- nomes de anexo ----------
test('ids a:b e a_b geram anexos diferentes e o segundo nunca substitui o primeiro', async () => {
  const p = pasta();
  await processarEvento(ev(msg(doc(), { id: 'a:b' })), deps(p, { baixar: async () => Readable.from([Buffer.from('um')]) }));
  await processarEvento(ev(msg(doc(), { id: 'a_b' })), deps(p, { baixar: async () => Readable.from([Buffer.from('dois')]) }));
  const l = lista(p);
  assert.equal(l.length, 2);
  assert.notEqual(l[0].anexo, l[1].anexo);
  const conteudos = l.map((j) => fs.readFileSync(path.join(p, 'anexos', j.anexo), 'utf8')).sort();
  assert.deepEqual(conteudos, ['dois', 'um']);
});

// ---------- erros de gravação ----------
test('disco cheio vira contador e não derruba as outras mensagens', async () => {
  const p = pasta();
  const c = {};
  let n = 0;
  const gravar = (m, pa, o) => {
    if (n++ === 0) { const e = new Error('cheio'); e.code = 'ENOSPC'; throw e; }
    return { gravado: true, arquivo: 'x.json' };
  };
  await processarEvento(ev(msg({ conversation: 'a' }), msg({ conversation: 'b' })), deps(p, { gravar, contadores: c }));
  assert.equal(c.disco_cheio, 1);
  assert.equal(c.gravadas, 1);
});

// ---------- v7: remoteJidAlt/participantAlt só quando o primário é @lid ----------
test('v7: primário telefone + LID em remoteJidAlt mantém o telefone', async () => {
  const p = pasta();
  await processarEvento(ev(
    msg({ conversation: 'a' }, { remoteJid: PRIV, remoteJidAlt: '123456789@lid', id: 'V1' }),
    msg({ conversation: 'b' }, { remoteJid: GRUPO, participant: PART, participantAlt: '999@lid', id: 'V2' }),
  ), deps(p));
  const por = Object.fromEntries(lista(p).map((j) => [j.id_externo, j]));
  assert.equal(por.V1.de, PRIV);
  assert.equal(por.V2.de, PART);
  assert.equal('lid' in por.V1 || 'lid' in por.V2, false);
});

test('v7: primário @lid + telefone em remoteJidAlt/participantAlt usa o telefone', async () => {
  const p = pasta();
  await processarEvento(ev(
    msg({ conversation: 'a' }, { remoteJid: '123@lid', remoteJidAlt: PRIV, id: 'V3' }),
    msg({ conversation: 'b' }, { remoteJid: GRUPO, participant: '999@lid', participantAlt: PART, id: 'V4' }),
  ), deps(p));
  const por = Object.fromEntries(lista(p).map((j) => [j.id_externo, j]));
  assert.equal(por.V3.de, PRIV);
  assert.equal(por.V4.de, PART);
});

test('I6: gatilho limitado a 1 vez a cada 60 s', () => {
  let t = 1_000_000;
  const toques = [];
  const g = criarGatilho('/x', { agora: () => t, tocar: (pasta) => toques.push(pasta) });
  assert.equal(g(), true);
  t += 30_000;
  assert.equal(g(), false);
  t += 30_000;
  assert.equal(g(), true);
  assert.deepEqual(toques, ['/x', '/x']);
});

test('I6: rajada de mensagens de risco toca o gatilho uma vez só', async () => {
  const p = pasta();
  const c = {};
  let toques = 0;
  const gatilho = criarGatilho(p, { agora: () => 5, tocar: () => { toques++; } });
  await processarEvento(ev(msg({ conversation: 'matar' }), msg({ conversation: 'matar' }), msg({ conversation: 'matar' })),
    deps(p, { palavras: () => ['matar'], gatilho, contadores: c }));
  assert.equal(toques, 1);
  assert.equal(c.gatilhos, 1);
  assert.equal(c.gatilhos_limitados, 2);
  assert.equal(lista(p).length, 3);
});
