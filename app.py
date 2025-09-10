# app.py
# ============================================
# Organizador de Escapadas IA (Streamlit)
# SOLO GEMINI (REST) para IMÁGENES + OpenAI para TEXTO
# Basado en tu script original (minimos cambios para UI)
# ============================================

import os, json, base64, requests
from datetime import datetime, date, time as time_cls
from io import BytesIO

import streamlit as st
from PIL import Image
from dotenv import load_dotenv
from openai import OpenAI

# =======================
# Configuración página
# =======================
st.set_page_config(page_title="Organizador de Escapadas IA", page_icon="🧭", layout="wide")

# =======================
# Utilidades de claves
# =======================
def get_secret(key: str, default: str | None = None):
    # Prioriza st.secrets si existe, luego variables de entorno (.env)
    try:
        if "secrets" in dir(st) and key in st.secrets:
            return st.secrets.get(key, default)
    except Exception:
        pass
    return os.getenv(key, default)

# =======================
# Estado global (costos)
# =======================
if "acumulado_tokens" not in st.session_state:
    st.session_state.acumulado_tokens = 0
if "acumulado_usd" not in st.session_state:
    st.session_state.acumulado_usd = 0.0
if "logs_costos" not in st.session_state:
    st.session_state.logs_costos = []

# =======================
# Configuración API
# =======================
load_dotenv()

OPENAI_API_KEY = get_secret("OPENAI_API_KEY")
GOOGLE_API_KEY = get_secret("GOOGLE_API_KEY")

if not OPENAI_API_KEY:
    st.error("Falta **OPENAI_API_KEY**. Definilo en `.env` o en `st.secrets` para continuar.")
    st.stop()
if not GOOGLE_API_KEY:
    st.error("Falta **GOOGLE_API_KEY** (requerido para imágenes Gemini). Definilo en `.env` o en `st.secrets`.")
    st.stop()

openai_client = OpenAI(api_key=OPENAI_API_KEY)
MODEL_IMG = get_secret("MODEL_IMG", "gemini-2.5-flash-image-preview")  # mismo default que tu código

# =======================
# Helpers
# =======================
def safe_json_parse(raw_text: str):
    cleaned = (raw_text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "").replace("json", "", 1).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        return {}

def _log_costo(linea: str):
    st.session_state.logs_costos.append(linea)

def calcular_costo(response, nombre="Prompt"):
    if not hasattr(response, "usage") or response.usage is None:
        return
    in_tokens = getattr(response.usage, "prompt_tokens", 0)
    out_tokens = getattr(response.usage, "completion_tokens", 0)
    total_tokens = getattr(response.usage, "total_tokens", in_tokens + out_tokens)

    # Mantengo tus tarifas unitarias
    in_price = in_tokens * 0.00000015
    out_price = out_tokens * 0.0000006
    costo_total = in_price + out_price

    st.session_state.acumulado_tokens += total_tokens
    st.session_state.acumulado_usd += costo_total
    _log_costo(f"{nombre} → Tokens usados: {total_tokens}, USD {costo_total:.6f}")

def calcular_costo_imagen(nombre="Imagen", costo_usd=0.039):
    # Mantengo la función y permitir override por compatibilidad
    st.session_state.acumulado_usd += costo_usd
    _log_costo(f"{nombre} → Costo imagen: USD {costo_usd:.6f}")

def guardar_resumen_tokens() -> str:
    # Devuelve el contenido de resumen para descarga
    lines = []
    lines.extend(st.session_state.logs_costos)
    lines.append("\n=== RESUMEN TOTAL ===")
    lines.append(f"Tokens totales consumidos: {st.session_state.acumulado_tokens}")
    lines.append(f"Costo total estimado: USD {st.session_state.acumulado_usd:.6f}")
    return "\n".join(lines)

def _extraer_b64_de_respuesta(data: dict) -> str:
    """
    Estructura oficial: candidates[0].content.parts[].inline_data.data (base64)
    + Fallbacks por cambios menores de esquema.
    """
    try:
        for cand in data.get("candidates", []):
            content = cand.get("content", {})
            for part in content.get("parts", []):
                inline = part.get("inline_data") or part.get("inlineData")
                if isinstance(inline, dict) and "data" in inline:
                    return inline["data"]
            # Fallbacks opcionales
            if "image" in cand and isinstance(cand["image"], dict) and "bytesBase64" in cand["image"]:
                return cand["image"]["bytesBase64"]
            for m in cand.get("media", []):
                if isinstance(m, dict):
                    if "data" in m: return m["data"]
                    if "bytesBase64" in m: return m["bytesBase64"]
    except Exception:
        pass
    return ""

def generar_imagen_gemini(prompt: str, model_img: str, nombre_salida: str, costo_estimado=0.00) -> tuple[bytes | None, dict]:
    """
    Llama a Gemini REST y devuelve (bytes_png, raw_json_respuesta)
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_img}:generateContent"
    headers = {"x-goog-api-key": GOOGLE_API_KEY, "Content-Type": "application/json"}
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    r = requests.post(url, headers=headers, json=body, timeout=120)
    try:
        r.raise_for_status()
    except Exception:
        # Trata de leer json del error
        try:
            return None, r.json()
        except Exception:
            return None, {"error_text": r.text}

    data = r.json()
    b64_img = _extraer_b64_de_respuesta(data)
    if not b64_img:
        return None, data

    img_bytes = base64.b64decode(b64_img)
    # Guardar en archivo por compatibilidad con tu flujo
    try:
        with open(nombre_salida, "wb") as f:
            f.write(img_bytes)
    except Exception:
        pass
    # Costos (mantengo tu preferencia por costo 0.00 si querés)
    calcular_costo_imagen(f"Imagen {nombre_salida} (Gemini)", costo_usd=costo_estimado)
    return img_bytes, data

# =======================
# Encabezado
# =======================
st.title("🧭 Organizador de Escapadas IA")
st.caption("Texto con OpenAI · Imágenes con Gemini (REST)")

# =======================
# Sidebar (config avanzada)
# =======================
with st.sidebar:
    st.header("⚙️ Configuración")
    model_text = st.text_input("Modelo de texto (OpenAI):", value="gpt-4o-mini")
    model_img = st.text_input("Modelo de imagen (Gemini):", value=MODEL_IMG, help="Ej: gemini-2.5-flash-image-preview o imagen-3.0-generate-001")
    costo_img = st.number_input("Costo estimado por imagen (USD)", min_value=0.00, max_value=1.0, step=0.001, value=0.00, help="Mantengo 0.00 como en tu script. Cambiá si querés estimar costo real.")
    if st.button("♻️ Reiniciar contadores de costo"):
        st.session_state.acumulado_tokens = 0
        st.session_state.acumulado_usd = 0.0
        st.session_state.logs_costos = []
        st.success("Contadores reiniciados.")

# =======================
# Formulario de entrada
# =======================
st.subheader("🧾 Datos del viaje")

transportes_map = {1: "auto", 2: "micro", 3: "avión", 4: "tren"}
presupuestos_map = {1: "bajo", 2: "medio", 3: "medio-alto", 4: "alto"}
modos_map = {
    1: ("Exprímelo", "Aprovechar al máximo cada hora."),
    2: ("Relax", "Ritmo tranquilo, descansos largos."),
    3: ("Cultural", "Museos, historia, arquitectura."),
    4: ("Gastronómico", "Comidas y vinos locales."),
    5: ("Aventura", "Deportes y excursiones."),
    6: ("Familiar", "Opciones aptas para todas las edades.")
}

today = date.today()
default_start = today
default_end = date.fromordinal(today.toordinal() + 3)

with st.form("form_viaje"):
    destino = st.text_input("Destino del viaje (texto libre):", value="Mendoza")

    col1, col2, col3 = st.columns(3)
    with col1:
        transporte_idx = st.selectbox("Medio de transporte:", options=list(transportes_map.keys()),
                                      format_func=lambda k: transportes_map[k].capitalize(), index=2)
    with col2:
        cant_personas = st.number_input("Cantidad de personas:", min_value=1, value=2, step=1)
    with col3:
        temporada = st.radio("Temporada:", options=["alta", "baja"], horizontal=True, index=0)

    col4, col5 = st.columns(2)
    with col4:
        fecha_inicio_date = st.date_input("Fecha de inicio:", value=default_start, format="DD/MM/YYYY")
        hora_llegada_time = st.time_input("Hora de llegada:", value=time_cls(10, 0), step=300)
    with col5:
        fecha_regreso_date = st.date_input("Fecha de regreso:", value=default_end, format="DD/MM/YYYY")
        hora_regreso_time = st.time_input("Hora de regreso:", value=time_cls(22, 0), step=300)

    col6, col7 = st.columns(2)
    with col6:
        presupuesto_idx = st.selectbox(
            "Nivel de presupuesto:",
            options=list(presupuestos_map.keys()),
            format_func=lambda k: {
                1: "Bajo → Económico, transporte público, hostels.",
                2: "Medio → Balance costo/comodidad.",
                3: "Medio-alto → Hoteles 3-4⭐, experiencias destacadas.",
                4: "Alto → Lujo, experiencias premium."
            }[k],
            index=2
        )
    with col7:
        modo_idx = st.selectbox(
            "Modo de viaje:",
            options=list(modos_map.keys()),
            format_func=lambda k: f"{modos_map[k][0]} → {modos_map[k][1]}",
            index=1
        )

    ninos_menores_12 = False
    if modos_map[modo_idx][0] == "Familiar":
        ninos_menores_12 = st.radio("¿Hay niños menores de 12 años?", options=[True, False],
                                    format_func=lambda b: "Sí" if b else "No", horizontal=True, index=0)

    submitted = st.form_submit_button("🚀 Generar itinerario, QA e imágenes")

# =======================
# Validación y ejecución
# =======================
if submitted:
    # Normalizo strings requeridos por tu prompt
    transporte = transportes_map[transporte_idx]
    presupuesto = presupuestos_map[presupuesto_idx]
    modo_viaje = modos_map[modo_idx][0]

    # Formatos de fecha/hora como en tu script
    fecha_inicio = fecha_inicio_date.strftime("%d/%m/%Y")
    hora_llegada = hora_llegada_time.strftime("%H:%M")
    fecha_regreso = fecha_regreso_date.strftime("%d/%m/%Y")
    hora_regreso = hora_regreso_time.strftime("%H:%M")

    dt_inicio = datetime.strptime(f"{fecha_inicio} {hora_llegada}", "%d/%m/%Y %H:%M")
    dt_regreso = datetime.strptime(f"{fecha_regreso} {hora_regreso}", "%d/%m/%Y %H:%M")
    if dt_regreso <= dt_inicio:
        st.error("La fecha/hora de regreso debe ser posterior a la de inicio.")
        st.stop()

    cant_dias = (dt_regreso.date() - dt_inicio.date()).days + 1
    if cant_dias < 1:
        st.error("La fecha de regreso debe ser posterior a la fecha de inicio.")
        st.stop()

    # Resumen
    with st.expander("📌 Resumen de tu viaje", expanded=True):
        st.write(f"**Destino:** {destino}")
        st.write(f"**Transporte:** {transporte}")
        st.write(f"**Duración:** {cant_dias} días, para {cant_personas} personas")
        st.write(f"**Llegada:** {fecha_inicio} {hora_llegada} — **Regreso:** {fecha_regreso} {hora_regreso}")
        st.write(f"**Presupuesto:** {presupuesto}")
        st.write(f"**Modo:** {modo_viaje}")
        if modo_viaje == "Familiar":
            st.write(f"**¿Niños < 12?:** {'Sí' if ninos_menores_12 else 'No'}")
        st.write(f"**Temporada:** {temporada.upper()}")

    # =======================
    # Prompt A — Intake JSON (OpenAI TEXTO)
    # =======================
    intake_prompt = f"""
Sos un organizador de viajes.
Devolvé SOLO un JSON válido.

JSON esperado:
{{
  "param": {{
    "dest": "{destino}",
    "transporte": "{transporte}",
    "dias": {cant_dias},
    "pers": {cant_personas},
    "presupuesto": "{presupuesto}",
    "modo": "{modo_viaje}",
    "fecha_inicio": "{fecha_inicio}",
    "hora_llegada": "{hora_llegada}",
    "fecha_regreso": "{fecha_regreso}",
    "hora_regreso": "{hora_regreso}",
    "ninos_menores_12": {str(ninos_menores_12).lower()},
    "temporada": "{temporada}"
  }}
}}
"""
    with st.spinner("🧩 Generando Intake JSON..."):
        intake_response = openai_client.chat.completions.create(
            model=model_text,
            messages=[
                {"role": "system", "content": "Respondé SOLO con JSON válido y breve."},
                {"role": "user", "content": intake_prompt}
            ],
            temperature=0.2
        )
        calcular_costo(intake_response, "Prompt A - Intake")
        raw_intake = intake_response.choices[0].message.content
        intake_json = safe_json_parse(raw_intake)
    st.subheader("Intake JSON")
    st.json(intake_json)

    # =======================
    # Itinerario (OpenAI TEXTO)
    # =======================
    itinerario_prompt = f"""
Usá este JSON:

{json.dumps(intake_json, indent=2, ensure_ascii=False)}

Generá un itinerario detallado de {cant_dias} días para {destino}.

Formato:
Día N - Zona
09:00-11:00 Actividad
[Si corresponde: (traslado: XX min medio)]
11:15-13:00 Actividad
[Si corresponde: (traslado: XX min medio)]
13:15-14:30 Almuerzo (2 opciones)
[Si corresponde: (traslado: XX min medio)]
15:00-17:00 Actividad
[Si corresponde: (traslado: XX min medio)]
17:15-19:00 Actividad
20:00 Cena (2 opciones)

Reglas:
- Todas las actividades, lugares y atracciones deben estar ubicados principalmente dentro del destino {destino} y su área de influencia inmediata. Solo se permiten sugerencias de ciudades o regiones cercanas si están a una distancia razonable para una excursión de un día (aprox. 100–150 km o menos de 2 horas de viaje).
No incluyas propuestas que requieran grandes traslados fuera de la provincia/país, salvo en destinos de frontera donde sea natural cruzar (ejemplo: Cataratas del Iguazú → Brasil, Mendoza → cordillera de Chile).
Si no hay suficientes opciones locales, ampliá la variedad dentro del mismo destino en lugar de traer actividades de regiones lejanas.
- Mostrá tiempos de traslado SOLO cuando cambie el lugar de la actividad.
- No repitas traslado si la siguiente actividad ocurre en el mismo sitio.
- Si el modo de viaje es "Familiar" y hay niños menores de 12 años:
  - Incluí actividades adaptadas y marcá con 👶.
  - Si alguna actividad no es apta para menores o es muy exigente, marcala con ⚠️ y proponé una "Actividad alternativa" en ese mismo día y horario.
- Considerá la temporada:
  - Si es ALTA → recomendá reservas anticipadas, horarios tempranos y opciones alternativas por alta demanda.
  - Si es BAJA → advertí sobre posibles cierres o menor disponibilidad de actividades.
- Al final de cada día, incluir un breve resumen con tips.
"""
    with st.spinner("🗺️ Generando Itinerario..."):
        itinerario_response = openai_client.chat.completions.create(
            model=model_text,
            messages=[
                {"role": "system", "content": "Devolvé solo itinerario en texto limpio."},
                {"role": "user", "content": itinerario_prompt}
            ],
            temperature=0.4
        )
        calcular_costo(itinerario_response, "Prompt A - Itinerario")
        itinerario = itinerario_response.choices[0].message.content

    st.subheader("Itinerario generado")
    st.text(itinerario)
    st.download_button("💾 Descargar itinerario (TXT)", data=itinerario.encode("utf-8"),
                       file_name="itinerario_final.txt", mime="text/plain")

    # =======================
    # QA — Auditoría (OpenAI TEXTO)
    # =======================
    qa_prompt = f"""
Revisá el siguiente itinerario y generá un JSON con advertencias relevantes agrupadas por día.

Itinerario:
{itinerario}

Devolvé SOLO un JSON con este formato:
{{
  "alertas": {{
    "Día 2": [
      "Actividad X puede no ser apta para niños",
      "Traslado mayor a 60 minutos"
    ],
    "Día 5": [
      "Actividad Y puede ser excesiva"
    ]
  }}
}}

Reglas:
- Agrupá todas las advertencias bajo el día correspondiente.
- Marcá traslados mayores a 60 minutos.
- Detectá jornadas con exceso de actividades según el modo elegido.
- Señalá actividades no aptas para niños si hay menores de 12 años.
- Si la temporada es "alta" → incluir advertencia de "Reserva anticipada".
- Si la temporada es "baja" → incluir advertencia de "Atracciones cerradas por estacionalidad".
- No incluyas advertencias de temporada que no correspondan.
- Si no hay alertas para un día, no incluyas ese día en el JSON.
"""
    with st.spinner("🔎 Auditando Itinerario..."):
        qa_response = openai_client.chat.completions.create(
            model=model_text,
            messages=[
                {"role": "system", "content": "Actuá como auditor de itinerarios. Respondé SOLO con JSON válido."},
                {"role": "user", "content": qa_prompt}
            ],
            temperature=0.2
        )
        calcular_costo(qa_response, "Prompt QA - Auditoría")
        qa_json = safe_json_parse(qa_response.choices[0].message.content)

    st.subheader("QA del itinerario")
    if qa_json.get("alertas"):
        for dia, alertas in qa_json["alertas"].items():
            with st.expander(f"📅 {dia}", expanded=False):
                for alerta in alertas:
                    icono = "⚠️"
                    al = alerta.lower()
                    if "niños" in al: icono = "👶"
                    elif "traslado" in al: icono = "🕒"
                    elif "reserva" in al or "temporada" in al: icono = "📅"
                    st.write(f"{icono} {alerta}")
    else:
        st.info("Sin advertencias relevantes detectadas.")

    # =======================
    # Extracción de lugares (desde itinerario)
    # =======================
    lugares = []
    palabras_clave = [
        "hotel","restaurante","bodega","actividad","excursión","remis","taxi",
        "auto de alquiler","transfer","museo","café","bar","parque","mercado",
        "zoológico","plaza","mirador","sendero","playa","río","laguna","reserva","centro"
    ]
    for line in itinerario.splitlines():
        texto = line.strip()
        if not texto:
            continue
        if any(palabra in texto.lower() for palabra in palabras_clave):
            lugares.append(texto)
        elif any(w.istitle() for w in texto.split()):
            lugares.append(texto)

    st.subheader("Lugares y servicios detectados")
    st.write(lugares if lugares else "—")
    st.download_button("💾 Descargar lugares (JSON)",
                       data=json.dumps(lugares, indent=2, ensure_ascii=False).encode("utf-8"),
                       file_name="lugares.json", mime="application/json")

    # =======================
    # Contactos simulados (OpenAI TEXTO)
    # =======================
    prompt_contactos = f"""
A partir de esta lista de lugares:

{json.dumps(lugares, indent=2, ensure_ascii=False)}

Simulá datos de contacto realistas.

Devolvé SOLO un JSON con:
[
  {{
    "nombre": "...",
    "tipo": "hotel | restaurante | bodega | actividad | excursión | transporte | museo | parque | café",
    "web": "...",
    "telefono": "...",
    "email": "..."
  }}
]
"""
    with st.spinner("📇 Generando contactos simulados..."):
        contactos_response = openai_client.chat.completions.create(
            model=model_text,
            messages=[
                {"role": "system", "content": "Respondé SOLO con JSON válido."},
                {"role": "user", "content": prompt_contactos}
            ],
            temperature=0.4
        )
        calcular_costo(contactos_response, "Prompt C - Contactos")
        contactos_json = safe_json_parse(contactos_response.choices[0].message.content)

    st.subheader("Lugares/Servicios con datos de contacto simulados")
    if isinstance(contactos_json, list) and len(contactos_json) > 0:
        try:
            import pandas as pd
            df = pd.DataFrame(contactos_json)
            st.dataframe(df, use_container_width=True)
        except Exception:
            st.json(contactos_json)
    else:
        st.info("No se generaron contactos.")

    st.download_button("💾 Descargar contactos (JSON)",
                       data=json.dumps(contactos_json, indent=2, ensure_ascii=False).encode("utf-8"),
                       file_name="contactos.json", mime="application/json")

    # =======================
    # Preparar puntos clave → prompts de imágenes
    # =======================
    puntos = []
    for line in itinerario.splitlines():
        if any(k in line.lower() for k in ["actividad","almuerzo","cena","tour","visita","excursión","paseo","mirador","sendero","reserva","playa","ballena","pingüino","ave"]):
            puntos.append(line.strip())
    puntos_unicos = []
    for p in puntos:
        if p not in puntos_unicos:
            puntos_unicos.append(p)
    lista_puntos = " | ".join(puntos_unicos[:8])  # limitar como tu script

    prompts_img = {
        "Mapa": f"""
Crear una ilustración 16:9 tipo mapa turístico vintage de {destino}, basada en el itinerario.
Paleta cálida (beige, terracota, verdes suaves), textura de papel envejecido.
Contorno simple/esquema del área y 4–6 mini-escenas derivadas de:
{lista_puntos}
Ilustración limpia, sin texto ni marcas de agua. Exportar PNG.
""",
        "Flyer": f"""
Crear un póster 16:9 estilo travel-poster de {destino}.
Motivos icónicos del lugar {destino}.
Exportar PNG.
Colores vibrantes y contraste claro. Sin marcas de agua.
"""
    }

    with st.expander("🖼️ Prompts de imagen generados"):
        st.code(prompts_img["Mapa"].strip(), language="markdown")
        st.code(prompts_img["Flyer"].strip(), language="markdown")

    # =======================
    # GEMINI REST — Generación de imágenes
    # =======================
    st.subheader("Imágenes (Gemini REST)")
    cols = st.columns(2)

    with st.spinner("🗺️ Generando Mapa con Gemini..."):
        nombre_mapa = f"{destino.replace(' ','_').lower()}_mapa.png"
        bytes_mapa, raw_mapa = generar_imagen_gemini(prompts_img["Mapa"], model_img, nombre_mapa, costo_estimado=costo_img)

    with cols[0]:
        if bytes_mapa:
            st.image(bytes_mapa, caption=nombre_mapa, use_container_width=True)
            st.download_button("💾 Descargar mapa (PNG)", data=bytes_mapa, file_name=nombre_mapa, mime="image/png")
        else:
            st.warning("No se detectó imagen en la respuesta del modelo para el **Mapa**.")
            with st.expander("Ver respuesta cruda (Mapa)"):
                st.json(raw_mapa)

    with st.spinner("🎫 Generando Flyer con Gemini..."):
        nombre_flyer = f"{destino.replace(' ','_').lower()}_flyer.png"
        bytes_flyer, raw_flyer = generar_imagen_gemini(prompts_img["Flyer"], model_img, nombre_flyer, costo_estimado=costo_img)

    with cols[1]:
        if bytes_flyer:
            st.image(bytes_flyer, caption=nombre_flyer, use_container_width=True)
            st.download_button("💾 Descargar flyer (PNG)", data=bytes_flyer, file_name=nombre_flyer, mime="image/png")
        else:
            st.warning("No se detectó imagen en la respuesta del modelo para el **Flyer**.")
            with st.expander("Ver respuesta cruda (Flyer)"):
                st.json(raw_flyer)

    # =======================
    # Costos totales
    # =======================
    st.subheader("💸 Costos estimados")
    resumen = guardar_resumen_tokens()
    st.text(resumen)
    st.download_button("💾 Descargar costos_totales.txt", data=resumen.encode("utf-8"),
                       file_name="costos_totales.txt", mime="text/plain")

# Fin
