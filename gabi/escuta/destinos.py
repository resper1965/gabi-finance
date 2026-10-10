"""Destinos da escuta: o que acontece com uma mensagem já classificada. Só a interface; a implementação real é da Task 6."""
from typing import Protocol


class Destinos(Protocol):
    def pedido(self, con, remetente_pessoa_id: str, numero: str, msg: dict, campos: dict) -> None:
        """ValueError = pedido incompleto (a rodada marca a mensagem como falhou e avisa)."""

    def saude(self, con, msg: dict, campos: dict) -> None: ...

    def crise(self, con, numero: str, nome: str | None) -> None:
        """Nunca recebe o texto da mensagem."""
