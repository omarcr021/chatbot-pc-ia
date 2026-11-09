"""Mide la recuperación: ¿el fragmento esperado aparece entre los 3 primeros?

Uso: python tests/probar_recuperacion.py
Un caso pasa si un fragmento de los 3 primeros es de la categoría esperada y contiene
el texto esperado. Sirve como evidencia de pruebas (esperado vs. obtenido).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from comun import consola_utf8
from indexar import buscar

# (pregunta, prefijo o tupla de prefijos de la categoría esperada, texto que debe traer)
CASOS = [
    ("¿Cuánto cuesta 1/4 de pollo con papas y ensalada?", ("carta_brasa_cuarto", "carta_productos"), "1/4 Pardos Brasa con Papas y Ensalada"),
    ("venden sanguches?", ("carta_sanguches", "carta_productos", "carta_resumen"), "Brioche Brasa"),
    ("tienen anticuchos?", ("carta_anticuchos", "carta_productos", "carta_resumen"), "Anticucho"),
    ("hay postres?", ("carta_postres", "carta_productos", "carta_resumen"), "Cheesecake"),
    ("que gaseosas tienen", ("carta_gaseosas", "carta_productos", "carta_resumen"), "Inca Kola"),
    ("podrias darme la carta completa por favor", "carta_resumen", "Pardos Brasa"),
    ("¿Cuánto cuesta el 1/4 de pollo en el local de Surco?", "carta_salon_lima", "1/4 Pardos Brasa: Original S/ 30.90"),
    ("precio del 1/4 de pollo para comer en el local de Arequipa", "carta_salon_arequipa", "1/4 Pardos Brasa: S/ 29.90"),
    ("¿Qué desayunos tienen en el local del aeropuerto?", "carta_salon_aeropuerto", "Desayuno Americano"),
    ("¿cuánto está la jarra de chicha en el salón de Trujillo?", "carta_salon_chiclayo_trujillo", "Jarra S/ 21.90"),
    ("Somos 8 y tenemos 300 soles, ¿algún local cercano a San Borja?", "carta_salon_lima", "Parrilla para 2"),
    ("Somos 8 y tenemos 300 soles, ¿algún local cercano a San Borja?", "locales", "PARDOS SAN BORJA"),
    ("Somos 6 y tenemos 250 soles, ¿algún local cerca de Los Olivos?", "carta_salon_lima", "S/"),
    ("¿Cuánto cuesta el 1/4 de pollo para comer en el local de Carabayllo?", "carta_salon_lima", "1/4 Pardos Brasa: Original S/ 30.90"),
    ("¿Qué platos tienen?", "carta_resumen", "S/"),
    ("¿Qué incluye la promo Tú Eliges 1.5 Lts?", "carta_productos", "Salsas (3 Ají, 3 Mayonesa y 3 Vinagreta"),
    ("¿Qué medios de pago aceptan?", "terminos", "MEDIOS DE PAGOS"),
    ("¿Cuál es el horario del local de Chorrillos?", "locales", "PARDOS CHORRILLOS"),
    ("Somos 4 personas, ¿qué promoción nos recomiendas?", "promociones", "Pardos Brasa"),
    ("¿Cuál es el pedido mínimo para delivery?", "terminos", "S/25.00"),
    ("¿Tienen chicha morada?", "carta_chicha", "Chicha"),
    ("¿Cómo presento un reclamo?", "reclamos", "LIBRO DE RECLAMACIONES"),
    ("¿Cuánto cuesta un pollo entero?", "carta_brasa_entero", "1 Pardos Brasa"),
    ("precio de medio pollo", "carta_brasa_medio", "1/2 Pardos Brasa"),
    ("¿Cuánto está la chicha?", "carta_chicha", "S/"),
    ("¿Cuánto cuestan los anticuchos?", "carta_anticuchos", "S/"),
    ("¿Cuánto cuesta el delivery?", "terminos", "delivery"),
]


# (pregunta, locales que debe devolver, y ningún otro)
CASOS_LOCALES = [
    ("¿Cuál es el horario del local de Chorrillos?", {"PARDOS CHORRILLOS"}),
    ("¿A qué hora abre Primavera?", {"PARDOS PRIMAVERA"}),
    ("direccion de pardos surquillo", {"PARDOS SURQUILLO"}),
    ("¿Dónde queda el local de La Molina?", {"PARDOS LA MOLINA", "PARDOS PLAZA CENTER LA MOLINA"}),
    ("horario de Pardos Chiclayo", {"PARDOS CHICLAYO"}),
    ("¿Hay un local en Arequipa? ¿dónde queda?", {"PARDOS AREQUIPA"}),
    ("¿Cuál es el correo de reservas de Surquillo?", {"PARDOS SURQUILLO"}),
]

# Nombra un local, pero pregunta por la carta: no debe quedar limitada a los locales.
PREGUNTA_SIN_FILTRO = "¿Cuánto cuesta el 1/4 de pollo en Surco?"


def probar_locales():
    aciertos = 0
    for pregunta, esperados in CASOS_LOCALES:
        obtenidos = [r.get("local", r["categoria"]) for r in buscar(pregunta)]
        paso = sorted(obtenidos) == sorted(esperados)
        aciertos += paso
        print(f"{'OK   ' if paso else 'FALLA'} {pregunta}\n      obtenido: {', '.join(obtenidos)}")

    categorias = [r["categoria"] for r in buscar(PREGUNTA_SIN_FILTRO)]
    paso = any(categoria != "locales" for categoria in categorias)
    aciertos += paso
    print(f"{'OK   ' if paso else 'FALLA'} {PREGUNTA_SIN_FILTRO}\n      obtenido: {', '.join(categorias)}")
    print(f"\n{aciertos} de {len(CASOS_LOCALES) + 1} casos de locales correctos.")


def main():
    consola_utf8()
    aciertos = 0
    for pregunta, categoria, texto in CASOS:
        resultados = buscar(pregunta)
        paso = any(
            r["categoria"].startswith(categoria) and texto in r["texto"]
            for r in resultados
        )
        aciertos += paso
        obtenido = ", ".join(f"{r['categoria']} ({r['distancia']})" for r in resultados)
        print(f"{'OK   ' if paso else 'FALLA'} {pregunta}\n      obtenido: {obtenido}")
    print(f"\n{aciertos} de {len(CASOS)} casos correctos.\n")
    probar_locales()


if __name__ == "__main__":
    main()
