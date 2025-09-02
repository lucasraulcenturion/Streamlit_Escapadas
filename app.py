import streamlit as st
from openai import OpenAI
import os, json
from dotenv import load_dotenv
from datetime import datetime

# =======================
# Configuración API
# =======================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =======================
# Helpers
# =======================
def safe_json_parse(raw_text: str):
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "").replace("json", "", 1).strip()
    try:
        return json.loads(cleaned)
    except:
        return {}

# =======================
# Configuración de la app
# =======================
st.set_page_config(page_title="Asistente de Escapadas", page_icon="✈️")
st.title("✈️ Organizador de Escapadas IA")

# Estado
if "datos" not in st.session_state:
    st.session_state.datos = {}
if "itinerary" not in st.session_state:
    st.session_state.itinerary = None
if "reservas" not in st.session_state:
    st.session_state.reservas = None

# =======================
# Paso 1 - Entrada de datos
# =======================
with st.form("datos_viaje"):
    st.subheader("Completemos tu escapada paso a paso:")

    destino = st.text_input("Destino del viaje", "")
    transporte = st.selectbox("Medio de transporte", ["Auto", "Micro", "Avión", "Tren"])
    personas = st.number_input("Cantidad de personas", min_value=1, max_value=20, value=2)

    fecha_inicio = st.date_input("Fecha de inicio")
    hora_llegada = st.time_input("Hora de llegada")
    fecha_regreso = st.date_input("Fecha de regreso")
    hora_regreso = st.time_input("Hora de regreso")

    presupuesto = st.selectbox("Presupuesto", ["Bajo", "Medio", "Medio-alto", "Alto"])
    modo_viaje = st.selectbox("Modo de viaje", 
        ["Exprímelo", "Relax", "Cultural", "Gastronómico", "Aventura", "Familiar"])

    submit = st.form_submit_button("Generar Itinerario")

# =======================
# Generar Itinerario (Prompt A)
# =======================
if submit:
    dt_inicio = datetime.combine(fecha_inicio, hora_llegada)
    dt_regreso = datetime.combine(fecha_regreso, hora_regreso)
    dias = (dt_regreso.date() - dt_inicio.date()).days + 1

    st.session_state.datos = {
        "dest": destino,
        "transporte": transporte,
        "dias": dias,
        "pers": personas,
        "presupuesto": presupuesto,
        "modo": modo_viaje,
        "fecha_inicio": str(fecha_inicio),
        "hora_llegada": str(hora_llegada),
        "fecha_regreso": str(fecha_regreso),
        "hora_regreso": str(hora_regreso),
    }

    st.subheader("Resumen de tu viaje")
    st.json(st.session_state.datos)

    intake_prompt = f"""
    Sos un organizador de viajes. Devolvé SOLO un itinerario detallado de {dias} días.

    Datos del viaje:
    {json.dumps(st.session_state.datos, indent=2, ensure_ascii=False)}

    Formato esperado:
    Día N - Zona
    09:00-11:00 Actividad
    11:15-13:00 Actividad
    13:15-14:30 Almuerzo (2 opciones)
    15:00-17:00 Actividad
    17:15-19:00 Actividad
    20:00 Cena (2 opciones)

    Tené en cuenta:
    - La hora de llegada del primer día (si es tarde, día reducido).
    - La hora de regreso del último día (si es temprano, día reducido).
    - Incluir traslados, resumen, tips y alertas QA.
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Sos un organizador de escapadas."},
            {"role": "user", "content": intake_prompt}
        ],
        temperature=0.4
    )

    st.session_state.itinerary = response.choices[0].message.content
    st.subheader("Itinerario generado")
    st.text(st.session_state.itinerary)

# =======================
# Generar Reservas (Prompt C)
# =======================
if st.session_state.itinerary:
    if st.button("Generar datos de contacto (Reservas)"):
        lugares = []
        for line in st.session_state.itinerary.splitlines():
            if any(p in line.lower() for p in ["hotel", "restaurante", "bodega", "excursión"]):
                lugares.append(line.strip())

        prompt_contactos = f"""
        A partir de la siguiente lista de lugares detectados en el itinerario:

        {json.dumps(lugares, indent=2, ensure_ascii=False)}

        Simulá que buscás en la web sus datos de contacto.

        Devolvé SOLO un JSON con este formato:
        [
          {{
            "nombre": "Nombre del lugar",
            "tipo": "hotel | restaurante | bodega | excursión",
            "web": "URL ficticia o realista",
            "telefono": "Teléfono ficticio con código de país",
            "email": "Email ficticio con formato válido"
          }}
        ]
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Respondé SOLO con JSON válido."},
                {"role": "user", "content": prompt_contactos}
            ],
            temperature=0.3
        )

        reservas_json = safe_json_parse(response.choices[0].message.content)
        st.session_state.reservas = reservas_json

        st.subheader("Contactos simulados de reservas")
        st.json(reservas_json)
