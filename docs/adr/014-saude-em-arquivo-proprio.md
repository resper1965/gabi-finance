# ADR-014 · Saúde em arquivo próprio e criptografado
Data: 10/10/2026 · Estado: aceito (T4.1; o plano mestre a chamava de ADR-008)

**Contexto.** A saúde da família não pode estar no `gabi.db` (backups, exportações e o painel leem esse banco). A spec previa SQLCipher; não há SQLCipher no ambiente (nem pacote nativo instalado) e o Ricardo não quer dependência nativa nova só para isso.

**Decisão.** Arquivo próprio (`/var/lib/gabi-brain/saude.enc`, modo 0600) cifrado inteiro com **AES-256-GCM** (`cryptography`). O SQLite só existe **em memória** enquanto o `with abrir_saude(...)` está aberto; sair sem erro grava (arquivo novo + rename), com erro descarta. A chave (32 bytes) vem de arquivo de ambiente colocado pelo Ricardo (R5), nunca do repositório. Toda leitura entra na tabela `leitura` (quem, pessoa, o quê). Nenhuma tabela ou coluna de saúde existe no banco principal (teste de esquema).

**Consequências.** Simples e sem dependência nativa; o arquivo inteiro é regravado a cada alteração (volume pequeno: exames de 6 pessoas) e há um escritor por vez (o chamador serializa; a API usa um lock de processo). Trocar por SQLCipher depois só muda `gabi/familia/saude.py`. Perder a chave = perder os dados: a chave entra no mesmo cofre do `backup.pub`/restic, e o arquivo cifrado entra no backup.

**Acesso.** `grau(matriz_acesso, 'saúde', nível)`: `total` vê todos; `parcial` só a própria pessoa (`pode_ver`); `nenhum` nunca. O laudo só entra com a pessoa confirmada por alguém (`confirmado_por`).
