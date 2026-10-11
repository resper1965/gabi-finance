# Ouvinte do WhatsApp (somente leitura)

Serviço Node pequeno e separado do brain. Liga ao WhatsApp pessoal como aparelho vinculado, **só recebe**, e grava cada mensagem
em `/var/lib/gabi-escuta-spool` (um JSON por mensagem, anexos em `anexos/`; contrato em `gabi/escuta/caixa.py` e em `docs/runbook.md#escuta`).
Nunca tem acesso ao banco nem a segredos. Nada de envio: `test/somente-leitura.test.js` falha se o código usar qualquer API de envio,
presença ou recibo, e confere `markOnlineOnConnect=false`, `syncFullHistory=false`, `emitOwnEvents=false`.

## Dependências (versões fixas)

| Pacote | Versão | Escolha |
|---|---|---|
| `@whiskeysockets/baileys` | **6.7.24** | 2026-10-11: `latest` do npm é `7.0.0-rc14` (pré-lançamento, descartado); a `legacy` estável mais nova é 6.7.24, publicada em 2026-07-29 (74 dias; regra: estável com 14+ dias). |
| `qrcode-terminal` | 0.12.0 | só para desenhar o QR no terminal em `--parear` |

`package-lock.json` foi gerado com `npm install --package-lock-only --ignore-scripts` (hashes de integridade, nenhum código de dependência executado).

**Verificação obrigatória do Ricardo antes de `npm ci --ignore-scripts` na VPS:**
- O Baileys já teve typosquats maliciosos no npm. Use somente o nome com escopo `@whiskeysockets/baileys`; confira `npm view @whiskeysockets/baileys@6.7.24 dist.integrity` contra `package-lock.json` (`sha512-Ljq7si+gsNIE9d5dP69E99TTQp+BxxPgitWvmZMXExGc1Ctr0SCDLFZmxRLUDC5HB0/Itw5uk+HJeBONrLP99Q==`) e o repositório oficial WhiskeySockets/Baileys.
- O Baileys declara `libsignal` como dependência git. Para não depender de git/ssh nem de código sem hash, o commit exato foi **vendorizado**: `vendor/libsignal-node-bcea72d.tgz` (código-fonte público de `WhiskeySockets/libsignal-node` no commit `bcea72df9ec34d9d9140ab30619cf479c7c144c7`, baixado de `https://codeload.github.com/WhiskeySockets/libsignal-node/tar.gz/bcea72df9ec34d9d9140ab30619cf479c7c144c7`; nada foi executado). `package.json` tem `"overrides": {"libsignal": "file:vendor/libsignal-node-bcea72d.tgz"}` e o lockfile guarda o integrity do tarball (teste confere). Tamanho 74615 bytes, sha256 `e8237ac721bdf8c622d2f13a4035b69acccb9f0c5999aa5e88944c4f171dd174`. **Passo do Ricardo:** baixe o mesmo commit do upstream, compare o sha256 e faça `diff -r` do conteúdo extraído contra o tarball (o gzip do GitHub pode variar, o conteúdo não).
- O lockfile foi gerado com `--legacy-peer-deps`: `sharp` (peer dependency do Baileys, com binários nativos) e `@img/*` NÃO entram; `jimp`, `audio-decode` e `link-preview-js` são opcionais e também não entram. O ouvinte só baixa e grava bytes (um teste falha se o lock tiver git/ssh, entrada sem integrity ou `sharp`). Na VPS use `npm ci --ignore-scripts --legacy-peer-deps`.
- O Baileys tem `install script`: por isso sempre `--ignore-scripts`.

## Uso

```
npm ci --ignore-scripts --legacy-peer-deps  # passo do Ricardo, em /opt/escuta-ouvinte
node src/ouvinte.js --parear            # QR no terminal; sai ao concluir
node src/ouvinte.js                     # roda para sempre (systemd: escuta-ouvinte.service)
node --test                             # testes; não precisam do Baileys instalado
```

Ambiente: `OUVINTE_SPOOL` (padrão `/var/lib/gabi-escuta-spool`), `OUVINTE_AUTH_DIR` (padrão `/var/lib/escuta-ouvinte/auth`), `OUVINTE_ANEXO_MAX_MB` (padrão 25, o mesmo teto do brain), `OUVINTE_ESPACO_MIN_MB` (padrão 2048) e `OUVINTE_DOWNLOAD_TIMEOUT_S` (padrão 60). O download é em fluxo: passou do teto (ou do prazo, ou tamanho declarado acima do teto) grava a mensagem sem anexo; nunca guarda o arquivo inteiro em memória antes de checar. Só documento e imagem de conversa privada são baixados: áudio e vídeo não (com legenda, só o texto), mídia de grupo nunca, e com menos de `OUVINTE_ESPACO_MIN_MB` livres na partição do spool nenhum anexo é baixado (contador `anexo_sem_espaco`). O `gatilho` é tocado no máximo 1 vez a cada 60 s. O brain apaga cada `<nome>.json` depois de gravá-lo no banco (não há `lidos/`): só a raiz do spool conta para "já gravado".
O estado de pareamento fica em `OUVINTE_AUTH_DIR` (0700); apagar essa pasta despareia.

## Privacidade e limites

- Log só com contadores e estado; nunca texto, número, nome ou QR (o QR só aparece no terminal do `--parear`).
- Quando o JID é `@lid` e o Baileys informa o telefone (`senderPn`/`participantPn`), `de` é o telefone; senão grava o id com `"lid": true`.
- Mídia expirada no servidor do WhatsApp não é rebaixada (não há pedido de reenvio): a mensagem é gravada sem anexo.
- O WhatsApp confirma entrega automaticamente (protocolo); o ouvinte nunca envia confirmação de leitura nem presença.
- Clientes não oficiais podem levar a restrição/banimento da conta; o aparelho vinculado pode ser desconectado após longa inatividade do celular.
