import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const RAIZ = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const lock = JSON.parse(fs.readFileSync(path.join(RAIZ, 'package-lock.json'), 'utf8'));
const pkg = JSON.parse(fs.readFileSync(path.join(RAIZ, 'package.json'), 'utf8'));

test('lock sem git+/ssh:// em resolved e toda entrada (menos a raiz) com integrity', () => {
  for (const [nome, v] of Object.entries(lock.packages)) {
    if (nome === '') continue;
    assert.ok(v.integrity, `sem integrity: ${nome}`);
    assert.ok(!/^(git\+|ssh:\/\/|git:\/\/)/.test(v.resolved ?? ''), `resolved git/ssh: ${nome}`);
    assert.ok(!/ssh:\/\/|git\+/.test(v.resolved ?? ''), nome);
  }
});

test('sharp e @img não entram no lock', () => {
  const ruins = Object.keys(lock.packages).filter((n) => /node_modules\/(sharp|@img\/)/.test(n));
  assert.deepEqual(ruins, []);
});

test('libsignal vem do tarball vendorizado, com o integrity batendo com o arquivo', () => {
  assert.equal(pkg.overrides.libsignal, 'file:vendor/libsignal-node-bcea72d.tgz');
  const e = lock.packages['node_modules/libsignal'];
  assert.equal(e.resolved, 'file:vendor/libsignal-node-bcea72d.tgz');
  const bytes = fs.readFileSync(path.join(RAIZ, 'vendor', 'libsignal-node-bcea72d.tgz'));
  assert.equal(e.integrity, `sha512-${crypto.createHash('sha512').update(bytes).digest('base64')}`);
});
