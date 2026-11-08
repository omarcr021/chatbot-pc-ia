"""Extrae lo que extraer.py no alcanza: páginas que necesitan interacción o enlaces internos.

- Locales de todas las ciudades (la página solo muestra Lima hasta elegir otra en el
  desplegable), con el contacto de reservas de la ficha de cada local.
- Ficha de cada producto de la carta, con la descripción completa (en las categorías
  aparece cortada con "... VER MÁS").

Uso:
  python extraer_detalle.py                       # locales y productos
  python extraer_detalle.py locales
  python extraer_detalle.py productos [--limite N]
Resultado: data/locales.md y data/carta_productos.md
"""

import argparse
import sys
import time
from contextlib import contextmanager
from datetime import date

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from comun import DATA, TIMEOUT_MS, USER_AGENT, Robots, consola_utf8
from extraer import B, ESPERA_EXTRA_MS, JS_TEXTO_PRINCIPAL, PAGINAS, PAUSA_S

URL_LOCALES = f"{B}/restaurantes"

# Cada nombre "PARDOS ..." visible, con el bloque más grande que no contiene otro nombre
# (la tarjeta del local) y su enlace a la ficha.
JS_TARJETAS = """() => {
  const nombres = [...document.querySelectorAll('main *')].filter(e =>
    e.children.length === 0 && /^PARDOS /i.test((e.innerText || '').trim()) && e.offsetParent !== null);
  const cuenta = el => nombres.filter(n => el.contains(n)).length;
  return nombres.map(n => {
    let c = n;
    while (c.parentElement && c.parentElement.tagName !== 'MAIN' && cuenta(c.parentElement) === 1)
      c = c.parentElement;
    const a = c.querySelector('a[href*="/restaurantes/"]');
    return {nombre: n.innerText.trim(), texto: c.innerText, enlace: a ? a.href : null};
  });
}"""

JS_ENLACES_PRODUCTO = """() => [...new Set(
  [...(document.querySelector('main') || document.body).querySelectorAll('a[href*="/productos/"]')]
    .map(a => a.href.split('#')[0]))]"""

LINEAS_DE_TARJETA_SOBRANTES = {"Ver", "Cómo llegar", "Ver cómo llegar"}

# Textos del formulario de pedido de la ficha de producto, sin información del plato.
LINEAS_DE_FICHA_SOBRANTES = {
    "1",  # selector de cantidad
    "Términos y Condiciones",
    "Por favor, elige todas las opciones necesarias para avanzar con tu pedido.",
    "Elegir método de entrega",
}
# Venta cruzada con precios de otros productos: se quita para no confundir precios.
INICIO_VENTA_CRUZADA = "Agrega más sabor a tu pedido"
FIN_VENTA_CRUZADA = "Si tienes alguna alergia"


def limpiar_ficha(texto):
    lineas, en_venta_cruzada = [], False
    for linea in texto.splitlines():
        limpia = linea.strip()
        if limpia.startswith(INICIO_VENTA_CRUZADA):
            en_venta_cruzada = True
        elif limpia.startswith(FIN_VENTA_CRUZADA):
            en_venta_cruzada = False
        elif not en_venta_cruzada and limpia not in LINEAS_DE_FICHA_SOBRANTES:
            lineas.append(linea)
    return "\n".join(lineas).strip()


class Visitante:
    """Abre páginas respetando robots.txt y la pausa entre visitas."""

    def __init__(self, contexto):
        self.contexto = contexto
        self.robots = Robots()
        self.pausa = 0

    @contextmanager
    def abrir(self, url):
        if not self.robots.permitido(url):
            raise PermissionError("bloqueada por robots.txt")
        time.sleep(self.pausa)
        self.pausa = max(PAUSA_S, self.robots.crawl_delay(url))
        pagina = self.contexto.new_page()
        pagina.set_default_timeout(TIMEOUT_MS)
        try:
            respuesta = pagina.goto(url, wait_until="domcontentloaded")
            if respuesta is not None and respuesta.status >= 400:
                raise RuntimeError(f"HTTP {respuesta.status}")
            try:
                pagina.wait_for_load_state("networkidle")
            except PlaywrightTimeout:
                pass
            pagina.wait_for_timeout(ESPERA_EXTRA_MS)
            yield pagina
        finally:
            pagina.close()


def encabezado(titulo, url):
    return f"# {titulo}\n\nFuente: {url}\nFecha de extracción: {date.today().isoformat()}\n\n"


def contacto_de_reservas(visitante, url):
    """Líneas de "Reservas:" de la ficha de un local (teléfono y correo)."""
    with visitante.abrir(url) as pagina:
        lineas = [l.strip() for l in pagina.evaluate(JS_TEXTO_PRINCIPAL).splitlines() if l.strip()]
    if "Reservas:" not in lineas:
        return []
    datos = []
    for linea in lineas[lineas.index("Reservas:") + 1:]:
        if linea.startswith(("Razón Social", "Ruc", "RUC", "Mapa")):
            break
        if linea != "Reservar ahora":
            datos.append(linea)
    return [f"Reservas: {' / '.join(datos)}"] if datos else []


def ordenar_tarjeta(lineas, nombre, ciudad):
    """Nombre, ciudad y datos del local, sin lo anterior al nombre.

    Cuando una ciudad tiene un solo local, la tarjeta incluye el título de la página y
    la lista de ciudades: eso se descarta.
    """
    limpias = [l.strip() for l in lineas if l.strip() and l.strip() not in LINEAS_DE_TARJETA_SOBRANTES]
    if nombre in limpias:
        limpias = limpias[limpias.index(nombre):]
    limpias = [l for l in limpias if not l.startswith("Ciudad: ")]
    return [limpias[0], f"Ciudad: {ciudad}", *limpias[1:]]


def extraer_locales(visitante, fallos):
    tarjetas = []
    with visitante.abrir(URL_LOCALES) as pagina:
        selector = pagina.locator("main select").first
        for ciudad in selector.evaluate("s => [...s.options].map(o => o.text.trim())"):
            selector.select_option(label=ciudad)
            pagina.wait_for_timeout(ESPERA_EXTRA_MS)
            encontradas = pagina.evaluate(JS_TARJETAS)
            print(f"  {ciudad}: {len(encontradas)} locales")
            tarjetas += [{**t, "ciudad": ciudad} for t in encontradas]

    bloques = []
    for tarjeta in tarjetas:
        lineas = ordenar_tarjeta(tarjeta["texto"].splitlines(), tarjeta["nombre"], tarjeta["ciudad"])
        if tarjeta["enlace"]:
            try:
                lineas += contacto_de_reservas(visitante, tarjeta["enlace"])
                lineas.append(f"Más información: {tarjeta['enlace']}")
            except Exception as error:
                fallos.append((tarjeta["nombre"], tarjeta["enlace"], str(error).splitlines()[0]))
        else:
            fallos.append((tarjeta["nombre"], "-", "la tarjeta no tiene enlace a su ficha"))
        bloques.append("\n".join(lineas))
        print(f"  {tarjeta['nombre']}")

    texto = encabezado("Nuestros restaurantes", URL_LOCALES) + "\n---\n".join(bloques) + "\n"
    (DATA / "locales.md").write_text(texto, encoding="utf-8")
    print(f"locales.md: {len(bloques)} locales")


def extraer_productos(visitante, fallos, limite=None):
    categorias = {c: u for c, u in PAGINAS.items() if c.startswith("carta_") or c == "promociones"}
    enlaces = {}
    for categoria, url in categorias.items():
        try:
            with visitante.abrir(url) as pagina:
                for enlace in pagina.evaluate(JS_ENLACES_PRODUCTO):
                    enlaces.setdefault(enlace, categoria)
        except Exception as error:
            fallos.append((categoria, url, str(error).splitlines()[0]))
    print(f"{len(enlaces)} productos encontrados en {len(categorias)} categorías")

    bloques = []
    for url, categoria in list(enlaces.items())[:limite]:
        try:
            with visitante.abrir(url) as pagina:
                texto = limpiar_ficha(pagina.evaluate(JS_TEXTO_PRINCIPAL))
            if "S/" not in texto:
                raise RuntimeError("no parece una ficha de producto (no tiene precio)")
            bloques.append(f"{texto}\nCategoría: {categoria}\nEnlace: {url}")
            print(f"  {texto.splitlines()[0][:60]}")
        except Exception as error:
            fallos.append((categoria, url, str(error).splitlines()[0]))

    texto = encabezado("Fichas de productos", f"{B}/") + "\n---\n".join(bloques) + "\n"
    (DATA / "carta_productos.md").write_text(texto, encoding="utf-8")
    print(f"carta_productos.md: {len(bloques)} productos")


def main():
    consola_utf8()
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("que", nargs="?", choices=["locales", "productos"])
    argumentos.add_argument("--limite", type=int, help="máximo de productos (para probar)")
    args = argumentos.parse_args()

    fallos = []
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        visitante = Visitante(navegador.new_context(user_agent=USER_AGENT, locale="es-PE"))
        if args.que in (None, "locales"):
            extraer_locales(visitante, fallos)
        if args.que in (None, "productos"):
            extraer_productos(visitante, fallos, args.limite)
        navegador.close()

    for nombre, url, motivo in fallos:
        print(f"FALLÓ {nombre}: {url} -> {motivo}")
    if fallos:
        sys.exit(1)


if __name__ == "__main__":
    main()
