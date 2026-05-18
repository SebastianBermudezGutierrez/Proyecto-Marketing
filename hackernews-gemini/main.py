import os
import json
import requests
import datetime
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


GEMINI_API_KEY = "AIzaSyB4zfFU2UuP2ZrfCZHvbW5Yc0yltjv5Ofk"

# Scopes necesarios para Google Docs y Drive
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file"
]

# Número de artículos a obtener
NUM_ARTICULOS = 30


# ============================================================
# PASO 1: Autenticación con Google
# ============================================================
def autenticar_google():
    """Autentica con Google y retorna las credenciales OAuth2."""
    creds = None

    # Reutiliza token guardado si existe
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # Si no hay credenciales válidas, solicita login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Guarda el token para la próxima vez
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    print("✅ Autenticación con Google exitosa.")
    return creds


# ============================================================
# PASO 2: Obtener artículos de HackerNews
# ============================================================
def obtener_articulos_hackernews(cantidad=NUM_ARTICULOS):
    """Obtiene los artículos más populares del día desde la API de HackerNews."""
    print(f"\n📡 Obteniendo los {cantidad} artículos más populares de HackerNews...")

    # Endpoint de las historias más populares
    url_top = "https://hacker-news.firebaseio.com/v0/topstories.json"
    respuesta = requests.get(url_top)
    ids_top = respuesta.json()[:cantidad]

    articulos = []
    for i, story_id in enumerate(ids_top):
        url_item = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
        item = requests.get(url_item).json()

        if item and item.get("type") == "story":
            articulos.append({
                "id": story_id,
                "titulo": item.get("title", "Sin título"),
                "url": item.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                "puntuacion": item.get("score", 0),
                "autor": item.get("by", "desconocido"),
                "comentarios": item.get("descendants", 0)
            })
            print(f"  [{i+1}/{cantidad}] {item.get('title', 'Sin título')[:60]}...")

    print(f"✅ {len(articulos)} artículos obtenidos.")
    return articulos


# ============================================================
# PASO 3: Procesar artículos con Gemini 2.0 Flash
# ============================================================
def procesar_con_gemini(articulos):
    """Usa Gemini 2.0 Flash para generar resúmenes y categorías de cada artículo."""
    print("\n🤖 Procesando artículos con Gemini 2.0 Flash...")

    genai.configure(api_key=GEMINI_API_KEY)
    modelo = genai.GenerativeModel("gemini-2.0-flash")

    articulos_procesados = []

    for i, articulo in enumerate(articulos):
        prompt = f"""Eres un asistente que analiza noticias tecnológicas.
        
Dado el siguiente título de artículo de HackerNews:
Título: "{articulo['titulo']}"
URL: {articulo['url']}

Responde ÚNICAMENTE en formato JSON con esta estructura exacta:
{{
  "resumen": "Un resumen conciso de 2-3 oraciones sobre de qué trata este artículo basándote en el título",
  "categoria": "Una de estas categorías: Inteligencia Artificial, Programación, Startups, Seguridad, Hardware, Ciencia, Negocios, Open Source, Web, Otros"
}}"""

        try:
            respuesta = modelo.generate_content(prompt)
            texto = respuesta.text.strip()

            # Limpiar posibles bloques de código markdown
            if texto.startswith("```"):
                texto = texto.split("```")[1]
                if texto.startswith("json"):
                    texto = texto[4:]
            texto = texto.strip()

            datos = json.loads(texto)
            articulo["resumen"] = datos.get("resumen", "Resumen no disponible.")
            articulo["categoria"] = datos.get("categoria", "Otros")

        except Exception as e:
            print(f"  ⚠️  Error procesando artículo {i+1}: {e}")
            articulo["resumen"] = "Resumen no disponible."
            articulo["categoria"] = "Otros"

        print(f"  [{i+1}/{len(articulos)}] ✓ {articulo['titulo'][:50]}... → {articulo['categoria']}")
        articulos_procesados.append(articulo)

    print("✅ Procesamiento con Gemini completado.")
    return articulos_procesados


# ============================================================
# PASO 4: Exportar a Google Docs
# ============================================================
def exportar_a_google_docs(articulos, creds):
    """Crea un documento en Google Docs con los artículos procesados."""
    print("\n📄 Exportando reporte a Google Docs...")

    docs_service = build("docs", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)

    # Fecha actual para el título del documento
    fecha = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    titulo_doc = f"HackerNews Top {NUM_ARTICULOS} - {datetime.datetime.now().strftime('%d-%m-%Y')}"

    # Crear el documento vacío
    documento = docs_service.documents().create(body={"title": titulo_doc}).execute()
    doc_id = documento["documentId"]

    # Construir el contenido del documento
    requests_body = []

    # Contenido completo como texto plano primero (se inserta al final y se formatea)
    contenido_completo = ""

    # Encabezado principal
    encabezado = (
        f"REPORTE DE NOTICIAS TECNOLÓGICAS - HACKERNEWS\n"
        f"Generado el: {fecha}\n"
        f"Total de artículos: {len(articulos)}\n"
        f"Procesado con: Gemini 2.0 Flash\n\n"
    )
    contenido_completo += encabezado

    # Agrupar por categoría
    categorias = {}
    for art in articulos:
        cat = art.get("categoria", "Otros")
        if cat not in categorias:
            categorias[cat] = []
        categorias[cat].append(art)

    # Resumen por categorías
    contenido_completo += "RESUMEN POR CATEGORÍAS\n"
    for cat, arts in sorted(categorias.items()):
        contenido_completo += f"  • {cat}: {len(arts)} artículos\n"
    contenido_completo += "\n"

    # Artículos detallados
    contenido_completo += "=" * 60 + "\n"
    contenido_completo += "ARTÍCULOS DETALLADOS\n"
    contenido_completo += "=" * 60 + "\n\n"

    for i, art in enumerate(articulos, 1):
        bloque = (
            f"{i}. {art['titulo']}\n"
            f"   Categoría:  {art.get('categoria', 'Otros')}\n"
            f"   Puntuación: {art['puntuacion']} puntos | "
            f"Comentarios: {art['comentarios']}\n"
            f"   Resumen:    {art.get('resumen', 'No disponible')}\n"
            f"   Enlace:     {art['url']}\n\n"
        )
        contenido_completo += bloque

    # Insertar todo el texto en el documento
    requests_body.append({
        "insertText": {
            "location": {"index": 1},
            "text": contenido_completo
        }
    })

    # Formatear el título principal (negrita, tamaño grande)
    largo_titulo = len("REPORTE DE NOTICIAS TECNOLÓGICAS - HACKERNEWS\n")
    requests_body.append({
        "updateTextStyle": {
            "range": {"startIndex": 1, "endIndex": largo_titulo},
            "textStyle": {"bold": True, "fontSize": {"magnitude": 16, "unit": "PT"}},
            "fields": "bold,fontSize"
        }
    })

    # Ejecutar todas las actualizaciones
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": requests_body}
    ).execute()

    # Hacer el documento accesible con enlace
    drive_service.permissions().create(
        fileId=doc_id,
        body={"role": "reader", "type": "anyone"}
    ).execute()

    url_doc = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"✅ Documento creado exitosamente.")
    print(f"🔗 Enlace: {url_doc}")
    return url_doc


# ============================================================
# EJECUCIÓN PRINCIPAL
# ============================================================
def main():
    print("=" * 60)
    print("  HackerNews → Gemini 2.0 Flash → Google Docs")
    print("  Proyecto de Aula - CORHUILA - Ing. de Sistemas")
    print("=" * 60)

    # 1. Autenticar con Google
    creds = autenticar_google()

    # 2. Obtener artículos de HackerNews
    articulos = obtener_articulos_hackernews(NUM_ARTICULOS)

    # 3. Procesar con Gemini
    articulos_procesados = procesar_con_gemini(articulos)

    # 4. Exportar a Google Docs
    url = exportar_a_google_docs(articulos_procesados, creds)

    print("\n" + "=" * 60)
    print("✅ PROCESO COMPLETADO")
    print(f"📄 Documento disponible en:\n   {url}")
    print("=" * 60)


if __name__ == "__main__":
    main()
