# ADR-027 · Documentos: números e validades de tudo que está no Paperless (amplia a ADR-025)

Data: 25/10/2026 · Estado: aceito · Spec: `docs/superpowers/specs/2026-10-23-documentos-design.md`

**Contexto.** O cadastro familiar (ADR-025) cobre só documentos de pessoas e foi carregado por expressões fixas. O Ricardo quer o mesmo para tudo que é relevante no Paperless: identidade, CNH, passaporte, escritura, matrícula, IPTU, CRLV, apólice, contrato, garantia. Ele não preenche nada: confere e aprova.

**Decisões (Ricardo, 23/10).**
1. **Usos:** perguntar ao Hermes, aviso de vencimento, ver no painel e ter os dados para preencher cadastros.
2. **Fonte única: o Paperless**, lido pela ponte só de leitura.
3. **Imagem nunca vai a modelo.** Escaneado sem texto fica com o OCR que o Paperless tiver.
4. **O texto (OCR) pode ir a um modelo** pelo OpenRouter (fraco; forte só se o fraco não devolver JSON válido).
5. **Caminho A:** ampliar o cadastro familiar (proposta, aprovação no painel), com bens ao lado das pessoas.

**Como ficou.**
- Migração 0081: `bem`, `documento`, `documento_numero`, `documento_data`, `documento_proposta`, `documento_leitura`. Os dados da família são copiados; as tabelas antigas viram `*_legado` (desfazer = renomear de volta). `familia_*` respondem como antes.
- Rodada diária `gabi-brain-documentos.timer` (05h): lê o que é novo ou mudou, até `documentos.max_por_rodada`. O número só vale se aparece no OCR "as is" (sem cálculo de dígito, sem correção); o Ricardo corrige na aprovação olhando o documento. Titular por CPF, nome, placa, Renavam, matrícula ou endereço; sem titular, a proposta traz `bem_novo` e fica `conferir`.
- Aba Documentos em `#cadastros/documentos` (`#cadastros/familia` redireciona). Aprovar cria ou atualiza `documento` (e `bem`) e registra em `decisao` com `origem='documentos'` (as aprovações de documento da família também passaram a gravar essa origem). Aprovar proposta cuja pessoa foi excluída responde 400 `titular_invalido`.
- MCP no escopo `familia`: `documentos_consultar`, `documentos_vencimentos`, `bens_listar`.
- Aviso `documento_vence` a 60, 30 e 7 dias (`documentos.avisar_dias`). Vencido há mais de 30 dias na aprovação não gera aviso.

**Exceções aceitas pelo Ricardo.**
- **ADR-025 "Fora: extração por modelo"** e o parecer de 22/10: passa a haver extração por modelo, só do texto.
- **Texto de documento com CPF, endereço e valores sai da VPS** para o provedor do modelo.
- **ADR-023, regra do mês:** tabelas, rodada e aviso novos sem o mês de uso manual.
- **Privacidade é decisão do dono (25/10).** Número de documento aparece completo no painel e para o Hermes (escopo `familia`), sem máscara por iniciativa do sistema. Logs, auditoria e payload de aviso continuam sem número.

**Limite conhecido.** Para tipos que podem coexistir (apólice, contrato, outro), um documento mais novo com o mesmo titular e tipo fecha o aviso de vencimento do outro.

**Fora.** Leitura de imagem por modelo; refazer OCR; escrever no Paperless; anexos de e-mail e Drive; preencher formulário sozinho.
