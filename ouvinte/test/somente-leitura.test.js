import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { opcoesBaileys } from '../src/ouvinte.js';

const SRC = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'src');
const PROIBIDOS = ['sendMessage', 'sendPresenceUpdate', 'sendReceipt', 'sendReceipts', 'readMessages', 'relayMessage',
  'updateMediaMessage', 'groupParticipantsUpdate', 'updateProfile', 'chatModify', 'presenceSubscribe'];

function arquivos(d) {
  return fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? arquivos(path.join(d, e.name)) : [path.join(d, e.name)]));
}

test('código do ouvinte não contém envio, presença nem recibo', () => {
  const fontes = arquivos(SRC);
  assert.ok(fontes.length >= 3);
  for (const f of fontes) {
    const txt = fs.readFileSync(f, 'utf8');
    for (const p of PROIBIDOS) assert.ok(!txt.includes(p), `${p} em ${path.basename(f)}`);
  }
});

test('opções do Baileys: sem presença, sem histórico, sem eco', () => {
  const o = opcoesBaileys({ state: { creds: {} }, logger: {}, version: [2, 3000, 1] });
  assert.equal(o.markOnlineOnConnect, false);
  assert.equal(o.syncFullHistory, false);
  assert.equal(o.emitOwnEvents, false);
  assert.equal(o.printQRInTerminal, false);
  assert.equal(o.shouldSyncHistoryMessage(), false);
  assert.deepEqual(o.version, [2, 3000, 1]);
});
