# Proyecto: Chatbot de atención al cliente (proyecto académico, inspirado en Pardos Chicken)

## Contexto
Proyecto final del curso "Diseño y Desarrollo de Chatbot". Equipo de 3-4 personas.

## Objetivo
Chatbot con IA generativa y RAG que responda en español peruano consultas frecuentes
(carta, promociones, locales, horarios, delivery, medios de pago, reclamos) y recomiende
platos según número de personas y presupuesto. No procesa pedidos ni pagos: deriva a
los canales oficiales cuando no tiene la información.

## Stack
- Python, Streamlit (interfaz web pensada para celular)
- Modelo: Gemini API con gemini-3.5-flash-lite (obligatorio, plan gratuito), con un modelo
  alterno de respaldo. Embeddings: gemini-embedding-001
- RAG: LangChain + ChromaDB (FAISS como contingencia)
- Despliegue: Streamlit Community Cloud (Render como contingencia)

## Requisitos del curso
- Conversación de varios turnos con memoria de contexto
- Flujo ideal y flujo alterno (fuera de alcance, ambigüedad, queja, sin información)
- Manejo de entradas/salidas y de errores
- Evidencias de pruebas (casos esperado vs. obtenido), medir calidad, alucinaciones y latencia

## Reglas
- El contenido de la base de conocimiento se extrae una sola vez con Playwright desde
  páginas públicas, respetando robots.txt y con pausas. Guardar fuente y fecha.
- Claves de API en variables de entorno o st.secrets, nunca en el código.
- Responder solo con el contexto recuperado; si no hay datos, decirlo y derivar.

## Estructura prevista
app.py (interfaz), rag.py (recuperación), prompts.py, comun.py (utilidades del
pipeline), descubrir.py, extraer.py, extraer_detalle.py, limpiar.py, generar_carta.py,
indexar.py, data/ (contenido en .md), assets/ (imagen de la carta), tests/ (casos de prueba)

## Equipo y roles
- Jefe de proyecto: Omar
- Ingeniero IA/ML: Giovanni
- Ingeniero Front-end: Giovanni
- QA / Tester: Omar Martin
- Documentación: Omar

## Cronograma
- Semana 1: propuesta de proyecto
- Semana 2: diseño del sistema (persona, flujos, arquitectura, mockup, evaluación, ética)
- Semana 3: prototipo funcional con conversación multi-turno y despliegue básico
- Semana 4: evaluación, mejoras y presentación final de 10 minutos
