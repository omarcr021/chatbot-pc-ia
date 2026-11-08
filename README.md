# chatbot-pc-ia
Trabajo Final de IA: chatbot de atención al cliente con RAG, inspirado en Pardos Chicken.
Proyecto académico; no es el canal oficial.

## Ejecutar en local

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

Copia `.env.example` como `.env`, agrega tu `GOOGLE_API_KEY` y ejecuta:

```bash
.venv/Scripts/python -m streamlit run app.py
```

## Desplegar en Streamlit Community Cloud

El índice `chroma_db/` va en el repositorio, así que la app desplegada no recalcula
vectores. Solo consume la API al responder: un embedding por consulta y la generación.

1. Entra a https://share.streamlit.io con tu cuenta de GitHub.
2. **Create app** → **Deploy a public app from GitHub**:
   - Repository: `omarcr021/chatbot-pc-ia`
   - Branch: `main`
   - Main file path: `app.py`
3. En **Advanced settings**:
   - Python version: **3.13**
   - Secrets:
     ```toml
     GOOGLE_API_KEY = "tu-clave"
     ```
     Opcional: `GEMINI_MODEL` y `GEMINI_MODEL_RESPALDO` para cambiar de modelo.
4. **Deploy**. Cada push a `main` vuelve a desplegar la app.

Si cambias los datos de `data/`, reindexa en local y compacta antes del commit:

```bash
.venv/Scripts/python limpiar.py
.venv/Scripts/python indexar.py
.venv/Scripts/python indexar.py --compactar
```
