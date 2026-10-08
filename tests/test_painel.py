"""O painel (painel/) entra na mesma suíte: Vitest (fidelidade ao design, componentes, telas, contrato com a API) e build."""
import shutil
import subprocess
from pathlib import Path

import pytest

PAINEL = Path(__file__).resolve().parent.parent / "painel"
pytestmark = pytest.mark.skipif(shutil.which("npm") is None or not (PAINEL / "node_modules").exists(), reason="node/npm ou painel/node_modules ausente")


def _npm(*args):
    return subprocess.run(["npm", *args], cwd=PAINEL, capture_output=True, text=True, timeout=300)


def test_vitest_do_painel_passa():
    r = _npm("test")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-1000:]


def test_build_do_painel_passa_e_respeita_o_orcamento_de_150kb():
    r = _npm("run", "build")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-1000:]
    a = _npm("run", "analisar")
    assert a.returncode == 0, a.stdout[-1000:]
