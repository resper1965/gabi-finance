import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { gravarMensagem, tocarGatilho } from '../src/spool.js';

const nova = () => fs.mkdtempSync(path.join(os.tmpdir(), 'spool-'));
const base = (o = {}) => ({
  id_externo: 'ABC123', de: '5511912345678@s.whatsapp.net', grupo: false, id_grupo: null,
  recebida_em: '2026-10-11T12:00:00+00:00', texto: 'oi', anexo: null, ...o,
});

test('grava arquivo no formato esperado', () => {
  const p = nova();
  const r = gravarMensagem(base(), p);
  assert.equal(r.gravado, true);
  const j = JSON.parse(fs.readFileSync(path.join(p, r.arquivo), 'utf8'));
  assert.deepEqual(j, base());
  assert.deepEqual(Object.keys(j).sort(), ['anexo', 'de', 'grupo', 'id_externo', 'id_grupo', 'recebida_em', 'texto']);
  assert.match(r.arquivo, /\.json$/);
});

test('modo 0660 e nenhum .tmp sobra', () => {
  const p = nova();
  const r = gravarMensagem(base(), p);
  assert.equal(fs.statSync(path.join(p, r.arquivo)).mode & 0o777, 0o660);
  assert.deepEqual(fs.readdirSync(p).filter((n) => n.endsWith('.tmp')), []);
});

test('mesmo id_externo duas vezes grava um', () => {
  const p = nova();
  assert.equal(gravarMensagem(base(), p).gravado, true);
  const r2 = gravarMensagem(base({ texto: 'outro' }), p);
  assert.equal(r2.gravado, false);
  assert.equal(fs.readdirSync(p).filter((n) => n.endsWith('.json')).length, 1);
  assert.equal(JSON.parse(fs.readFileSync(path.join(p, r2.arquivo), 'utf8')).texto, 'oi');
});

test('id já consumido pelo brain (lidos/) não é regravado', () => {
  const p = nova();
  const r = gravarMensagem(base(), p);
  fs.mkdirSync(path.join(p, 'lidos'));
  fs.renameSync(path.join(p, r.arquivo), path.join(p, 'lidos', r.arquivo));
  assert.equal(gravarMensagem(base(), p).gravado, false);
  assert.deepEqual(fs.readdirSync(p).filter((n) => n.endsWith('.json')), []);
});

test('o .json.tmp nunca é visível como .json: o json só aparece completo', () => {
  const p = nova();
  const vistos = [];
  const orig = fs.linkSync;
  const origRen = fs.renameSync;
  const espia = (nome, f) => (...a) => {
    for (const n of fs.readdirSync(p)) vistos.push(n);
    return f(...a);
  };
  fs.linkSync = espia('link', orig);
  fs.renameSync = espia('rename', origRen);
  try { gravarMensagem(base(), p); } finally { fs.linkSync = orig; fs.renameSync = origRen; }
  assert.ok(vistos.length > 0);
  assert.ok(vistos.every((n) => !n.endsWith('.json')), 'nenhum .json antes da publicação');
  assert.ok(vistos.some((n) => n.endsWith('.json.tmp')));
});

test('anexo é gravado em anexos/ ANTES do json', () => {
  const p = nova();
  const ordem = [];
  const origW = fs.writeFileSync;
  fs.writeFileSync = (f, ...a) => { ordem.push(String(f)); return origW(f, ...a); };
  let r;
  try {
    r = gravarMensagem(base({ anexo: 'ABC123.pdf', texto: null }), p, { anexo: { nome: 'ABC123.pdf', dados: Buffer.from('%PDF-1') } });
  } finally { fs.writeFileSync = origW; }
  const iAnexo = ordem.findIndex((f) => f.includes(`${path.sep}anexos${path.sep}`));
  const iJson = ordem.findIndex((f) => f.endsWith('.json.tmp'));
  assert.ok(iAnexo >= 0 && iJson >= 0 && iAnexo < iJson);
  assert.equal(fs.readFileSync(path.join(p, 'anexos', 'ABC123.pdf')).toString(), '%PDF-1');
  assert.equal(fs.statSync(path.join(p, 'anexos', 'ABC123.pdf')).mode & 0o777, 0o660);
  assert.equal(JSON.parse(fs.readFileSync(path.join(p, r.arquivo), 'utf8')).anexo, 'ABC123.pdf');
});

test('nomes com separadores ou .. são recusados', () => {
  const p = nova();
  for (const id of ['../x', 'a/b', 'a\\b', '..', '', 'a\0b']) {
    assert.throws(() => gravarMensagem(base({ id_externo: id }), p), /id_externo/);
  }
  for (const nome of ['../x.pdf', 'a/b.pdf', 'a\\b.pdf', '..', '.', '']) {
    assert.throws(() => gravarMensagem(base({ anexo: nome }), p, { anexo: { nome, dados: Buffer.from('x') } }), /anexo/);
  }
  assert.deepEqual(fs.readdirSync(p), []);
});

test('id com caracteres estranhos vira nome seguro e distinto', () => {
  const p = nova();
  const a = gravarMensagem(base({ id_externo: 'a:b' }), p);
  const b = gravarMensagem(base({ id_externo: 'a_b' }), p);
  assert.equal(a.gravado && b.gravado, true);
  assert.notEqual(a.arquivo, b.arquivo);
  assert.match(a.arquivo, /^[A-Za-z0-9._-]+\.json$/);
});

test('tocarGatilho cria e atualiza gatilho', () => {
  const p = nova();
  tocarGatilho(p);
  const g = path.join(p, 'gatilho');
  assert.ok(fs.statSync(g).isFile());
  fs.utimesSync(g, 1000, 1000);
  tocarGatilho(p);
  assert.ok(fs.statSync(g).mtimeMs > 2000 * 1000);
});
