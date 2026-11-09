# Projetos no Linear, pasta no brain (ADR-038)

Data: 09/11/2026 · Pedido do Ricardo: falar com o agente ("vamos vender a fazenda"), ele infere e conversa sobre as etapas e cria o projeto, num gerenciador como o Linear.

## Entendimento (o que ele disse e o que assumi)
- **Disse:** o painel do brain é pobre de dados e pesado no celular; o brain ficou com projetos por causa do dinheiro, o que não é o mais importante; pensou em Linear conectado pelo Composio. Escolheu: só projetos no Linear (atividades soltas ficam no brain), caminho híbrido e sem espelho.
- **Assumi:** conexão direta pelo MCP oficial do Linear (sem Composio); o brain mantém dinheiro, documentos, fatos, anexos e pessoas; um mês de uso antes de pensar em espelho de um sentido.
- **Sucesso:** conversar com o Hermes, aprovar a lista de etapas e ver o projeto no Linear (celular), com orçamento e documentos no brain, sem criar nada duplicado.

## Fronteira
| Linear | Brain |
|---|---|
| projeto, etapas, dependências, prazos, marcos, responsável, comentários | orçamento e gastos, fatos, anexos, documentos (`paperless_id`), pessoas |
| quadro, linha do tempo, app de celular | atividades soltas e avisos do Telegram |

## Fluxo
1. Ricardo conta o projeto; o Hermes infere etapas, conversa e mostra a lista.
2. **Só após o sim** cria projeto e etapas (com dependências) no Linear, depois chama `projeto_ligar` (também após o sim) para o brain registrar `linear_id` e `linear_url`.
3. Dinheiro, fato, anexo, documento e pessoa são gravados no brain, ligados ao projeto.
4. "Como está X?": o Hermes junta etapas (Linear) e pasta (brain: `projeto_ver`).
5. Etapa do Ricardo: criada no Linear atribuída a ele; aviso pelo app do Linear.
6. Regra do SOUL: parte de projeto → Linear; solto → brain; nunca nos dois. Linear fora do ar → avisa e para, sem plano B no brain.

## Componentes
- **Hermes:** novo `mcp_servers.linear` (MCP oficial), chave em `~/.hermes/.env` colocada pelo Ricardo. `include` fechado: listar/ver projetos e etapas, criar/mudar projeto e etapa, comentar; sem apagar. Nomes exatos conferidos na instalação a partir das ferramentas que o servidor oferece. Se o servidor exigir OAuth em vez de chave no cabeçalho, o fluxo roda em segundo plano (como o do Teams) e o Ricardo só digita o código.
- **Migração 0089:** `projeto.linear_id` (único quando preenchido) e `projeto.linear_url`; só acrescenta colunas.
- **MCP do brain:** `projeto_ligar(projeto, linear_id, linear_url)` (cria a pasta, ou liga uma existente, só com sim; idempotente por `linear_id`). `projeto_ver` e `projeto_listar` devolvem o link. Saem do include (código fica): `projeto_criar` e os parâmetros `projeto`, `depois_de`, `marco` de `atividade_criar` e `atividade_listar`. Permanecem `projeto_gasto`, `projeto_fato`, `projeto_fatos`, `projeto_pessoa`, `projeto_anexar`, `anexo_recentes`, `projeto_atualizar`.
- **Painel Dia › Projetos:** vira a pasta (orçamento contra gasto, fatos, anexos, pessoas, "abrir no Linear"); saem progresso e detalhe de etapas. `projeto_parado` (ADR-034 §9) passa a considerar só atividade do brain, fato e anexo; para projeto com `linear_id` não avisa por falta de atividade.
- **SOUL:** regra da fronteira e do sim antes de criar no Linear.

## Dados antigos
Só existe "Trocar Lâmpadas" (id 1, cancelado, 3 atividades, 1 anexo). Fica como está, sem `linear_id`; nenhuma migração de dados.

## Fora desta versão
Sincronização em qualquer sentido, aviso do brain por prazo do Linear, Composio, escrever no Linear sem o sim, apagar no Linear, migrar atividades soltas, importar projetos antigos.

## Testes
Migração (colunas, unicidade do `linear_id`); `projeto_ligar` (cria, liga, idempotente, exige sim/escopo); lista de ferramentas do include (sem `projeto_criar`); painel (pasta sem progresso, link); `projeto_parado` com e sem `linear_id`; suíte e lint do projeto. Aceite real pelo runbook `#linear`.

## Aceite real
`/new`; "vamos vender a fazenda"; o Hermes conversa e só cria após o sim; conferir no Linear (projeto, etapas, dependências, celular); "orçamento de R$ X" grava no brain com o link; "como está a fazenda?" junta as duas fontes; com chave errada de propósito o Hermes avisa e não cria no brain; cancelar o projeto de teste no Linear.

## Instalação e desfazer
Branch própria, nada instalado sem ok. Antes: backup `gabi.db.antes-linear-<data>`, `npm run build`, `sudo ~/instalar-brain.sh`, backup `config.yaml.bak-antes-linear`, SOUL, restart do `hermes-gateway`, `/new`. Desfazer como no ADR-038. Depois de um mês: decidir o espelho de um sentido.
