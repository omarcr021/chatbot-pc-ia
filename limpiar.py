"""Tarea 3: limpia los .md de data/ y guarda el resultado en data/limpio/.

Uso: python limpiar.py
Resultado: data/limpio/*.md y data/limpio/_eliminadas.txt (para revisar qué se quitó)

Regla principal: ante la duda, una línea se conserva. Las líneas con precios u
horarios nunca se eliminan y el texto de una línea nunca se reescribe. La única
sustitución es la de los botones que cierran un plato o local por un separador.
"""

import math
import re
import sys
from collections import Counter

from comun import DATA, consola_utf8

LIMPIO = DATA / "limpio"

# Un bloque solo cuenta como menú si lo comparten este número de archivos o más
# (y al menos la mitad del total).
MIN_ARCHIVOS_REPETIDA = 3
MAX_LARGO_MENU = 60

PROTEGIDA = re.compile(
    r"""
    s/\.?\s*\d                                  # S/ 25, S/. 25.90
    | \b\d+[.,]\d{2}\b                          # 25.90
    | \b\d{1,2}:\d{2}\b                         # 12:30
    | \b\d{1,2}\s*(?:a\.?\s?m|p\.?\s?m|hrs?)\b  # 11 am, 10 p.m., 22 hrs
    | \b(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)s?\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# La línea completa debe coincidir: "Ver más" se quita, "Ver más platos en..." no.
NAVEGACION = re.compile(
    r"""
    (?:ir\ a(?:l)?\ (?:contenido|inicio)|saltar\ al\ contenido|volver(?:\ arriba)?
    |inicio|men[uú]|ver\ m[aá]s|ver\ todo|leer\ m[aá]s|mostrar\ m[aá]s|cerrar
    |anterior|siguiente|buscar|compartir|iniciar\ sesi[oó]n|reg[ií]strate
    |mi\ cuenta|carrito|ver|s[ií]guenos|aceptar|rechazar|configurar|entendido
    |pol[ií]tica\ de\ privacidad|t[eé]rminos\ y\ condiciones)
    [\s:.!>›»]*
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Botones que cierran cada plato o local. Se cambian por SEPARADOR para que un precio no
# quede pegado al plato siguiente e indexar.py no corte un plato por la mitad.
FIN_DE_BLOQUE = re.compile(r"agregar|c[oó]mo llegar", re.IGNORECASE)
SEPARADOR = "---"

# Basta con que aparezca en la línea.
AVISOS_LEGALES = re.compile(
    r"\bcookies?\b|todos los derechos reservados|©", re.IGNORECASE
)


def separar_encabezado(lineas):
    """Separa el encabezado de extraer.py (hasta la fecha) del contenido."""
    for i, linea in enumerate(lineas):
        if linea.startswith("Fecha de extracción:"):
            return lineas[: i + 1], lineas[i + 1 :]
    return [], lineas


def es_eliminable_por_patron(linea):
    texto = linea.strip()
    if not texto or PROTEGIDA.search(texto):
        return False
    return bool(NAVEGACION.fullmatch(texto) or AVISOS_LEGALES.search(texto))


def marcar_bloque_comun(contenidos, umbral, desde_final=False):
    """Índices, por archivo, de la secuencia que varios archivos comparten en un extremo.

    Avanza línea a línea desde el inicio (o el final) y se detiene en cuanto los archivos
    dejan de coincidir. Así el título propio de cada página corta el bloque, y un plato
    que figura en varias páginas no se confunde con el menú del sitio.
    """
    posiciones = {}
    for nombre, lineas in contenidos.items():
        indices = [i for i, linea in enumerate(lineas) if linea.strip()]
        posiciones[nombre] = indices[::-1] if desde_final else indices

    marcados = {nombre: set() for nombre in contenidos}
    activos = set(contenidos)
    paso = 0
    while True:
        textos = {
            nombre: contenidos[nombre][posiciones[nombre][paso]].strip()
            for nombre in activos
            if paso < len(posiciones[nombre])
        }
        candidatos = Counter(
            t for t in textos.values()
            if len(t) <= MAX_LARGO_MENU and not PROTEGIDA.search(t)
        )
        if not candidatos:
            return marcados
        comun, veces = candidatos.most_common(1)[0]
        if veces < umbral:
            return marcados

        activos = {nombre for nombre, texto in textos.items() if texto == comun}
        for nombre in activos:
            marcados[nombre].add(posiciones[nombre][paso])
        paso += 1


def colapsar_vacias(lineas):
    resultado = []
    for linea in lineas:
        if linea.strip() or (resultado and resultado[-1].strip()):
            resultado.append(linea.rstrip())
    while resultado and not resultado[-1].strip():
        resultado.pop()
    return resultado


def main():
    consola_utf8()
    archivos = sorted(DATA.glob("*.md"))
    if not archivos:
        sys.exit("No hay archivos .md en data/. Ejecuta primero extraer.py.")

    encabezados, contenidos, totales = {}, {}, {}
    for archivo in archivos:
        lineas = archivo.read_text(encoding="utf-8").splitlines()
        totales[archivo.name] = len(lineas)
        encabezados[archivo.name], contenidos[archivo.name] = separar_encabezado(lineas)

    umbral = max(MIN_ARCHIVOS_REPETIDA, math.ceil(len(contenidos) / 2))
    menu_inicio = marcar_bloque_comun(contenidos, umbral)
    menu_final = marcar_bloque_comun(contenidos, umbral, desde_final=True)

    LIMPIO.mkdir(exist_ok=True)
    for viejo in LIMPIO.glob("*.md"):  # evita indexar categorías ya retiradas
        viejo.unlink()

    registro = []
    print(f"{'Archivo':<30}{'Antes':>8}{'Después':>9}{'Eliminadas':>12}")
    for nombre, lineas in contenidos.items():
        menu = menu_inicio[nombre] | menu_final[nombre]
        conservadas = []
        for i, linea in enumerate(lineas):
            if i in menu:
                registro.append(f"{nombre}\tmenú repetido\t{linea.strip()}")
            elif FIN_DE_BLOQUE.fullmatch(linea.strip()):
                conservadas.append(SEPARADOR)
            elif es_eliminable_por_patron(linea):
                registro.append(f"{nombre}\tnavegación/cookies\t{linea.strip()}")
            else:
                conservadas.append(linea)

        cuerpo = colapsar_vacias(conservadas)
        final = encabezados[nombre] + ([""] if encabezados[nombre] else []) + cuerpo
        (LIMPIO / nombre).write_text("\n".join(final) + "\n", encoding="utf-8")
        antes = totales[nombre]
        print(f"{nombre:<30}{antes:>8}{len(final):>9}{antes - len(final):>12}")

    (LIMPIO / "_eliminadas.txt").write_text(
        "\n".join(registro) + "\n", encoding="utf-8"
    )
    print("\nDetalle de lo eliminado (sin contar líneas vacías): data/limpio/_eliminadas.txt")
    if len(archivos) < MIN_ARCHIVOS_REPETIDA:
        print(f"AVISO: con menos de {MIN_ARCHIVOS_REPETIDA} archivos no se detectan menús repetidos.")


if __name__ == "__main__":
    main()
