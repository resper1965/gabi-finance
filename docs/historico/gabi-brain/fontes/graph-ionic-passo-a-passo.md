# ionic (Microsoft 365 + Teams): o que o administrador do tenant precisa fazer
Decisão do Ricardo (16/10, revertendo a de não mexer na ionic): a Gabi **lê** e-mail, agenda e Teams da conta `resper@ionic.health`. Só leitura; e-mail inútil vai para **Itens Excluídos** (recuperável, nunca apaga de vez); nada é enviado (R2). A ionic usa Teams, não WhatsApp.

Já está pronto na VPS: o certificado do app. Chave privada em `/etc/gabi/graph.key` (root:gabibrain 0640). Certificado **público** em `~/ionic-graph-certificado.cer.pem` (vence em 15/10/2028); impressão digital (x5t): `WADeQiJcfaMprTLy35tnTIYLwT8` (em `~/ionic-graph-x5t.txt`).

## Passos no Entra ID (portal.azure.com ou entra.microsoft.com), por quem for administrador
1. **Registro de aplicativo** > Novo registro, nome "gabi-brain (leitura)", conta de uma só organização. Anote **ID do locatário (tenant)** e **ID do aplicativo (client)**.
2. **Certificados e segredos** > Certificados > Carregar: envie `ionic-graph-certificado.cer.pem`. Não crie segredo de cliente.
3. **Permissões de API** > Microsoft Graph > **Permissões de aplicativo** (não delegadas): `Mail.ReadWrite` (para mover ao Itens Excluídos; o código não envia nem apaga), `Calendars.Read`, `Chat.Read.All`, `ChannelMessage.Read.All`, `User.Read.All`. Clique em **Conceder consentimento do administrador**.
   - `Chat.Read.All` e `ChannelMessage.Read.All` como permissão de aplicativo são APIs protegidas do Teams: a Microsoft pede um formulário de solicitação de acesso a APIs protegidas (https://aka.ms/teamsgraph/requestaccess) antes de funcionarem. Sem isso o Graph responde 403 só nas mensagens do Teams; e-mail e agenda funcionam.
4. **Restringir à caixa do Ricardo** (recomendado, privilégio mínimo): no Exchange Online PowerShell, `New-ApplicationAccessPolicy -AppId <client> -PolicyScopeGroupId <grupo com só resper@ionic.health> -AccessRight RestrictAccess -Description "gabi-brain"`. Sem isso o app enxerga todas as caixas do tenant.
5. Entregue ao Ricardo (ele cola na VPS): tenant e client id.

## Na VPS (Ricardo)
`/etc/gabi/graph.env` (root:gabibrain 0640): `GRAPH_TENANT=<tenant>`, `GRAPH_CLIENT_ID=<client>`, `GRAPH_CERT_KEY_FILE=/etc/gabi/graph.key`, `GRAPH_CERT_X5T=WADeQiJcfaMprTLy35tnTIYLwT8`. Depois liberar a fonte em Cadastros (e-mail, agenda). O link de aprovação do administrador é gerado por `gabi.fontes.graph.link_aprovacao_admin(tenant, client_id)`.
