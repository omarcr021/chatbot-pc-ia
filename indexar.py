"""Tarea 4: indexa data/limpio/ en ChromaDB y permite probar la recuperación.

Uso:
  python indexar.py                                # reconstruye ./chroma_db
  python indexar.py --probar "¿Tienen delivery?"   # muestra los 3 fragmentos más cercanos

El proveedor se elige con EMBEDDINGS_PROVIDER (sentence-transformers o gemini).
Queda guardado en la colección, y buscar() lo lee de ahí para consultar siempre con el
mismo modelo con el que se indexó.
"""

import argparse
import os
import re
import sys

import chromadb
from chromadb.config import Settings
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from comun import DATA, RAIZ, consola_utf8

LIMPIO = DATA / "limpio"
CHROMA_DIR = RAIZ / "chroma_db"
COLECCION = "base_conocimiento"

CHUNK_SIZE = 500
CHUNK_OVERLAP = 80

MODELOS_POR_DEFECTO = {
    "sentence-transformers": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "gemini": "models/gemini-embedding-001",
}

RE_FUENTE = re.compile(r"^Fuente: (.+)$", re.MULTILINE)
RE_FECHA = re.compile(r"^Fecha de extracción: (.+)$", re.MULTILINE)


def configuracion_embeddings():
    proveedor = os.environ.get("EMBEDDINGS_PROVIDER", "sentence-transformers").lower()
    if proveedor not in MODELOS_POR_DEFECTO:
        sys.exit(f"EMBEDDINGS_PROVIDER no válido: {proveedor}. "
                 f"Opciones: {', '.join(MODELOS_POR_DEFECTO)}")
    modelo = os.environ.get("EMBEDDINGS_MODEL") or MODELOS_POR_DEFECTO[proveedor]
    return proveedor, modelo


def crear_embeddings(proveedor, modelo):
    if proveedor == "gemini":
        if not os.environ.get("GOOGLE_API_KEY"):
            sys.exit("Falta GOOGLE_API_KEY en el entorno o en .env.")
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(model=modelo)

    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(model_name=modelo)


def cliente_chroma():
    return chromadb.PersistentClient(
        path=str(CHROMA_DIR), settings=Settings(anonymized_telemetry=False)
    )


def cargar_fragmentos():
    separador = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    fragmentos = []
    for archivo in sorted(LIMPIO.glob("*.md")):
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
        }
        partes = separador.create_documents([cuerpo], metadatas=[metadatos])
        print(f"{archivo.name}: {len(partes)} fragmentos")
        fragmentos += partes
    return fragmentos


def indexar():
    fragmentos = cargar_fragmentos()
    if not fragmentos:
        sys.exit("No hay contenido en data/limpio/. Ejecuta primero limpiar.py.")

    proveedor, modelo = configuracion_embeddings()
    embeddings = crear_embeddings(proveedor, modelo)

    cliente = cliente_chroma()
    if any(c.name == COLECCION for c in cliente.list_collections()):
        cliente.delete_collection(COLECCION)

    almacen = Chroma(
        client=cliente,
        collection_name=COLECCION,
        embedding_function=embeddings,
        collection_metadata={
            "hnsw:space": "cosine",
            "proveedor": proveedor,
            "modelo": modelo,
        },
    )
    almacen.add_documents(fragmentos)
    print(f"\n{len(fragmentos)} fragmentos indexados en {CHROMA_DIR} ({proveedor}: {modelo})")


def buscar(pregunta, k=3):
    """Devuelve los k fragmentos más cercanos con sus metadatos y distancia coseno."""
    cliente = cliente_chroma()
    try:
        metadatos = cliente.get_collection(COLECCION).metadata
    except Exception:
        sys.exit("No existe el índice. Ejecuta primero: python indexar.py")

    almacen = Chroma(
        client=cliente,
        collection_name=COLECCION,
        embedding_function=crear_embeddings(metadatos["proveedor"], metadatos["modelo"]),
    )
    resultados = almacen.similarity_search_with_score(pregunta, k=k)
    return [
        {"texto": doc.page_content, "distancia": round(distancia, 4), **doc.metadata}
        for doc, distancia in resultados
    ]


def main():
    consola_utf8()
    load_dotenv(RAIZ / ".env")

    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--probar", metavar="PREGUNTA", help="prueba la recuperación")
    pregunta = argumentos.parse_args().probar

    if pregunta is None:
        indexar()
        return

    for i, r in enumerate(buscar(pregunta), start=1):
        print(f"--- {i}. {r['categoria']} | distancia {r['distancia']} | {r['fecha']}")
        print(f"Fuente: {r['fuente']}\n{r['texto']}\n")


if __name__ == "__main__":
    main()
