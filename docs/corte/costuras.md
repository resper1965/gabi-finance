# Costuras do corte

Gerado por `python -m tools.grafo_imports --fica <lista do plano> gabi.importar --sai <lista do spec>`.
O fecho puro dos imports a partir do que fica arrasta quase tudo (`api`, `avisos`, `dia` e `mcp.servidor` importam as áreas que saem), então
`--sai` declara os prefixos que o spec manda embora; cada aresta de um módulo que fica para um deles é uma costura. Os módulos que saem
estão em `saem.txt` (um por linha). As Tasks 2–5 executam as ações abaixo; os testes dos módulos que saem são apagados na Task 5, não antes.

## Decisões que o spec não fecha

| Módulo | Decisão | Motivo |
|---|---|---|
| `gabi.importar` | FICA | Carga do staging do Plano 1 (planilha, lançamentos, cadastros de compromissos): só usa `db`, `dinheiro`, `rodada`, `hoje`. É financeiro; o spec só o manda embora se servisse só à família, e não serve. Seu teste (`tests/test_importar.py`) é financeiro e não pode ser apagado. |
| `gabi.qualidade` + `rotas.qualidade` | SAI | EV5 mede aceite de sugestões, custo do modelo (OpenRouter) e latência de ferramentas do MCP; não lê tabela financeira e só `rotas.qualidade` a importa. |
| `gabi.fontes.nibo_escrita` | FICA | `ambiente.fontes_do_ambiente()` ainda instancia `NiboEscrita` como a fonte `nibo` (leitura de notas e a receber) e `tests/cobrar/test_nibo*.py` a cobrem; a ponte só permite os métodos de leitura (R2). Trocar por `Nibo` seria mudar comportamento financeiro. |
| `gabi.fontes.tokens` | SAI | Só emite tokens de Google, Graph e Linear (`token_google_*`, `token_graph`, `linear_do_ambiente`); nada que fica a importa (só `tests/fontes/test_tokens.py`). mcp.ai e Nibo usam variável de ambiente. O spec o listava em "fica" por engano de nome (o `gabi.mcp.tokens`, dos escopos do MCP, é outro e fica). |
| `gabi.fontes.roteador` | SAI (decidido na Task 2) | Só roteia contatos (Google x Graph) e correio (Gmail x Graph) e só `correio`, `contatos` e `rotas.contatos` o importam; não há nada de mcp.ai/Nibo para reduzir. Fica no disco até a Task 5, junto com `tests/fontes/test_roteador.py`. O "recusar fonte desconhecida" do brief vive em `ponte._atender` e foi testado ali. |
| mcp.ai na ponte | NÃO entra na ponte (decidido na Task 2) | Hoje `dinheiro.rodar` usa `mcpai.Cliente()` direto, com `MCPAI_KEY` no ambiente da própria unit de extratos/saldos; pôr o mcp.ai na ponte seria mudar o fluxo financeiro (funcionalidade nova, fora de escopo). A ponte ficou só com `nibo`, que é a única fonte financeira que passa por ela hoje. Revisar na Task de deploy se a R5 deve cobrir o mcp.ai. |
| `gabi.correio.modelo` | Edição mínima (import tardio de `PonteModelo`) | Módulo que sai na Task 5; sem a edição o import de `PonteModelo` (removido) derrubava a coleta de 26 arquivos de teste financeiros do MCP via `ferramentas_agir`. |
| `gabi.rotas.dia` | SAI | Telas Hoje e Agenda; o `dia.py` que fica só alimenta o resumo financeiro. Fora da lista de rotas do spec (F2). |
| `gabi.rotas.cadastros` | FICA, reduzir na Task 3 | Rota mista; não importa módulo que sai (sem costura no grafo), mas expõe cadastros não financeiros por dentro. |
| `gabi.mcp.ferramentas_{atividades,documentos,envios,familia,projetos}` | SAEM inteiros | Só têm ferramentas de áreas que saem. |
| `gabi.mcp.ferramentas_{agir,assistente,dec,prop,ver,dia}` | FICAM, reduzidos na Task 3 | Mistos: só as ferramentas não financeiras saem. `ferramentas_despesas` é financeiro e fica inteiro. |
| `tools/*` (`carga_familia`, `comparar_agenda`, `obter_token_google`, `obter_token_teams`, `sonda_teams_ness`, `gerar_docs_api`, ...) | Fora desta etapa | Task 5 e seguintes; não importados por `gabi/`. |

## Costuras (módulo que fica -> importa algo que sai)

| Módulo que fica | Importa | Arquivo:linha | O que fazer |
|---|---|---|---|
| `gabi.api` | `rotas.agenda`, `atividades`, `contatos`, `correio`, `dia`, `documentos`, `envios`, `familia`, `projetos`, `qualidade`, `teams` | `gabi/api.py:167-198` | Remover o uso: tirar os `include_router` (Task 3). Os motivos estão acima. |
| `gabi.avisos` | `agenda`, `agenda.consulta`, `agenda.convites` | `gabi/avisos.py:16-17` | Remover o uso: avisos de convite e de agenda saem (F7: só avisos financeiros). |
| `gabi.avisos` | `atividades`, `projetos` | `gabi/avisos.py:15` | Remover o uso: avisos de atividade e projeto saem. |
| `gabi.avisos` | `documentos.repositorio` | `gabi/avisos.py:324,330,351` | Remover o uso: aviso `documento_vence` sai (documentos vão para o esper-brain). |
| `gabi.avisos` | `teams`, `teams.regra` | `gabi/avisos.py:120,266` | Remover o uso: aviso `teams_sem_resposta` sai. |
| `gabi.decisoes` | `contatos.telefone` | `gabi/decisoes.py:75` | Trazer a função (`normalizar_telefone`) para o módulo, como privada (Task 2). |
| `gabi.decisoes` | `correio.regras` | `gabi/decisoes.py:74` | Trazer a função (`endereco`) para o módulo, como privada (Task 2). |
| `gabi.dia` | `agenda`, `agenda.consulta`, `correio`, `correio.consulta` | `gabi/dia.py:5-6` | Remover o uso: `dia.py` fica só com o bloco `dinheiro` (F7); agenda e e-mail saem. |
| `gabi.fontes.ambiente` | `graph_ness`, `paperless` | `gabi/fontes/ambiente.py:6-7` | Remover o uso: fábricas só `nibo` e `mcpai` (Task 2). |
| `gabi.fontes.ponte` | `google_agenda`, `google_contatos`, `google_email`, `google_oauth`, `graph_ness`, `openrouter`, `paperless` | `gabi/fontes/ponte.py:13-20` | Remover o uso: `PonteAgenda`, `PonteEmail`, `PonteGraph`, `PonteModelo` e as entradas de `PERMITIDOS`/`ERROS` que não são `nibo`/`mcpai` (Task 2). |
| `gabi.fontes.roteador` | `google_oauth`, `graph_ness` | `gabi/fontes/roteador.py:4,64` | Remover o uso: só `nibo` e `mcpai` roteiam; as demais caem em fonte desconhecida (Task 2). |
| `gabi.fontes.servico` | `google_agenda`, `google_contatos`, `google_email`, `graph_ness`, `openrouter` | `gabi/fontes/servico.py:7-11` | Remover o uso: o serviço de fontes monta só `nibo` e `mcpai` (Task 2). |
| `gabi.fontes.tokens` | `google`, `graph`, `linear` | `gabi/fontes/tokens.py:16,17,107` | O módulo que fica sai também (ver decisão acima); `saem.txt`, apagado na Task 5 com `tests/fontes/test_tokens.py`. |
| `gabi.mcp.ferramentas_agir` | `correio`, `correio.fontes`, `correio.lixeira` | `gabi/mcp/ferramentas_agir.py:8` | Remover o uso: ferramentas de e-mail (lixeira etc.) saem; ficam as de `receber_manual`, `gastador`, `nao_gasto` (Task 3). |
| `gabi.mcp.ferramentas_assistente` | `antecipar`, `reuniao`, `revisao`, `google_oauth`, `graph_ness` | `gabi/mcp/ferramentas_assistente.py:5-7` | Remover o uso das ferramentas que dependem deles; conferir na Task 3 o que sobra financeiro (se nada, o módulo sai). |
| `gabi.mcp.ferramentas_dia` | `agenda`, `antecipar`, `correio`, `google_oauth`, `graph_ness` | `gabi/mcp/ferramentas_dia.py:6-12` | Remover o uso: agenda e e-mail saem; fica o resumo financeiro e `_inteiro`/`AVISO_TERCEIROS` se algo que fica os usa (Task 3). |
| `gabi.mcp.ferramentas_prop` | `fontes.paperless` | `gabi/mcp/ferramentas_prop.py:8` | Remover o uso: ferramentas de proposta de documento saem; `ErroFerramenta` e as propostas financeiras ficam (Task 3). |
| `gabi.mcp.ferramentas_ver` | `contatos.contatos` | `gabi/mcp/ferramentas_ver.py:13` | Remover o uso: ferramentas de contato saem (Task 3). |
| `gabi.mcp.ferramentas_ver` | `teams.regra` | `gabi/mcp/ferramentas_ver.py:17` | Remover o uso: ferramentas ligadas a Teams saem (Task 3). |
| `gabi.mcp.servidor` | `ferramentas_atividades`, `ferramentas_documentos`, `ferramentas_envios`, `ferramentas_familia`, `ferramentas_projetos` | `gabi/mcp/servidor.py:24` | Remover o uso: deixam de ser registradas (Task 3). |
| `gabi.mcp.servidor` | `fontes.graph_ness` | `gabi/mcp/servidor.py:280` | Remover o uso: sem `PonteGraph` nem `ErroGraphNess` (Tasks 2-3). |

## Decisões da Task 3 (API, rotas e MCP)

| Item | Decisão | Motivo |
|---|---|---|
| `resumo_manha` (MCP) | FICA, reduzido ao bloco financeiro + contagem de decisões | F7: o resumo da manhã é só do dinheiro. Agenda, e-mail, "Prioridade" e o olhar à frente saíram de `resumo_da_manha`; o escopo continua `trabalho` (o token do Hermes não muda). `dia.py`/`avisos.py`/`telegram.py` seguem na Task 4. |
| `olhar_a_frente`, `promessas_candidatas`, `preparar_reuniao`, `revisao_semana` | SAEM (`ferramentas_assistente` removido) | Dependem de `antecipar`, `reuniao`, `revisao` e do correio, todos fora. `olhar_a_frente` tinha escopo `fin`, mas lê documentos e atividades por dentro. |
| `avisos_abertos` | FICA, sem os campos `evento_id`/`conta` do `convite_agenda` | Avisos financeiros ficam (F7); o convite de agenda sai. |
| `decisoes_abertas`, `decisao_responder`, `decisoes_recentes` | FICAM | `gabi.decisoes` fica (canal de decisões financeiras). Os efeitos `adicionar_canal_email` e afins ainda tocam `contato_google_email`: conferir na Task 4/migração. |
| Escopos de token | Saem `docs`, `envios`, `familia`, `contatos`, `atividades`, `projetos`; ficam `fin`, `trabalho`, `propostas`, `decisoes`, `pedidos`, `sensivel` | `pedidos` e `sensivel` já não serviam a nenhuma ferramenta antes do corte; não são deste corte. Token antigo com escopo removido segue válido (teste novo). `ESCOPOS_HERMES` = `fin, trabalho, propostas, pedidos, decisoes`. |
| `GET /cadastros/pessoas/{pid}/cpf` | SAI | Lê `familia_documento` (ficha da família). O resto de `rotas/cadastros.py` é financeiro e ficou como estava (a tabela `pessoa`, com `telefone` e `dados`, fica até a migração). |
| Arquivos `gabi/rotas/{agenda,atividades,contatos,correio,dia,documentos,envios,familia,projetos,qualidade,teams}.py` | Só desligados do `api.py` | Os arquivos e os testes deles saem na Task 5. |
| Testes apagados na Task 3 | `tests/mcp/test_{assistente,atividades_mcp,documentos,envios,familia,projetos_mcp}.py` | Testam os módulos `ferramentas_*` removidos nesta task. Os demais testes de `tests/mcp` foram ajustados sem perder asserção financeira. |
| `docs/fontes/hermes.md` | Lista `tools.include` regerada por `tools.gerar_hermes` (32 ferramentas) | O teste `test_hermes` compara a doc com o código. A chave `gabi_brain:` e o prefixo `mcp__gabi_brain__` no SOUL ficam para a task do Hermes (F8). |
| `painel/tests/amostras/{qualidade,hoje,agenda,atividades,projetos}.json` e `tools/gerar_amostras.py` | Amostras e rotas dessas telas removidas | `tests/test_amostras_painel.py` exige uma amostra por rota; as telas dessas rotas saem na task do painel. |
| `gabi.mcp.servidor` | `WWW-Authenticate: realm="gabi-brain"` e o caminho padrão `/var/lib/gabi-brain/gabi.db` não mudaram | Nomes de VPS/paths são do F9 (virada), não da superfície. |

## Decisões da Task 4 (avisos, Telegram, resumo da manhã)

| Item | Decisão | Motivo |
|---|---|---|
| `olhar_a_frente` | VOLTA, só financeiro: `gabi/dinheiro/olhar_a_frente.py` (`_caixa`, `_atrasados`, `bloco_resumo`); ferramenta MCP de mesmo nome, escopo `fin`, em `ferramentas_dia`; bloco "Olhando à frente" de volta no `resumo_da_manha` | Decisão do controlador (corrige a Task 3): caixa negativo e a receber atrasado são sinais financeiros. Documentos e atividades vencendo saíram do retorno (`documentos`, `atividades_vencendo` não existem mais). 33 ferramentas. Testes de caixa e a receber vieram de `tests/test_antecipar.py` com as mesmas asserções (`tests/dinheiro/test_olhar_a_frente.py`). |
| Resumo da manhã no Telegram | Não existe no `telegram.py`: o resumo das 07:05 é a ferramenta MCP `resumo_manha`, que o Hermes entrega | `telegram.py` só envia avisos; ficou com a única mudança de ordem (sem `email_emergencial` na frente). |
| `gabi/avisos.py` | Saem `hermes_parado`, `google_parado`, `teams_sem_resposta`, `documento_vence`, atividades, `projeto_parado`, `convite_agenda`, `estado_do_servico` e o parâmetro `estado_servico` de `gerar_avisos`; não importa mais nada que sai | F7. O aviso `servico_falhou` segue (a unidade vem de `--falha`; o exemplo da doc virou `gabi-finance-saldos.service`). |
| `gabi/rotas/avisos.py` `descrever` | Saem os textos de e-mail, atividade, documento, Teams, Hermes, Google, convite, projeto, `caixa_reconectar`, `agenda_reconectar` | Nenhum produtor que fica emite esses tipos. Aviso antigo desses tipos já gravado no banco cai no texto genérico (`tipo` + payload). |
| `gabi/dia.py` | Reduzido a `hoje(con, agora) -> {"dinheiro": ...}`; teste novo `tests/test_dia.py` mantém a asserção de `atrasadas` do antigo teste da rota `/hoje` | F7/costuras. Hoje ninguém o chama (a rota sai na Task 5; o resumo usa `agenda_financeira`); fica por decisão do spec ("`dia.py` reduzido ao bloco dinheiro"). |
| `gabi/decisoes.py` | Sai o efeito `adicionar_canal_email` com `_endereco`, `_normalizar_telefone` (as cópias da Task 2) e os testes dele | Lia `contato_google_email` (contatos saem). `tests/decisoes/test_helpers_privados.py` apagado: testava só essas cópias. |
| `gabi/api.py:67` | Comentário "fábricas de Nibo/Paperless" virou "fábrica do Nibo" | Ajuste do controlador. |
| Testes apagados | `tests/test_avisos_teams.py`, `test_avisos_convites.py`, `test_atividades_avisos.py`, `test_projetos_avisos.py`; trechos hermes/google/documento de `test_avisos.py`; `test_email_emergencial_vai_antes...` de `test_telegram.py`; descrever de caixa/agenda/correio/convite em `test_avisos_api.py`; efeito `adicionar_canal_email` em `test_decisoes.py` | Só cobrem comportamento não financeiro que saiu. |

## Decisões da Task 5 (remoção)

| Item | Decisão | Motivo |
|---|---|---|
| Módulos de `saem.txt` + `gabi/fontes/roteador.py` | Removidos (`git rm`) com os pacotes `agenda`, `contatos`, `correio`, `documentos`, `envios`, `familia`, `teams` inteiros | `roteador` não estava em `saem.txt` mas a Task 2 decidiu que sai (ruling do controlador). `tokens.py` já estava na lista. |
| `tools/comparar_agenda.py` e `tests/test_comparar_agenda.py` | FICAM | O brief mandava remover, mas "agenda" ali é a agenda de COMPROMISSOS financeiros (compara com o gabi-financeiro, critério G21); não importa nada que sai e o teste é financeiro (regra: nenhum teste financeiro apagado). A decisão de aposentá-lo, se for o caso, é da Task de deploy/virada. |
| `tools/capturas.py` | FICA | Capturas do painel (Playwright), sem dependência do que sai; o painel reduz na Task 7. |
| `tools/auditar_promessas.py`, `tests/tools/*` | FICAM | Task 8 (prefixo e lista `ESCRITAS` só financeira). |
| `tools/{carga_familia,obter_token_google,obter_token_teams,sonda_teams_ness}.py` | Removidos | Só serviam aos módulos que saem. |
| `gabi/static` (`index.html`, `industry.css`) | FICA | `api.py` ainda monta `/static` e usa `static/index.html` como página reserva quando o painel não está construído. |
| `deploy/gabi-brain-{agenda,anexos,contatos,correio,documentos,teams}.{service,timer}` | Removidos já aqui; `instalar.sh` os desliga e apaga na VPS (lista das units cortadas) | Sem eles o teste "todo módulo que uma unit executa existe" falha (zero falhas é exigência da Task 5). O RENOMEAR `gabi-brain-*` -> `gabi-finance-*` continua na Task 8; o `gabi-brain-fontes.service` ainda lê `google.env`/`google-contatos.env` (Task 8). |
| `tests/test_deploy.py` | Saem os testes das units removidas; as removidas entram em `CORTADAS` (teste de que não voltam) | Só cobriam o que saiu. |
| `tests/cobrar/test_nibo.py::test_nenhuma_rota_de_exclusao_no_codigo` | `achados == []` (antes aceitava o `apagar` de `graph_ness_contatos.py`) | O único DELETE do código saiu com os contatos; a asserção ficou mais forte, não mais fraca. |
| `tests/rotas/test_cadastros_api.py` | Tira o import de `tests.familia.apoio.doc_pessoa` e os 2 documentos da família do banco de teste | O fixture só alimentava o `GET /pessoas/{pid}/cpf`, removido na Task 3; a tabela `documento` cai na migração 0090. |

## Decisões da Task 6 (migração 0090)

Tabelas que caem (27 tabelas e 2 visões): `anexo`, `atividade`, `bem`, `caixa_email`, `contato_google`, `contato_google_email`, `contato_graph`, `contato_proposta`, `documento`, `documento_data`, `documento_leitura`, `documento_numero`, `documento_proposta`, `email_fonte`, `email_msg`, `email_respondido`, `envio_proposta`, `escuta_remetente`, `pessoa_documento_legado`, `pessoa_historico`, `pessoa_proposta_legado`, `projeto`, `projeto_fato`, `projeto_gasto`, `projeto_pessoa`, `teams_conversa`, `teams_fonte`; visões `familia_documento`, `familia_proposta`. Ordem: visões, filhas, mães (o banco roda com `foreign_keys=ON`). A lista inteira (os dois conjuntos, KEEP e DROP) está em `tests/test_migracao_corte.py`.

| Item | Decisão | Motivo |
|---|---|---|
| `pet`, `allowlist_vip`, `memoria`, `agenda_estado`, `agenda_eventos`, `compromisso_fixo`, `conta_estado` | FICAM | `gabi/importar.py` (carga do staging, FICA desde a Task 1) as grava e `tests/test_importar.py` (financeiro) confere a contagem de cada uma. Tirar `pet`/`memoria`/`allowlist_vip` exigiria mudar `importar` e enfraquecer esse teste. Candidatas a uma limpeza futura junto com o `importar`. |
| `agenda_evento`, `agenda_fonte` | FICAM | `dinheiro.sugestoes_agenda` (roda em `dinheiro.rodar`, tem teste em `tests/dinheiro`) lê os dois. Sem sincronizador de agenda ficam vazias numa instalação nova; num banco copiado do gabi-brain trazem as linhas antigas. A decisão de aposentar `sugestoes_agenda` é do controlador (mudaria comportamento financeiro). |
| `custo_modelo` | FICA | `dinheiro.modelo` (gasto do modelo, tetos em `parametro`) lê a tabela. |
| `chamada`, `chamada_mcp`, `aviso`, `rodada`, `parametro`, `pergunta`, `decisao`, `acesso`, `matriz_acesso`, `token_agente`, `schema_versao`, `pessoa`, `gastador_regra` | FICAM | Base, auth, MCP, canal de decisões e "para quem". `pessoa` não tem nenhuma linha tocada (teste com banco cheio). |
| `gabi/envelope.py` | `agenda`, `correio`, `documentos` e `teams` passam a `CORTADAS` (somem de `FONTES`); saem `_em_uso`, `_agenda_em_uso`, `_correio_em_uso` | Num banco copiado do gabi-brain a fonte de agenda liberada e as rodadas antigas de `agenda`/`correio` fariam TODA resposta financeira vir `desatualizado` (ninguém mais sincroniza). Teste novo cobre isso. Saem os 4 testes de frescor de agenda/correio e o de `_agenda_em_uso` (módulos que saíram); `test_envelope_fontes_filtradas` passou a usar `notas-nibo` como fonte de exemplo (mesma asserção). |
| `gabi/backup.py` | `TABELAS_CONTAGEM` sem `atividade`, `projeto`, `documento` | O teste de restauração conta linhas nelas; as tabelas caem. `tests/test_backup_banco.py` segue conferindo `compromisso_linha` e `valor_do_mes`. |
| Testes de esquema/migração | Saem `test_correio_*` e `test_documentos_0081_*` (`test_esquema.py`) e os dois de `envio_proposta` (`test_migracao_convites.py`); `test_migracao_simplificacao` migra até a 0089 no passo final | Cobrem tabelas que a 0090 derruba; a 0075 continua testada no estado em que ela vale. |
| `painel/tests/amostras/*.json` | Regeradas por `tools.gerar_amostras` (some só a fonte `agenda` da lista `fontes`; 27 arquivos, 135 linhas) | `tests/test_amostras_painel.py` (Python) compara as amostras com a API; o vitest do painel é da Task 7 e pode ler a lista de fontes. |
