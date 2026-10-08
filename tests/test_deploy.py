import importlib
import re
import subprocess
from pathlib import Path

DEPLOY = Path(__file__).parent.parent / "deploy"
API = (DEPLOY / "gabi-brain-api.service").read_text()
BKP = (DEPLOY / "gabi-brain-backup.service").read_text()
TIMER = (DEPLOY / "gabi-brain-backup.timer").read_text()
INSTALAR = (DEPLOY / "instalar.sh").read_text()


def test_api_escuta_so_em_localhost_porta_8080():
    exec_start = re.search(r"^ExecStart=(.*)$", API, re.M).group(1)
    assert "--host 127.0.0.1" in exec_start and "--port 8080" in exec_start and "--factory gabi.api:fabrica" in exec_start


def test_nenhum_arquivo_de_deploy_escuta_em_todas_as_interfaces():
    for p in DEPLOY.iterdir():
        assert "0.0.0.0" not in p.read_text(), p.name


def test_servicos_rodam_como_usuario_sem_privilegios_e_endurecidos():
    for unidade in (API, BKP):
        assert "User=gabibrain" in unidade
        assert "NoNewPrivileges=yes" in unidade and "ProtectSystem=strict" in unidade
        assert "ProtectHome=yes" in unidade and "PrivateTmp=yes" in unidade
    assert "ReadWritePaths=/var/lib/gabi-brain" in API
    assert "/var/backups/gabi-brain" in BKP


def test_api_nao_le_arquivo_de_segredos_na_fase_0():
    assert "EnvironmentFile" not in API  # R5: a Fase 0 não usa credencial


def test_backup_diario_as_0330_com_teste_de_restauracao():
    assert "OnCalendar=*-*-* 03:30:00" in TIMER and "Persistent=true" in TIMER
    assert "-m gabi.backup" in BKP and "--testar" in BKP and "Type=oneshot" in BKP


def test_unidades_apontam_para_modulos_que_existem():
    assert hasattr(importlib.import_module("gabi.api"), "fabrica")
    assert hasattr(importlib.import_module("gabi.backup"), "main")


def test_instalar_tem_sintaxe_valida():
    assert subprocess.run(["bash", "-n", str(DEPLOY / "instalar.sh")]).returncode == 0


def test_instalar_exige_confirmacao_do_gate_g1():
    assert "--confirmo-backup-exportado" in INSTALAR


def test_instalar_nao_toca_nas_outras_pilhas_nem_em_segredos():
    for proibido in ("openclaw", "paperless", "buzz", "/etc/gabi", "docker", "ufw", "iptables"):
        assert proibido not in INSTALAR.lower(), proibido


def test_instalar_nao_abre_porta_nem_roda_tailscale_serve():
    executadas = [l for l in INSTALAR.splitlines() if l.strip() and not l.lstrip().startswith(("#", "echo"))]
    texto = "\n".join(executadas)
    assert "tailscale" not in texto and "ufw" not in texto
