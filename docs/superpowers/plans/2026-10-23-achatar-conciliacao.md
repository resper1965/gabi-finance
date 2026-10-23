# Achatar compromissos e conciliação — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** trocar a conciliação portada do gabi-fin (6 estados, 8 regras, float) por uma de 4 estados, regras simples e centavos, sem mudar o que o Ricardo vê além disso.

**Architecture:** `compromissos.gerar` passa a trabalhar em centavos (converte os Cadastros na entrada; `FontesBanco` entrega centavos). `conciliacao.conciliar` é reescrito: casamento em ordem de vencimento, um lançamento por compromisso. Os consumidores (contas a pagar, projeção, avisos, agenda financeira) reconhecem débito automático pela `forma`. Uma cópia do código antigo em `tools/_conciliacao_antiga/` alimenta a comparação que o Ricardo roda antes do merge.

**Tech Stack:** Python 3 (stdlib, sqlite3), pytest; painel React/TS (vitest) sem mudança esperada.

**Spec:** `docs/superpowers/specs/2026-10-23-achatar-conciliacao-design.md`

## Global Constraints
- Estados gravados em `compromisso.estado`: só `pago`, `aberto`, `atrasado`, `a_conferir`.
- Valores em centavos (int) dentro de `gerar` e `conciliar`; conversão de reais só na entrada de `gerar` (`gabi.dinheiro.valor.para_centavos`).
- `tolerancia_valor` vem em reais na planilha: usar `round(tolerancia_valor * 100)` centavos. `tolerancia_fixo` é fração. `tolerancia_juros` é ignorado (continua aceito pela planilha).
- Interface pública mantida: `compromissos.gerar(fontes, leitura, docs, hoje, invalidas=None)` e `conciliacao.conciliar(comps, txs, vinculos, estado_contas, pagos, params, hoje, agora, donos=None) -> (res, novos)`; `conciliacao.CONFIRMADO` continua exportado.
- `_serie` continua em `compromissos.py` (usado por `planilha.py` e `rotas/cadastros.py`).
- Nada de push, merge ou instalação sem autorização do Ricardo. Leitura do banco de produção e sudo: script para o Ricardo rodar com `!`.
- Ler o resumo do pytest (não confiar no exit code de pipeline).
- Trabalhar na branch `feat/conciliacao-achatada`.

## Review Focus
1. Débito automático sem lançamento não pode entrar no aviso "vence hoje" nem virar atrasado — `avisos.py:352` filtra só por estado; com `debito_automatico` virando `aberto`, precisa filtrar `forma`. Teste na Task 3.
2. Linhas antigas fora da janela de 2 meses ficam no banco com `previsto`/`debito_automatico` e `dados.diferenca` em reais — migração 0080 normaliza o estado; `contas_pagar` lê `diferenca_centavos` com recuo para `diferenca`. Testes na Task 3.
3. Dois meses da mesma linha e um só Pix atrasado: o lançamento fica com o mês vencido, o mês seguinte segue `aberto`. Teste na Task 2.
4. Lançamento com vínculo gravado a um compromisso de outra rodada não pode pagar outro compromisso. Teste na Task 2.
5. Pagamento de fatura com valor igual a uma conta comum não paga a conta comum (só fatura). Teste na Task 2.

---

### Task 1: Guardar o código antigo e ferramenta de comparação

**Files:**
- Create: `tools/_conciliacao_antiga/__init__.py`, `tools/_conciliacao_antiga/compromissos.py`, `tools/_conciliacao_antiga/conciliacao.py`, `tools/_conciliacao_antiga/fontes.py`
- Create: `tools/comparar_conciliacao.py`
- Test: `tests/test_comparar_conciliacao.py`

**Interfaces:**
- Produces: `tools.comparar_conciliacao._rodar_novo(con, hoje, agora) -> dict[comp_id, (nome, vencimento, estado, motivo)]` (mesmo formato de `rodar_antigo`); `tools.comparar_conciliacao.comparar(con, hoje: date, agora: datetime) -> list[dict]` com chaves `id, nome, vencimento, antes, depois, motivo` (só estados que mudaram, sem `previsto→aberto` e `debito_automatico→aberto`); `main(argv) -> int`.

- [ ] **Step 1:** Criar a branch `feat/conciliacao-achatada`. Copiar `gabi/dinheiro/compromissos.py` e `conciliacao.py` como estão para `tools/_conciliacao_antiga/`; no `conciliacao.py` copiado, importar `_contem, _norm, _serie` da cópia local. Em `fontes.py`, copiar de `gabi/dinheiro/repositorio.py` a versão atual (float) de `FontesBanco`, `txs_para_conciliar`, `_real` e `_cent`, e uma função `rodar_antigo(con, hoje, agora) -> dict[comp_id, (nome, vencimento, estado, motivo)]` que faz o mesmo que `contas_pagar.atualizar_compromissos` sem gravar (lê `repositorio.ler_leitura`, `estado_contas`, `vinculos`, `titulares` do código atual, que não mudam).
- [ ] **Step 2: teste que falha** em `tests/test_comparar_conciliacao.py`:

```python
def test_sem_mudanca_de_codigo_nao_ha_diferenca(con_cenario):
    assert comparar(con_cenario, date(2026, 10, 8), datetime.fromisoformat("2026-10-08T15:00:00-03:00")) == []

def test_trocas_esperadas_nao_aparecem(monkeypatch, con_cenario):
    hoje, agora = date(2026, 10, 8), datetime.fromisoformat("2026-10-08T15:00:00-03:00")
    antigo = rodar_antigo(con_cenario, hoje, agora)
    assert {v[2] for v in antigo.values()} & {"previsto", "debito_automatico"}  # o cenário base tem os dois
    novo = {k: (n, v, "aberto" if e in ("previsto", "debito_automatico") else e, m) for k, (n, v, e, m) in antigo.items()}
    monkeypatch.setattr(comparar_conciliacao, "_rodar_novo", lambda *a: novo)
    assert comparar(con_cenario, hoje, agora) == []

def test_estado_que_muda_aparece(monkeypatch, con_cenario):
    hoje, agora = date(2026, 10, 8), datetime.fromisoformat("2026-10-08T15:00:00-03:00")
    antigo = rodar_antigo(con_cenario, hoje, agora)
    cid, (n, v, e, m) = next((k, x) for k, x in antigo.items() if x[2] == "pago")
    monkeypatch.setattr(comparar_conciliacao, "_rodar_novo", lambda *a: {**antigo, cid: (n, v, "atrasado", None)})
    assert comparar(con_cenario, hoje, agora) == [{"id": cid, "nome": n, "vencimento": v, "antes": "pago", "depois": "atrasado", "motivo": None}]

def test_main_le_o_banco_so_leitura(tmp_path):
    # banco em arquivo; depois de main(["--banco", str(p), "--hoje", "2026-10-08"]) o arquivo não mudou (mtime e conteúdo)
```

`con_cenario`: banco migrado carregado com o cenário `base` (usar `carregar_cenario` de `tests/dinheiro/test_pipeline_compromissos.py`; mover o helper para `tests/dinheiro/cenarios.py` se precisar importar).
- [ ] **Step 3:** Rodar `pytest tests/test_comparar_conciliacao.py -q` → FAIL (módulo não existe).
- [ ] **Step 4:** Implementar `comparar` (roda `rodar_antigo` e o novo `gerar`+`conciliar` de `gabi.dinheiro`, ambos sem gravar) e `main`: `--banco` (padrão `/var/lib/gabi-brain/gabi.db`), `--hoje` opcional; abre com `sqlite3.connect(f"file:{banco}?mode=ro", uri=True)`, copia para memória com `.backup`, roda `comparar` e imprime uma linha por diferença: `id | nome | vencimento | antes → depois | motivo`, e no fim `N diferença(s)`.
- [ ] **Step 5:** `pytest tests/test_comparar_conciliacao.py -q` → PASS.
- [ ] **Step 6:** Criar `~/comparar-conciliacao.sh` no mesmo padrão de usuário/venv de `~/instalar-ajustes-familia.sh`, rodando `python -m tools.comparar_conciliacao` a partir do checkout da branch. Commit: `chore(conciliacao): guarda o código antigo e compara antigo x novo`.

### Task 2: Núcleo em centavos e conciliação nova

**Files:**
- Modify: `gabi/dinheiro/compromissos.py`, `gabi/dinheiro/conciliacao.py` (reescrito), `gabi/dinheiro/repositorio.py:17-24,80-115,132-160`
- Create: `tests/dinheiro/test_conciliacao.py`, `tests/dinheiro/cenarios.json` (só as `entrada` dos 8 cenários de `tests/golden/cenarios.json`, sem `saida`)
- Delete: `tests/golden/cenarios.json`, `tests/dinheiro/test_golden_cenarios.py`, a seção "cenários completos" de `tools/golden.py` (`_L`, `_entrada_base`, `CENARIOS`, `_w_cenario` e a entrada `"cenarios"`), a chave `"cenarios"` de `tests/test_golden_meta.py`
- Modify: `tests/dinheiro/test_pipeline_compromissos.py` (lê `tests/dinheiro/cenarios.json`; sai `test_banco_novo_reproduz_o_gabi_fin`; os demais testes ficam)

**Interfaces:**
- Consumes: nada das outras tasks.
- Produces: compromisso (dict de `gerar`) com `valor_centavos: int|None` no lugar de `valor`; resultado por compromisso `{estado, metodo, tx_id, pago_em, diferenca_centavos, motivo}`; `novos = [(tx_id, comp_id, metodo, diferenca_centavos)]`; `FontesBanco.debitos` → `(descricao, valor_centavos, data, account_id, id)`; `FontesBanco.faturas` → `total_centavos`; `FontesBanco.anterior` → `{id: (valor_centavos, valor_fonte)}`; `txs_para_conciliar` → `valor_centavos`.

- [ ] **Step 1: testes que falham** em `tests/dinheiro/test_conciliacao.py`, chamando `conciliar` direto com compromissos montados à mão (helper `_comp(id, venc, valor_centavos=None, valor_tipo="fixo", valor_fonte="padrao", forma="pix", chaves=("FAVORECIDO",), linha_id=None, **kw)` e `_tx(id, data, valor_centavos, descricao, account_id="c1", tipo_conta="BANK")`; params `{"janela_antes_dias": 10, "tolerancia_fixo": 0.01, "tolerancia_valor": 1.0, "horas_conta_parada": 24}`; hoje 2026-10-08). Um teste por regra, nomes e asserções:
  - `test_vinculo_gravado_paga_e_tira_o_lancamento_do_jogo`: vínculo `{t1: A}`; B com a mesma chave e mesmo valor → A `pago` metodo `favorecido`, B `atrasado`.
  - `test_vinculo_de_outra_rodada_nao_paga_outro` (Review Focus 4): vínculo `{t1: "x:2026-09"}` inexistente em comps; A casa t1 por favorecido → A não recebe t1.
  - `test_transferencia_propria_e_conta_pj_ficam_fora`: tx com `natureza="neutro"` e tx de conta com `pj=1` → compromisso `atrasado`.
  - `test_favorecido_na_janela_paga` / `test_favorecido_fora_da_janela_nao_paga` (11 dias antes do `vencimento_util`).
  - `test_pix_atrasado_fica_com_o_mes_vencido` (Review Focus 3): A out (venc 2026-10-05) e A nov (venc 2026-11-05), um Pix em 2026-10-07 → out `pago`, nov `aberto`.
  - `test_mais_proximo_do_vencimento_ganha`: dois Pix ao mesmo favorecido → fica o de data mais próxima; empate, id menor.
  - `test_por_valor_so_sem_favorecido_de_ninguem`: tx de valor igual cuja descrição contém chave de outro compromisso → não paga por valor.
  - `test_pagamento_de_fatura_so_paga_fatura` (Review Focus 5): tx "PAGAMENTO FATURA" de valor igual a um boleto → boleto `atrasado`.
  - `test_fatura_casa_pelo_nome_do_cartao` (metodo `emissor`).
  - `test_fixo_dentro_da_tolerancia_paga`, `test_fixo_a_menor_vai_a_conferir` (motivo `"pago a menor: R$ 1.900,00 de R$ 2.000,00"`, sem vínculo em `novos`), `test_fatura_a_menor_diz_minimo` (`"pago a menor (mínimo?): ..."`), `test_fixo_acima_vai_a_conferir` (motivo começa com `"pago acima: "`).
  - `test_variavel_estimado_aceita_qualquer_valor`, `test_variavel_confirmado_a_menor_vai_a_conferir`.
  - `test_fatura_paid_sem_lancamento_e_pago` (metodo `banco`).
  - `test_baixa_manual_sem_lancamento_e_pago` (`tx_id == "manual:<id>"`, em `novos`) e `test_baixa_manual_com_lancamento_vale_o_extrato`.
  - `test_debito_automatico_vencido_sem_lancamento_fica_aberto`.
  - `test_extrato_parado_vira_a_conferir` (motivo `"extrato parado desde dd/mm"`).
  - `test_vencido_sem_nada_e_atrasado`, `test_nao_vencido_e_aberto` (inclusive com valor estimado), `test_nunca_ha_previsto_nem_debito_automatico` (conjunto de estados ⊆ os 4).
  - `test_diferenca_em_centavos` (`diferenca_centavos == -100` para pago 1990,00 de 2000,00 com tolerância 1%).
- [ ] **Step 2:** `pytest tests/dinheiro/test_conciliacao.py -q` → FAIL.
- [ ] **Step 3: reescrever `gabi/dinheiro/conciliacao.py`** seguindo a seção 2 da spec, na ordem dela. Manter `CONFIRMADO`, `_casa_emissor`, `_parada`, `_neutro`, `_corrente`, `_brl`, `_ddmm`. Remover `_avalia`/`_certeza`/`_ordenar`/`_atribui`, a faixa de juros e o campo `juros`, a regra do cartão ambíguo e "perdeu no empate". Algoritmo do casamento (o que a assinatura não determina):

```python
for comp in sorted(abertos, key=lambda c: (c["vencimento_util"], c["id"])):
    cands = [t for t in pool if t["id"] not in usados and na_janela(comp, t) and _metodo_chave(comp, t)]
    if not cands and comp["valor_centavos"] is not None:
        cands = [t for t in pool if t["id"] not in usados and na_janela(comp, t) and t["id"] not in com_chave
                 and abs(abs(t["valor_centavos"]) - comp["valor_centavos"]) <= tol_valor
                 and (_eh_fatura(comp) or not caixa.FATURA_RE.search(t.get("descricao") or ""))]
    if cands:
        tx = min(cands, key=lambda t: (abs((_dia(t["data"]) - _dia(comp["vencimento_util"])).days), t["id"]))
        usados.add(tx["id"]); ...  # estado pelo valor (passo 5 da spec)
```

O lançamento que dá `a_conferir` também sai do pool (não paga outro), mas não vai para `novos`.
- [ ] **Step 4: `compromissos.py` em centavos:** na entrada de `gerar`, converter `linha["valor_padrao"]` e `valores[*]["valor"]` com `para_centavos` (sem mutar `leitura`); documentos (`d["valor"]`, reais) idem; `ultimos_pagamentos` passa a ler centavos de `fontes.debitos`. O dict de saída troca `valor` por `valor_centavos`. Juntar `_contem`/`_chaves` numa só função usada pelos dois módulos (`contem_chave(chaves, texto) -> bool`). Atualizar a docstring (tirar "portado SEM alterar a lógica").
- [ ] **Step 5: `repositorio.py`:** `FontesBanco.debitos/faturas/anterior` e `txs_para_conciliar` devolvem centavos (sem `_real`); `gravar_resultado` grava `comp["valor_centavos"]` e `diferenca_centavos` direto; `dados` passa a guardar `diferenca_centavos` (sem `juros`). Atualizar a docstring do módulo (fronteira em centavos).
- [ ] **Step 6:** Em `tests/test_comparar_conciliacao.py`, `test_sem_mudanca_de_codigo_nao_ha_diferenca` passa a ser `test_comparacao_roda_no_cenario_base` (devolve lista; cada item tem as 6 chaves e `antes != depois`). Mover as entradas para `tests/dinheiro/cenarios.json`, apagar os arquivos da lista Delete, ajustar `test_pipeline_compromissos.py`, `tests/test_golden_meta.py` e `tools/golden.py`.
- [ ] **Step 7:** `pytest tests/dinheiro -q` → todos PASS (ler o resumo). Commit: `refactor(conciliacao): 4 estados, casamento por vencimento e centavos`.

### Task 3: Consumidores e normalização das linhas antigas

**Files:**
- Create: `migrations/0080_compromisso_quatro_estados.sql`
- Modify: `gabi/dinheiro/contas_pagar.py:28-60`, `gabi/dinheiro/projecao.py:1-41`, `gabi/avisos.py:60-98,130,255-290,340-355`, `gabi/dinheiro/agenda_financeira.py:35-40`
- Test: `tests/dinheiro/test_contas_pagar.py`, `tests/dinheiro/test_projecao.py`, `tests/test_avisos.py`, `tests/test_avisos_antecipados.py`, `tests/dinheiro/test_agenda_financeira.py`, `tests/test_esquema.py` (e os demais da lista `grep -rln "previsto\|debito_automatico" tests`)

**Interfaces:**
- Consumes: estados e `dados.diferenca_centavos` da Task 2.
- Produces: grupos de `contas_a_pagar` iguais aos de hoje (`GRUPOS` não muda); payload de aviso com `debito_automatico` pela `forma`.

- [ ] **Step 1: testes que falham:**
  - `test_contas_pagar`: compromisso `aberto` com `forma='debito_automatico'` cai no grupo `debito_automatico`; linha antiga com `dados={"diferenca": -1.0}` dá `diferenca_centavos == -100`, nova com `diferenca_centavos: -100` idem.
  - `test_projecao`: `aberto` + débito automático com vencimento passado não entra; com vencimento futuro entra no dia; `aberto` comum vencido sai hoje.
  - `test_avisos` (Review Focus 1): `aberto` com `forma='debito_automatico'` vencendo hoje não entra no `vence_hoje`; no `vence_em_breve` entra com `debito_automatico: True`.
  - `test_agenda_financeira`: marca " (déb. auto)" pela `forma`.
  - `test_esquema`: depois de migrar, `update` com linhas `previsto` e `debito_automatico` → `aberto`.
- [ ] **Step 2:** Rodar esses arquivos → FAIL.
- [ ] **Step 3:** Migração `0080`: `update compromisso set estado='aberto' where estado in ('previsto','debito_automatico');`. Ajustes:
  - `contas_pagar`: `forma == "debito_automatico"` e estado `aberto` → grupo `debito_automatico`; `diferenca_centavos=d.get("diferenca_centavos", _cent(d.get("diferenca")))`.
  - `projecao`: `SAIDA_COM_ATRASO = {"aberto", "atrasado"}` exceto débito automático; débito automático (`forma`) só no dia e se `venc >= hoje`; o `select` traz `forma`.
  - `avisos`: `ABERTOS_A_VENCER = ("aberto",)`; tirar `previsto` das consultas e de `_item_estado`; `vence_hoje` com `forma <> 'debito_automatico'`; `debito_automatico` do payload = `forma == 'debito_automatico'` (trazer `forma` nos `select`); atualizar a docstring de `revalidar`.
  - `agenda_financeira:40`: pela `forma`.
- [ ] **Step 4:** `pytest -q` (suíte inteira) e `cd painel && npx vitest run` → PASS (ler os resumos). `grep -rn "previsto\|juros" gabi painel/src` não acha estado de compromisso.
- [ ] **Step 5:** Commit: `refactor(conciliacao): consumidores pela forma e 0080 normaliza estados antigos`.

### Task 4: Fechamento: ADR, docs e medida

**Files:**
- Create: `docs/adr/026-conciliacao-achatada.md`
- Modify: `docs/BACKLOG.md` (item sai do "Depois", entra em "Aberto" como `CA1` com dono R: "rodar `~/comparar-conciliacao.sh` e conferir a lista"), `docs/STATUS.md`, spec (seção "Fora do escopo": a migração 0080 é só de dados)

- [ ] **Step 1:** ADR-026 curta: contexto (porte do gabi-fin, 27 linhas/mês), decisão (4 estados, regras da spec, centavos), consequências (sem juros, sem paridade com o gabi-fin, `tolerancia_juros` ignorado).
- [ ] **Step 2:** `wc -l gabi/dinheiro/compromissos.py gabi/dinheiro/conciliacao.py` — anotar no ADR; meta ~320 (hoje 585). Se passar de 380, revisar antes de seguir.
- [ ] **Step 3:** `pytest -q` → PASS. Commit: `docs: ADR-026 conciliação achatada; CA1 para o Ricardo comparar`.

### Depois do plano (passos do Ricardo, fora das tasks)
1. `! ~/comparar-conciliacao.sh` e conferir a lista.
2. Com o OK: merge, instalação (script `~/instalar-conciliacao.sh` a preparar), conferir a rodada de extratos seguinte (`conferida=True`) e a tela A pagar; depois apagar `tools/_conciliacao_antiga/` e `tools/comparar_conciliacao.py`.
