# Hermes enxuto: achados das sobreposições (06/11/2026)

Registro da Task 6 do plano `2026-11-06-hermes-enxuto.md`. Só leitura, nada migrado.

## S1, memória do Hermes (`~/.hermes/memories`)
- `MEMORY.md` (509 bytes): (a) "alguns e-mails do backoffice@bekaa.eu são do projeto ORM da Família Reis (não todos)"; (b) um resumo da infraestrutura do brain (MCP local, portas da Tailscale, units systemd).
- `USER.md` (224 bytes): preferências do Ricardo (ignorar alertas do GitHub no resumo de e-mails; ele mesmo sobe documentos ao Paperless) e uma linha rotulada "Chave:" cujo conteúdo não sei identificar (não copiado aqui; o Ricardo diz o que é).
- Conclusão: não há fato de pessoa nem de dinheiro que devia estar no brain. O item (a) é regra de e-mail e poderia virar regra no brain, se o Ricardo quiser (hoje o brain classifica e-mail de outro jeito). Nada migrado; a `write_approval` da memória está ligada.

## S2, transcrição de áudio duplicada
- O Hermes tem `stt` ligado (português, modelo local `base`); o brain tem `faster-whisper` (ADR-034).
- Não medido: o Ricardo pulou o teste de áudio. Recomendação mantida da spec: fazer o teste (um áudio curto no Telegram, ler o `state.db`) antes de mudar o ADR-034.

## S3, `a2a`
- `ss -ltnp`: só `127.0.0.1:9119` (painel do Hermes) e `127.0.0.1:3011` (ponte do WhatsApp). Nenhuma porta pública. Plugin `a2a-platform` desligado em 06/11.

## S4, rotinas (`hermes cron list`)
- Onze rotinas, iguais antes e depois da limpeza: `resumo-manha`, `continuidade`, quatro `aniversario-*`, `lembrete-passaporte`, `forecast-semanal`, `resumo-semanal-pagamentos` (pausada), `fechamento-noturno`, `vigia-semanal`.
- As duas criadas em 06/11 às 04:28 provavelmente são `fechamento-noturno` e `vigia-semanal` (existem os scripts `fechamento_dia.py` e `vigia_semanal.py` em `~/.hermes/scripts`); a data de criação não foi conferida. O Ricardo confirma se foi ele quem pediu.

## Descobertas fora do plano
- **Visão:** o Hermes não lia imagem desde 26/10 (`No LLM provider configured for task=vision`). Corrigido com `auxiliary.vision` = `openrouter` / `google/gemini-3.8-flash` (backup `config.yaml.bak-antes-visao`); a imagem de teste foi lida.
- **Imagem gerada:** `check_image_generation_requirements` falha desde antes da limpeza; nenhum provedor tem chave e nunca houve chamada de `image_generate`. Toolset mantido ligado por decisão do Ricardo.
- **Restart do gateway:** os avisos `owned by uid 1001, not the current uid 0` e `run hermes pm repair` aparecem em todo reinício como root; não impedem o reinício.
- **Saldo:** o Hermes mostrou "Santander — --R$ 1.280,13" (sinal duplicado) na resposta de saldo; é formatação do texto do Hermes sobre o dado do brain, a conferir.
