import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { carregarPalavras, temRisco, criarRecarregador } from '../src/palavras.js';

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'pal-'));

test('sem acento e sem caixa', () => {
  assert.ok(temRisco('Não aguento MAIS, quero me MATAR', ['matar']));
  assert.ok(temRisco('preciso de ajuda urgente', ['URGÊNCIA', 'Ajuda']));
  assert.ok(!temRisco('tudo bem', ['matar']));
});

test('palavra inteira, não pedaço', () => {
  assert.ok(!temRisco('amatar não', ['matar']));
  assert.ok(!temRisco('matarei', ['matar']));
  assert.ok(temRisco('(matar)', ['matar']));
});

test('expressão de várias palavras', () => {
  assert.ok(temRisco('estou SEM  saída agora', ['sem saída']));
  assert.ok(!temRisco('sem uma saída', ['sem saída']));
});

test('entradas vazias ou texto nulo não casam', () => {
  assert.ok(!temRisco(null, ['matar']));
  assert.ok(!temRisco('oi', ['', '  ']));
  assert.ok(!temRisco('oi', []));
});

test('arquivo ausente, inválido ou de tipo errado dá lista vazia', () => {
  const d = tmp();
  assert.deepEqual(carregarPalavras(path.join(d, 'nao-existe.json')), []);
  fs.writeFileSync(path.join(d, 'a.json'), '{quebrado');
  assert.deepEqual(carregarPalavras(path.join(d, 'a.json')), []);
  fs.writeFileSync(path.join(d, 'b.json'), '{"x":1}');
  assert.deepEqual(carregarPalavras(path.join(d, 'b.json')), []);
  fs.writeFileSync(path.join(d, 'c.json'), '["a", 3, null, "b"]');
  assert.deepEqual(carregarPalavras(path.join(d, 'c.json')), ['a', 'b']);
});

test('recarrega no máximo a cada 60 s e só se o mtime mudou', () => {
  const d = tmp();
  const f = path.join(d, 'p.json');
  fs.writeFileSync(f, '["um"]');
  let t = 1_000_000;
  const pega = criarRecarregador(f, { agora: () => t });
  assert.deepEqual(pega(), ['um']);
  fs.writeFileSync(f, '["dois"]');
  fs.utimesSync(f, 5000, 5000);
  t += 30_000;
  assert.deepEqual(pega(), ['um']);
  t += 31_000;
  assert.deepEqual(pega(), ['dois']);
});
