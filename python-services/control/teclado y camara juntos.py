import keyboard
import threading
import time
import paho.mqtt.client as mqtt

# ============================
# CONFIGURACIÓN
# ============================
# Configuración MQTT
MQTT_BROKER = "192.168.1.102"  # IP de tu PC (donde corre el broker)
MQTT_PORT = 1883
MQTT_TOPIC_CONTROL = "rover/control"
MQTT_TOPIC_SPEED = "rover/speed"
MQTT_CLIENT_ID = "RoverController"

# Timeout de reconexión
MQTT_RECONNECT_DELAY = 5  # segundos

# ============================
# VARIABLES GLOBALES
# ============================
control_activo = threading.Event()
control_activo.set()

mqtt_client = None
mqtt_conectado = False

ultimo_comando = None
tiempo_ultimo_comando = 0

velocidad_pwm = 800   # Valor inicial (0–1023)
VELOCIDAD_MIN = 750
VELOCIDAD_MAX = 2000
PASO_VEL = 50

# Control de debounce para teclas de velocidad
ultimo_cambio_velocidad = 0
DEBOUNCE_VELOCIDAD = 0.15

# ============================
# MQTT
# ============================
def on_mqtt_connect(client, userdata, flags, rc, properties=None):
    """Callback de conexión MQTT"""
    global mqtt_conectado
    mqtt_conectado = (rc == 0)
    if rc == 0:
        print("✅ MQTT Conectado")
        # Reenviar velocidad al reconectar (evitar llamar si mqtt_client no está listo)
        time.sleep(0.1)  # Pequeña pausa para asegurar que la conexión esté lista
        try:
            enviar_velocidad()
        except:
            pass  # Si falla, se reenviará en el main
    else:
        print(f"❌ Error MQTT conexión (código {rc})")


def on_mqtt_disconnect(client, userdata, rc, properties=None):
    """Callback de desconexión con intento de reconexión"""
    global mqtt_conectado
    mqtt_conectado = False
    if rc != 0:
        print(f"⚠️ MQTT desconectado inesperadamente (código {rc})")
        print("🔄 Reintentando conexión automática...")
    else:
        print("⚠️ MQTT desconectado")


def iniciar_mqtt():
    """Inicia cliente MQTT con auto-reconexión"""
    global mqtt_client
    try:
        mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=MQTT_CLIENT_ID)
        mqtt_client.on_connect = on_mqtt_connect
        mqtt_client.on_disconnect = on_mqtt_disconnect
        
        # Habilitar reconexión automática
        mqtt_client.reconnect_delay_set(min_delay=1, max_delay=MQTT_RECONNECT_DELAY)
        
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        return True
    except Exception as e:
        print(f"❌ Error MQTT: {e}")
        return False


def enviar_mqtt(topic, payload):
    """Envía mensaje MQTT con manejo de errores mejorado"""
    if mqtt_client and mqtt_conectado:
        try:
            # QoS 0 = fire-and-forget, no espera ACK, no bloquea
            result = mqtt_client.publish(topic, payload, qos=0)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                print(f"⚠️ Error publicando en {topic}: código {result.rc}")
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            print(f"⚠️ Excepción publicando MQTT: {e}")
            return False
    elif not mqtt_conectado and mqtt_client:
        # No llamar a reconnect() desde el hilo principal (puede bloquear).
        # Confiar en loop_start() + reconnect_delay_set() para reintentos automáticos.
        # Si quieres forzar reconexión no bloqueante, podríamos iniciar un hilo dedicado.
        print("⚠️ Intento de publicar mientras MQTT desconectado; omitiendo envío")
        return False
    else:
        return False


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
    """Hilo principal de control por teclado con manejo mejorado"""
    global velocidad_pwm, ultimo_cambio_velocidad

    ultima_tecla = None
    contador_heartbeat = 0
    print("✅ Control de teclado iniciado")

    while control_activo.is_set():
        try:
            # Salir
            if keyboard.is_pressed("esc"):
                print("🛑 ESC presionado - Saliendo...")
                enviar_comando("stop")
                break

            # CONTROL DE VELOCIDAD → Z / X (con debounce)
            ahora = time.time()
            if ahora - ultimo_cambio_velocidad > DEBOUNCE_VELOCIDAD:
                if keyboard.is_pressed("z"):
                    velocidad_pwm = min(velocidad_pwm + PASO_VEL, VELOCIDAD_MAX)
                    enviar_velocidad()
                    ultimo_cambio_velocidad = ahora

                elif keyboard.is_pressed("x"):
                    velocidad_pwm = max(velocidad_pwm - PASO_VEL, VELOCIDAD_MIN)
                    enviar_velocidad()
                    ultimo_cambio_velocidad = ahora

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

            # Enviar comando solo si cambió o como heartbeat cada 2s
            if tecla != ultima_tecla:
                enviar_comando(tecla)
                ultima_tecla = tecla
                contador_heartbeat = 0
            else:
                contador_heartbeat += 1
                # Heartbeat cada ~5s (250 iteraciones * 0.02s) para evitar saturar
                if contador_heartbeat >= 250:
                    enviar_comando(tecla)
                    contador_heartbeat = 0

            time.sleep(0.02)

        except KeyboardInterrupt:
            print("\n⚠️ Interrupción de teclado detectada")
            enviar_comando("stop")
            break
        except Exception as e:
            print(f"❌ Error en control_teclado: {e}")
            enviar_comando("stop")
            break

    # Envío de seguridad al salir
    print("🛑 Enviando comandos de parada de seguridad...")
    for _ in range(3):
        enviar_comando("stop")
        time.sleep(0.1)


# ============================
# MAIN
# ============================
if __name__ == "__main__":
    print("=" * 50)
    print("🎮 CONTROL ROVER - MQTT + VELOCIDAD PWM")
    print("=" * 50)
    print("🔼 MOVER: Flechas ↑ ↓ ← →")
    print("⚡ VELOCIDAD: Z = subir / X = bajar")
    print(f"📊 Rango velocidad: {VELOCIDAD_MIN} - {VELOCIDAD_MAX}")
    print(f"📈 Paso: {PASO_VEL}")
    print("❌ ESC = salir")
    print("=" * 50)
    print()

    print(f"🔌 Conectando a broker MQTT: {MQTT_BROKER}:{MQTT_PORT}")
    if not iniciar_mqtt():
        print("❌ No se pudo iniciar MQTT. Verifica el broker.")
        exit(1)

    # Esperar conexión
    timeout = 5
    for i in range(timeout * 2):
        if mqtt_conectado:
            break
        time.sleep(0.5)
        if i % 2 == 0:  # Cada segundo
            print(".", end="", flush=True)
    print()

    if not mqtt_conectado:
        print("❌ Timeout conectando a MQTT")
        exit(1)

    print("✅ MQTT conectado")
    enviar_velocidad()
    time.sleep(0.2)

    try:
        hilo = threading.Thread(target=control_teclado, daemon=True)
        hilo.start()
        hilo.join()
    except KeyboardInterrupt:
        print("\n⚠️ Ctrl+C detectado")

    print("\n🛑 Deteniendo rover…")
    for _ in range(3):
        enviar_comando("stop")
        time.sleep(0.1)

    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        print("✅ MQTT desconectado")

    print("👋 Programa terminado")
