-- EV2: o que cada rodada de captura já gravou, por conta. Uma rodada interrompida (queda de energia, kill) deixa estas linhas;
-- a rodada seguinte, no mesmo dia e dentro da janela, não refaz as contas que já estão aqui.
create table captura_conta (
    rodada_id    integer not null references rodada(id),
    account_id   text    not null,
    dia          text    not null,
    lidos        integer not null default 0,
    novos        integer not null default 0,
    concluida_em text    not null,
    primary key (rodada_id, account_id)
);
create index captura_conta_dia on captura_conta(dia);
