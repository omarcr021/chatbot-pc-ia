"""Pruebas de la imagen de la carta. No usa la API: Gemini y la búsqueda se simulan.

Uso: python tests/probar_carta.py   (después de generar_carta.py)
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from PIL import Image
from streamlit.testing.v1 import AppTest

import prompts
import rag
from comun import consola_utf8
from indexar import leer_carta

resultados = []


def comprobar(nombre, condicion):
    resultados.append(condicion)
    print(f"{'OK   ' if condicion else 'FALLA'} {nombre}")


def probar_imagen():
    comprobar("existe assets/carta.png", rag.RUTA_CARTA.exists())
    secciones, _, _ = leer_carta()
    comprobar("la carta tiene 89 platos", sum(len(p) for p in secciones.values()) == 89)
    ancho, alto = Image.open(rag.RUTA_CARTA).size
    comprobar(f"tamaño para celular ({ancho}x{alto})", ancho == 1080 and alto > 3000)


def probar_responder():
    enviados = []

    def generar_simulado(contenido, sistema=None):
        enviados.append(contenido)
        return "Aquí tienes la carta.", "simulado"

    originales = rag.generar, rag.buscar
    rag.generar, rag.buscar = generar_simulado, (lambda consulta, k: [])
    try:
        r = rag.responder("podrias darme la carta completa por favor")
        comprobar("pedir la carta adjunta la imagen", r.imagen == str(rag.RUTA_CARTA))
        ultimo = enviados[-1][-1].parts[0].text
        comprobar("el modelo recibe la nota de imagen adjunta", prompts.NOTA_CARTA_ADJUNTA in ultimo)
        r = rag.responder("¿Cuánto cuesta 1/4 de pollo?")
        comprobar("otra pregunta no adjunta la imagen", r.imagen is None)
        comprobar("sin imagen no se envía la nota", prompts.NOTA_CARTA_ADJUNTA not in enviados[-1][-1].parts[0].text)
    finally:
        rag.generar, rag.buscar = originales


def probar_app():
    def responder_simulado(pregunta, historial=()):
        imagen = str(rag.RUTA_CARTA) if "carta" in pregunta else None
        return rag.Respuesta("Aquí tienes la carta.", imagen=imagen)

    rag.responder = responder_simulado  # app.py lo importa de rag
    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=30).run()
    at.chat_input[0].set_value("dame la carta completa").run()
    comprobar("la app muestra la imagen", len(at.get("image")) == 1)
    at.chat_input[0].set_value("¿tienen delivery?").run()
    comprobar("la imagen sigue visible en el historial", len(at.get("image")) == 1)


def main():
    consola_utf8()
    probar_imagen()
    probar_responder()
    probar_app()
    print(f"\n{sum(resultados)} de {len(resultados)} pruebas correctas.")
    sys.exit(0 if all(resultados) else 1)


if __name__ == "__main__":
    main()
