"""As telas do painel são testadas contra respostas reais da API (painel/tests/amostras). Se a API mudar, regenere: python -m tools.gerar_amostras."""
import json
from pathlib import Path

from tools.gerar_amostras import DESTINO, gerar


def test_amostras_do_painel_estao_atualizadas():
    atuais = gerar()
    for nome, corpo in atuais.items():
        arquivo = DESTINO / f"{nome}.json"
        assert arquivo.exists(), f"falta {arquivo.name}; rode python -m tools.gerar_amostras"
        assert json.loads(arquivo.read_text(encoding="utf-8")) == corpo, f"{arquivo.name} está desatualizado; rode python -m tools.gerar_amostras"
    sobras = {p.stem for p in Path(DESTINO).glob("*.json")} - set(atuais)
    assert not sobras, f"amostras sem rota: {sobras}"
