import importlib
import pytest
import re
import subprocess
from pathlib import Path

DEPLOY = Path(__file__).parent.parent / "deploy"
API = (DEPLOY / "gabi-finance-api.service").read_text()
BKP = (DEPLOY / "gabi-finance-backup.service").read_text()
TIMER = (DEPLOY / "gabi-finance-backup.timer").read_text()
INSTALAR = (DEPLOY / "instalar.sh").read_text()


def test_api_escuta_so_em_socket_unix_sem_proxy_headers():
    exec_start = re.search(r"^ExecStart=(.*)$", API, re.M).group(1)
    assert "--uds /run/gabi-finance/api.sock" in exec_start and "--factory gabi.api:fabrica" in exec_start
    assert "--no-proxy-headers" in exec_start      # C1: nunca confiar em X-Forwarded-For
    assert "--port" not in exec_start and "--host" not in exec_start


def test_socket_fica_em_pasta_so_do_servico():
    assert "RuntimeDirectory=gabi-finance" in API and "RuntimeDirectoryMode=0700" in API and "UMask=0077" in API


def test_servicos_sem_rede_alem_de_socket_unix():
    for unidade in (API, BKP):
        assert "IPAddressDeny=any" in unidade and "RestrictAddressFamilies=AF_UNIX" in unidade
        assert "PrivateDevices=yes" in unidade and "ProtectKernelTunables=yes" in unidade


def test_nenhum_arquivo_de_deploy_escuta_em_todas_as_interfaces():
    for p in (f for f in DEPLOY.rglob("*") if f.is_file()):
        assert "0.0.0.0" not in p.read_text(), p.name


def test_servicos_rodam_como_usuario_sem_privilegios_e_endurecidos():
    for unidade in (API, BKP):
        assert "User=gabifinance" in unidade
        assert "NoNewPrivileges=yes" in unidade and "ProtectSystem=strict" in unidade
        assert "ProtectHome=yes" in unidade and "PrivateTmp=yes" in unidade
    assert "ReadWritePaths=/var/lib/gabi-finance" in API
    assert "/var/backups/gabi-finance" in BKP


def test_api_nao_le_arquivo_de_segredos_na_fase_0():
    assert "EnvironmentFile" not in API  # R5: a Fase 0 não usa credencial


def test_backup_diario_as_0330_com_teste_de_restauracao():
    assert "OnCalendar=*-*-* 03:30:00 America/Sao_Paulo" in TIMER and "Persistent=true" in TIMER
    assert "-m gabi.backup" in BKP and "--testar" in BKP and "Type=oneshot" in BKP


def test_servicos_longos_avisam_falha():
    for nome in ("api", "mcp", "fontes"):
        texto = (DEPLOY / f"gabi-finance-{nome}.service").read_text()
        assert "OnFailure=gabi-finance-falha@%n.service" in texto, nome
        assert "StartLimitBurst=" in texto, nome


def test_unidades_apontam_para_modulos_que_existem():
    assert hasattr(importlib.import_module("gabi.api"), "fabrica")
    assert hasattr(importlib.import_module("gabi.backup"), "main")


def test_instalar_tem_sintaxe_valida():
    assert subprocess.run(["bash", "-n", str(DEPLOY / "instalar.sh")]).returncode == 0


def test_instalar_faz_backup_do_banco_antes_de_copiar():
    i_bkp = INSTALAR.index("gabi.db.antes-instalar-")
    assert i_bkp < INSTALAR.index("cp -r")
    assert ".backup(" in INSTALAR and "cp /var/lib/gabi-finance/gabi.db" not in INSTALAR
    assert "chmod 600" in INSTALAR and "chown gabifinance:gabifinance" in INSTALAR
    assert "tail -n +6" in INSTALAR
    assert "if [ -f /var/lib/gabi-finance/gabi.db ]" in INSTALAR  # primeira instalação: sem banco, pula


def test_backup_do_instalar_roda_como_gabifinance_e_sem_mode_ro():
    assert "runuser -u gabifinance -- python3" in INSTALAR and "mode=ro" not in INSTALAR
    assert "pragma integrity_check" in INSTALAR and "journal_mode=delete" in INSTALAR


def test_backup_ruim_do_instalar_e_apagado_antes_de_sair():
    assert "os.unlink(sys.argv[1])" in INSTALAR
    assert INSTALAR.index("os.unlink(sys.argv[1])") < INSTALAR.index("sys.exit(")


def test_instalar_troca_por_mv_e_nao_apaga_antes_de_copiar():
    assert "rm -rf /opt/gabi-finance/gabi " not in INSTALAR
    assert ".novo" in INSTALAR and ".velho" in INSTALAR and 'mv "/opt/gabi-finance/.novo/$d"' in INSTALAR
    laco = INSTALAR.split("for d in gabi")[1].split("done")[0]
    assert 'if [ -e "/opt/gabi-finance/$d" ]; then' in laco and "&& mv" not in laco  # if/fi, não && sob set -e


def test_instalar_exige_confirmacao_do_gate_g1():
    assert "--confirmo-backup-exportado" in INSTALAR


def test_instalar_usa_dependencias_fixas_e_nao_instala_o_projeto():
    assert "requirements.lock" in INSTALAR and "pip install /opt/gabi-finance" not in INSTALAR
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
    for proibido in ("openclaw", "paperless", "buzz", "gabi-brain", "gabibrain", "docker", "ufw", "iptables"):
        assert proibido not in executadas, proibido  # mencionar em comentário/mensagem é ok; executar, não
    assert not re.search(r"/etc/gabi(?!-finance)", executadas)  # só a pasta /etc/gabi-finance (vazia); nenhum segredo é lido nem escrito


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


MCP = _ler("gabi-finance-mcp.service")
SALDOS, EXTRATOS = _ler("gabi-finance-saldos.service"), _ler("gabi-finance-extratos.service")
T_SALDOS, T_EXTRATOS = _ler("gabi-finance-saldos.timer"), _ler("gabi-finance-extratos.timer")


def test_mcp_escuta_so_em_localhost_8082_sem_proxy_headers():
    ex = re.search(r"^ExecStart=(.*)$", MCP, re.M).group(1)
    assert "--factory gabi.mcp.servidor:fabrica" in ex and "--host 127.0.0.1" in ex and "--port 8082" in ex and "--no-proxy-headers" in ex
    assert "0.0.0.0" not in MCP


def test_mcp_so_aceita_trafego_local_e_nao_le_segredo_de_agentes():
    assert "IPAddressDeny=any" in MCP and "IPAddressAllow=localhost" in MCP
    assert "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX" in MCP
    assert "EnvironmentFile" not in MCP  # o MCP só usa tokens do banco; nenhuma chave de fonte externa


def test_servicos_de_captura_podem_sair_para_a_internet_mas_com_o_resto_endurecido():
    for u in (SALDOS, EXTRATOS):
        assert "EnvironmentFile=-/etc/gabi-finance/mcpai.env" in u            # a chave da mcp.ai (G4); '-' = opcional
        assert "IPAddressDeny" not in u and "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX" in u
        for dur in ("User=gabifinance", "NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes", "UMask=0077"):
            assert dur in u, dur
        assert "ReadWritePaths=/var/lib/gabi-finance" in u and "Type=oneshot" in u


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


def test_instalar_instala_todas_as_units_mas_nao_liga_nenhuma():
    """A virada (docs/virada.md) liga na ordem certa, depois da conferência com o serviço anterior."""
    executadas = "\n".join(l for l in INSTALAR.splitlines() if l.strip() and not l.lstrip().startswith(("#", "echo")))
    for proibido in ("enable", "start ", "restart", "reload-or-restart", "--now"):
        assert proibido not in executadas, proibido
    unidades = sorted(p.name for p in DEPLOY.glob("gabi-finance-*") if p.suffix in (".service", ".timer"))
    assert unidades
    for nome in unidades:
        assert nome in INSTALAR, nome


def test_instalar_cria_pastas_do_bruto_e_dos_locks_privadas():
    assert "/var/lib/gabi-finance/bruto" in INSTALAR and "/var/lib/gabi-finance/locks" in INSTALAR


def test_nenhuma_unidade_traz_segredo():
    for p in (f for f in DEPLOY.rglob("*") if f.is_file()):
        assert not re.search(r"sk_live|sk-[a-z0-9]{10}|Bearer |gb_[A-Za-z0-9_-]{20}", p.read_text()), p.name


# ---------------- Fase 2: serviço de fontes (ponte para o Nibo) ----------------
FONTES = _ler("gabi-finance-fontes.service")


def test_so_o_servico_de_fontes_tem_rede_e_le_o_token_do_nibo():
    assert "EnvironmentFile=-/etc/gabi-finance/nibo.env" in FONTES
    assert "mcpai" not in "\n".join(l for l in FONTES.splitlines() if l.startswith("EnvironmentFile"))  # o mcp.ai fica fora da ponte (spec F5)
    assert "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX" in FONTES and "IPAddressDeny" not in FONTES
    for u in (API, MCP):
        assert "EnvironmentFile" not in u and "GABI_FONTES_SOCKET=/run/gabi-finance-fontes/fontes.sock" in u
        assert "IPAddressDeny=any" in u  # a API e o MCP continuam sem rede


def test_ponte_so_para_o_servico_e_o_grupo():
    assert "User=gabifinance-fontes" in FONTES and "Group=gabifinance" in FONTES
    assert "RuntimeDirectory=gabi-finance-fontes" in FONTES and "RuntimeDirectoryMode=0750" in FONTES and "UMask=0007" in FONTES
    for dur in ("NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes", "PrivateDevices=yes", "CapabilityBoundingSet="):
        assert dur in FONTES, dur
    assert "-m gabi.fontes.servico --socket /run/gabi-finance-fontes/fontes.sock" in FONTES
    assert hasattr(importlib.import_module("gabi.fontes.servico"), "main")


def test_instalar_cria_os_usuarios_e_a_pasta_de_segredos():
    assert "useradd" in INSTALAR and "gabifinance-fontes" in INSTALAR and "id gabifinance " in INSTALAR
    assert "/etc/gabi-finance" in INSTALAR


# ---------------- avisos (plano de finalização, tarefa 4): o brain passa a avisar quando algo para ----------------
AVISOS, T_AVISOS, FALHA = _ler("gabi-finance-avisos.service"), _ler("gabi-finance-avisos.timer"), _ler("gabi-finance-falha@.service")
NOTAS = _ler("gabi-finance-notas.service")


def test_timer_de_avisos_roda_a_cada_15_minutos_e_esta_instalado_e_habilitado():
    assert "OnUnitActiveSec=15min" in T_AVISOS and "Unit=gabi-finance-avisos.service" in T_AVISOS
    for nome in ("gabi-finance-avisos.service", "gabi-finance-avisos.timer", "gabi-finance-falha@.service"):
        assert nome in INSTALAR


def test_servicos_de_rotina_avisam_quando_falham():
    # a chave do mcp.ai expirou em 09/10 e ninguém soube por horas: toda rotina com OnFailure= chama o serviço de falha
    for texto in (SALDOS, EXTRATOS, BKP, NOTAS, AVISOS):
        assert "OnFailure=gabi-finance-falha@%n.service" in texto


def test_servico_de_falha_grava_aviso_com_o_nome_da_unidade_e_sem_rede():
    ex = re.search(r"^ExecStart=(.*)$", FALHA, re.M).group(1)
    assert "gabi.avisos" in ex and "--falha %i" in ex and "RestrictAddressFamilies=AF_UNIX" in FALHA and "User=gabifinance" in FALHA


def test_servico_de_avisos_so_le_e_grava_o_banco_sem_rede():
    assert "gabi.avisos" in AVISOS and "User=gabifinance" in AVISOS and "RestrictAddressFamilies=AF_UNIX" in AVISOS and "ReadWritePaths=/var/lib/gabi-finance" in AVISOS
    assert "NoNewPrivileges=yes" in AVISOS and "ProtectSystem=strict" in AVISOS


def test_timer_de_notas_roda_todo_dia_cedo_em_horario_de_brasilia_e_esta_instalado():
    t = _ler("gabi-finance-notas.timer")
    assert "OnCalendar=*-*-* 06:40:00 America/Sao_Paulo" in t and "Unit=gabi-finance-notas.service" in t and "Persistent=true" in t
    assert "gabi-finance-notas.timer" in INSTALAR


def test_timer_de_exportacao_semanal_instalado():
    svc = (DEPLOY / "gabi-finance-exportacao.service").read_text()
    tmr = (DEPLOY / "gabi-finance-exportacao.timer").read_text()
    expr = re.search(r"^OnCalendar=(.*)$", tmr, re.M).group(1)
    assert subprocess.run(["systemd-analyze", "calendar", expr], capture_output=True, text=True).returncode == 0
    assert expr.startswith("Sun ") and "America/Sao_Paulo" in expr
    assert "-m gabi.exportacao" in svc and "ConditionPathExists=/etc/gabi-finance/backup.pub" in svc  # sem chave, não roda (nem exporta em claro)
    assert "OnFailure=gabi-finance-falha@%n.service" in svc and "IPAddressDeny=any" in svc
    assert "gabi-finance-exportacao.timer" in INSTALAR and "gabi-finance-exportacao.service" in INSTALAR


def test_telegram_so_envia_com_arquivo_de_ambiente_do_ricardo_e_nao_tem_o_token_no_repositorio():
    srv, t = _ler("gabi-finance-telegram.service"), _ler("gabi-finance-telegram.timer")
    assert "-m gabi.telegram" in srv and "EnvironmentFile=-/etc/gabi-finance/telegram.env" in srv and "OnFailure=gabi-finance-falha@%n.service" in srv
    assert "User=gabifinance" in srv and "NoNewPrivileges=yes" in srv and "ReadWritePaths=/var/lib/gabi-finance" in srv
    assert "OnUnitActiveSec=5min" in t and "Unit=gabi-finance-telegram.service" in t
    assert "gabi-finance-telegram.timer" in INSTALAR
    assert "TELEGRAM_BOT_TOKEN=" not in srv + t + INSTALAR


def test_instalar_instala_corrigir_moeda_e_comparar_agenda():
    linha = next(l for l in INSTALAR.splitlines() if "marcar_padroes.py" in l and l.startswith("install -d /opt/gabi-finance/.novo/tools"))
    assert '"$AQUI/tools/corrigir_moeda.py"' in linha and '"$AQUI/tools/comparar_agenda.py"' in linha and "carga_familia" not in linha
    assert '"$AQUI/tools/conferir_virada.py"' in linha  # a conferência de docs/virada.md roda de /opt/gabi-finance and linha.rstrip().endswith("/opt/gabi-finance/.novo/tools/")


# ---------------- simplificação (ADR-023) ----------------
def test_todo_modulo_que_uma_unit_executa_existe():
    """Módulo removido referenciado por unit só quebraria em produção: cada `-m gabi.X` (e cada app do uvicorn) precisa importar."""
    import re
    nomes = set()
    for unit in DEPLOY.glob("*.service"):
        txt = unit.read_text()
        nomes |= set(re.findall(r"-m (gabi(?:\.\w+)+)", txt))
        nomes |= {m.split(":")[0] for m in re.findall(r"uvicorn\S* .*?(gabi(?:\.\w+)+:\w+)", txt)}
    assert nomes
    for nome in sorted(nomes):
        assert importlib.util.find_spec(nome) is not None, nome


def test_so_existem_units_gabi_finance_e_nenhuma_traz_o_nome_antigo():
    for p in (f for f in DEPLOY.iterdir() if f.suffix in (".service", ".timer")):
        assert p.name.startswith("gabi-finance-"), p.name
    nomes = {p.name for p in DEPLOY.glob("gabi-finance-*")}
    for cortada in ("agenda", "anexos", "contatos", "correio", "documentos", "teams", "escuta", "trabalho", "exames"):
        assert not {f"gabi-finance-{cortada}.service", f"gabi-finance-{cortada}.timer"} & nomes, cortada


def test_deploy_so_usa_usuario_caminhos_e_segredos_do_gabi_finance():
    texto = "\n".join(p.read_text() for p in DEPLOY.rglob("*") if p.is_file() and p.suffix in (".service", ".timer", ".sh", ".py", ".md"))
    assert "User=gabifinance" in texto and "/opt/gabi-finance" in texto and "/var/lib/gabi-finance" in texto
    assert "/run/gabi-finance/" in texto and "/etc/gabi-finance/" in texto
    for velho in ("gabi-brain", "gabi_brain", "gabibrain", "gabi.brain", "GABI_BRAIN", "/etc/gabi/", "/opt/gabi/"):
        assert velho not in texto, velho


def test_defaults_de_gabi_e_tools_nao_apontam_para_o_gabi_brain():
    raiz = DEPLOY.parent
    for pasta in ("gabi", "tools"):
        for p in (raiz / pasta).rglob("*"):
            if p.is_file() and p.suffix in (".py", ".html", ".sh") and "painel" not in p.parts:
                t = p.read_text(encoding="utf-8")
                for velho in ("gabi-brain", "gabi_brain", "gabibrain", "gabi.brain", "/etc/gabi/", "mcp__gabi_brain"):
                    assert velho not in t, (str(p.relative_to(raiz)), velho)


def test_mcp_nao_disputa_a_porta_com_o_gabi_brain_durante_a_virada():
    """O serviço anterior segue em 127.0.0.1:8081 até a volta ser descartada; o gabi-finance usa 8082."""
    assert "--port 8082" in MCP and "8081" not in MCP
    assert "8081" not in INSTALAR
