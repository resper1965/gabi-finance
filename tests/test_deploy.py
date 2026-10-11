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


# ---------------- Fase 2: serviço de fontes (ponte para Paperless e Nibo) ----------------
FONTES = _ler("gabi-brain-fontes.service")


def test_so_o_servico_de_fontes_tem_rede_e_le_o_arquivo_de_tokens():
    assert "EnvironmentFile=-/etc/gabi/cobrar.env" in FONTES
    assert "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX" in FONTES and "IPAddressDeny" not in FONTES
    for u in (API, MCP):
        assert "EnvironmentFile" not in u and "GABI_FONTES_SOCKET=/run/gabi-brain-fontes/fontes.sock" in u
        assert "IPAddressDeny=any" in u  # a API e o MCP continuam sem rede


def test_ponte_so_para_o_servico_e_o_grupo():
    assert "User=gabibrain-fontes" in FONTES and "Group=gabibrain" in FONTES
    assert "RuntimeDirectory=gabi-brain-fontes" in FONTES and "RuntimeDirectoryMode=0750" in FONTES and "UMask=0007" in FONTES
    for dur in ("NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes", "PrivateDevices=yes", "CapabilityBoundingSet="):
        assert dur in FONTES, dur
    assert "-m gabi.fontes.servico --socket /run/gabi-brain-fontes/fontes.sock" in FONTES
    assert hasattr(importlib.import_module("gabi.fontes.servico"), "main")


def test_instalar_cria_o_usuario_e_liga_o_servico_de_fontes():
    assert "useradd" in INSTALAR and "gabibrain-fontes" in INSTALAR
    ligadas = [l for l in INSTALAR.splitlines() if "enable --now" in l and not l.lstrip().startswith(("#", "echo"))]
    assert "gabi-brain-fontes.service" in ligadas[0] and "gabi-brain-fontes.service" in INSTALAR.split("restart")[1]


# ---------------- avisos (plano de finalização, tarefa 4): o brain passa a avisar quando algo para ----------------
AVISOS, T_AVISOS, FALHA = _ler("gabi-brain-avisos.service"), _ler("gabi-brain-avisos.timer"), _ler("gabi-brain-falha@.service")
NOTAS = _ler("gabi-brain-notas.service")


def test_timer_de_avisos_roda_a_cada_15_minutos_e_esta_instalado_e_habilitado():
    assert "OnUnitActiveSec=15min" in T_AVISOS and "Unit=gabi-brain-avisos.service" in T_AVISOS
    for nome in ("gabi-brain-avisos.service", "gabi-brain-avisos.timer", "gabi-brain-falha@.service"):
        assert nome in INSTALAR
    ligadas = [l for l in INSTALAR.splitlines() if l.startswith("systemctl enable")]
    assert ligadas and "gabi-brain-avisos.timer" in ligadas[0]


def test_servicos_de_rotina_avisam_quando_falham():
    # a chave do mcp.ai expirou em 09/10 e ninguém soube por horas: toda rotina com OnFailure= chama o serviço de falha
    for texto in (SALDOS, EXTRATOS, BKP, NOTAS, AVISOS):
        assert "OnFailure=gabi-brain-falha@%n.service" in texto


def test_servico_de_falha_grava_aviso_com_o_nome_da_unidade_e_sem_rede():
    ex = re.search(r"^ExecStart=(.*)$", FALHA, re.M).group(1)
    assert "gabi.avisos" in ex and "--falha %i" in ex and "RestrictAddressFamilies=AF_UNIX" in FALHA and "User=gabibrain" in FALHA


def test_servico_de_avisos_so_le_e_grava_o_banco_sem_rede():
    assert "gabi.avisos" in AVISOS and "User=gabibrain" in AVISOS and "RestrictAddressFamilies=AF_UNIX" in AVISOS and "ReadWritePaths=/var/lib/gabi-brain" in AVISOS
    assert "NoNewPrivileges=yes" in AVISOS and "ProtectSystem=strict" in AVISOS


def test_timer_de_notas_roda_todo_dia_cedo_em_horario_de_brasilia_e_esta_instalado():
    t = _ler("gabi-brain-notas.timer")
    assert "OnCalendar=*-*-* 06:40:00 America/Sao_Paulo" in t and "Unit=gabi-brain-notas.service" in t and "Persistent=true" in t
    assert "gabi-brain-notas.timer" in INSTALAR
    ligadas = [l for l in INSTALAR.splitlines() if l.startswith("systemctl enable")]
    assert ligadas and "gabi-brain-notas.timer" in ligadas[0]


def test_timer_de_exportacao_semanal_instalado():
    svc = (DEPLOY / "gabi-brain-exportacao.service").read_text()
    tmr = (DEPLOY / "gabi-brain-exportacao.timer").read_text()
    expr = re.search(r"^OnCalendar=(.*)$", tmr, re.M).group(1)
    assert subprocess.run(["systemd-analyze", "calendar", expr], capture_output=True, text=True).returncode == 0
    assert expr.startswith("Sun ") and "America/Sao_Paulo" in expr
    assert "-m gabi.exportacao" in svc and "ConditionPathExists=/etc/gabi/backup.pub" in svc  # sem chave, não roda (nem exporta em claro)
    assert "OnFailure=gabi-brain-falha@%n.service" in svc and "IPAddressDeny=any" in svc
    assert "gabi-brain-exportacao.timer" in INSTALAR and "gabi-brain-exportacao.service" in INSTALAR
    ligadas = [l for l in INSTALAR.splitlines() if "enable --now" in l and not l.lstrip().startswith(("#", "echo"))]
    assert "gabi-brain-exportacao.timer" in ligadas[0]


def test_ingestao_de_comprovantes_tem_timer_diario_usa_a_ponte_e_avisa_quando_falha():
    srv, t = _ler("gabi-brain-comprovantes.service"), _ler("gabi-brain-comprovantes.timer")
    assert "gabi.cobrar.ingestao" in srv and "GABI_FONTES_SOCKET=/run/gabi-brain-fontes/fontes.sock" in srv
    assert "RestrictAddressFamilies=AF_UNIX" in srv and "OnFailure=gabi-brain-falha@%n.service" in srv and "User=gabibrain" in srv
    assert "OnCalendar=*-*-* 07:00:00 America/Sao_Paulo" in t and "Unit=gabi-brain-comprovantes.service" in t
    for nome in ("gabi-brain-comprovantes.service", "gabi-brain-comprovantes.timer"):
        assert nome in INSTALAR
    ligadas = [l for l in INSTALAR.splitlines() if l.startswith("systemctl enable")]
    assert ligadas and "gabi-brain-comprovantes.timer" in ligadas[0]


def test_job_do_trabalho_roda_de_15_em_15_min_com_credenciais_so_do_ambiente_e_avisa_quando_falha():
    srv, t = _ler("gabi-brain-trabalho.service"), _ler("gabi-brain-trabalho.timer")
    assert "-m gabi.trabalho" in srv and "EnvironmentFile=-/etc/gabi/trabalho.env" in srv and "OnFailure=gabi-brain-falha@%n.service" in srv
    assert "User=gabibrain" in srv and "NoNewPrivileges=yes" in srv and "ProtectSystem=strict" in srv and "ReadWritePaths=/var/lib/gabi-brain" in srv
    assert "Unit=gabi-brain-trabalho.service" in t
    for nome in ("gabi-brain-trabalho.service", "gabi-brain-trabalho.timer"):
        assert nome in INSTALAR
    ligadas = [l for l in INSTALAR.splitlines() if l.startswith("systemctl enable")]
    assert ligadas and "gabi-brain-trabalho.timer" in ligadas[0]


def test_api_le_a_chave_da_saude_so_de_arquivo_e_grava_o_cofre_na_pasta_do_banco():
    api = _ler("gabi-brain-api.service")
    assert "GABI_SAUDE_CHAVE_ARQUIVO=/etc/gabi/saude.key" in api and "ReadWritePaths=/var/lib/gabi-brain" in api
    assert "saude.key" not in INSTALAR or "chmod" in INSTALAR  # a chave nunca é criada pelo instalador


def test_telegram_so_envia_com_arquivo_de_ambiente_do_ricardo_e_nao_tem_o_token_no_repositorio():
    srv, t = _ler("gabi-brain-telegram.service"), _ler("gabi-brain-telegram.timer")
    assert "-m gabi.telegram" in srv and "EnvironmentFile=-/etc/gabi/telegram.env" in srv and "OnFailure=gabi-brain-falha@%n.service" in srv
    assert "User=gabibrain" in srv and "NoNewPrivileges=yes" in srv and "ReadWritePaths=/var/lib/gabi-brain" in srv
    assert "OnUnitActiveSec=5min" in t and "Unit=gabi-brain-telegram.service" in t
    ligadas = [l for l in INSTALAR.splitlines() if l.startswith("systemctl enable")]
    assert ligadas and "gabi-brain-telegram.timer" in ligadas[0]
    assert "TELEGRAM_BOT_TOKEN=" not in srv + t + INSTALAR


def test_unit_fontes_tem_environmentfile_opcional_do_openrouter():
    assert "EnvironmentFile=-/etc/gabi/openrouter.env" in FONTES
    for u in (API, MCP):
        assert "openrouter" not in u  # a chave só é lida pelo serviço de fontes


def test_runbook_openrouter_env_root_0600_e_limite_de_credito():
    from pathlib import Path
    rb = (Path(__file__).resolve().parent.parent / "docs/runbook.md").read_text()
    trecho = rb.split("{#openrouter}")[1].split("\n## ")[0]
    assert "root:root" in trecho and "0600" in trecho and "limite de crédito" in trecho


# ---------------- escuta (WhatsApp): serviço, timer e gatilho por arquivo ----------------
def test_unidades_escuta_seguem_o_padrao():
    srv, t, p = _ler("gabi-brain-escuta.service"), _ler("gabi-brain-escuta.timer"), _ler("gabi-brain-escuta.path")
    assert "-m gabi.escuta" in srv and "Type=oneshot" in srv and "User=gabibrain" in srv
    assert "OnFailure=gabi-brain-falha@%n.service" in srv
    assert "GABI_FONTES_SOCKET=/run/gabi-brain-fontes/fontes.sock" in srv and "GABI_ESCUTA_SPOOL=/var/lib/gabi-escuta-spool" in srv
    assert "RestrictAddressFamilies=AF_UNIX" in srv and "IPAddressDeny=any" in srv
    assert "ReadWritePaths=/var/lib/gabi-brain /var/lib/gabi-escuta-spool" in srv
    for dur in ("NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes", "PrivateDevices=yes", "UMask=0077"):
        assert dur in srv, dur
    assert "EnvironmentFile" not in srv
    assert "OnUnitActiveSec=5min" in t and "OnBootSec=2min" in t and "Unit=gabi-brain-escuta.service" in t
    assert "PathChanged=/var/lib/gabi-escuta-spool/gatilho" in p and "Unit=gabi-brain-escuta.service" in p
    assert hasattr(importlib.import_module("gabi.escuta.__main__"), "main")
    for nome in ("gabi-brain-escuta.service", "gabi-brain-escuta.timer", "gabi-brain-escuta.path"):
        assert nome in INSTALAR


def test_instalar_nao_liga_timer_nem_path_da_escuta():
    ligadas = [l for l in INSTALAR.splitlines() if "enable" in l and not l.lstrip().startswith(("#", "echo"))]
    assert not any("escuta" in l for l in ligadas)


def test_spool_da_escuta_fica_fora_da_arvore_0700_com_setgid_e_grupo():
    srv = _ler("gabi-brain-escuta.service")
    assert "/var/lib/gabi-brain/escuta-spool" not in INSTALAR + srv + _ler("gabi-brain-escuta.path")
    assert "SupplementaryGroups=gabibrain-escuta" in srv
    assert "ReadWritePaths=/var/lib/gabi-brain /var/lib/gabi-escuta-spool" in srv
    assert "groupadd --system gabibrain-escuta" in INSTALAR
    assert re.search(r"install -d -o gabibrain -g gabibrain-escuta -m 2770 /var/lib/gabi-escuta-spool", INSTALAR)


def test_service_da_escuta_sem_limite_de_partidas_para_o_path_nao_se_desligar():
    assert "StartLimitIntervalSec=0" in _ler("gabi-brain-escuta.service").split("[Service]")[0]


# ---------------- contatos do Google ----------------
def test_unidades_contatos_seguem_o_padrao_e_nao_sao_ligadas():
    srv, t = _ler("gabi-brain-contatos.service"), _ler("gabi-brain-contatos.timer")
    assert "-m gabi.escuta.contatos" in srv and "Type=oneshot" in srv and "User=gabibrain" in srv
    assert "OnFailure=gabi-brain-falha@%n.service" in srv
    assert "GABI_FONTES_SOCKET=/run/gabi-brain-fontes/fontes.sock" in srv
    assert "RestrictAddressFamilies=AF_UNIX" in srv and "IPAddressDeny=any" in srv and "ReadWritePaths=/var/lib/gabi-brain" in srv
    for dur in ("NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes", "PrivateDevices=yes", "UMask=0077"):
        assert dur in srv, dur
    assert "EnvironmentFile" not in srv
    assert "OnCalendar=*-*-* 05:00:00 America/Sao_Paulo" in t and "Unit=gabi-brain-contatos.service" in t
    assert hasattr(importlib.import_module("gabi.escuta.contatos"), "main")
    for nome in ("gabi-brain-contatos.service", "gabi-brain-contatos.timer"):
        assert nome in INSTALAR
    ligadas = [l for l in INSTALAR.splitlines() if "enable" in l and not l.lstrip().startswith(("#", "echo"))]
    assert not any("contatos" in l for l in ligadas)


def test_fontes_le_o_ambiente_dos_contatos_como_opcional():
    assert "EnvironmentFile=-/etc/gabi/google-contatos.env" in _ler("gabi-brain-fontes.service")


# ---------------- ouvinte do WhatsApp (serviço separado, só leitura) ----------------
def test_unidade_do_ouvinte_segue_o_padrao_e_isola_o_brain():
    u = (DEPLOY / "escuta-ouvinte.service").read_text()
    for linha in ("User=escuta-ouvinte", "Group=escuta-ouvinte", "SupplementaryGroups=gabibrain-escuta", "UMask=0007",
                  "Restart=always", "RestartSec=10", "WorkingDirectory=/opt/escuta-ouvinte",
                  "ExecStart=/usr/bin/node /opt/escuta-ouvinte/src/ouvinte.js",
                  "NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes", "PrivateDevices=yes",
                  "ProtectKernelTunables=yes", "ProtectKernelModules=yes", "ProtectControlGroups=yes", "CapabilityBoundingSet=\n",
                  "RestrictAddressFamilies=AF_INET AF_INET6\n", "ReadWritePaths=/var/lib/gabi-escuta-spool /var/lib/escuta-ouvinte\n",
                  "InaccessiblePaths=/var/lib/gabi-brain /etc/gabi", "MemoryMax=512M",
                  "ProtectKernelLogs=yes", "ProtectClock=yes", "RestrictNamespaces=yes", "LockPersonality=yes",
                  "RestrictSUIDSGID=yes", "SystemCallFilter=@system-service", "SystemCallErrorNumber=EPERM",
                  "RestartPreventExitStatus=78",
                  "OUVINTE_SPOOL=/var/lib/gabi-escuta-spool", "OUVINTE_AUTH_DIR=/var/lib/escuta-ouvinte/auth"):
        assert linha in u, linha
    assert "AF_UNIX" not in re.sub(r"(?m)^#.*$", "", u)
    assert "EnvironmentFile" not in u and "gabi-brain.env" not in u


def test_instalar_cria_usuario_do_ouvinte_e_instala_sem_ligar_nem_rodar_npm():
    assert "escuta-ouvinte.service" in INSTALAR
    assert re.search(r"useradd --system .*--shell /usr/sbin/nologin .*escuta-ouvinte", INSTALAR)
    assert "gabibrain-escuta" in re.search(r"useradd .*escuta-ouvinte", INSTALAR).group(0)
    assert re.search(r"install -d -o escuta-ouvinte -g escuta-ouvinte -m 700 /var/lib/escuta-ouvinte", INSTALAR)
    assert "/opt/escuta-ouvinte" in INSTALAR
    assert 'cp -r "$AQUI/ouvinte/vendor" /opt/escuta-ouvinte/vendor' in INSTALAR
    ativas = [l for l in INSTALAR.splitlines() if not l.lstrip().startswith(("#", "echo"))]
    assert not any("escuta-ouvinte" in l and ("enable" in l or "start" in l) for l in ativas)
    assert not any(re.search(r"\bnpm\b", l) for l in ativas)


def test_runbook_escuta_paralelo_tem_os_passos_e_o_aviso_de_crise():
    from pathlib import Path
    rb = (Path(__file__).resolve().parent.parent / "docs/runbook.md").read_text()
    trecho = rb.split("{#escuta-paralelo}")[1].split("\n## ")[0]
    for esperado in ("tools.comparar_escuta", "google-contatos.env", "openrouter.env", "limite de crédito", "anexo_caminho",
                     "gabi-wa-docs", "gabi-reembolso.path", "escuta.py", "PYTHONPATH=/opt/gabi-brain", "ilegiveis", "sem_numero", "ambiguos",
                     "meia-noite", "Aparelhos conectados", "órfãos", "NÃO somem na hora", "set anexo_caminho=null where anexo_caminho is not null", "NÃO pode ser desligado antes de `escuta.modo='ativo'`"):
        assert esperado in trecho, esperado


def test_instalar_instala_o_comparador_da_escuta():
    linha = next(l for l in INSTALAR.splitlines() if "marcar_padroes.py" in l and l.startswith("install -d /opt/gabi-brain/tools"))
    assert '"$AQUI/tools/comparar_escuta.py"' in linha and linha.rstrip().endswith("/opt/gabi-brain/tools/")
    assert "PYTHONPATH=/opt/gabi-brain" in (Path(__file__).resolve().parent.parent / "docs/runbook.md").read_text()


def test_i7_i8_m4_ouvinte_teto_25_espaco_minimo_e_onfailure():
    u = (DEPLOY / "escuta-ouvinte.service").read_text()
    assert "Environment=OUVINTE_ANEXO_MAX_MB=25\n" in u and "Environment=OUVINTE_ESPACO_MIN_MB=2048\n" in u
    assert "OnFailure=gabi-brain-falha@%n.service\n" in u
    assert "ReadWritePaths=/var/lib/gabi-brain\n" in (DEPLOY / "gabi-brain-falha@.service").read_text()   # o template grava no banco, como para os gabi-brain-*


def test_unit_fontes_le_google_env_e_o_antigo():
    unit = _ler("gabi-brain-fontes.service")
    assert "EnvironmentFile=-/etc/gabi/google.env" in unit
    assert "EnvironmentFile=-/etc/gabi/google-contatos.env" in unit  # compatibilidade
    # systemd: o ÚLTIMO arquivo vence — o canônico (dois escopos) tem de vir depois do legado (só contatos)
    assert unit.index("EnvironmentFile=-/etc/gabi/google-contatos.env") < unit.index("EnvironmentFile=-/etc/gabi/google.env")
    assert not [l for l in unit.splitlines() if l.startswith("Environment=") and ("REFRESH" in l or "SECRET" in l)]  # nenhum segredo na unit


# ---------------- agenda ----------------
def test_unidades_da_agenda_seguem_o_padrao_e_nao_sao_habilitadas():
    srv, t = _ler("gabi-brain-agenda.service"), _ler("gabi-brain-agenda.timer")
    assert "-m gabi.agenda" in srv and "Type=oneshot" in srv and "User=gabibrain" in srv
    assert "OnFailure=gabi-brain-falha@%n.service" in srv
    assert "GABI_FONTES_SOCKET=/run/gabi-brain-fontes/fontes.sock" in srv
    assert "RestrictAddressFamilies=AF_UNIX" in srv and "IPAddressDeny=any" in srv and "ReadWritePaths=/var/lib/gabi-brain" in srv
    for dur in ("NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes", "PrivateDevices=yes", "UMask=0077"):
        assert dur in srv, dur
    assert "EnvironmentFile" not in srv
    assert "OnCalendar=*-*-* 06..22:00,15,30,45:00 America/Sao_Paulo" in t and "Persistent=true" in t and "Unit=gabi-brain-agenda.service" in t
    assert hasattr(importlib.import_module("gabi.agenda.__main__"), "main")
    for nome in ("gabi-brain-agenda.service", "gabi-brain-agenda.timer"):
        assert nome in INSTALAR
    ligadas = [l for l in INSTALAR.splitlines() if "enable" in l and not l.lstrip().startswith(("#", "echo"))]
    assert not any("agenda" in l for l in ligadas)


def test_instalar_instala_corrigir_moeda_e_comparar_agenda():
    linha = next(l for l in INSTALAR.splitlines() if "marcar_padroes.py" in l and l.startswith("install -d /opt/gabi-brain/tools"))
    assert '"$AQUI/tools/corrigir_moeda.py"' in linha and '"$AQUI/tools/comparar_agenda.py"' in linha and linha.rstrip().endswith("/opt/gabi-brain/tools/")


# ---------------- correio ----------------
def test_unidades_do_correio_seguem_o_padrao_e_nao_sao_habilitadas():
    srv, t = _ler("gabi-brain-correio.service"), _ler("gabi-brain-correio.timer")
    assert "-m gabi.correio" in srv and "Type=oneshot" in srv and "User=gabibrain" in srv
    assert "OnFailure=gabi-brain-falha@%n.service" in srv
    assert "GABI_FONTES_SOCKET=/run/gabi-brain-fontes/fontes.sock" in srv
    assert "RestrictAddressFamilies=AF_UNIX" in srv and "IPAddressDeny=any" in srv and "ReadWritePaths=/var/lib/gabi-brain" in srv
    for dur in ("NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes", "PrivateDevices=yes", "UMask=0077"):
        assert dur in srv, dur
    assert "EnvironmentFile" not in srv  # segredo só no serviço de fontes
    assert "TimeoutStartSec=600" in srv  # sincronizar (até 130 s) + conferência (até 130 s) + processar (210 s) + lixeira cabem
    assert "OnCalendar=*-*-* 06..22:00,15,30,45:00 America/Sao_Paulo" in t and "Persistent=true" in t and "Unit=gabi-brain-correio.service" in t
    assert hasattr(importlib.import_module("gabi.correio.__main__"), "main")
    for nome in ("gabi-brain-correio.service", "gabi-brain-correio.timer"):
        assert nome in INSTALAR
    ligadas = [l for l in INSTALAR.splitlines() if "enable" in l and not l.lstrip().startswith(("#", "echo"))]
    assert not any("correio" in l for l in ligadas)


def test_unit_fontes_continua_com_google_env_por_ultimo_e_sem_segredo():
    unit = _ler("gabi-brain-fontes.service")
    assert unit.index("EnvironmentFile=-/etc/gabi/google-contatos.env") < unit.index("EnvironmentFile=-/etc/gabi/google.env")
