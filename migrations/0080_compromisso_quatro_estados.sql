-- Conciliação achatada: só pago, aberto, atrasado e a_conferir; débito automático passa a ser a `forma` do compromisso.
update compromisso set estado='aberto' where estado in ('previsto','debito_automatico');
