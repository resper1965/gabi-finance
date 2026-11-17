# Fonte: Microsoft Graph (IONIC; ness depois da migração) — `gabi/fontes/graph.py` (T3.1, gate G11)
- **Autenticação:** app registrado no Entra ID com **certificado** (client_credentials; `assertion_certificado` monta o JWT RS256 com `x5t`). Admin do tenant precisa aprovar: `link_aprovacao_admin(tenant, client_id)` gera o link para o Ricardo copiar e enviar. Certificado e IDs ficam no arquivo de ambiente, nunca no banco nem no código (R5).
- **Escopos mínimos:** leitura de mensagens, agenda e tarefas; `Mail.ReadWrite` só para criar **rascunho**. A classe não tem `send*` nem exclusão (R2).
- **Incremental:** `delta_mensagens` / `delta_eventos` devolvem o `deltaLink`; guardar em `caixa_email.cursor` e usar na rodada seguinte.
- **Renovação do certificado:** antes do vencimento, gerar o novo, subir no app e trocar no ambiente; o aviso fica no vigia.
- **Estado:** cliente pronto e testado contra servidor falso. **Não validado com o tenant real** (falta G11).
