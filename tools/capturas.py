"""Capturas lado a lado protótipo × app para aprovação tela a tela (R17, G14).
Uso: .venv/bin/python -m tools.capturas   (precisa do demo em :8099 e do protótipo servido em :8098)
Saída: docs/design/<tela>-{prototipo,app}-{claro,escuro,celular}.png"""
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SAIDA = Path(__file__).resolve().parent.parent / "docs" / "design"
APP, PROTO = "http://127.0.0.1:8099/", "http://127.0.0.1:8098/Gabi%20Dashboard.dc.html"
# (arquivo, área, id da aba na app, rótulo da área no protótipo, rótulo da aba no protótipo)
TELAS = [
    ("caixa-resumo", "caixa", "visao", "Caixa", "Resumo"),
    ("caixa-semanas", "caixa", "fluxo", "Caixa", "Semanas"),
    ("caixa-a-pagar", "caixa", "contas", "Caixa", "A pagar"),
    ("gastos-lancamentos", "gastos", "lanc", "Gastos", "Lançamentos"),
    ("gastos-para-onde-vai", "gastos", "destino", "Gastos", "Para onde vai"),
    ("gastos-cartoes", "gastos", "cartao", "Gastos", "Cartões"),
    ("gastos-parcelas", "gastos", "parcelas", "Gastos", "Parcelas"),
    ("gastos-assinaturas", "gastos", "assin", "Gastos", "Assinaturas"),
    ("regras", "regras", "regras", "Regras", None),
]
VISTAS = [("claro", 1280, 800, "claro"), ("escuro", 1280, 800, "escuro"), ("celular", 390, 844, "claro")]


def app(b, nome, area, aba, vista, w, h, tema):
    ctx = b.new_context(viewport={"width": w, "height": h}, extra_http_headers={"Tailscale-User-Login": "boss@x.com"})
    pg = ctx.new_page()
    pg.add_init_script(f"localStorage.setItem('gabi.area','{area}');localStorage.setItem('gabi.aba.{area}','{aba}');localStorage.setItem('gabi.tema','{tema}');localStorage.setItem('gabi.periodo','mes')")
    pg.goto(APP)
    pg.wait_for_timeout(1200)
    pg.screenshot(path=str(SAIDA / f"{nome}-app-{vista}.png"), full_page=False)
    ctx.close()


def proto(b, nome, rot_area, rot_aba, vista, w, h, tema):
    ctx = b.new_context(viewport={"width": 1500 if w > 800 else w, "height": h})
    pg = ctx.new_page()
    pg.set_default_timeout(4000)
    pg.goto(PROTO)
    pg.wait_for_timeout(1500)
    try:
        if w <= 800:
            pg.get_by_role("button", name="Celular", exact=True).first.click()
        if tema == "escuro":
            pg.get_by_role("button", name="Tema escuro").first.click()
        if w <= 800 and rot_area not in ("Hoje", "Agenda", "Mensagens", "Caixa"):
            pg.get_by_role("button", name="Mais", exact=True).first.click()
        pg.get_by_role("button", name=rot_area, exact=True).first.click()
        if rot_aba:
            pg.get_by_role("tab", name=re.compile(rf"^{re.escape(rot_aba)}(\s|$)")).first.click()
        pg.wait_for_timeout(500)
    except Exception as e:  # protótipo é de terceiros: registra e segue
        print(f"  aviso protótipo {nome}/{vista}: {str(e)[:90]}")
    pg.screenshot(path=str(SAIDA / f"{nome}-prototipo-{vista}.png"))
    ctx.close()


if __name__ == "__main__":
    SAIDA.mkdir(parents=True, exist_ok=True)
    alvo = sys.argv[1:] 
    with sync_playwright() as p:
        b = p.chromium.launch()
        for nome, area, aba, ra, rb in TELAS:
            if alvo and nome not in alvo:
                continue
            for vista, w, h, tema in VISTAS:
                app(b, nome, area, aba, vista, w, h, tema)
                proto(b, nome, ra, rb, vista, w, h, tema)
            print("ok", nome)
