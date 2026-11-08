"""Pruebas de rag.py sin API: búsqueda con pregunta original y reformulada.

Uso: python tests/probar_rag.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rag
from comun import consola_utf8

resultados = []


def comprobar(nombre, condicion):
    resultados.append(condicion)
    print(f"{'OK   ' if condicion else 'FALLA'} {nombre}")


def main():
    consola_utf8()
    llamadas = []

    def buscar_simulado(consulta, k):
        llamadas.append(consulta)
        return [{"texto": f"{consulta} #{i}", "categoria": "x", "fuente": "f"} for i in range(k)]

    original = rag.buscar
    rag.buscar = buscar_simulado
    try:
        fr = rag.buscar_ambas("venden sanguches?", "¿Venden sánguches en Chorrillos?")
        comprobar("busca con la reformulada y con la original", llamadas == [
            "¿Venden sánguches en Chorrillos?", "venden sanguches?"])
        comprobar("agrega 3 fragmentos de la original", len(fr) == rag.FRAGMENTOS + 3)
        comprobar("la reformulada va primero", fr[0]["texto"].startswith("¿Venden"))

        llamadas.clear()
        fr = rag.buscar_ambas("¿Venden sánguches?", "venden sanguches?")
        comprobar("si son iguales (sin tildes) busca una sola vez", len(llamadas) == 1)
    finally:
        rag.buscar = original

    print(f"\n{sum(resultados)} de {len(resultados)} pruebas correctas.")
    sys.exit(0 if all(resultados) else 1)


if __name__ == "__main__":
    main()
