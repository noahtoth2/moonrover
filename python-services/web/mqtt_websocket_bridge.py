"""
🌉 PUENTE MQTT ↔ WebSocket
Conecta el broker MQTT con la interfaz web HTML
Calcula velocidades reales basadas en PWM (800-2000 = 0-6 cm/s)
"""

import asyncio
import websockets
import json
import paho.mqtt.client as mqtt
import threading
import time

# Configuración
MQTT_BROKER = "192.168.1.102"
MQTT_PORT = 1883
WEBSOCKET_PORT = 8765

# Velocidades físicas del rover
PWM_MIN = 800
PWM_MAX = 2000
VELOCIDAD_MAX_CM_S = 6.0  # cm/s a PWM máximo

# Estado global
velocidad_pwm_actual = 800
comando_actual = "stop"
velocidades_ruedas = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # cm/s
clientes_ws = set()


def pwm_a_velocidad(pwm):
    """
    Regla de 3: PWM 800-2000 → 0-6 cm/s
    800 → 0 cm/s
    2000 → 6 cm/s
    """
    if pwm < PWM_MIN:
        return 0.0
    
    # Normalizar PWM al rango 0-1200
    pwm_normalizado = pwm - PWM_MIN
    rango_pwm = PWM_MAX - PWM_MIN  # 1200
    
    # Calcular velocidad proporcional
    velocidad = (pwm_normalizado / rango_pwm) * VELOCIDAD_MAX_CM_S
    return round(velocidad, 2)


def calcular_velocidades_ruedas(comando, velocidad_base_cm_s):
    """
    Calcula velocidad de cada rueda según el comando
    Ruedas: [0, 1, 2, 3, 4, 5]
    Izquierdas: 0, 2, 4
    Derechas: 1, 3, 5
    
    Returns: array de 6 velocidades en cm/s
    """
    velocidades = [0.0] * 6
    
    if comando == "forward":
        # Todas las ruedas hacia adelante
        velocidades = [velocidad_base_cm_s] * 6
    
    elif comando == "backward":
        # Todas las ruedas hacia atrás (negativo)
        velocidades = [-velocidad_base_cm_s] * 6
    
    elif comando == "left":
        # Izquierdas atrás, derechas adelante
        velocidades[0] = velocidad_base_cm_s   # Izq adelante
        velocidades[1] = -velocidad_base_cm_s  # Der adelante
        velocidades[2] = velocidad_base_cm_s   # Izq medio
        velocidades[3] = -velocidad_base_cm_s  # Der medio
        velocidades[4] = velocidad_base_cm_s   # Izq atrás
        velocidades[5] = -velocidad_base_cm_s  # Der atrás
    
    elif comando == "right":
        # Izquierdas adelante, derechas atrás
        velocidades[0] = -velocidad_base_cm_s  # Izq adelante
        velocidades[1] = velocidad_base_cm_s   # Der adelante
        velocidades[2] = -velocidad_base_cm_s  # Izq medio
        velocidades[3] = velocidad_base_cm_s   # Der medio
        velocidades[4] = -velocidad_base_cm_s  # Izq atrás
        velocidades[5] = velocidad_base_cm_s   # Der atrás
    
    elif comando == "stop":
        velocidades = [0.0] * 6
    
    return velocidades


# =================== MQTT ===================
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
    
    # Recalcular velocidades
    velocidad_cm_s = pwm_a_velocidad(velocidad_pwm_actual)
    velocidades_ruedas = calcular_velocidades_ruedas(comando_actual, velocidad_cm_s)
    
    # Enviar a WebSocket
    asyncio.run(broadcast_velocidades())


def iniciar_mqtt():
    """Inicia cliente MQTT en thread separado"""
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


# =================== WebSocket ===================
async def handler(websocket):
    """Maneja conexiones WebSocket"""
    clientes_ws.add(websocket)
    print(f"🔌 Cliente WebSocket conectado ({len(clientes_ws)} total)")
    
    try:
        # Enviar estado inicial
        await websocket.send(json.dumps({
            'velocidades': velocidades_ruedas,
            'comando': comando_actual,
            'pwm': velocidad_pwm_actual
        }))
        
        # Mantener conexión abierta
        async for message in websocket:
            # Aquí podrías recibir comandos del web si quisieras
            pass
            
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clientes_ws.remove(websocket)
        print(f"❌ Cliente WebSocket desconectado ({len(clientes_ws)} restantes)")


async def broadcast_velocidades():
    """Envía velocidades a todos los clientes WebSocket"""
    if not clientes_ws:
        return
    
    mensaje = json.dumps({
        'velocidades': velocidades_ruedas,
        'comando': comando_actual,
        'pwm': velocidad_pwm_actual,
        'velocidad_cm_s': pwm_a_velocidad(velocidad_pwm_actual)
    })
    
    # Enviar a todos los clientes conectados
    websockets.broadcast(clientes_ws, mensaje)


async def main_websocket():
    """Inicia servidor WebSocket"""
    async with websockets.serve(handler, "0.0.0.0", WEBSOCKET_PORT):
        print(f"🌐 WebSocket servidor escuchando en puerto {WEBSOCKET_PORT}")
        await asyncio.Future()  # Mantener vivo


# =================== MAIN ===================
if __name__ == "__main__":
    print("=" * 70)
    print("🌉 PUENTE MQTT ↔ WebSocket PARA ROVER")
    print("=" * 70)
    print(f"📡 MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"🌐 WebSocket: ws://localhost:{WEBSOCKET_PORT}")
    print(f"⚙️  PWM Range: {PWM_MIN}-{PWM_MAX}")
    print(f"🏎️  Velocidad máxima: {VELOCIDAD_MAX_CM_S} cm/s")
    print("=" * 70)
    print()
    
    # Iniciar MQTT en thread separado
    mqtt_thread = threading.Thread(target=iniciar_mqtt, daemon=True)
    mqtt_thread.start()
    
    print("⏳ Esperando conexión MQTT...")
    time.sleep(2)
    
    # Iniciar WebSocket
    print("🚀 Iniciando WebSocket...")
    asyncio.run(main_websocket())
