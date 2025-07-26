import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
from pydub import AudioSegment
import speech_recognition as sr
from gtts import gTTS
import datetime
import csv

# === AGREGAR RUTA DE FFMPEG AL PATH TEMPORALMENTE ===
ffmpeg_path = r"C:\Users\User\Downloads\ffmpeg-7.1.1-essentials_build\ffmpeg-7.1.1-essentials_build\bin"
os.environ["PATH"] += os.pathsep + ffmpeg_path
AudioSegment.converter = os.path.join(ffmpeg_path, "ffmpeg.exe")

# === CONFIGURACIÓN ===
TELEGRAM_TOKEN = '8458815660:AAFk16pLa5AfT_c5ZfiAEWcE3iYiaRE_tiI'
OPENAI_API_KEY = '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'
client = OpenAI(api_key=OPENAI_API_KEY)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "registro_conversaciones.csv")

if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="", encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(["Usuario", "Mensaje del usuario", "Respuesta del bot", "Fecha y hora", "Sentimiento" ])

faq = {
    "horario": "Nuestro horario es de lunes a viernes de 8:00 a.m. a 5:00 p.m.",
    "agendar": "Puedes agendar una cita llamando al 321 123 4567 o escribiendo por este medio.",
    "servicios": "Ofrecemos consultoría, mantenimiento industrial y automatización de procesos.",
    "ubicados": "Estamos en Pereira, Risaralda. Cra 10 #12-34.",
    "soporte": "Sí, ofrecemos soporte técnico 24/7 para nuestros clientes registrados.",
    "medios de pago": "Aceptamos transferencias, consignaciones y pagos en línea.",
    "visitas técnicas": "Sí, ofrecemos visitas técnicas bajo solicitud previa.",
    "scada": "Sí, trabajamos con integración y mantenimiento de sistemas SCADA.",
    "respuesta promedio": "Respondemos generalmente en menos de 24 horas hábiles.",
    "atención regional": "Atendemos en todo el Eje Cafetero y zonas aledañas.",
    "precios": "Para obtener información sobre los precios de nuestros servicios, te recomiendo agendar una consulta gratuita o escribirnos directamente con más detalles del servicio que necesitas."
}

user_context = {}
user_preferences = {}

def registrar_interaccion(usuario, entrada, salida, sentimiento):
    with open(LOG_FILE, "a", newline="", encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([usuario, entrada, salida,  datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sentimiento ])
    print(f"💾 Registrado: {entrada[:30]}... → {salida[:30]}... | Sentimiento: {sentimiento}")

async def chatgpt_response(user_id, user_input):
    historial = user_context.get(user_id, [])
    messages = [{"role": "system", "content": "Eres un asistente de atención al cliente de INGELEAN S.A.S."}]
    messages += historial
    messages.append({"role": "user", "content": user_input})

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        max_tokens=200
    )
    answer = response.choices[0].message.content.strip()
    historial.append({"role": "user", "content": user_input})
    historial.append({"role": "assistant", "content": answer})
    user_context[user_id] = historial[-10:]
    return answer

async def analizar_sentimiento(user_input):
    prompt = f"Clasifica el siguiente mensaje como Positivo, Negativo o Neutral. Solo responde con una palabra.\n\nMensaje: \"{user_input}\""
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1,
        temperature=0
    )
    sentimiento = response.choices[0].message.content.strip().capitalize()
    return sentimiento if sentimiento in ["Positivo", "Negativo", "Neutral"] else "Desconocido"

def generar_audio(texto, user_id):
    tts = gTTS(text=texto, lang="es")
    audio_path = os.path.join(BASE_DIR, f"respuesta_{user_id}.mp3")
    tts.save(audio_path)
    return audio_path

def detectar_cambio_preferencia(texto):
    texto = texto.lower()
    if "texto" in texto and ("quiero" in texto or "prefiero" in texto or "responde" in texto or "ya no"):
        return "texto"
    if ("audio" in texto or "voz" in texto) and ("quiero" in texto or "prefiero" in texto or "responde" in texto):
        return "audio"
    return None

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    ogg_path = os.path.join(BASE_DIR, f"{user_id}.ogg")
    wav_path = os.path.join(BASE_DIR, f"{user_id}.wav")
    await file.download_to_drive(ogg_path)

    audio = AudioSegment.from_ogg(ogg_path)
    audio.export(wav_path, format="wav")

    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_path) as source:
        audio_data = recognizer.record(source)
        try:
            texto = recognizer.recognize_google(audio_data, language="es-ES")
            print(f"🎤 Voz convertida a texto: {texto}")
            await handle_text(update, context, texto)
        except sr.UnknownValueError:
            await update.message.reply_text("❌ No pude entender el mensaje de voz.")
        except sr.RequestError:
            await update.message.reply_text("❌ Error al procesar el reconocimiento de voz.")

    os.remove(ogg_path)
    os.remove(wav_path)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE, texto=None):
    user_id = str(update.message.from_user.id)
    user_input = texto if texto else update.message.text.lower().strip()

    cambio = detectar_cambio_preferencia(user_input)
    if cambio:
        user_preferences[user_id] = cambio
        mensaje = "✅ Responderé solo por texto." if cambio == "texto" else "✅ Responderé con mensajes de voz."
        await update.message.reply_text(mensaje)
        return

    if user_input in ["sí", "si"]:
        user_preferences[user_id] = "audio"
        await update.message.reply_text("🔊 Perfecto, responderé con mensajes de voz.")
        return
    elif user_input == "no":
        user_preferences[user_id] = "texto"
        await update.message.reply_text("💬 Está bien, seguiré respondiendo por texto.")
        return

    # === Lógica de jerarquía para responder precios antes que servicios ===
    if "precio" in user_input or "cuánto cuesta" in user_input or "tarifa" in user_input:
        respuesta = faq.get("precios")
        sentimiento = await analizar_sentimiento(user_input)
        await responder(update, context, user_id, user_input, respuesta, sentimiento)
        return

    for clave, respuesta in faq.items():
        if clave in user_input:
            sentimiento = await analizar_sentimiento(user_input)
            await responder(update, context, user_id, user_input, respuesta, sentimiento)
            return

    respuesta = await chatgpt_response(user_id, user_input)
    sentimiento = await analizar_sentimiento(user_input)
    await responder(update, context, user_id, user_input, respuesta, sentimiento)

    if user_id not in user_preferences:
        await update.message.reply_text("🗣️ ¿Quieres que te responda con mensajes de voz en adelante? Responde 'sí' o 'no'.")

async def responder(update, context, user_id, entrada, salida, sentimiento="Desconocido"):
    preferencia = user_preferences.get(user_id, "texto")

    if preferencia == "audio":
        audio_path = generar_audio(salida, user_id)
        with open(audio_path, "rb") as audio_file:
            await update.message.reply_voice(audio_file)
        os.remove(audio_path)
    else:
        await update.message.reply_text(salida)

    registrar_interaccion(user_id, entrada, salida, sentimiento)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje = "👋 ¡Hola! Soy el asistente inteligente de INGELEAN S.A.S. ¿En qué puedo ayudarte hoy?"
    await update.message.reply_text(mensaje)

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))

print("🎙️ Bot corriendo con soporte de voz, control dinámico y análisis de sentimiento...")
app.run_polling()
