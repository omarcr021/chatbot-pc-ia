"""Genera la imagen de la carta completa (platos y precios) que adjunta el chatbot.

Uso: python generar_carta.py   (después de limpiar.py; no usa ninguna API)
Resultado: assets/carta.png, pensada para verse en el celular (una sola columna).
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from comun import RAIZ, consola_utf8
from indexar import leer_carta

RUTA_IMAGEN = RAIZ / "assets" / "carta.png"

ANCHO = 1080
MARGEN = 64
ANCHO_PRECIO = 190

FONDO = "#FFF8EE"
TEXTO = "#2B1D14"
SUAVE = "#7A6A5C"
ACENTO = "#A3331F"
CABECERA = "#2B1D14"
CABECERA_TEXTO = "#FFF8EE"
LINEA = "#E8DCCB"

FUENTES = {
    "normal": ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"],
    "negrita": ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "DejaVuSans-Bold.ttf"],
}


def fuente(estilo, tamano):
    for ruta in FUENTES[estilo]:
        try:
            return ImageFont.truetype(ruta, tamano)
        except OSError:
            continue
    return ImageFont.load_default(tamano)


F_TITULO = fuente("negrita", 60)
F_SUBTITULO = fuente("normal", 28)
F_SECCION = fuente("negrita", 40)
F_PLATO = fuente("normal", 31)
F_PRECIO = fuente("negrita", 31)
F_PIE = fuente("normal", 24)


def partir(texto, letra, ancho, medidor):
    """Divide el texto en líneas que entren en el ancho dado."""
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if medidor.textlength(prueba, font=letra) <= ancho or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    return lineas + [actual]


def dibujar(secciones, fecha, lienzo=None):
    """Dibuja la carta y devuelve la altura usada. Sin lienzo, solo mide."""
    medidor = ImageDraw.Draw(lienzo or Image.new("RGB", (1, 1)))
    d = medidor if lienzo else None
    ancho_texto = ANCHO - 2 * MARGEN
    y = 0

    alto_cabecera = 210
    if d:
        d.rectangle([0, 0, ANCHO, alto_cabecera], fill=CABECERA)
        d.text((MARGEN, 52), "Nuestra carta", font=F_TITULO, fill=CABECERA_TEXTO)
        d.text((MARGEN, 136), f"Platos y precios según la web oficial al {fecha}",
               font=F_SUBTITULO, fill=CABECERA_TEXTO)
    y = alto_cabecera + 30

    for seccion, platos in secciones.items():
        y += 26
        if d:
            d.text((MARGEN, y), seccion.upper(), font=F_SECCION, fill=ACENTO)
        y += 58
        if d:
            d.line([MARGEN, y, ANCHO - MARGEN, y], fill=ACENTO, width=3)
        y += 18
        for plato, precio in platos:
            lineas = partir(plato, F_PLATO, ancho_texto - ANCHO_PRECIO, medidor)
            if d:
                for i, linea in enumerate(lineas):
                    d.text((MARGEN, y + i * 42), linea, font=F_PLATO, fill=TEXTO)
                ancho = medidor.textlength(precio, font=F_PRECIO)
                d.text((ANCHO - MARGEN - ancho, y), precio, font=F_PRECIO, fill=TEXTO)
            y += 42 * len(lineas) + 14
            if d:
                d.line([MARGEN, y - 7, ANCHO - MARGEN, y - 7], fill=LINEA, width=1)

    y += 30
    pie = [
        "Precios referenciales: pueden cambiar. Confírmalos en pardoschicken.pe.",
        "Imagen de un proyecto académico; no es la carta oficial.",
    ]
    for linea in pie:
        for parte in partir(linea, F_PIE, ancho_texto, medidor):
            if d:
                d.text((MARGEN, y), parte, font=F_PIE, fill=SUAVE)
            y += 34
    return y + MARGEN


def main():
    consola_utf8()
    carta = leer_carta()
    if carta is None:
        sys.exit("No hay data/limpio/carta_productos.md. Ejecuta extraer_detalle.py y limpiar.py.")
    secciones, _, fecha = carta

    alto = dibujar(secciones, fecha)
    imagen = Image.new("RGB", (ANCHO, alto), FONDO)
    dibujar(secciones, fecha, imagen)

    RUTA_IMAGEN.parent.mkdir(exist_ok=True)
    imagen.save(RUTA_IMAGEN, optimize=True)
    platos = sum(len(p) for p in secciones.values())
    print(f"{RUTA_IMAGEN.relative_to(RAIZ)}: {platos} platos, {len(secciones)} secciones, {ANCHO}x{alto}px")


if __name__ == "__main__":
    main()
