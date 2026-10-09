# ADR-011 — Favorecido não é "para quem"

**Contexto.** Pagamentos a Carla e a Adriana (ex-esposas, mães das filhas) apareciam como se fossem para elas. O Ricardo paga por causa das filhas, não para elas.

**Decisão.** São dois campos distintos: favorecido = quem recebe o pagamento; "para quem" = quem se beneficia (Ricardo, Giovanna, Louise, Sabrina, Casa, Pets…). Carla e Adriana nunca são opções de "para quem". `gabi/dinheiro/favorecidos.py` sugere "para quem" por favorecido recorrente (mínimo 3), sempre como sugestão a confirmar. Não há regras de viagem (moeda, período, cidade): gasto de viagem é fato histórico decidido caso a caso.

**Consequência.** A pensão da Giovanna fica ligada a ela; qualquer favorecido novo exige uma decisão (ou regra por loja) antes de virar padrão.

**Quando reverter.** Se surgir beneficiário real que seja o próprio favorecido em volume (aí vale uma regra por favorecido explícita).
