"""Pruebas del control de spam. No usa la API: Gemini y la búsqueda se simulan.

Uso: python tests/probar_spam.py
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from streamlit.testing.v1 import AppTest

import prompts
import rag
from comun import consola_utf8

resultados = []


def comprobar(nombre, condicion):
    resultados.append(condicion)
    print(f"{'OK   ' if condicion else 'FALLA'} {nombre}")


def probar_deteccion_local():
    previo = [{"role": "user", "content": "¿Cuánto cuesta el pollo?"},
              {"role": "assistant", "content": "S/ 62.50"}]
    comprobar("sin letras ni números es spam", rag.spam_local("!!!! 😡😡", []) is not None)
    comprobar("mensaje repetido es spam", rag.spam_local("cuanto cuesta el POLLO", previo) is not None)
    comprobar("pregunta normal no es spam", rag.spam_local("¿Tienen delivery?", previo) is None)
    comprobar("pregunta corta con número no es spam", rag.spam_local("1/4", []) is None)


def probar_marca_del_modelo():
    texto, spam = rag.separar_marca_spam("[SPAM] Entiendo. ¿Te ayudo con la carta?")
    comprobar("la marca se detecta", spam)
    comprobar("la marca no se muestra", "[SPAM]" not in texto and texto.startswith("Entiendo"))
    comprobar("sin marca no es spam", rag.separar_marca_spam("El 1/4 cuesta S/ 31.90")[1] is False)

    # responder() completo, con el modelo y la búsqueda simulados
    originales = rag.generar, rag.buscar
    rag.buscar = lambda consulta, k: []
    rag.generar = lambda contenido, sistema=None: ("[SPAM] Entiendo tu punto.", "simulado")
    r = rag.responder("eres un tonto")
    comprobar("responder() marca spam y limpia el texto", r.spam and r.texto == "Entiendo tu punto.")
    r = rag.responder("!!!!")
    comprobar("responder() no llama al modelo con spam evidente", r.spam and r.modelo == "")
    rag.generar, rag.buscar = originales


def respuesta_simulada(pregunta, historial=()):
    spam = "tonto" in pregunta or "mejor" in pregunta
    return rag.Respuesta("Entendido." if spam else "El 1/4 cuesta S/ 31.90.", spam=spam)


def probar_cierre_en_app():
    rag.responder = respuesta_simulada  # app.py lo importa de rag
    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=30).run()

    at.chat_input[0].set_value("Norkys es mejor").run()
    comprobar("spam 1: sin aviso", prompts.AVISO_SPAM not in at.markdown[-1].value)
    at.chat_input[0].set_value("¿Cuánto cuesta 1/4?").run()
    comprobar("pregunta válida entre medio no cierra", not at.session_state.cerrado)
    at.chat_input[0].set_value("te dije que norkys es mejor").run()
    comprobar("spam 2: muestra el aviso", prompts.AVISO_SPAM in at.markdown[-1].value)
    at.chat_input[0].set_value("eres un tonto").run()
    comprobar("spam 3: cierra el chat", at.session_state.cerrado)
    comprobar("spam 3: muestra el mensaje de cierre", any(prompts.CHAT_CERRADO in m.value for m in at.markdown))
    comprobar("spam 3: campo de texto desactivado", at.chat_input[0].disabled)

    nueva =next(b for b in at.button if b.label == "Nueva conversación")
    nueva.click().run()
    comprobar("nueva conversación reabre el chat",
              not at.chat_input[0].disabled and at.session_state.spam == 0)


def main():
    consola_utf8()
    probar_deteccion_local()
    probar_marca_del_modelo()
    probar_cierre_en_app()
    print(f"\n{sum(resultados)} de {len(resultados)} pruebas correctas.")
    sys.exit(0 if all(resultados) else 1)


if __name__ == "__main__":
    main()
