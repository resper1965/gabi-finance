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
- O Baileys traz um `install script` e uma dependência **git** (`libsignal` de `github.com/whiskeysockets/libsignal-node`, fixada por commit `bcea72d…`, sem hash de integridade do npm). Por isso `--ignore-scripts`. O lockfile referencia o git por `ssh://`; sem chave SSH do GitHub o `npm ci` falha, e o contorno é `git config --global url."https://github.com/".insteadOf ssh://git@github.com/` (como root, só para o `npm ci`).
- Dependências opcionais do Baileys (sharp, jimp, audio-decode) NÃO são usadas: o ouvinte só baixa e grava bytes.

## Uso

```
npm ci --ignore-scripts                 # passo do Ricardo, em /opt/escuta-ouvinte
node src/ouvinte.js --parear            # QR no terminal; sai ao concluir
node src/ouvinte.js                     # roda para sempre (systemd: escuta-ouvinte.service)
node --test                             # testes; não precisam do Baileys instalado
```

Ambiente: `OUVINTE_SPOOL` (padrão `/var/lib/gabi-escuta-spool`), `OUVINTE_AUTH_DIR` (padrão `/var/lib/escuta-ouvinte/auth`), `OUVINTE_ANEXO_MAX_MB` (padrão 50; acima disso grava a mensagem sem anexo).
O estado de pareamento fica em `OUVINTE_AUTH_DIR` (0700); apagar essa pasta despareia.

## Privacidade e limites

- Log só com contadores e estado; nunca texto, número, nome ou QR (o QR só aparece no terminal do `--parear`).
- Mídia expirada no servidor do WhatsApp não é rebaixada (não há pedido de reenvio): a mensagem é gravada sem anexo.
- O WhatsApp confirma entrega automaticamente (protocolo); o ouvinte nunca envia confirmação de leitura nem presença.
- Clientes não oficiais podem levar a restrição/banimento da conta; o aparelho vinculado pode ser desconectado após longa inatividade do celular.
