"""Tarea 1: lista los enlaces internos de la home y los marca según robots.txt.

Uso: python descubrir.py
Resultado: data/enlaces.txt
"""

import sys
from datetime import date
from urllib.parse import urldefrag, urlsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from comun import DATA, TIMEOUT_MS, USER_AGENT, Robots, consola_utf8

# Sitio oficial confirmado por el equipo.
BASE = "https://www.pardoschicken.pe/"


def dominio(url):
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def obtener_enlaces(base):
    """Abre la home y devuelve (url final tras redirecciones, hrefs absolutos)."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        try:
            pagina = navegador.new_context(user_agent=USER_AGENT).new_page()
            pagina.set_default_timeout(TIMEOUT_MS)
            respuesta = pagina.goto(base, wait_until="domcontentloaded")
            if respuesta is not None and respuesta.status >= 400:
                raise RuntimeError(f"la home respondió HTTP {respuesta.status}")
            try:
                pagina.wait_for_load_state("networkidle")
            except PlaywrightTimeout:
                print("AVISO: la red no quedó inactiva; se usan los enlaces ya cargados.")
            hrefs = pagina.eval_on_selector_all("a[href]", "as => as.map(a => a.href)")
            return pagina.url, hrefs
        finally:
            navegador.close()


def filtrar_internos(hrefs, url_home):
    """Deja solo http(s) del mismo dominio, sin anclas y sin duplicados."""
    internos = set()
    for href in hrefs:
        url = urldefrag(href).url
        if urlsplit(url).scheme not in ("http", "https"):
            continue
        if dominio(url) == dominio(url_home):
            internos.add(url.rstrip("/") if urlsplit(url).path != "/" else url)
    return sorted(internos)


def main():
    consola_utf8()
    if not BASE:
        sys.exit("Falta configurar BASE en descubrir.py con la URL oficial.")

    robots = Robots()
    if not robots.permitido(BASE):
        sys.exit(f"robots.txt no permite abrir {BASE}. No se continúa.")

    url_home, hrefs = obtener_enlaces(BASE)
    enlaces = filtrar_internos(hrefs, url_home)

    lineas = [f"# Enlaces de {url_home} | Fecha: {date.today().isoformat()}"]
    lineas += [f"{'OK' if robots.permitido(u) else 'NO'}\t{u}" for u in enlaces]
    texto = "\n".join(lineas) + "\n"

    DATA.mkdir(exist_ok=True)
    (DATA / "enlaces.txt").write_text(texto, encoding="utf-8")

    print(texto)
    permitidos = sum(l.startswith("OK") for l in lineas)
    print(f"{len(enlaces)} enlaces ({permitidos} OK). Guardado en data/enlaces.txt")


if __name__ == "__main__":
    main()
