import keyboard
import threading
import time
import paho.mqtt.client as mqtt

# ============================
# CONFIGURACIÓN
# ============================
<<<<<<< HEAD
ESP32_CONTROL_IP = "192.168.1.100"  # 🚗 ESP32 motores - VERIFICA ESTA IP

# Configuración MQTT
MQTT_BROKER = "192.168.1.101"  # IP de tu PC (donde corre el broker)
=======
ESP32_CONTROL_IP = "192.168.1.101"  

MQTT_BROKER = "192.168.1.102"
>>>>>>> eb02e2416b1b27ac6de324838028c8ca9dd5b257
MQTT_PORT = 1883
MQTT_TOPIC_CONTROL = "rover/control"
MQTT_TOPIC_SPEED = "rover/speed"
MQTT_CLIENT_ID = "RoverController"

# ============================
# VARIABLES GLOBALES
# ============================
control_activo = threading.Event()
control_activo.set()

mqtt_client = None
mqtt_conectado = False

ultimo_comando = None
tiempo_ultimo_comando = 0

velocidad_pwm = 600   # Valor inicial (0–1023)
VELOCIDAD_MIN = 200
VELOCIDAD_MAX = 1023
PASO_VEL = 50

# ============================
# MQTT
# ============================
def on_mqtt_connect(client, userdata, flags, rc, properties=None):
    global mqtt_conectado
    mqtt_conectado = (rc == 0)
    print("✅ MQTT Conectado" if rc == 0 else f"❌ Error MQTT {rc}")


def on_mqtt_disconnect(client, userdata, rc, properties=None):
    global mqtt_conectado
    mqtt_conectado = False
    print("⚠️ MQTT desconectado")


def iniciar_mqtt():
    global mqtt_client
    try:
        mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=MQTT_CLIENT_ID)
        mqtt_client.on_connect = on_mqtt_connect
        mqtt_client.on_disconnect = on_mqtt_disconnect
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        return True
    except Exception as e:
        print(f"❌ Error MQTT: {e}")
        return False


def enviar_mqtt(topic, payload):
    if mqtt_client and mqtt_conectado:
        try:
            mqtt_client.publish(topic, payload, qos=0)
        except:
            print("⚠️ Error publicando MQTT")


def enviar_comando(cmd):
    global ultimo_comando, tiempo_ultimo_comando

    ahora = time.time()
    if cmd == ultimo_comando and (ahora - tiempo_ultimo_comando) < 0.05:
        return

    ultimo_comando = cmd
    tiempo_ultimo_comando = ahora

    enviar_mqtt(MQTT_TOPIC_CONTROL, cmd)


def enviar_velocidad():
    global velocidad_pwm
    enviar_mqtt(MQTT_TOPIC_SPEED, str(velocidad_pwm))
    print(f"⚡ Velocidad PWM: {velocidad_pwm}")


# ============================
# CONTROL DE TECLADO
# ============================
def control_teclado():
    global velocidad_pwm

    ultima_tecla = None
    contador_heartbeat = 0

    while control_activo.is_set():
        try:
            # Salir
            if keyboard.is_pressed("esc"):
                enviar_comando("stop")
                break

            # CONTROL DE VELOCIDAD → Z / X
            if keyboard.is_pressed("z"):
                velocidad_pwm = min(velocidad_pwm + PASO_VEL, VELOCIDAD_MAX)
                enviar_velocidad()
                time.sleep(0.15)

            elif keyboard.is_pressed("x"):
                velocidad_pwm = max(velocidad_pwm - PASO_VEL, VELOCIDAD_MIN)
                enviar_velocidad()
                time.sleep(0.15)

            # MOVIMIENTO
            if keyboard.is_pressed("up"):
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
                contador_heartbeat += 1
                if contador_heartbeat >= 100:
                    enviar_comando(tecla)
                    contador_heartbeat = 0

            time.sleep(0.02)

        except:
            enviar_comando("stop")
            break

    for _ in range(3):
        enviar_comando("stop")
        time.sleep(0.1)


# ============================
# MAIN
# ============================
if __name__ == "__main__":
    print("🎮 CONTROL ROVER - MQTT + VELOCIDAD PWM (Z/X)")

    print("🔼 MOVER: Flechas")
    print("⚡ VELOCIDAD:  Z = subir / X = bajar")
    print("❌ ESC = salir")
    print("——————\n")

    iniciar_mqtt()
    time.sleep(1)
    enviar_velocidad()

    hilo = threading.Thread(target=control_teclado)
    hilo.start()
    hilo.join()

    print("🛑 Deteniendo rover…")
    enviar_comando("stop")
    enviar_velocidad()

    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
