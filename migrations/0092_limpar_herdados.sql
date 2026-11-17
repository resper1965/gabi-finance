-- Limpeza do que a cópia do banco do gabi-brain traz e o gabi-finance não usa (minimização de dados, depois da 0090 e da 0091).
-- Só linhas: nenhuma tabela nem coluna muda. Cada instrução é idempotente (rodar de novo não muda mais nada).
-- Nomes conferidos contra o código: tipos de aviso = os que gabi/avisos.py grava; efeitos de pergunta = gabi.decisoes.EFEITOS;
-- pessoa.dados: o código só lê `responsavel_por` (gabi/dinheiro/classificar.py) e tools/semear_donos.py grava `responsavel_por` e `beneficiario`.

-- 1. Avisos de tipos que o gabi-finance não gera (agenda, e-mail, Teams, documentos, Google, Hermes...): o sino e o Telegram não saberiam mostrá-los.
delete from aviso where tipo not in ('vence_hoje', 'vence_em_breve', 'valor_diferente', 'rodada_parada', 'saldo_divergente', 'banco_desatualizado',
  'conta_atrasada', 'cobrada_apos_cancelar', 'servico_falhou', 'lancamento_sem_conversao', 'exportacao_parada');
-- `servico_falhou` de unidade do brain (chave = nome da unidade, ex. gabi-brain-correio.service) não é deste serviço.
delete from aviso where tipo = 'servico_falhou' and coalesce(json_extract(payload, '$.chave'), '') not like 'gabi-finance-%';

-- 2. Pergunta aberta com efeito fora da lista do gabi-finance (ex. `adicionar_canal_email`): responder quebraria; expira.
update pergunta set estado = 'expirada'
 where estado = 'aberta'
   and (not json_valid(opcoes)
        or exists (select 1 from json_each(pergunta.opcoes) o
                    where coalesce(json_extract(o.value, '$.efeito'), '') not in
                          ('registrar_nota', 'marcar_conta_nao', 'marcar_conta_sim', 'criar_compromisso', 'atribuir_para_quem')));

-- 3. Pessoa: sem telefone (ninguém o lê aqui) e `dados` reduzido às chaves que o dinheiro usa.
update pessoa set telefone = null where telefone is not null;
update pessoa set dados = case
    when json_valid(dados) and json_type(dados) = 'object'
      then json_patch('{}', json_object(
             'responsavel_por', case json_type(dados, '$.responsavel_por')
                                  when 'array' then json(json_extract(dados, '$.responsavel_por'))
                                  when 'object' then json(json_extract(dados, '$.responsavel_por'))
                                  when 'true' then json('true') when 'false' then json('false')
                                  else json_extract(dados, '$.responsavel_por') end,
             'beneficiario', case json_type(dados, '$.beneficiario')
                               when 'true' then json('true') when 'false' then json('false')
                               when 'array' then json(json_extract(dados, '$.beneficiario'))
                               when 'object' then json(json_extract(dados, '$.beneficiario'))
                               else json_extract(dados, '$.beneficiario') end))
    else '{}' end
 where dados is not null and dados <> '{}';

-- 4. Agenda: só o que `dinheiro.sugestoes_agenda` lê (eventos futuros, não privados, não cancelados, de calendário liberado), sem link,
-- organizador nem resposta ao convite.
delete from agenda_evento
 where coalesce(privado, 0) = 1 or status = 'cancelled' or dia_local < date('now')
    or coalesce(fonte_id, -1) not in (select id from agenda_fonte where estado = 'sim');
update agenda_evento set link_reuniao = null, organizador_nome = null, resposta = null
 where link_reuniao is not null or organizador_nome is not null or resposta is not null;

-- 5. Parâmetros dos módulos que saíram (e-mail, Teams, agenda sincronizada, contatos, envios, escuta, documentos, vigias do brain) e o
-- `mcp.url` do brain (o gabi-finance usa o padrão do código, gabi.agentes.URL_PADRAO). `email.vips` guardava endereços: sai também.
delete from parametro
 where chave like 'email.%' or chave like 'teams.%' or chave like 'agenda.%' or chave like 'contatos.%' or chave like 'envios.%'
    or chave like 'escuta.%' or chave like 'documentos.%' or chave like 'avisos.vigiar_%'
    or chave in ('avisos.google_horas', 'avisos.hermes_unidade', 'mcp.url', 'painel.url', 'paperless.url');
