import keyboard
import threading
import time
import paho.mqtt.client as mqtt

# ============================
# CONFIGURACIÓN
# ============================
ESP32_CONTROL_IP = "192.168.1.100"  # 🚗 ESP32 motores - VERIFICA ESTA IP

# Configuración MQTT
MQTT_BROKER = "192.168.1.101"  # IP de tu PC (donde corre el broker)
MQTT_PORT = 1883
MQTT_TOPIC = "rover/control"
MQTT_CLIENT_ID = "RoverController"

# Variables globales thread-safe
control_activo = threading.Event()
control_activo.set()

# Cliente MQTT
mqtt_client = None
mqtt_conectado = False

# ============================
# MQTT - CONTROL DEL CARRO
# ============================
ultimo_comando = None
motor_conectado = True
tiempo_ultimo_comando = 0

def on_mqtt_connect(client, userdata, flags, rc, properties=None):
    """Callback cuando se conecta al broker MQTT"""
    global mqtt_conectado
    if rc == 0:
        mqtt_conectado = True
        print("✅ MQTT conectado al broker")
    else:
        mqtt_conectado = False
        print(f"❌ Error MQTT: código {rc}")


def on_mqtt_disconnect(client, userdata, rc, properties=None):
    """Callback cuando se desconecta del broker"""
    global mqtt_conectado
    mqtt_conectado = False
    print("⚠️ MQTT desconectado")


def iniciar_mqtt():
    """Inicializar y conectar cliente MQTT"""
    global mqtt_client
    try:
        mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
        mqtt_client.on_connect = on_mqtt_connect
        mqtt_client.on_disconnect = on_mqtt_disconnect
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        return True
    except Exception as e:
        print(f"❌ Error conectando MQTT: {e}")
        return False


def enviar_comando(cmd):
    """Envía comandos al ESP32 vía MQTT - ULTRA RÁPIDO"""
    global ultimo_comando, tiempo_ultimo_comando, mqtt_conectado
    ahora = time.time()
    if cmd == ultimo_comando and (ahora - tiempo_ultimo_comando) < 0.05:
        return

    ultimo_comando = cmd
    tiempo_ultimo_comando = ahora

    if mqtt_client and mqtt_conectado:
        try:
            mqtt_client.publish(MQTT_TOPIC, cmd, qos=0)
        except Exception as e:
            print(f"⚠️ Error MQTT: {e}")
    else:
        print("⚠️ MQTT no conectado")


def control_teclado():
    """Control con heartbeat para mantener conexión"""
    ultima_tecla = None
    contador_heartbeat = 0

    while control_activo.is_set():
        try:
            if keyboard.is_pressed("esc"):
                enviar_comando("stop")
                control_activo.clear()
                break
            elif keyboard.is_pressed("up"):
                tecla = "forward"
            elif keyboard.is_pressed("down"):
                tecla = "backward"
            elif keyboard.is_pressed("left"):
                tecla = "left"
            elif keyboard.is_pressed("right"):
                tecla = "right"
            else:
                tecla = "stop"

            if tecla != ultima_tecla:
                enviar_comando(tecla)
                ultima_tecla = tecla
                contador_heartbeat = 0
            else:
                # Heartbeat: reenviar comando cada 2 segundos para mantener conexión
                contador_heartbeat += 1
                if contador_heartbeat >= 100:  # 100 * 0.02s = 2s
                    enviar_comando(tecla)
                    contador_heartbeat = 0

            time.sleep(0.02)  # 50Hz
        except:
            enviar_comando("stop")
            break

    # Stop múltiple al salir
    for _ in range(3):
        enviar_comando("stop")
        time.sleep(0.1)


# ============================
# MAIN - CONTROL DEL ROVER
# ============================
if __name__ == "__main__":
    print("=" * 60)
    print("🎮 CONTROL ROVER VÍA MQTT")
    print("=" * 60)
    print("⌨️  Flechas: ↑ ↓ ← → para mover")
    print("⌨️  ESC: Detener y salir")
    print("=" * 60)
    
    # Conectar MQTT
    print("\n📡 Conectando MQTT...")
    if iniciar_mqtt():
        time.sleep(1)  # Esperar conexión
        if mqtt_conectado:
            print("✅ MQTT listo")
        else:
            print("⚠️ MQTT no conectado (continuando)")
    else:
        print("⚠️ Error MQTT (continuando)")
    
    print("=" * 60)
    print("🚀 Control activo - Usa las flechas del teclado")
    print("=" * 60)
    print("")
    
    # Iniciar control de teclado
    hilo_control = threading.Thread(target=control_teclado, daemon=False)
    
    try:
        hilo_control.start()
        hilo_control.join()
        
    except KeyboardInterrupt:
        pass
    finally:
        control_activo.clear()
        time.sleep(0.1)
        
        # Enviar STOP múltiple vía MQTT
        print("🛑 Deteniendo rover...")
        for _ in range(5):
            if mqtt_client and mqtt_conectado:
                mqtt_client.publish(MQTT_TOPIC, "stop", qos=1)
            time.sleep(0.1)
        
        # Desconectar MQTT
        if mqtt_client:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
        
        print("\n✅ Control detenido")
