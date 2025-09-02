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

def calcular_costo(response, nombre="Prompt"):
    if not hasattr(response, "usage"):
        return
    in_tokens = response.usage.prompt_tokens
    out_tokens = response.usage.completion_tokens
    total_tokens = response.usage.total_tokens
    in_price = in_tokens * 0.00000015
    out_price = out_tokens * 0.0000006
    st.sidebar.write(f"**{nombre}** → {total_tokens} tokens usados (${in_price+out_price:.6f} USD)")

# =======================
# Configuración de la app
# =======================
st.set_page_config(page_title="Mini ChatGPT Turístico", page_icon="✈️")
st.title("✈️ Organizador de Escapadas IA")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "itinerary" not in st.session_state:
    st.session_state.itinerary = None
if "reservas" not in st.session_state:
    st.session_state.reservas = None

# =======================
# Chat interface
# =======================
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("Escribí tu consulta o pedí un itinerario..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # Prompt A - Itinerario
    if "itinerario" in prompt.lower():
        system_msg = "Sos un organizador de escapadas. Generá itinerarios de viaje."
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4
        )
        reply = response.choices[0].message.content
        st.session_state.itinerary = reply
        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.chat_message("assistant").write(reply)
        calcular_costo(response, "Prompt A - Itinerario")

    # Prompt C - Contactos simulados
    elif "reservas" in prompt.lower() and st.session_state.itinerary:
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
        reply = response.choices[0].message.content
        reservas_json = safe_json_parse(reply)
        st.session_state.reservas = reservas_json
        st.session_state.messages.append({"role": "assistant", "content": "Acá tenés los contactos simulados de los lugares detectados:"})
        st.chat_message("assistant").write(reservas_json)
        calcular_costo(response, "Prompt C - Contactos")

    # Default: conversación genérica
    else:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=st.session_state.messages,
            temperature=0.6
        )
        reply = response.choices[0].message.content
        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.chat_message("assistant").write(reply)
        calcular_costo(response, "Chat genérico")
