"""Recuperación y generación: recibe una pregunta y su historial, y devuelve la respuesta."""

import logging
import os
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from google import genai
from google.genai import errors, types

import prompts
from indexar import buscar, normalizar, pide_carta_completa  # también carga .env

log = logging.getLogger(__name__)

MODELO = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
MODELO_RESPALDO = os.environ.get("GEMINI_MODEL_RESPALDO", "gemini-3.5-flash")

MAX_PREGUNTA = 500
MENSAJES_EN_MEMORIA = 8
FRAGMENTOS = 6
FRAGMENTOS_PREGUNTA_ORIGINAL = 3  # extra, si la pregunta se reformuló
INTENTOS_POR_MODELO = 2
PAUSA_REINTENTO_S = 2
TIMEOUT_MS = 30_000

# La genera generar_carta.py; si no existe, el bot escribe la carta como texto.
RUTA_CARTA = Path(__file__).resolve().parent / "assets" / "carta.png"


@dataclass
class Respuesta:
    texto: str
    fuentes: list = field(default_factory=list)
    modelo: str = ""
    consulta: str = ""
    latencia_s: float = 0.0
    error: bool = False
    spam: bool = False
    imagen: str | None = None  # ruta de una imagen para mostrar junto a la respuesta


@lru_cache(maxsize=1)
def cliente():
    clave = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    return genai.Client(api_key=clave, http_options=types.HttpOptions(timeout=TIMEOUT_MS))


def es_temporal(error):
    """Saturación (5xx) o cuota (429): vale la pena reintentar o cambiar de modelo."""
    return isinstance(error, errors.ServerError) or getattr(error, "code", None) == 429


def generar(contenido, sistema=None):
    """Llama al modelo principal y, si está saturado, al de respaldo. Devuelve (texto, modelo)."""
    configuracion = types.GenerateContentConfig(system_instruction=sistema, temperature=0.2)
    ultimo_error = None
    for modelo in (MODELO, MODELO_RESPALDO):
        for intento in range(INTENTOS_POR_MODELO):
            if ultimo_error:
                time.sleep(PAUSA_REINTENTO_S)
            try:
                resultado = cliente().models.generate_content(
                    model=modelo, contents=contenido, config=configuracion
                )
            except errors.APIError as error:
                if not es_temporal(error):
                    raise
                log.warning("%s no disponible (intento %s): %s", modelo, intento + 1, error.code)
                ultimo_error = error
                continue
            if not resultado.text:
                raise RuntimeError(f"{modelo} devolvió una respuesta vacía")
            return resultado.text.strip(), modelo
    raise ultimo_error


def reformular(pregunta, historial):
    """Convierte "¿y en Surco?" en una pregunta completa para poder buscarla."""
    if not historial:
        return pregunta
    conversacion = "\n".join(
        f"{'Cliente' if m['role'] == 'user' else 'Asistente'}: {m['content']}" for m in historial
    )
    try:
        texto, _ = generar(prompts.REFORMULAR.format(conversacion=conversacion, pregunta=pregunta))
        return texto
    except Exception as error:
        log.warning("No se pudo reformular: %s", error)
        anteriores = [m["content"] for m in historial if m["role"] == "user"]
        return f"{anteriores[-1]} {pregunta}" if anteriores else pregunta


def spam_local(pregunta, historial):
    """Spam evidente que no necesita al modelo. Devuelve la respuesta fija, o None."""
    if not re.search(r"[^\W_]", pregunta):  # sin letras ni números: "!!!!", solo emojis
        return prompts.SPAM_SIN_TEXTO
    anteriores = [m["content"] for m in historial if m["role"] == "user"]
    if anteriores and normalizar(anteriores[-1]) == normalizar(pregunta):
        return prompts.SPAM_REPETIDO
    return None


def separar_marca_spam(texto):
    """Quita la marca que pone el modelo ante un insulto o provocación: (texto, es_spam)."""
    if prompts.MARCA_SPAM not in texto:
        return texto, False
    return texto.replace(prompts.MARCA_SPAM, "").strip(), True


def buscar_ambas(pregunta, consulta):
    """Busca con la pregunta reformulada y también con la original.

    La reformulada resuelve "¿y la dirección?"; la original protege de una reformulación
    que mezcle la pregunta con un tema anterior de la conversación.
    """
    fragmentos = buscar(consulta, k=FRAGMENTOS)
    if normalizar(consulta) == normalizar(pregunta):
        return fragmentos
    vistos = {f["texto"] for f in fragmentos}
    extra = [f for f in buscar(pregunta, k=FRAGMENTOS) if f["texto"] not in vistos]
    return fragmentos + extra[:FRAGMENTOS_PREGUNTA_ORIGINAL]


def imagen_de_carta(pregunta, consulta):
    """Ruta de la imagen de la carta si la piden y existe; si no, None."""
    if RUTA_CARTA.exists() and (pide_carta_completa(pregunta) or pide_carta_completa(consulta)):
        return str(RUTA_CARTA)
    return None


def armar_contexto(fragmentos):
    bloques = [f"[{f['categoria']}]\n{f['texto']}" for f in fragmentos]
    return "\n\n".join(bloques) or "(sin resultados)"


def armar_mensajes(pregunta, historial, contexto):
    mensajes = [
        types.Content(
            role="user" if m["role"] == "user" else "model",
            parts=[types.Part(text=m["content"])],
        )
        for m in historial
    ]
    texto = prompts.PLANTILLA_USUARIO.format(contexto=contexto, pregunta=pregunta)
    mensajes.append(types.Content(role="user", parts=[types.Part(text=texto)]))
    return mensajes


def responder(pregunta, historial=()):
    """Responde una pregunta. historial: lista de {"role": "user"|"assistant", "content": str}.

    Nunca lanza excepciones: si algo falla, devuelve un mensaje que deriva a los canales.
    """
    inicio = time.perf_counter()
    pregunta = (pregunta or "").strip()
    if not pregunta:
        return Respuesta(prompts.PREGUNTA_VACIA)
    if len(pregunta) > MAX_PREGUNTA:
        return Respuesta(prompts.PREGUNTA_LARGA.format(maximo=MAX_PREGUNTA))

    memoria = list(historial)[-MENSAJES_EN_MEMORIA:]
    respuesta_fija = spam_local(pregunta, memoria)
    if respuesta_fija:
        return Respuesta(respuesta_fija, latencia_s=time.perf_counter() - inicio, spam=True)

    try:
        consulta = reformular(pregunta, memoria)
        fragmentos = buscar_ambas(pregunta, consulta)
        log.info(
            "pregunta=%r consulta=%r categorias=%s",
            pregunta, consulta, [f["categoria"] for f in fragmentos],
        )
        imagen = imagen_de_carta(pregunta, consulta)
        pregunta_modelo = f"{pregunta}\n\n{prompts.NOTA_CARTA_ADJUNTA}" if imagen else pregunta
        mensajes = armar_mensajes(pregunta_modelo, memoria, armar_contexto(fragmentos))
        texto, modelo = generar(mensajes, sistema=prompts.SISTEMA)
        log.info("modelo=%s respuesta=%r", modelo, texto[:120])
    except (Exception, SystemExit) as error:  # buscar() usa sys.exit si no hay índice
        log.exception("Error al responder: %s", error)
        return Respuesta(
            prompts.SIN_SERVICIO, latencia_s=time.perf_counter() - inicio, error=True
        )

    texto, es_spam = separar_marca_spam(texto)
    return Respuesta(
        texto=texto,
        fuentes=list(dict.fromkeys(f["fuente"] for f in fragmentos)),
        modelo=modelo,
        consulta=consulta,
        latencia_s=time.perf_counter() - inicio,
        spam=es_spam,
        imagen=None if es_spam else imagen,
    )
