"""
🌉 PUENTE MQTT ↔ WebSocket + FLASK CAMARA
Conecta el broker MQTT con la interfaz web HTML
Calcula velocidades reales basadas en PWM (800-2000 = 0-6 cm/s)
Sirve la cámara en tiempo real en /video_feed
"""

import asyncio
import websockets
import json
import paho.mqtt.client as mqtt
import threading
import time
import cv2
from flask import Flask, Response

# ================= CONFIGURACIÓN =================
MQTT_BROKER = "192.168.1.102"
MQTT_PORT = 1883
WEBSOCKET_PORT = 8765
FLASK_PORT = 5000

# Velocidades físicas del rover
PWM_MIN = 800
PWM_MAX = 2000
VELOCIDAD_MAX_CM_S = 6.0  # cm/s a PWM máximo

# ================= ESTADO GLOBAL =================
velocidad_pwm_actual = 800
comando_actual = "stop"
velocidades_ruedas = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # cm/s
clientes_ws = set()
frame_actual = None  # Para la cámara
control_activo = threading.Event()
control_activo.set()

# ================= FUNCIONES AUX =================
def pwm_a_velocidad(pwm):
    if pwm < PWM_MIN:
        return 0.0
    pwm_normalizado = pwm - PWM_MIN
    rango_pwm = PWM_MAX - PWM_MIN
    velocidad = (pwm_normalizado / rango_pwm) * VELOCIDAD_MAX_CM_S
    return round(velocidad, 2)

def calcular_velocidades_ruedas(comando, velocidad_base_cm_s):
    velocidades = [0.0] * 6
    if comando == "forward":
        velocidades = [velocidad_base_cm_s] * 6
    elif comando == "backward":
        velocidades = [-velocidad_base_cm_s] * 6
    elif comando == "left":
        velocidades[0] = velocidad_base_cm_s
        velocidades[1] = -velocidad_base_cm_s
        velocidades[2] = velocidad_base_cm_s
        velocidades[3] = -velocidad_base_cm_s
        velocidades[4] = velocidad_base_cm_s
        velocidades[5] = -velocidad_base_cm_s
    elif comando == "right":
        velocidades[0] = -velocidad_base_cm_s
        velocidades[1] = velocidad_base_cm_s
        velocidades[2] = -velocidad_base_cm_s
        velocidades[3] = velocidad_base_cm_s
        velocidades[4] = -velocidad_base_cm_s
        velocidades[5] = velocidad_base_cm_s
    elif comando == "stop":
        velocidades = [0.0] * 6
    return velocidades

# ================= MQTT =================
def on_mqtt_connect(client, userdata, flags, rc, properties=None):
    print(f"✅ MQTT conectado (código {rc})")
    client.subscribe("rover/control")
    client.subscribe("rover/speed")

def on_mqtt_message(client, userdata, msg):
    global comando_actual, velocidad_pwm_actual, velocidades_ruedas
    topic = msg.topic
    payload = msg.payload.decode('utf-8')

    if topic == "rover/control":
        comando_actual = payload
        print(f"📩 Comando: {comando_actual}")
    elif topic == "rover/speed":
        try:
            velocidad_pwm_actual = int(payload)
            print(f"⚡ PWM: {velocidad_pwm_actual}")
        except:
            pass

    velocidad_cm_s = pwm_a_velocidad(velocidad_pwm_actual)
    velocidades_ruedas = calcular_velocidades_ruedas(comando_actual, velocidad_cm_s)
    asyncio.run(broadcast_velocidades())

def iniciar_mqtt():
    mqtt_client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="WebSocketBridge"
    )
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_message = on_mqtt_message
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_forever()
    except Exception as e:
        print(f"❌ Error MQTT: {e}")

# ================= WEBSOCKET =================
async def handler(websocket):
    clientes_ws.add(websocket)
    print(f"🔌 Cliente WebSocket conectado ({len(clientes_ws)} total)")
    try:
        await websocket.send(json.dumps({
            'velocidades': velocidades_ruedas,
            'comando': comando_actual,
            'pwm': velocidad_pwm_actual
        }))
        async for message in websocket:
            pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clientes_ws.remove(websocket)
        print(f"❌ Cliente WebSocket desconectado ({len(clientes_ws)} restantes)")

async def broadcast_velocidades():
    if not clientes_ws:
        return
    mensaje = json.dumps({
        'velocidades': velocidades_ruedas,
        'comando': comando_actual,
        'pwm': velocidad_pwm_actual,
        'velocidad_cm_s': pwm_a_velocidad(velocidad_pwm_actual)
    })
    websockets.broadcast(clientes_ws, mensaje)

async def main_websocket():
    async with websockets.serve(handler, "0.0.0.0", WEBSOCKET_PORT):
        print(f"🌐 WebSocket servidor escuchando en puerto {WEBSOCKET_PORT}")
        await asyncio.Future()

# ================= FLASK / CAMARA =================
def capturar_video():
    global frame_actual
    cap = cv2.VideoCapture(0)  # Cambiar a tu fuente real si es otra
    while control_activo.is_set():
        ret, frame = cap.read()
        if ret:
            frame_actual = frame

def gen_frames():
    global frame_actual
    while True:
        if frame_actual is None:
            continue
        ret, buffer = cv2.imencode('.jpg', frame_actual)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

app = Flask(__name__)
@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def iniciar_flask():
    app.run(host='0.0.0.0', port=FLASK_PORT, threaded=True)

# ================= MAIN =================
if __name__ == "__main__":
    print("=" * 70)
    print("🌉 PUENTE MQTT ↔ WebSocket + Cámara")
    print("=" * 70)
    print(f"📡 MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"🌐 WebSocket: ws://localhost:{WEBSOCKET_PORT}")
    print(f"🎥 Cámara Flask: http://localhost:{FLASK_PORT}/video_feed")
    print(f"⚙️  PWM Range: {PWM_MIN}-{PWM_MAX}")
    print(f"🏎️  Velocidad máxima: {VELOCIDAD_MAX_CM_S} cm/s")
    print("=" * 70)
    print()

    # Hilos de video y Flask
    threading.Thread(target=capturar_video, daemon=True).start()
    threading.Thread(target=iniciar_flask, daemon=True).start()

    # Hilo MQTT
    mqtt_thread = threading.Thread(target=iniciar_mqtt, daemon=True)
    mqtt_thread.start()

    print("⏳ Esperando conexión MQTT...")
    time.sleep(2)

    # Servidor WebSocket
    print("🚀 Iniciando WebSocket...")
    asyncio.run(main_websocket())
