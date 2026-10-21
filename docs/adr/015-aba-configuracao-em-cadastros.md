# ADR-015 — Aba "Configuração" na área Cadastros (desvio do protótipo, R17)

**Encerrada pela ADR-023 (22/10/2026):** a aba Configuração saiu (testava conexões de módulos cortados).

**Contexto.** O protótipo importado não tem o assistente de configuração inicial (T4.5). O Ricardo pediu o assistente em 7 passos (Microsoft 365, Bancos, Paperless, Nibo, Extras, Canal, Pronto), cada um testado na hora e adiável.

**Decisão.** Nova aba "Configuração" ("Está tudo conectado?") em Cadastros (grupo Casa), usando só as classes do sistema Industry. A tela nunca pede nem mostra segredo: diz em que arquivo de ambiente cada credencial vai (R5) e testa a conexão pela API.

**Consequência.** Um ponto de navegação a mais para as capturas do G14. O progresso fica em `setup_passo` (só estado e detalhe em português).

**Quando reverter.** Se o Ricardo preferir um assistente em tela cheia na primeira execução.
