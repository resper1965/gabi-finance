# Revisão geral 04/11/2026 — correções (design)

Origem: avaliação do projeto inteiro em 04/11 (três revisões: backend, arquitetura/deploy, painel; achados graves conferidos no código).
Pedido do Ricardo: "spec plan execute todos" (pacotes A a D). Branch única `fix/revisao-geral`, worktree `~/gabi-brain-revisao`.
Merge, push e instalação continuam só com ok explícito dele.

## Objetivo e critério de sucesso
Fechar o que pode corromper dado de dinheiro, deixar instalação e backup seguros, fechar vazamento de token nas fontes e
arrumar documentação e dependências. Sucesso: pytest e vitest verdes (sem teste dependente da data de hoje), `npm run build` ok,
ruff sem erro nas regras escolhidas, nenhum comportamento visível mudado além do descrito aqui.

## Pacote A — integridade do dinheiro
A1. **Valor ilegível não vira zero.** `dinheiro/moeda.py:valor_lancamento`: se `amount` não for legível, levanta `ValueError`
   (hoje vira 0). `captura.py` (laço de lançamentos) pula essa transação, conta em `ilegiveis` e segue; o resumo da rodada mostra a
   contagem. Nunca faz upsert com valor inventado. O mesmo para o saldo (`captura.py:191`, `balance` ilegível): não grava o saldo
   daquela conta naquela rodada.
A2. **Ler e depois gravar usa `begin immediate`.** Trocar `transacao(con)` por `transacao(con, imediata=True)` onde o bloco lê antes de
   gravar: `dinheiro/captura.py` (bloco por conta), `cobrar/recebimentos.py`, `mcp/ferramentas_agir.py`, `rotas/dinheiro.py`
   (confirmações). O plano lista cada ponto com grep de `transacao(` e justifica os que ficam como estão.
A3. **`_purgar_futuro` dentro de transação** (`begin immediate`), tudo ou nada; mesmo critério de hoje (data > hoje).
A4. **`transacao` fecha a transação se o `commit` falhar** (`db.py`): rollback e relança.
A5. **`/api/revogar-tudo` atômico** (`api.py`): update dos tokens e linha em `decisao` na mesma transação.
A6. **Testes que dependem da data de hoje.** `painel/tests/despesas.test.tsx` ("dispensar...") passa a fixar a data
   (`vi.setSystemTime`), como o outro teste do mesmo arquivo. Qualquer outro teste (pytest ou vitest) que falhe só por causa da data
   recebe o mesmo tratamento.

## Pacote B — instalação e backup seguros
B1. **Backup no fuso certo.** `gabi-brain-backup.timer`: `OnCalendar=*-*-* 03:30:00 America/Sao_Paulo` (a VPS está em CET; hoje roda
   às 23:30 de Brasília). Continua antes da exportação de domingo (04:00).
B2. **Teste de restauração conta as tabelas novas**: `atividade`, `projeto`, `compromisso_linha` (despesas), `valor_do_mes`, `documento`.
B3. **Instalador com backup e troca atômica** (`deploy/instalar.sh`):
   - antes de copiar, se o banco existe: cópia consistente com a API sqlite `backup` (como `gabi/backup.py`) para
     `/var/backups/gabi-brain/gabi.db.antes-instalar-<AAAA-MM-DD-HHMM>` (0600, dono gabibrain); guarda as 5 últimas;
   - copia o código para `/opt/gabi-brain/.novo-<ts>/` e troca cada pasta com `mv` (a antiga vai para `.velho-<ts>`, apagada no fim);
     se a cópia falhar, o código antigo segue intacto.
   As migrações continuam rodando no start dos serviços; o backup acima cobre a migração destrutiva.
B4. **Restauração documentada** em `docs/runbook.md#restaurar`: parar serviços e timers, copiar, `chown`, `integrity_check`, subir.
B5. **Loop de falha avisa.** `gabi-brain-api`, `-mcp` e `-fontes`: `OnFailure=gabi-brain-falha@%n.service` e `StartLimitIntervalSec`/
   `StartLimitBurst` (iguais ao da api hoje) nos três.

## Pacote C — segurança das fontes
C1. **Redirecionamento sem credencial.** Em `fontes/_http.py`, um handler de redirecionamento que, quando o host muda, remove
   `Authorization`, `ApiToken` e afins antes de seguir. Usado por `_http.py`, `paperless.py`, `nibo.py` (inclui `obter_arquivo`),
   `nibo_escrita.py`, `google_oauth.py`, `openrouter.py`, `mcpai.py`, `tokens.py`. O Graph continua bloqueando redirecionamento.
C2. **Paperless `next` só no mesmo servidor**: o link precisa começar com `self.base`; senão `ErroPaperless("link inválido")`.
C3. **Retry em leitura.** `graph_ness._get` e os GET do Google (e-mail, agenda, contatos): até 2 novas tentativas em 429/502/503/504,
   respeitando `Retry-After` limitado a 20 s (padrão 2 s, 5 s). Escrita (enviar, criar evento, contato) continua com uma tentativa só.
C4. **Ponte não espera para sempre**: o servidor dá 30 s para receber o pedido (`settimeout` na leitura); depois a execução segue como hoje.
C5. **Links externos no painel só `http(s)`**: `urlSegura()` em `painel/src/lib`, usada em `link_reuniao` (Trabalho/Hoje) e `paperless_url`
   (Cadastros › Documentos); outro esquema vira texto sem link.

## Pacote D — painel e arrumação
D1. **`useApi` sem dado velho**: guarda `{url, env}`; se a url mudou, o estado é `carregando` e não mostra o dado da url anterior.
   Releitura da mesma url continua mantendo o último dado bom em erro. `liberar()` só pela requisição vigente. Teste novo `tests/useApi.test.tsx`.
D2. **Um formatador de R$ e um de hora**: `formatarBRL` e `horaDe` em `lib/formato.ts`, usados em Projetos, `Valor`, `CustoGabi`,
   `Gabi/Qualidade` e Atividades; `dia()` de Atividades e Documentos passa a usar o dia de America/Sao_Paulo (o `diaLocal` da Agenda vai para `lib`).
D3. **Código morto do painel**: apagar `graficos/Treemap.tsx`; `corDestino` e os tipos saem de `Sankey.tsx` para `graficos/fluxo.ts`;
   `Sankey.tsx` apagado se ninguém mais usar.
D4. **Dependências declaradas**: `pyproject.toml` lista o que o código importa (PyJWT, mcp, cryptography, python-multipart, httpx, conferido
   no plano); `dev` ganha `ruff`. O `requirements.lock` (produção) não muda.
D5. **ruff** com regras `F` (pyflakes: imports e variáveis sem uso, nomes indefinidos) em `gabi/`, `tools/`, `tests/`; corrige o que achar;
   comando no STATUS ao lado do pytest. Sem CI no GitHub.
D6. **Documentação em dia**: `STATUS.md` (estado em 04/11: despesas e projetos mergeados e instalados em 27/10), `HANDOFF.md` sem as
   seções vencidas, `BACKLOG.md` (DS1, PJ1 fechados); README de uma linha em `migrations/` e `docs/adr/` explicando os números pulados
   (faixas reservadas; aplicação por nome de arquivo).
D7. **Git** (com ok dele, no fim): push da `main`; apagar a branch `feat/projetos-melhorias` só se ele disser (tem spec e plano não executados).

## Fora deste trabalho (decidido, não reabrir sem pedido)
- Ponte verificar proposta aprovada: o socket já fica numa pasta 0750 do grupo gabibrain (só código nosso), e o serviço de fontes não
  lê o banco (R5); verificar lá quebraria essa separação.
- Renomear escopo `trabalho` e nomes "escuta" internos: muda token do Hermes e tipos de aviso gravados; ganho só cosmético.
- Texto de erro cru para o cliente: os únicos clientes são o Ricardo e o Hermes.
- Tirar SQL das rotas antigas (cadastros, dinheiro, gastos): fazer quando cada uma for mexida.
- Divisão de `CadastrosDocumentos.tsx`/`Projetos.tsx`, acessibilidade de abas e alvos de 44 px: próxima vez que a tela for mexida.

## Testes
Cada item com teste: A1 (amount ilegível pulado, valor guardado não muda), A2/A3 (dois `transacao` concorrentes não dão BUSY_SNAPSHOT;
purga tudo ou nada), A4, A5, B2 (contagem inclui as tabelas), B3 (`tests/test_deploy.py`: script tem backup antes da cópia e troca por `mv`),
B1/B5 (test_deploy: fuso e OnFailure), C1 (redirecionamento para outro host chega sem Authorization), C2, C3 (429 com Retry-After, escrita
sem retry), C4, C5/D1/D2 (vitest). Verificação final: pytest completo, vitest, `npm run build`, ruff.
