# Migrações
Os números pulados (por exemplo 0024, 0033 a 0039, 0041 a 0049, 0052 a 0069) são faixas reservadas, não migrações perdidas: `gabi/db.py` (`migrar`) aplica por nome de arquivo, em ordem, as que existem, e anota cada uma em `schema_versao`.
