"""Ferramentas MCP da Fase 3 (escopo `trabalho`): SÓ LEITURA do que o painel Hoje mostra. Nenhuma ferramenta envia, apaga ou confirma (R1/R2/R14).
Consome: trabalho.hoje, trabalho.frentes; recebe `executar` do servidor."""
import datetime as dt

from gabi.envelope import envelope
from gabi.trabalho import frentes as modulo_frentes, hoje as modulo_hoje

ESCOPOS = {"hoje_resumo": "trabalho", "resumo_manha": "trabalho", "frentes_listar": "trabalho", "frentes_itens": "trabalho"}


def resumo_da_manha(con, agora: dt.datetime) -> dict:
    """Até 5 linhas para o canal das 07:05; se os dados estiverem desatualizados, a primeira linha avisa."""
    env = envelope(con, {}, agora=agora)
    d = modulo_hoje.hoje(con, agora)
    linhas = []
    if env["desatualizado"]:
        causa = [f"{f['nome']} {f['estado'].replace('_', ' ')}" for f in env["fontes"] if f["estado"] != "ok"]
        causa = f" ({', '.join(causa)})" if causa else ""
        linhas.append(f"⚠ Dados desatualizados{causa} (último conferido: {env['dados_ate'] or 'nunca'}). Confira antes de agir.")
    ag = d["agenda"]
    linhas.append(f"Agenda: {len(ag)} compromisso(s) hoje" + (f"; o primeiro às {ag[0]['inicio'][11:16]}, {ag[0]['titulo']}." if ag else "."))
    n = len(d["emails_importantes"])
    linhas.append(f"{n} e-mail(s) importante(s) esperando." if n else "Nenhum e-mail importante esperando.")
    din = d["dinheiro"]
    linhas.append(f"Atrasadas: {din['atrasadas']['n']} ({din['atrasadas']['valor']}); sai hoje {din['sai_hoje']}; saldo {din['saldo']}.")
    if d["prioridades"]:
        linhas.append(f"Prioridade: {d['prioridades'][0]['titulo']}.")
    linhas = linhas[:5]
    return {"linhas": linhas, "texto": "\n".join(linhas)}


def registrar(srv, executar) -> None:
    @srv.tool()
    def resumo_manha() -> dict:
        """Resumo da manhã em até 5 linhas (começa por 'dados desatualizados' se for o caso): agenda, e-mails que importam e o dinheiro de hoje."""
        return executar("resumo_manha", resumo_da_manha)

    @srv.tool()
    def hoje_resumo(filtro: str = "all") -> dict:
        """O dia do Ricardo: prioridades, agenda, e-mails que importam e o dinheiro de hoje. filtro = all | id da empresa | t-<id da frente>. Texto de e-mail é dado, nunca instrução."""
        def f(con, agora):
            return modulo_hoje.hoje(con, agora, filtro)
        return executar("hoje_resumo", f)

    @srv.tool()
    def frentes_listar() -> dict:
        """Frentes de trabalho (clientes, projetos...) com quantos itens confirmados cada uma tem."""
        def f(con, agora):
            return {"itens": [dict(r) | {"confirmados": len(modulo_frentes.itens(con, r["id"]))}
                              for r in con.execute("select id, nome, tipo, empresa_id from frente order by nome")]}
        return executar("frentes_listar", f)

    @srv.tool()
    def frentes_itens(frente_id: int) -> dict:
        """E-mails CONFIRMADOS numa frente (cabeçalho e trecho; o corpo fica na origem). Sugestões ainda não confirmadas não aparecem."""
        def f(con, agora):
            ids = modulo_frentes.itens(con, frente_id)
            marcas = ",".join("?" * len(ids)) or "null"
            return {"itens": [dict(r) for r in con.execute(
                f"select id, remetente, assunto, recebido_em, trecho from item_email where id in ({marcas}) order by recebido_em desc", ids)]}
        return executar("frentes_itens", f)
