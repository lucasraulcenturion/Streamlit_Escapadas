# app.py
# ============================================
# Organizador de Escapadas IA (Streamlit)
# Texto: OpenAI · Imágenes: Gemini (REST)
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
# Modelos preconfigurados (sin UI)
# =======================
MODEL_TEXT = "gpt-4o-mini"
MODEL_IMG  = "gemini-2.5-flash-image-preview"   # Cambiar aquí si querés forzar otro

# =======================
# Helpers de claves
# =======================
def get_secret(key: str, default: str | None = None):
    try:
        if "secrets" in dir(st) and key in st.secrets:
            return st.secrets.get(key, default)
    except Exception:
        pass
    return os.getenv(key, default)

# =======================
# Carga de entorno + clientes
# =======================
load_dotenv()
OPENAI_API_KEY = get_secret("OPENAI_API_KEY")
GOOGLE_API_KEY = get_secret("GOOGLE_API_KEY")

if not OPENAI_API_KEY:
    st.error("Falta **OPENAI_API_KEY**. Definilo en `.env` o en `st.secrets`.")
    st.stop()
if not GOOGLE_API_KEY:
    st.error("Falta **GOOGLE_API_KEY** (requerido para imágenes Gemini).")
    st.stop()

openai_client = OpenAI(api_key=OPENAI_API_KEY)

# =======================
# Utilidades
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

def _extraer_b64_de_respuesta(data: dict) -> str:
    """Busca la imagen base64 en la respuesta de Gemini."""
    try:
        for cand in data.get("candidates", []):
            content = cand.get("content", {})
            for part in content.get("parts", []):
                inline = part.get("inline_data") or part.get("inlineData")
                if isinstance(inline, dict) and "data" in inline:
                    return inline["data"]
            if "image" in cand and isinstance(cand["image"], dict) and "bytesBase64" in cand["image"]:
                return cand["image"]["bytesBase64"]
            for m in cand.get("media", []):
                if isinstance(m, dict):
                    if "data" in m: return m["data"]
                    if "bytesBase64" in m: return m["bytesBase64"]
    except Exception:
        pass
    return ""

def generar_imagen_gemini(prompt: str, model_img: str, nombre_salida: str) -> tuple[bytes | None, dict]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_img}:generateContent"
    headers = {"x-goog-api-key": GOOGLE_API_KEY, "Content-Type": "application/json"}
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    r = requests.post(url, headers=headers, json=body, timeout=120)
    try:
        r.raise_for_status()
    except Exception:
        try:
            return None, r.json()
        except Exception:
            return None, {"error_text": r.text}

    data = r.json()
    b64_img = _extraer_b64_de_respuesta(data)
    if not b64_img:
        return None, data

    img_bytes = base64.b64decode(b64_img)
    try:
        with open(nombre_salida, "wb") as f:
            f.write(img_bytes)
    except Exception:
        pass
    return img_bytes, data

def validar_fecha_ddmmyyyy(s: str) -> bool:
    try:
        datetime.strptime(s, "%d/%m/%Y"); return True
    except ValueError:
        return False

def validar_hora_hhmm(s: str) -> bool:
    try:
        datetime.strptime(s, "%H:%M"); return True
    except ValueError:
        return False

# =======================
# UI principal
# =======================
st.title("🧭 Organizador de Escapadas IA")
st.caption("Texto con OpenAI · Imágenes con Gemini (REST)")

transportes = ["auto", "micro", "avión", "tren"]
presupuestos = ["bajo", "medio", "medio-alto", "alto"]
modos = ["Exprímelo", "Relax", "Cultural", "Gastronómico", "Aventura", "Familiar"]
temporadas = ["alta", "baja"]

# Calendario y horas con defaults
today = date.today()
default_start = today
default_end = date.fromordinal(today.toordinal() + 3)
default_in_time = time_cls(10, 0)
default_out_time = time_cls(22, 0)

# ---- Formulario (sin precarga excepto fechas/horas) ----
with st.form("form_viaje"):
    destino = st.text_input("Destino del viaje", value="", placeholder="Ej: Bariloche")

    c1, c2, c3 = st.columns(3)
    with c1:
        transporte = st.selectbox("Medio de transporte", options=transportes, index=None, placeholder="Elegí un medio")
    with c2:
        cant_personas_str = st.text_input("Cantidad de personas", value="", placeholder="Ej: 2")
    with c3:
        temporada = st.selectbox("Temporada", options=temporadas, index=None, placeholder="Elegí temporada")

    c4, c5 = st.columns(2)
    with c4:
        fecha_inicio_date = st.date_input("Fecha de inicio", value=default_start, format="DD/MM/YYYY")
        hora_llegada_time = st.time_input("Hora de llegada", value=default_in_time, step=300)
    with c5:
        fecha_regreso_date = st.date_input("Fecha de regreso", value=default_end, format="DD/MM/YYYY")
        hora_regreso_time = st.time_input("Hora de regreso", value=default_out_time, step=300)

    c6, c7 = st.columns(2)
    with c6:
        presupuesto = st.selectbox("Nivel de presupuesto", options=presupuestos, index=None, placeholder="Elegí presupuesto")
    with c7:
        modo_viaje = st.selectbox("Modo de viaje", options=modos, index=None, placeholder="Elegí modo")

    ninos_menores_12 = None
    if modo_viaje == "Familiar":
        ninos_menores_12 = st.selectbox("¿Hay niños menores de 12 años?", options=[True, False],
                                        index=None, placeholder="Elegí una opción",
                                        format_func=lambda b: "Sí" if b else "No")
    submitted = st.form_submit_button("🚀 Generar itinerario, QA e imágenes")

# ---- Validación y ejecución ----
if submitted:
    # Validaciones
    errores = []
    if not destino.strip(): errores.append("Ingresá un destino.")
    if transporte is None: errores.append("Seleccioná el medio de transporte.")
    try:
        cant_personas = int(cant_personas_str)
        if cant_personas < 1: raise ValueError()
    except Exception:
        errores.append("Ingresá una **cantidad de personas** válida (entero ≥ 1).")
    if temporada is None: errores.append("Seleccioná la temporada.")
    if presupuesto is None: errores.append("Seleccioná el nivel de presupuesto.")
    if modo_viaje is None: errores.append("Seleccioná el modo de viaje.")
    if modo_viaje == "Familiar" and ninos_menores_12 is None:
        errores.append("Indicá si viajan niños menores de 12 años.")

    if errores:
        for e in errores: st.error(e)
        st.stop()

    if modo_viaje != "Familiar":
        ninos_menores_12 = False

    # Normalizo a string como usa el prompt
    fecha_inicio = fecha_inicio_date.strftime("%d/%m/%Y")
    fecha_regreso = fecha_regreso_date.strftime("%d/%m/%Y")
    hora_llegada = hora_llegada_time.strftime("%H:%M")
    hora_regreso = hora_regreso_time.strftime("%H:%M")

    dt_inicio = datetime.strptime(f"{fecha_inicio} {hora_llegada}", "%d/%m/%Y %H:%M")
    dt_regreso = datetime.strptime(f"{fecha_regreso} {hora_regreso}", "%d/%m/%Y %H:%M")
    if dt_regreso <= dt_inicio:
        st.error("La fecha/hora de regreso debe ser posterior a la de inicio.")
        st.stop()

    cant_dias = (dt_regreso.date() - dt_inicio.date()).days + 1

    # Resumen final (visible)
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
    # Intake JSON (NO visible)
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
    with st.spinner("🧩 Preparando parámetros..."):
        intake_response = openai_client.chat.completions.create(
            model=MODEL_TEXT,
            messages=[
                {"role": "system", "content": "Respondé SOLO con JSON válido y breve."},
                {"role": "user", "content": intake_prompt}
            ],
            temperature=0.2
        )
        intake_json = safe_json_parse(intake_response.choices[0].message.content)

    # =======================
    # Itinerario
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
            model=MODEL_TEXT,
            messages=[
                {"role": "system", "content": "Devolvé solo itinerario en texto limpio."},
                {"role": "user", "content": itinerario_prompt}
            ],
            temperature=0.4
        )
        itinerario = itinerario_response.choices[0].message.content

    st.subheader("Itinerario generado")
    st.text(itinerario)
    st.download_button("💾 Descargar itinerario (TXT)",
                       data=itinerario.encode("utf-8"),
                       file_name="itinerario_final.txt",
                       mime="text/plain")

    # =======================
    # QA — Auditoría
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
            model=MODEL_TEXT,
            messages=[
                {"role": "system", "content": "Actuá como auditor de itinerarios. Respondé SOLO con JSON válido."},
                {"role": "user", "content": qa_prompt}
            ],
            temperature=0.2
        )
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
    # Contactos simulados (sin mostrar "lugares detectados")
    # =======================
    prompt_contactos = f"""
A partir del siguiente itinerario, generá datos de contacto **verosímiles** (no reales) para lugares y servicios mencionados.

Itinerario:
{itinerario}

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
            model=MODEL_TEXT,
            messages=[
                {"role": "system", "content": "Respondé SOLO con JSON válido."},
                {"role": "user", "content": prompt_contactos}
            ],
            temperature=0.4
        )
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
                       file_name="contactos.json",
                       mime="application/json")

    # =======================
    # Prompts de imágenes (no se muestran)
    #  - Mapa: SIN depender del itinerario. Solo paisajes/objetos del destino.
    # =======================
    prompt_mapa = f"""
Ilustración 16:9 tipo mapa turístico vintage de {destino}.
- Base: silueta/contorno simple del área del destino con textura de papel antiguo.
- Añadí 4–6 mini-escenas (viñetas) de **paisajes u objetos** característicos del destino
  (montañas, lagos, costas, bosques, viñedos, fauna local, arquitectura típica, faros, artesanías
  o comida regional). Evitá actividades, horarios o rutas.
- Paleta cálida (beige, terracota, verdes suaves); líneas limpias y contraste claro.
- **Sin texto, sin personas, sin logotipos ni marcas de agua.**
- Composición clara y centrada. Exportá **una única imagen PNG** en 1920×1080.
"""

    prompt_flyer = f"""
Crear un póster 16:9 estilo travel-poster de {destino}.
Motivos icónicos del lugar {destino}.
Exportar PNG, colores vibrantes y contraste claro. Sin texto ni marcas de agua.
"""

    # =======================
    # GEMINI REST — Imágenes
    # =======================
    st.subheader("Imágenes (Gemini REST)")
    cols = st.columns(2)

    with st.spinner("🗺️ Generando Mapa..."):
        nombre_mapa = f"{destino.replace(' ','_').lower()}_mapa.png"
        bytes_mapa, raw_mapa = generar_imagen_gemini(prompt_mapa, MODEL_IMG, nombre_mapa)
    with cols[0]:
        if bytes_mapa:
            st.image(bytes_mapa, caption=nombre_mapa, use_container_width=True)
            st.download_button("💾 Descargar mapa (PNG)", data=bytes_mapa, file_name=nombre_mapa, mime="image/png")
        else:
            st.warning("No se detectó imagen en la respuesta del modelo para el **Mapa**.")
            with st.expander("Ver respuesta cruda (Mapa)"):
                st.json(raw_mapa)

    with st.spinner("🎫 Generando Flyer..."):
        nombre_flyer = f"{destino.replace(' ','_').lower()}_flyer.png"
        bytes_flyer, raw_flyer = generar_imagen_gemini(prompt_flyer, MODEL_IMG, nombre_flyer)
    with cols[1]:
        if bytes_flyer:
            st.image(bytes_flyer, caption=nombre_flyer, use_container_width=True)
            st.download_button("💾 Descargar flyer (PNG)", data=bytes_flyer, file_name=nombre_flyer, mime="image/png")
        else:
            st.warning("No se detectó imagen en la respuesta del modelo para el **Flyer**.")
            with st.expander("Ver respuesta cruda (Flyer)"):
                st.json(raw_flyer)

# Fin
