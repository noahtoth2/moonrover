"""
🌐 SERVIDOR WEB PARA CÁMARA ROVER
Sirve video MJPEG y controla el rover vía web
"""

from flask import Flask, Response, render_template_string, jsonify, request
from flask_cors import CORS
import cv2
import socket
import struct
import threading
import time
import numpy as np
from ultralytics import YOLO
import paho.mqtt.client as mqtt

app = Flask(__name__)
CORS(app)

# Configuración
ESP32_UDP_PORT = 5005
MQTT_BROKER = "192.168.1.102"
MQTT_PORT = 1883

# Estado global
current_frame = None
yolo_enabled = False
tracking_enabled = False
rotation = 0
detections = []
fps = 0
frame_lock = threading.Lock()

# YOLO Model
print("🤖 Cargando modelo YOLO...")
yolo_model = YOLO('yolo11n.pt')
print("✅ Modelo cargado")

# MQTT Client
mqtt_client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id="WebInterface"
)

def on_connect(client, userdata, flags, rc, properties=None):
    print(f"✅ MQTT conectado" if rc == 0 else f"❌ MQTT error: {rc}")

mqtt_client.on_connect = on_connect

try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()
except Exception as e:
    print(f"⚠️ MQTT no disponible: {e}")


def receive_video_udp():
    """Recibe video del ESP32 por UDP"""
    global current_frame, fps
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8388608)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", ESP32_UDP_PORT))
    sock.settimeout(1.0)
    
    print(f"📡 Escuchando video UDP en puerto {ESP32_UDP_PORT}")
    
    buffer = bytearray()
    expected_size = None
    fps_counter = 0
    fps_time = time.time()
    
    while True:
        try:
            data, _ = sock.recvfrom(65535)
            
            # Primer paquete: tamaño
            if len(data) == 4 and expected_size is None:
                expected_size = struct.unpack("I", data)[0]
                if expected_size > 200000 or expected_size < 500:
                    expected_size = None
                    continue
                buffer = bytearray()
                continue
            
            if expected_size:
                buffer.extend(data)
                
                if len(buffer) >= expected_size:
                    frame = cv2.imdecode(
                        np.frombuffer(buffer[:expected_size], np.uint8),
                        cv2.IMREAD_COLOR
                    )
                    
                    if frame is not None:
                        # Aplicar rotación
                        if rotation == 90:
                            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                        elif rotation == 180:
                            frame = cv2.rotate(frame, cv2.ROTATE_180)
                        elif rotation == 270:
                            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
                        
                        # YOLO si está habilitado
                        if yolo_enabled:
                            process_yolo(frame)
                        
                        with frame_lock:
                            current_frame = frame.copy()
                        
                        # Calcular FPS
                        fps_counter += 1
                        if time.time() - fps_time >= 1.0:
                            fps = fps_counter
                            fps_counter = 0
                            fps_time = time.time()
                    
                    expected_size = None
                    buffer = bytearray()
                
                elif len(buffer) > expected_size + 50000:
                    buffer = bytearray()
                    expected_size = None
        
        except socket.timeout:
            if len(buffer) > 0:
                buffer = bytearray()
                expected_size = None
        except Exception as e:
            pass


def process_yolo(frame):
    """Procesa frame con YOLO"""
    global detections
    
    try:
        results = yolo_model.predict(frame, verbose=False, conf=0.45, iou=0.5)
        
        detections = []
        for box in results[0].boxes:
            conf = float(box.conf[0])
            cls = int(box.cls[0])
            name = results[0].names[cls]
            
            detections.append({
                'name': name,
                'confidence': round(conf * 100, 1)
            })
    except Exception:
        detections = []


def generate_frames():
    """Genera stream MJPEG"""
    global current_frame
    
    while True:
        with frame_lock:
            if current_frame is not None:
                frame = current_frame.copy()
            else:
                # Frame placeholder
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, "Esperando video ESP32...", (150, 240),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Codificar como JPEG
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        frame_bytes = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        time.sleep(0.033)  # ~30 FPS


@app.route('/')
def index():
    """Sirve la interfaz HTML"""
    with open('web/camera_vision.html', 'r', encoding='utf-8') as f:
        html = f.read()
    
    # Reemplazar placeholder de video
    html = html.replace(
        "simulateVideoFrame();",
        "// Video stream real desde /video_feed"
    )
    html = html.replace(
        '<canvas id="videoCanvas"></canvas>',
        '<img id="videoCanvas" src="/video_feed" style="width: 100%; height: auto; border-radius: 10px;">'
    )
    
    return html


@app.route('/video_feed')
def video_feed():
    """Stream de video MJPEG"""
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/stats')
def get_stats():
    """Obtiene estadísticas en tiempo real"""
    return jsonify({
        'fps': fps,
        'yolo_enabled': yolo_enabled,
        'tracking_enabled': tracking_enabled,
        'rotation': rotation,
        'detections': detections,
        'object_count': len(detections)
    })


@app.route('/api/command', methods=['POST'])
def send_command():
    """Envía comandos MQTT"""
    global yolo_enabled, tracking_enabled, rotation
    
    data = request.json
    command = data.get('command', '')
    
    if command == 'yolo_on':
        yolo_enabled = True
    elif command == 'yolo_off':
        yolo_enabled = False
    elif command == 'tracking_on':
        tracking_enabled = True
    elif command == 'tracking_off':
        tracking_enabled = False
    elif command.startswith('rotate_'):
        rotation = int(command.split('_')[1])
    elif command in ['forward', 'backward', 'left', 'right', 'stop']:
        mqtt_client.publish('rover/control', command, qos=0)
    
    return jsonify({'status': 'ok', 'command': command})


if __name__ == '__main__':
    # Iniciar thread de recepción de video
    video_thread = threading.Thread(target=receive_video_udp, daemon=True)
    video_thread.start()
    
    print("\n" + "=" * 60)
    print("🌐 SERVIDOR WEB ROVER VISION AI")
    print("=" * 60)
    print(f"📡 Recibiendo video UDP en puerto: {ESP32_UDP_PORT}")
    print(f"🌐 Interfaz web: http://localhost:5000")
    print(f"📹 Stream MJPEG: http://localhost:5000/video_feed")
    print(f"📊 API Stats: http://localhost:5000/api/stats")
    print("=" * 60)
    print()
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
