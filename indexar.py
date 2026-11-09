"""Tarea 4: indexa data/limpio/ en ChromaDB y permite probar la recuperación.

Uso:
  python indexar.py                                # reconstruye ./chroma_db
  python indexar.py --probar "¿Tienen delivery?"   # muestra los 3 fragmentos más cercanos
  python indexar.py --compactar                    # quita restos de índices viejos (sin API)

chroma_db/ se sube al repositorio para que la app desplegada no tenga que recalcular los
vectores. Antes de hacer commit tras reindexar, ejecuta --compactar.

El proveedor es Gemini (requiere GOOGLE_API_KEY en el entorno o en .env). Con
EMBEDDINGS_PROVIDER=sentence-transformers se usa un modelo local (requirements-local.txt).
Queda guardado en la colección, y buscar() lo lee de ahí para consultar siempre con el
mismo modelo con el que se indexó.
"""

import argparse
import multiprocessing
import os
import re
import shutil
import sys
import time
import unicodedata
import uuid
from functools import lru_cache

import chromadb
from chromadb.config import Settings
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from comun import DATA, RAIZ, consola_utf8

load_dotenv(RAIZ / ".env")

LIMPIO = DATA / "limpio"
CHROMA_DIR = RAIZ / "chroma_db"
COLECCION = "base_conocimiento"

CHUNK_SIZE = 500
CHUNK_OVERLAP = 80

# El plan gratuito de Gemini admite 100 textos por minuto, y cada fragmento cuenta como uno.
TAMANO_LOTE = 40
PAUSA_GEMINI_S = 30
REINTENTOS = 4
ESPERA_REINTENTO_S = 65

# La carta dice "1 Pardos Brasa", pero el cliente pregunta por "pollo entero". Esta línea
# se antepone a cada fragmento para que coincidan; el texto original no se toca.
ETIQUETAS = {
    "carta_brasa_entero": "Pollo a la brasa entero (1 pollo)",
    "carta_brasa_medio": "Medio pollo a la brasa (1/2 pollo)",
    "carta_brasa_cuarto": "Cuarto de pollo a la brasa (1/4 de pollo)",
}

# Secciones del resumen de la carta, en el orden en que se muestran. Se arma a partir de
# carta_productos.md para poder entregar la carta completa: la búsqueda normal solo trae
# unos pocos fragmentos.
SECCIONES_CARTA = [
    ("carta_brasa", "Pardos Brasa (pollo a la brasa)"),
    ("carta_parrillero", "Pardos Parrilleros"),
    ("carta_anticuchos", "Anticuchos y mollejitas"),
    ("carta_mollejitas", "Anticuchos y mollejitas"),
    ("carta_chicharrones", "Chicharrones"),
    ("carta_sanguches", "Sánguches"),
    ("carta_ensalada", "Ensaladas"),
    ("carta_guarniciones", "Guarniciones"),
    ("carta_adicionales", "Adicionales"),
    ("carta_chicha", "Bebidas"),
    ("carta_gaseosas", "Bebidas"),
    ("carta_postres", "Postres"),
    ("promociones", "Promociones"),
]
CATEGORIA_RESUMEN = "carta_resumen"
RE_LINEA_PRECIO = re.compile(r"^S/\s*\d")

# Categorías con un fragmento por bloque en vez de cortar por tamaño.
CATEGORIAS_POR_BLOQUE = {"locales"}

# Cartas salón (pedidos presenciales en el local), un archivo por zona: carta_salon_<zona>.md.
# Cada sección es un fragmento entero, para que ningún precio quede sin su zona.
PREFIJO_SALON = "carta_salon_"
ZONA_POR_CIUDAD = {
    "Lima": "lima", "Arequipa": "arequipa", "Chiclayo": "chiclayo_trujillo", "Trujillo": "chiclayo_trujillo",
}
ZONA_POR_LOCAL = {"PARDOS ASIA": "asia", "PARDOS AEROPUERTO": "aeropuerto"}  # tienen carta propia
# La carta salón de Lima vale para toda la provincia de Lima, y para el Callao, que la web
# también clasifica como Lima (Pardos Bellavista). Normalizados, con alias comunes.
DISTRITOS_LIMA = (
    "lima norte", "lima sur", "lima este", "lima centro", "lima metropolitana", "cercado de lima",
    "ancon", "ate", "ate vitarte", "barranco", "brena", "carabayllo", "chaclacayo", "chorrillos",
    "cieneguilla", "comas", "el agustino", "independencia", "jesus maria", "la molina",
    "la victoria", "lince", "los olivos", "lurigancho", "chosica", "lurin", "magdalena",
    "magdalena del mar", "miraflores", "pachacamac", "pucusana", "pueblo libre",
    "puente piedra", "punta hermosa", "punta negra", "rimac", "san bartolo", "san borja",
    "san isidro", "san juan de lurigancho", "sjl", "san juan de miraflores", "sjm", "san luis",
    "san martin de porres", "smp", "san miguel", "santa anita", "santa maria del mar",
    "santa rosa", "santiago de surco", "surco", "surquillo", "villa el salvador",
    "villa maria del triunfo", "callao", "bellavista", "carmen de la legua", "la perla",
    "la punta", "ventanilla", "mi peru",
)
ZONAS_SALON = sorted(set(ZONA_POR_CIUDAD.values()) | set(ZONA_POR_LOCAL.values()))
RE_CIUDAD = re.compile(r"^Ciudad: (.+)$", re.MULTILINE)
MAX_SECCIONES_SALON = 25  # para devolver una carta salón completa

# Bases legales de promociones ya vencidas: ocupaban 2 de cada 3 fragmentos y desplazaban
# a la carta. El archivo se conserva en data/, pero no se indexa.
EXCLUIR_DEL_INDICE = {"promociones_terminos"}

MODELOS_POR_DEFECTO = {
    "sentence-transformers": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "gemini": "models/gemini-embedding-001",
}

RE_FUENTE = re.compile(r"^Fuente: (.+)$", re.MULTILINE)
RE_FECHA = re.compile(r"^Fecha de extracción: (.+)$", re.MULTILINE)
RE_LOCAL = re.compile(r"^PARDOS .+$", re.MULTILINE)

# Sobre texto normalizado. Solo estas preguntas se limitan al local mencionado: en
# "¿cuánto cuesta el 1/4 en Surco?" lo que se busca está en la carta, no en el local.
RE_UBICACION = re.compile(
    r"\b(horarios?|horas?|abren?|abierto|cierran?|atienden?|atencion|direccion|donde"
    r"|ubic\w+|telefonos?|delivery|local(es)?|llegar|correos?|email|reservas?|contacto|hay)\b"
)

# Sobre texto normalizado. Las preguntas de precio se limitan a carta y promociones, salvo
# las de servicios cuyo costo no está ahí.
RE_PRECIO = re.compile(
    r"\b(cuestan?|costo|precios?|cuanto (esta|estan|sale|salen|vale|valen)"
    r"|recomiend\w*|presupuesto|personas|somos \d+|soles)\b"
)
RE_CARTA_COMPLETA = re.compile(
    r"\b(carta|menu)\b.*\b(complet\w*|enter\w*|tod[oa])\b"
    r"|\btod[oa] (la|el) (carta|menu)\b"
    r"|\b(ver|dame|dar|darme|muestrame|mostrar|pasame|pasas|mandame|mandas|envia\w*|tienes)"
    r" (la|el|su|tu) (carta|menu)\b"
    r"|\bque (platos|productos|comidas) (tienen|hay|venden|ofrecen)\b"
)
RE_SERVICIO = re.compile(r"\b(delivery|envio|recargo|catering|fiestas?|cumpleanos|giftcards?|vales?)\b")
# Pedidos presenciales: se responden con la carta salón de la zona.
RE_SALON = re.compile(
    r"\b(salon|presencial\w*|en (el )?local|en (el )?restaurante|en tienda"
    r"|(comer|consumir) (ahi|alli|aqui|en (el )?(local|restaurante|salon)))\b"
)


def configuracion_embeddings():
    proveedor = os.environ.get("EMBEDDINGS_PROVIDER", "gemini").lower()
    if proveedor not in MODELOS_POR_DEFECTO:
        sys.exit(f"EMBEDDINGS_PROVIDER no válido: {proveedor}. "
                 f"Opciones: {', '.join(MODELOS_POR_DEFECTO)}")
    modelo = os.environ.get("EMBEDDINGS_MODEL") or MODELOS_POR_DEFECTO[proveedor]
    return proveedor, modelo


@lru_cache(maxsize=1)
def crear_embeddings(proveedor, modelo):
    if proveedor == "gemini":
        if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
            sys.exit("Falta GOOGLE_API_KEY. Copia .env.example como .env y agrega tu clave.")
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(model=modelo)

    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(model_name=modelo)


def cliente_chroma():
    return chromadb.PersistentClient(
        path=str(CHROMA_DIR), settings=Settings(anonymized_telemetry=False)
    )


def es_carta(categoria):
    return categoria.startswith("carta_") or categoria == "promociones"


def seccion_de(categoria):
    return next((nombre for prefijo, nombre in SECCIONES_CARTA if categoria.startswith(prefijo)), "Otros")


def leer_carta():
    """Platos y precios de las fichas de producto, agrupados y ordenados por sección.

    Devuelve (secciones, fuente, fecha), con secciones = {sección: [(plato, precio), ...]},
    o None si aún no existe carta_productos.md. Lo usan el índice y generar_carta.py.
    """
    ruta = LIMPIO / "carta_productos.md"
    if not ruta.exists():
        return None
    texto = ruta.read_text(encoding="utf-8")
    fuente, fecha = RE_FUENTE.search(texto), RE_FECHA.search(texto)

    por_seccion = {}
    for bloque in re.split(r"^---$", texto[fecha.end():], flags=re.MULTILINE):
        lineas = [l.strip() for l in bloque.splitlines() if l.strip()]
        precio = next((l for l in lineas if RE_LINEA_PRECIO.match(l)), None)
        categoria = next((l.split(": ", 1)[1] for l in lineas if l.startswith("Categoría: ")), None)
        if lineas and precio and categoria:
            por_seccion.setdefault(seccion_de(categoria), []).append((lineas[0], precio))

    orden = list(dict.fromkeys(nombre for _, nombre in SECCIONES_CARTA)) + ["Otros"]
    secciones = {s: por_seccion[s] for s in orden if s in por_seccion}
    return secciones, fuente.group(1).strip(), fecha.group(1).strip()


def resumen_de_carta():
    """Un fragmento por sección con cada plato y su precio, tomado de las fichas de producto."""
    carta = leer_carta()
    if carta is None:
        print("AVISO: no hay carta_productos.md; no se arma el resumen de la carta.")
        return []
    secciones, fuente, fecha = carta
    return [
        Document(
            page_content=(
                f"Carta completa, sección {seccion} (precios de la web al {fecha})\n"
                + "\n".join(f"- {plato}: {precio}" for plato, precio in platos)
            ),
            metadata={"categoria": CATEGORIA_RESUMEN, "fuente": fuente, "fecha": fecha, "tipo": "carta"},
        )
        for seccion, platos in secciones.items()
    ]


def pide_carta_completa(pregunta):
    return bool(RE_CARTA_COMPLETA.search(normalizar(pregunta)))


def fragmentos_por_local(cuerpo, metadatos):
    """Un fragmento por local, para que nunca se mezclen los datos de dos locales."""
    partes = []
    for bloque in re.split(r"^---$", cuerpo, flags=re.MULTILINE):
        nombre = RE_LOCAL.search(bloque)
        if nombre:
            ciudad = RE_CIUDAD.search(bloque)
            partes.append(Document(
                page_content=bloque[nombre.start():].strip(),
                metadata={
                    **metadatos,
                    "local": nombre.group(0).strip(),
                    "ciudad": ciudad.group(1).strip() if ciudad else "",
                },
            ))
    return partes


def fragmentos_por_seccion(cuerpo, metadatos):
    """Un fragmento por sección (separadas por "---"), sin cortarlas por tamaño."""
    return [
        Document(page_content=bloque.strip(), metadata=metadatos)
        for bloque in re.split(r"^---$", cuerpo, flags=re.MULTILINE)
        if bloque.strip()
    ]


def cargar_fragmentos():
    # "---" lo pone limpiar.py entre platos y locales: se corta ahí antes que en otro lado.
    separador = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n---\n", "\n\n", "\n", " ", ""],
        keep_separator=False,
    )
    fragmentos = []
    for archivo in sorted(LIMPIO.glob("*.md")):
        if archivo.stem in EXCLUIR_DEL_INDICE:
            print(f"{archivo.name}: excluido del índice")
            continue
        texto = archivo.read_text(encoding="utf-8")
        fuente, fecha = RE_FUENTE.search(texto), RE_FECHA.search(texto)
        if not fuente or not fecha:
            print(f"AVISO: {archivo.name} no tiene fuente o fecha; se omite.")
            continue

        cuerpo = texto[fecha.end():].strip()
        metadatos = {
            "categoria": archivo.stem,
            "fuente": fuente.group(1).strip(),
            "fecha": fecha.group(1).strip(),
            "tipo": "carta" if es_carta(archivo.stem) else "general",
        }
        if archivo.stem in CATEGORIAS_POR_BLOQUE:
            partes = fragmentos_por_local(cuerpo, metadatos)
        elif archivo.stem.startswith(PREFIJO_SALON):
            zona = archivo.stem.removeprefix(PREFIJO_SALON)
            partes = fragmentos_por_seccion(cuerpo, {**metadatos, "zona": zona})
        else:
            partes = separador.create_documents([cuerpo], metadatas=[metadatos])
        if archivo.stem in ETIQUETAS:
            for parte in partes:
                parte.page_content = f"{ETIQUETAS[archivo.stem]}\n{parte.page_content}"
        print(f"{archivo.name}: {len(partes)} fragmentos")
        fragmentos += partes

    resumen = resumen_de_carta()
    print(f"resumen de la carta: {len(resumen)} secciones")
    return fragmentos + resumen


def borrar_coleccion(cliente, nombre):
    if any(c.name == nombre for c in cliente.list_collections()):
        cliente.delete_collection(nombre)


def vectores_previos(cliente, proveedor, modelo):
    """Vectores del índice actual por texto, si se hizo con el mismo modelo; si no, {}."""
    try:
        coleccion = cliente.get_collection(COLECCION)
    except Exception:
        return {}
    if (coleccion.metadata or {}).get("modelo") != modelo or coleccion.metadata.get("proveedor") != proveedor:
        return {}
    datos = coleccion.get(include=["documents", "embeddings"])
    return dict(zip(datos["documents"], datos["embeddings"]))


def guardar(coleccion, fragmentos, vectores):
    coleccion.add(
        ids=[str(uuid.uuid4()) for _ in fragmentos],
        documents=[f.page_content for f in fragmentos],
        metadatas=[f.metadata for f in fragmentos],
        embeddings=[list(v) for v in vectores],
    )


def agregar_por_lotes(coleccion, fragmentos, embeddings, previos, pausa):
    """Reutiliza los vectores de textos sin cambios y calcula solo los nuevos, por lotes,
    respetando el límite por minuto y reintentando si se supera."""
    reutilizables = [f for f in fragmentos if f.page_content in previos]
    if reutilizables:
        guardar(coleccion, reutilizables, [previos[f.page_content] for f in reutilizables])
    nuevos = [f for f in fragmentos if f.page_content not in previos]
    print(f"Vectores reutilizados: {len(reutilizables)} | por calcular: {len(nuevos)}")

    for inicio in range(0, len(nuevos), TAMANO_LOTE):
        if inicio:
            time.sleep(pausa)
        lote = nuevos[inicio:inicio + TAMANO_LOTE]
        for intento in range(1, REINTENTOS + 1):
            try:
                vectores = embeddings.embed_documents([f.page_content for f in lote])
                break
            except Exception as error:
                if "RESOURCE_EXHAUSTED" not in str(error) or intento == REINTENTOS:
                    raise
                print(f"Límite de la API alcanzado; reintento {intento} en {ESPERA_REINTENTO_S} s.")
                time.sleep(ESPERA_REINTENTO_S)
        guardar(coleccion, lote, vectores)
        print(f"  {inicio + len(lote)} de {len(nuevos)} nuevos")


def indexar():
    fragmentos = cargar_fragmentos()
    if not fragmentos:
        sys.exit("No hay contenido en data/limpio/. Ejecuta primero limpiar.py.")

    proveedor, modelo = configuracion_embeddings()
    embeddings = crear_embeddings(proveedor, modelo)

    # Se construye aparte y se reemplaza al final: si algo falla, el índice actual sigue.
    cliente = cliente_chroma()
    previos = vectores_previos(cliente, proveedor, modelo)
    temporal = f"{COLECCION}_nueva"
    borrar_coleccion(cliente, temporal)
    coleccion = cliente.create_collection(
        temporal, metadata={"hnsw:space": "cosine", "proveedor": proveedor, "modelo": modelo}
    )
    try:
        agregar_por_lotes(
            coleccion, fragmentos, embeddings, previos,
            PAUSA_GEMINI_S if proveedor == "gemini" else 0,
        )
    except BaseException:
        borrar_coleccion(cliente, temporal)
        raise

    borrar_coleccion(cliente, COLECCION)
    cliente.get_collection(temporal).modify(name=COLECCION)
    print(f"\n{len(fragmentos)} fragmentos indexados en {CHROMA_DIR} ({proveedor}: {modelo})")


def normalizar(texto):
    """Minúsculas, sin tildes y solo palabras separadas por un espacio."""
    descompuesto = unicodedata.normalize("NFD", texto)
    sin_tildes = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return " ".join(re.findall(r"\w+", sin_tildes.lower()))


def contiene_frase(texto, frase):
    return f" {frase} " in f" {texto} "


def locales_mencionados(pregunta, nombres):
    """Locales que nombra la pregunta.

    Si el nombre es ambiguo incluye todos los que lo contienen: "La Molina" devuelve
    PARDOS LA MOLINA y PARDOS PLAZA CENTER LA MOLINA.
    """
    texto = normalizar(pregunta)
    claves = {nombre: normalizar(nombre).removeprefix("pardos ") for nombre in nombres}
    citadas = [clave for clave in claves.values() if contiene_frase(texto, clave)]
    return sorted(
        nombre for nombre, clave in claves.items()
        if any(contiene_frase(clave, citada) for citada in citadas)
    )


def filtro_por_local(pregunta, coleccion):
    """Filtro de Chroma si la pregunta es sobre un local concreto; si no, None."""
    if not RE_UBICACION.search(normalizar(pregunta)):
        return None
    registros = coleccion.get(where={"categoria": "locales"}, include=["metadatas"])
    nombres = {metadatos["local"] for metadatos in registros["metadatas"]}
    mencionados = locales_mencionados(pregunta, nombres)
    return {"local": {"$in": mencionados}} if mencionados else None


def zonas_mencionadas(pregunta, coleccion):
    """Zonas de carta salón según el local o la ciudad que nombra la pregunta."""
    registros = coleccion.get(where={"categoria": "locales"}, include=["metadatas"])
    ciudad_por_local = {m["local"]: m.get("ciudad", "") for m in registros["metadatas"]}
    zonas = {
        ZONA_POR_LOCAL.get(nombre) or ZONA_POR_CIUDAD.get(ciudad_por_local[nombre])
        for nombre in locales_mencionados(pregunta, ciudad_por_local)
    }
    texto = normalizar(pregunta)
    ciudades = {zona for ciudad, zona in ZONA_POR_CIUDAD.items() if contiene_frase(texto, normalizar(ciudad))}
    # Un distrito de Lima cuenta como Lima, salvo que nombren otra ciudad: Miraflores y
    # La Victoria también existen en Arequipa y Chiclayo.
    if not ciudades and any(contiene_frase(texto, distrito) for distrito in DISTRITOS_LIMA):
        ciudades.add("lima")
    zonas |= ciudades
    return sorted(z for z in zonas if z)


def filtro_por_salon(pregunta, coleccion):
    """Filtro de Chroma si la pregunta es sobre consumo presencial; si no, None.

    Con local o ciudad, usa la carta salón de esa zona; sin ellos, todas las cartas salón.
    """
    if not RE_SALON.search(normalizar(pregunta)):
        return None
    zonas = zonas_mencionadas(pregunta, coleccion) or ZONAS_SALON
    return {"categoria": {"$in": [PREFIJO_SALON + zona for zona in zonas]}}


def filtro_por_precio(pregunta):
    """Filtro de Chroma si la pregunta es por el precio de un plato; si no, None."""
    texto = normalizar(pregunta)
    if RE_PRECIO.search(texto) and not RE_SERVICIO.search(texto):
        return {"tipo": "carta"}
    return None


def buscar(pregunta, k=3):
    """Devuelve hasta k fragmentos cercanos con sus metadatos y distancia coseno.

    Si es sobre consumo presencial, busca en la carta salón de la zona.
    Si la pregunta es sobre un local concreto, devuelve solo los fragmentos de ese local;
    si además pide precios o una recomendación, suma la carta salón de la zona del local.
    Si pide la carta completa, devuelve todas las secciones del resumen de la carta.
    Si es por un precio, busca solo en carta y promociones.
    """
    cliente = cliente_chroma()
    try:
        coleccion = cliente.get_collection(COLECCION)
    except Exception:
        sys.exit("No existe el índice. Ejecuta primero: python indexar.py")
    metadatos = coleccion.metadata

    almacen = Chroma(
        client=cliente,
        collection_name=COLECCION,
        embedding_function=crear_embeddings(metadatos["proveedor"], metadatos["modelo"]),
    )
    filtro = filtro_por_salon(pregunta, coleccion)
    filtro_extra = None
    if filtro is not None:
        if pide_carta_completa(pregunta):
            k = MAX_SECCIONES_SALON  # la carta salón completa de la zona
    else:
        filtro = filtro_por_local(pregunta, coleccion)
        pide_local = RE_UBICACION.search(normalizar(pregunta))
        if pide_local and filtro_por_precio(pregunta):
            # "Somos 8 con S/ 300, ¿algún local en San Borja?": el local y sus precios.
            zonas = zonas_mencionadas(pregunta, coleccion)
            if zonas:
                filtro_extra = {"categoria": {"$in": [PREFIJO_SALON + zona for zona in zonas]}}
                # Un distrito sin local con ese nombre: los locales más cercanos al texto.
                filtro = filtro or {"categoria": "locales"}
        if filtro is None and pide_carta_completa(pregunta):
            filtro = {"categoria": CATEGORIA_RESUMEN}
            k = len(SECCIONES_CARTA)  # todas las secciones, no solo las k más parecidas
        filtro = filtro or filtro_por_precio(pregunta)

    vector = almacen.embeddings.embed_query(pregunta)  # un solo embedding por búsqueda
    resultados = almacen.similarity_search_by_vector_with_relevance_scores(
        vector, k=k, filter=filtro
    )
    if filtro_extra is not None:
        resultados += almacen.similarity_search_by_vector_with_relevance_scores(
            vector, k=k, filter=filtro_extra
        )
    return [
        {"texto": doc.page_content, "distancia": round(distancia, 4), **doc.metadata}
        for doc, distancia in resultados
    ]


def copiar_indice(nueva):
    """Copia la colección a la carpeta nueva con sus vectores guardados."""
    origen = cliente_chroma().get_collection(COLECCION)
    datos = origen.get(include=["documents", "embeddings", "metadatas"])
    destino = chromadb.PersistentClient(
        path=str(nueva), settings=Settings(anonymized_telemetry=False)
    ).create_collection(COLECCION, metadata=origen.metadata)
    destino.add(
        ids=datos["ids"],
        documents=datos["documents"],
        embeddings=datos["embeddings"],
        metadatas=datos["metadatas"],
    )
    if destino.count() != origen.count():
        raise RuntimeError("La copia del índice quedó incompleta.")


def compactar():
    """Copia el índice a una carpeta nueva, sin los restos de colecciones borradas.

    Chroma no borra del disco los vectores de una colección eliminada, y cada reindexación
    deja unos 1.2 MB de restos. Reutiliza los vectores guardados: no llama a la API.
    """
    nueva = CHROMA_DIR.with_name(CHROMA_DIR.name + "_nuevo")
    shutil.rmtree(nueva, ignore_errors=True)

    # La copia corre en otro proceso: Chroma no suelta sus archivos mientras el proceso
    # vive, y en Windows no se puede reemplazar una carpeta con archivos abiertos.
    proceso = multiprocessing.Process(target=copiar_indice, args=(str(nueva),))
    proceso.start()
    proceso.join()
    if proceso.exitcode != 0:
        shutil.rmtree(nueva, ignore_errors=True)
        sys.exit("No se pudo copiar el índice; chroma_db quedó como estaba.")

    shutil.rmtree(CHROMA_DIR)
    nueva.rename(CHROMA_DIR)
    print(f"Índice compactado en {CHROMA_DIR}")


def main():
    consola_utf8()

    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--probar", metavar="PREGUNTA", help="prueba la recuperación")
    argumentos.add_argument("--compactar", action="store_true",
                            help="quita del disco los restos de índices anteriores")
    opciones = argumentos.parse_args()
    pregunta = opciones.probar

    if opciones.compactar:
        compactar()
        return

    if pregunta is None:
        indexar()
        return

    for i, r in enumerate(buscar(pregunta), start=1):
        print(f"--- {i}. {r['categoria']} | distancia {r['distancia']} | {r['fecha']}")
        print(f"Fuente: {r['fuente']}\n{r['texto']}\n")


if __name__ == "__main__":
    main()
