"""Rodada única da fila de "para quem": sugestão pendente que hoje passa no critério certeiro (classificar.para_quem_certeiro) é aplicada
e fechada ("aplicada sozinha"); a de lançamento que a Gabi já preencheu com a mesma pessoa também fecha; as demais seguem pendentes (ADR-023).
Idempotente: só olha pendentes. Consome: sugestao, lancamento."""
import json

from gabi.dinheiro.classificar import aplicar_certeiro, para_quem_certeiro


def aplicar_fila_para_quem(con, agora_iso: str) -> int:
    aplicadas = 0
    for s in con.execute("select s.id, s.lancamento_id, s.payload, l.estabelecimento, l.para_quem_id, l.para_quem_origem from sugestao s "
                         "join lancamento l on l.id=s.lancamento_id where s.tipo='para_quem' and s.estado='pendente' order by s.id").fetchall():
        sugerida = json.loads(s["payload"]).get("para_quem_id")
        if s["para_quem_id"] is not None:
            if s["para_quem_origem"] == "gabi" and s["para_quem_id"] == sugerida:
                con.execute("update sugestao set estado='aprovada', decidida_em=?, motivo=coalesce(motivo,'') || '; aplicada sozinha' where id=?", (agora_iso, s["id"]))
            continue
        pessoa = para_quem_certeiro(con, s["lancamento_id"], s["estabelecimento"])
        if pessoa is None or sugerida != pessoa:
            continue
        aplicar_certeiro(con, s["lancamento_id"], s["estabelecimento"], pessoa, agora_iso)
        aplicadas += 1
    return aplicadas
