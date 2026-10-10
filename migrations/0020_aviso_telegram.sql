-- 0020: quando o aviso foi enviado ao Telegram (NULL = não enviado). Só é preenchido depois que o Telegram responde 200 (G15).
alter table aviso add column telegram_em text;
