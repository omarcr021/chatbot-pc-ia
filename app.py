"""Interfaz del chatbot. Uso: streamlit run app.py"""

import logging
import os

import streamlit as st

# Muestra en el terminal qué buscó el bot y qué respondió, para diagnosticar respuestas.
logging.basicConfig(format="%(asctime)s %(name)s %(levelname)s %(message)s")
logging.getLogger("rag").setLevel(logging.INFO)

st.set_page_config(page_title="Asistente Pardos", page_icon="🍗", layout="centered")

# En Streamlit Cloud la configuración viene de st.secrets; en local, de .env.
# Se copia al entorno antes de importar rag, que la lee al cargarse.
try:
    for clave in ("GOOGLE_API_KEY", "GEMINI_MODEL", "GEMINI_MODEL_RESPALDO"):
        if clave in st.secrets:
            os.environ[clave] = str(st.secrets[clave])
except FileNotFoundError:
    pass

import prompts
from rag import responder

# Mensajes spam (insultos, provocaciones, sin sentido) que cierran la conversación.
MAX_SPAM = 3


def reiniciar():
    st.session_state.mensajes = []
    st.session_state.spam = 0
    st.session_state.cerrado = False


def texto_tras_spam(texto):
    """Suma un mensaje spam y devuelve lo que se muestra: con aviso o de cierre."""
    st.session_state.spam += 1
    if st.session_state.spam >= MAX_SPAM:
        st.session_state.cerrado = True
        return prompts.CHAT_CERRADO
    if st.session_state.spam == MAX_SPAM - 1:
        return f"{texto}\n\n_{prompts.AVISO_SPAM}_"
    return texto


def mostrar_imagen(ruta):
    if ruta:
        st.image(ruta, caption="Carta completa (toca la imagen para ampliarla)")


def agregar_respuesta(pregunta):
    """Muestra la pregunta, consulta al modelo y guarda ambos mensajes."""
    historial = [{"role": m["role"], "content": m["content"]} for m in st.session_state.mensajes]
    st.session_state.mensajes.append({"role": "user", "content": pregunta})
    with st.chat_message("user"):
        st.markdown(pregunta)

    with st.chat_message("assistant"):
        with st.spinner("Revisando la carta..."):
            respuesta = responder(pregunta, historial)
        texto = texto_tras_spam(respuesta.texto) if respuesta.spam else respuesta.texto
        st.markdown(texto)
        mostrar_imagen(respuesta.imagen)
    st.session_state.mensajes.append(
        {"role": "assistant", "content": texto, "imagen": respuesta.imagen}
    )


st.title("🍗 Asistente Pardos")
st.caption(
    "Mr. Pardos. Proyecto académico inspirado en Pardos Chicken; no es el canal oficial. "
    f"Pedidos y datos oficiales en {prompts.WEB}"
)

if "mensajes" not in st.session_state:
    reiniciar()

with st.chat_message("assistant"):
    st.markdown(prompts.BIENVENIDA)

for mensaje in st.session_state.mensajes:
    with st.chat_message(mensaje["role"]):
        st.markdown(mensaje["content"])
        mostrar_imagen(mensaje.get("imagen"))

sugerida = None
if not st.session_state.mensajes:
    for texto in prompts.SUGERENCIAS:
        if st.button(texto, width="stretch"):
            sugerida = texto

cerrado = st.session_state.cerrado
escrita = st.chat_input(
    "Chat cerrado" if cerrado else "Escribe tu consulta...", max_chars=500, disabled=cerrado
)
pregunta = escrita or sugerida
if pregunta and not cerrado:
    agregar_respuesta(pregunta)
    if sugerida or st.session_state.cerrado:
        st.rerun()  # oculta las sugerencias o desactiva el campo de texto

if st.session_state.mensajes and st.button("Nueva conversación"):
    reiniciar()
    st.rerun()
