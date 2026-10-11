import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { gravarMensagem, tocarGatilho, nomeDoId, nomeAnexo } from '../src/spool.js';

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

test('anexo com separadores ou .. é recusado (nome vem de fora)', () => {
  const p = nova();
  for (const nome of ['../x.pdf', 'a/b.pdf', 'a\\b.pdf', '..', '.', '']) {
    assert.throws(() => gravarMensagem(base({ anexo: nome }), p, { anexo: { nome, dados: Buffer.from('x') } }), /anexo/);
  }
  assert.deepEqual(fs.readdirSync(p), []);
});

test('id com separador ou .. nunca derruba a mensagem: vira nome seguro com hash', () => {
  const p = nova();
  const nomes = [];
  for (const id of ['../x', 'a/b', 'a\\b', '..', 'x..y', '.oculto']) {
    const r = gravarMensagem(base({ id_externo: id }), p);
    assert.equal(r.gravado, true, id);
    assert.match(r.arquivo, /^[A-Za-z0-9_-][A-Za-z0-9._-]*\.json$/);
    assert.ok(!r.arquivo.includes('..'));
    nomes.push(r.arquivo);
  }
  assert.equal(new Set(nomes).size, nomes.length);
  assert.deepEqual(fs.readdirSync(p).filter((n) => n.endsWith('.json')).sort(), nomes.sort());
  assert.throws(() => gravarMensagem(base({ id_externo: '' }), p), /id_externo/);
  assert.equal(gravarMensagem(base({ id_externo: 'a\0b' }), p).gravado, true);
});

test('nomes reservados (palavras-risco, gatilho) ganham sufixo de hash', () => {
  const p = nova();
  for (const id of ['palavras-risco', 'gatilho', 'Palavras-Risco']) {
    const r = gravarMensagem(base({ id_externo: id }), p);
    assert.notEqual(r.arquivo, `${id}.json`);
    assert.match(r.arquivo, /-[0-9a-f]{12}\.json$/);
  }
});

test('tmp é aberto com wx: symlink plantado em .json.tmp não é seguido', () => {
  const p = nova();
  const vitima = path.join(nova(), 'vitima.txt');
  fs.writeFileSync(vitima, 'intacto');
  const nome = nomeDoId('SYM1');
  fs.symlinkSync(vitima, path.join(p, `${nome}.json.tmp`));
  const r = gravarMensagem(base({ id_externo: 'SYM1' }), p);
  assert.equal(r.gravado, true);
  assert.equal(fs.readFileSync(vitima, 'utf8'), 'intacto');
  assert.equal(fs.lstatSync(path.join(p, r.arquivo)).isFile(), true);
});

test('falha de escrita (disco cheio) limpa o tmp e propaga o erro', () => {
  const p = nova();
  const orig = fs.writeFileSync;
  fs.writeFileSync = (f, ...a) => {
    if (String(f).endsWith('.json.tmp')) { orig(f, 'parcial', { flag: 'wx' }); const e = new Error('cheio'); e.code = 'ENOSPC'; throw e; }
    return orig(f, ...a);
  };
  try { assert.throws(() => gravarMensagem(base(), p), { code: 'ENOSPC' }); } finally { fs.writeFileSync = orig; }
  assert.deepEqual(fs.readdirSync(p), []);
});

test('fsync do arquivo antes de publicar', () => {
  const p = nova();
  const eventos = [];
  const of = fs.fsyncSync, ol = fs.linkSync;
  fs.fsyncSync = (...a) => { eventos.push('fsync'); return of(...a); };
  fs.linkSync = (...a) => { eventos.push('link'); return ol(...a); };
  try { gravarMensagem(base(), p); } finally { fs.fsyncSync = of; fs.linkSync = ol; }
  assert.ok(eventos.indexOf('fsync') >= 0 && eventos.indexOf('fsync') < eventos.indexOf('link'));
});

test('anexo existente nunca é sobrescrito', () => {
  const p = nova();
  gravarMensagem(base({ id_externo: 'U1', anexo: 'mesmo.pdf' }), p, { anexo: { nome: 'mesmo.pdf', dados: Buffer.from('primeiro') } });
  gravarMensagem(base({ id_externo: 'U2', anexo: 'mesmo.pdf' }), p, { anexo: { nome: 'mesmo.pdf', dados: Buffer.from('segundo') } });
  assert.equal(fs.readFileSync(path.join(p, 'anexos', 'mesmo.pdf'), 'utf8'), 'primeiro');
});

test('nomeAnexo: id estranho, nome distinto e limite de tamanho', () => {
  assert.notEqual(nomeAnexo('a:b', 'pdf'), nomeAnexo('a_b', 'pdf'));
  assert.equal(nomeAnexo('ABC', 'pdf'), 'ABC.pdf');
  assert.ok(nomeAnexo('x'.repeat(500), 'pdf').length <= 140);
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
