"""Tarefas (To Do do Graph, Tasks do Google). Espelho local; concluir acontece NA ORIGEM (rota /tarefas/{id}/concluir)."""
from gabi.db import transacao


def ingerir_tarefas(con, origem: str, tarefas: list[dict]) -> int:
    with transacao(con):
        for t in tarefas:
            con.execute("insert into tarefa(origem, externo_id, titulo, prazo, estado) values (?,?,?,?,?) "
                        "on conflict(origem, externo_id) do update set titulo=excluded.titulo, prazo=excluded.prazo, estado=excluded.estado",
                        (origem, t["externo_id"], t["titulo"], t.get("prazo"), "concluida" if t.get("concluida") else "aberta"))
    return len(tarefas)
