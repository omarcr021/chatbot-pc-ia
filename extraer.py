"""Tarea 2: extrae el texto principal de las páginas elegidas.

Uso: python extraer.py
Resultado: data/<categoria>.md y data/raw/<categoria>_endpoints.json
"""

import json
import sys
import time
from datetime import date

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from comun import DATA, TIMEOUT_MS, USER_AGENT, Robots, consola_utf8

# Editar después de revisar data/enlaces.txt. Ejemplo: {"carta": "https://.../carta"}
PAGINAS = {}

PAUSA_S = 3
ESPERA_EXTRA_MS = 2_000

# Los <header>/<footer> dentro de article, section o main son parte del contenido
# (títulos de sección), así que solo se quitan los del sitio.
JS_TEXTO_PRINCIPAL = """() => {
  document.querySelectorAll('header, footer').forEach(e => {
    if (!e.parentElement.closest('article, section, main')) e.remove();
  });
  document.querySelectorAll(
    'nav, aside, script, style, noscript, iframe, svg, ' +
    '[role=navigation], [role=banner], [role=contentinfo]'
  ).forEach(e => e.remove());
  return (document.querySelector('main') || document.body).innerText;
}"""


def extraer_pagina(contexto, categoria, url):
    """Extrae una URL, guarda sus archivos y devuelve los avisos que hubo."""
    avisos = []
    endpoints = {}

    def registrar_json(respuesta):
        if "json" in respuesta.headers.get("content-type", "").lower():
            endpoints[respuesta.url] = respuesta.status

    pagina = contexto.new_page()
    pagina.set_default_timeout(TIMEOUT_MS)
    pagina.on("response", registrar_json)
    try:
        respuesta = pagina.goto(url, wait_until="domcontentloaded")
        if respuesta is not None and respuesta.status >= 400:
            raise RuntimeError(f"HTTP {respuesta.status}")
        try:
            pagina.wait_for_load_state("networkidle")
        except PlaywrightTimeout:
            avisos.append("la red no quedó inactiva en 45 s; revisar que esté completa")
        pagina.wait_for_timeout(ESPERA_EXTRA_MS)

        titulo = pagina.title().strip() or categoria
        texto = pagina.evaluate(JS_TEXTO_PRINCIPAL).strip()
    finally:
        pagina.close()

    if not texto:
        raise RuntimeError("la página no tiene texto principal")

    encabezado = (
        f"# {titulo}\n\n"
        f"Fuente: {url}\n"
        f"Fecha de extracción: {date.today().isoformat()}\n\n"
    )
    (DATA / f"{categoria}.md").write_text(encabezado + texto + "\n", encoding="utf-8")

    lista = [{"url": u, "status": s} for u, s in sorted(endpoints.items())]
    (DATA / "raw" / f"{categoria}_endpoints.json").write_text(
        json.dumps(lista, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  {len(texto)} caracteres, {len(lista)} respuestas JSON")
    return avisos


def main():
    consola_utf8()
    if not PAGINAS:
        sys.exit("PAGINAS está vacío. Edítalo en extraer.py tras revisar data/enlaces.txt.")

    (DATA / "raw").mkdir(parents=True, exist_ok=True)
    robots = Robots()
    correctas, avisos, omitidas, fallidas = [], [], [], []

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        contexto = navegador.new_context(user_agent=USER_AGENT, locale="es-PE")
        pausa = 0
        for categoria, url in PAGINAS.items():
            if not robots.permitido(url):
                print(f"[{categoria}] bloqueada por robots.txt: {url}")
                omitidas.append((categoria, url))
                continue

            time.sleep(pausa)
            pausa = max(PAUSA_S, robots.crawl_delay(url))
            print(f"[{categoria}] {url}")
            try:
                for aviso in extraer_pagina(contexto, categoria, url):
                    avisos.append((categoria, aviso))
                correctas.append(categoria)
            except Exception as error:
                print(f"  ERROR: {error}")
                fallidas.append((categoria, url, str(error).splitlines()[0]))
        navegador.close()

    print(f"\nResumen: {len(correctas)} de {len(PAGINAS)} páginas extraídas.")
    for categoria, aviso in avisos:
        print(f"  AVISO {categoria}: {aviso}")
    for categoria, url in omitidas:
        print(f"  OMITIDA {categoria} (robots.txt): {url}")
    for categoria, url, motivo in fallidas:
        print(f"  FALLÓ {categoria}: {url} -> {motivo}")
    if fallidas:
        sys.exit(1)


if __name__ == "__main__":
    main()
