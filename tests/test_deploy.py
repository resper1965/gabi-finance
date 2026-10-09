import importlib
import pytest
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
    for pacote in ("fastapi", "uvicorn", "starlette", "pydantic", "mcp"):
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
    assert r.stdout.strip() == str(len(list((DEPLOY.parent / "migrations").glob("*.sql"))))
    assert (tmp_path / "gabi" / "static" / "index.html").exists()


def test_instalar_nao_toca_nas_outras_pilhas_nem_em_segredos():
    executadas = "\n".join(l for l in INSTALAR.splitlines() if l.strip() and not l.lstrip().startswith(("#", "echo"))).lower()
    for proibido in ("openclaw", "paperless", "buzz", "/etc/gabi", "docker", "ufw", "iptables"):
        assert proibido not in executadas, proibido  # mencionar em comentário/mensagem é ok; executar, não


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


# ---------------- Fase 1: servidor MCP e rodadas de captura ----------------
def _ler(nome):
    return (DEPLOY / nome).read_text()


MCP = _ler("gabi-brain-mcp.service")
SALDOS, EXTRATOS = _ler("gabi-brain-saldos.service"), _ler("gabi-brain-extratos.service")
T_SALDOS, T_EXTRATOS = _ler("gabi-brain-saldos.timer"), _ler("gabi-brain-extratos.timer")


def test_mcp_escuta_so_em_localhost_8081_sem_proxy_headers():
    ex = re.search(r"^ExecStart=(.*)$", MCP, re.M).group(1)
    assert "--factory gabi.mcp.servidor:fabrica" in ex and "--host 127.0.0.1" in ex and "--port 8081" in ex and "--no-proxy-headers" in ex
    assert "0.0.0.0" not in MCP


def test_mcp_so_aceita_trafego_local_e_nao_le_segredo_de_agentes():
    assert "IPAddressDeny=any" in MCP and "IPAddressAllow=localhost" in MCP
    assert "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX" in MCP
    assert "EnvironmentFile" not in MCP  # o MCP só usa tokens do banco; nenhuma chave de fonte externa


def test_servicos_de_captura_podem_sair_para_a_internet_mas_com_o_resto_endurecido():
    for u in (SALDOS, EXTRATOS):
        assert "EnvironmentFile=-/etc/gabi/brain.env" in u            # a chave da mcp.ai (G4); '-' = opcional
        assert "IPAddressDeny" not in u and "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX" in u
        for dur in ("User=gabibrain", "NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes", "UMask=0077"):
            assert dur in u, dur
        assert "ReadWritePaths=/var/lib/gabi-brain" in u and "Type=oneshot" in u


def test_captura_chama_os_modulos_certos():
    assert "-m gabi.dinheiro.rodar saldos" in SALDOS
    assert "-m gabi.dinheiro.rodar extratos --sincronizar" in EXTRATOS and "TimeoutStartSec=" in EXTRATOS
    assert hasattr(importlib.import_module("gabi.dinheiro.rodar"), "main") and hasattr(importlib.import_module("gabi.mcp.servidor"), "fabrica")


def test_horarios_saldos_de_hora_em_hora_e_extratos_as_07_e_15_de_brasilia():
    assert "OnCalendar=*-*-* *:05:00" in T_SALDOS and "Persistent=true" in T_SALDOS
    assert "OnCalendar=*-*-* 06,14:00:00 America/Sao_Paulo" in T_EXTRATOS and "Persistent=true" in T_EXTRATOS


@pytest.mark.skipif(subprocess.run(["which", "systemd-analyze"], capture_output=True).returncode != 0, reason="sem systemd-analyze")
def test_os_horarios_sao_aceitos_pelo_systemd():
    for t in (T_SALDOS, T_EXTRATOS, TIMER):
        expr = re.search(r"^OnCalendar=(.*)$", t, re.M).group(1)
        r = subprocess.run(["systemd-analyze", "calendar", expr], capture_output=True, text=True)
        assert r.returncode == 0, (expr, r.stderr)


def test_instalar_liga_api_mcp_e_backup_mas_nao_a_captura():
    ligadas = [l for l in INSTALAR.splitlines() if "enable --now" in l and not l.lstrip().startswith(("#", "echo"))]
    assert len(ligadas) == 1 and "gabi-brain-api.service" in ligadas[0] and "gabi-brain-mcp.service" in ligadas[0] and "gabi-brain-backup.timer" in ligadas[0]
    assert "extratos" not in ligadas[0] and "saldos" not in ligadas[0]  # só depois do G4 (chave da mcp.ai)
    assert "gabi-brain-extratos.timer" in INSTALAR and "gabi-brain-saldos.timer" in INSTALAR  # mas instala as unidades


def test_instalar_cria_pastas_do_bruto_e_dos_locks_privadas():
    assert "/var/lib/gabi-brain/bruto" in INSTALAR and "/var/lib/gabi-brain/locks" in INSTALAR


def test_nenhuma_unidade_traz_segredo():
    for p in DEPLOY.iterdir():
        assert not re.search(r"sk_live|sk-[a-z0-9]{10}|Bearer |gb_[A-Za-z0-9_-]{20}", p.read_text()), p.name


def test_api_e_mcp_leem_o_arquivo_de_ambiente_dos_segredos():
    from pathlib import Path
    for u in ("gabi-brain-api.service", "gabi-brain-mcp.service"):
        assert "EnvironmentFile=-/etc/gabi/brain.env" in (Path(__file__).parent.parent / "deploy" / u).read_text()  # NIBO_TOKEN/PAPERLESS_* chegam ao processo
