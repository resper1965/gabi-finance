import importlib
import re
import subprocess
from pathlib import Path

DEPLOY = Path(__file__).parent.parent / "deploy"
API = (DEPLOY / "gabi-brain-api.service").read_text()
BKP = (DEPLOY / "gabi-brain-backup.service").read_text()
TIMER = (DEPLOY / "gabi-brain-backup.timer").read_text()
INSTALAR = (DEPLOY / "instalar.sh").read_text()


def test_api_escuta_so_em_socket_unix_sem_proxy_headers():
    exec_start = re.search(r"^ExecStart=(.*)$", API, re.M).group(1)
    assert "--uds /run/gabi-brain/api.sock" in exec_start and "--factory gabi.api:fabrica" in exec_start
    assert "--no-proxy-headers" in exec_start      # C1: nunca confiar em X-Forwarded-For
    assert "--port" not in exec_start and "--host" not in exec_start


def test_socket_fica_em_pasta_so_do_servico():
    assert "RuntimeDirectory=gabi-brain" in API and "RuntimeDirectoryMode=0700" in API and "UMask=0077" in API


def test_servicos_sem_rede_alem_de_socket_unix():
    for unidade in (API, BKP):
        assert "IPAddressDeny=any" in unidade and "RestrictAddressFamilies=AF_UNIX" in unidade
        assert "PrivateDevices=yes" in unidade and "ProtectKernelTunables=yes" in unidade


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


def test_instalar_usa_dependencias_fixas_e_nao_instala_o_projeto():
    assert "requirements.lock" in INSTALAR and "pip install /opt/gabi-brain" not in INSTALAR
    lock = (DEPLOY.parent / "requirements.lock").read_text()
    for pacote in ("fastapi", "uvicorn", "starlette", "pydantic"):
        assert re.search(rf"^{pacote}==\d", lock, re.M | re.I), pacote


def test_arvore_copiada_pelo_instalar_roda_sozinha(tmp_path):
    """C2: copia só o que o instalar.sh copia e importa/arranca a app a partir dali (sem pip install do projeto)."""
    import os, shutil, sys
    raiz = DEPLOY.parent
    shutil.copytree(raiz / "gabi", tmp_path / "gabi", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(raiz / "migrations", tmp_path / "migrations")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"} | {"GABI_BANCO": str(tmp_path / "x.db")}
    codigo = ("from gabi.api import fabrica; a = fabrica(); import sqlite3; "
              "c = sqlite3.connect(r'%s'); print(c.execute('select count(*) from schema_versao').fetchone()[0])"
              % (tmp_path / "x.db"))
    r = subprocess.run([sys.executable, "-c", codigo], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "1"
    assert (tmp_path / "gabi" / "static" / "index.html").exists()


def test_instalar_nao_toca_nas_outras_pilhas_nem_em_segredos():
    for proibido in ("openclaw", "paperless", "buzz", "/etc/gabi", "docker", "ufw", "iptables"):
        assert proibido not in INSTALAR.lower(), proibido


def test_instalar_nao_abre_porta_nem_roda_tailscale_serve():
    executadas = [l for l in INSTALAR.splitlines() if l.strip() and not l.lstrip().startswith(("#", "echo"))]
    texto = "\n".join(executadas)
    assert "tailscale" not in texto and "ufw" not in texto


def test_uvicorn_real_em_socket_unix_ignora_x_forwarded_for(tmp_path):
    """C1: com o uvicorn de verdade, X-Forwarded-For não pode trocar a origem e derrubar a identidade."""
    import http.client, os, socket, subprocess as sp, sys, time
    from gabi.acesso import adicionar
    from gabi.db import conectar, migrar

    banco = tmp_path / "g.db"
    con = conectar(banco)
    migrar(con, DEPLOY.parent / "migrations")
    adicionar(con, "boss@x.com", "p1", "boss", por="t")
    con.close()
    sock = tmp_path / "api.sock"
    env = {**os.environ, "GABI_BANCO": str(banco)}
    proc = sp.Popen([sys.executable, "-m", "uvicorn", "--factory", "gabi.api:fabrica", "--uds", str(sock),
                     "--no-proxy-headers"], cwd=DEPLOY.parent, env=env, stdout=sp.DEVNULL, stderr=sp.DEVNULL,
                    preexec_fn=lambda: os.umask(0o077))
    try:
        for _ in range(100):
            if sock.exists():
                break
            time.sleep(0.1)
        assert sock.exists(), "uvicorn não criou o socket"

        class Unix(http.client.HTTPConnection):
            def connect(self):
                self.sock = socket.socket(socket.AF_UNIX)
                self.sock.connect(str(sock))

        def pedir(cab):
            c = Unix("localhost")
            c.request("GET", "/api/eu", headers=cab)
            r = c.getresponse()
            return r.status

        assert pedir({"Tailscale-User-Login": "boss@x.com", "X-Forwarded-For": "100.101.102.103"}) == 200
        assert pedir({"Tailscale-User-Login": "boss@x.com", "X-Forwarded-For": "127.0.0.1"}) == 200
        assert pedir({"X-Forwarded-For": "100.1.1.1"}) == 401
        # O uvicorn força 0666 no arquivo do socket (sem opção). A barreira é a PASTA 0700 do serviço
        # (RuntimeDirectoryMode=0700, coberta em test_socket_fica_em_pasta_so_do_servico).
    finally:
        proc.terminate()
        proc.wait(timeout=10)
