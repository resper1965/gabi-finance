# Status

Última atualização: 17/11/2026 (fim do corte, antes da virada).

## Onde estamos

| Etapa | Estado |
|---|---|
| Corte do `gabi-brain` em `gabi-finance` (código, banco, painel, MCP, deploy, documentação) | **Pronto na branch `corte`**, falta o merge na `main` |
| Instalação na VPS (usuários, pastas, código, unidades **desligadas**) | A fazer: [`virada.md`](virada.md), passo 1 |
| Virada (cópia do banco, conferência lado a lado, ligar, Hermes) | **Pendente**: roteiro pronto em [`virada.md`](virada.md); o Ricardo roda, o Claude guia |
| Etapa 3 do `esper-brain` (coletor, digestão, Hermes lendo o markdown) | Fora deste repositório |

## Pendências conhecidas

- **Token do Nibo novo** (o atual expirou; notas paradas desde ao menos 09/11). Sem ele, a ponte responde `nao_configurada`.
- **Endereço novo no Tailscale** (`gabi-finance.tail985643.ts.net`): depende de configuração no console da Tailscale; a sintaxe do comando será confirmada no passo 7 da virada.
- **Agenda financeira degradada** depois da virada: as tabelas `agenda_evento` e `agenda_fonte` ficam, mas nada as alimenta. Decisão da etapa 3. Ver [`operacao.md`](operacao.md#limitação-conhecida-agenda-financeira).
- **SOUL do Hermes só financeiro:** instruções de agenda, contatos etc. saem do SOUL até a etapa 3 (há backup datado).

## Histórico

O status e o backlog do tempo do `gabi-brain` estão preservados em [`historico/gabi-brain/`](historico/gabi-brain/) (`STATUS-ate-2026-11-17.md`, `BACKLOG.md`, `HANDOFF.md`, `PLANO-DEFINITIVO.md`). Nada daquilo é backlog deste repositório.
