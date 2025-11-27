"""
🎨 INTERFAZ MODERNA PARA CÁMARA ESP32 CON YOLO
Características:
- Detección de objetos con YOLO en tiempo real
- UI moderna con estadísticas, FPS, objetos detectados
- Visualización profesional de detecciones
"""

import socket
import struct
import time
import threading
import queue
import cv2
import numpy as np
import os
from datetime import datetime
from ultralytics import YOLO
import paho.mqtt.client as mqtt


class CamaraModerna:
    def __init__(self, control_event, port=5005):
        self.control_event = control_event
        self.port = port
        self.frame_queue = None
        self.frame_actual = None
        
        # YOLO
        self.yolo_enabled = False
        self.model = None
        self.detecciones = []
        
        # Seguimiento automático
        self.seguimiento_activo = False
        self.objeto_seguir = "person"  # Objeto por defecto a seguir
        self.objetos_disponibles = ["person", "car", "bicycle", "dog", "cat", "bottle", "cell phone", "laptop"]
        self.indice_objeto = 0
        
        # MQTT para control
        self.mqtt_client = None
        self.mqtt_conectado = False
        self.MQTT_BROKER = "192.168.1.102"
        self.MQTT_PORT = 1883
        self.ultimo_comando = None
        self.tiempo_ultimo_comando = 0
        
        # Estadísticas
        self.fps = 0
        self.frame_count = 0
        self.tiempo_inicio = time.time()
        self.objetos_totales = 0
        self.confianza_promedio = 0
        
        # Cargar YOLO
        print("🤖 Cargando modelo YOLOv11n...")
        try:
            self.model = YOLO('yolo11n.pt')
            print("✅ Modelo cargado correctamente")
        except Exception as e:
            print(f"⚠️ Error cargando YOLO: {e}")
    
    def iniciar_mqtt(self):
        """Inicia cliente MQTT para control autónomo"""
        try:
            self.mqtt_client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id="CamaraAutonoma"
            )
            self.mqtt_client.on_connect = self._on_connect
            self.mqtt_client.on_disconnect = self._on_disconnect
            self.mqtt_client.connect(self.MQTT_BROKER, self.MQTT_PORT, 60)
            self.mqtt_client.loop_start()
            time.sleep(1)
            return True
        except Exception as e:
            print(f"⚠️ MQTT no disponible: {e}")
            return False
    
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        self.mqtt_conectado = (rc == 0)
        if rc == 0:
            print("✅ MQTT conectado para control autónomo")
    
    def _on_disconnect(self, client, userdata, rc, properties=None):
        self.mqtt_conectado = False
    
    def enviar_comando(self, cmd):
        """Envía comando de movimiento vía MQTT"""
        ahora = time.time()
        if cmd == self.ultimo_comando and (ahora - self.tiempo_ultimo_comando) < 0.1:
            return
        
        self.ultimo_comando = cmd
        self.tiempo_ultimo_comando = ahora
        
        if self.mqtt_client and self.mqtt_conectado:
            try:
                self.mqtt_client.publish("rover/control", cmd, qos=0)
            except:
                pass
    
    def seguir_objeto(self, detecciones, frame_width, frame_height):
        """Lógica de seguimiento: calcula posición del objeto y envía comandos"""
        if not self.seguimiento_activo or not detecciones:
            self.enviar_comando("stop")
            return
        
        # Buscar el objeto que queremos seguir
        objetivo = None
        for det in detecciones:
            if det['clase'].lower() == self.objeto_seguir.lower():
                objetivo = det
                break
        
        if not objetivo:
            self.enviar_comando("stop")
            return
        
        # Calcular centro del objeto
        x1, y1, x2, y2 = objetivo['bbox']
        centro_x = (x1 + x2) / 2
        centro_y = (y1 + y2) / 2
        
        # Normalizar posición (0-1)
        pos_x = centro_x / frame_width
        
        # Área del objeto (para determinar distancia aproximada)
        area = (x2 - x1) * (y2 - y1)
        area_relativa = area / (frame_width * frame_height)
        
        # Lógica de control basada en posición
        ZONA_CENTRO = 0.15  # ±15% del centro
        AREA_OBJETIVO_MIN = 0.15  # 15% del frame
        AREA_OBJETIVO_MAX = 0.35  # 35% del frame
        
        # Decidir comando
        if pos_x < (0.5 - ZONA_CENTRO):
            # Objeto a la izquierda
            self.enviar_comando("left")
        elif pos_x > (0.5 + ZONA_CENTRO):
            # Objeto a la derecha
            self.enviar_comando("right")
        elif area_relativa < AREA_OBJETIVO_MIN:
            # Objeto muy lejos, acercarse
            self.enviar_comando("forward")
        elif area_relativa > AREA_OBJETIVO_MAX:
            # Objeto muy cerca, alejarse
            self.enviar_comando("backward")
        else:
            # Objeto centrado y a distancia correcta
            self.enviar_comando("stop")
    
    def obtener_socket_udp(self, port, rcvbuf=8388608):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, rcvbuf)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", port))
        sock.settimeout(1.0)
        return sock
    
    def start(self):
        self.frame_queue = queue.Queue(maxsize=1)
        
        # Iniciar MQTT
        self.iniciar_mqtt()
        
        hilo_udp = threading.Thread(target=self._recibir_video_udp, daemon=True)
        hilo_video = threading.Thread(target=self._mostrar_video_moderno, daemon=True)
        
        hilo_udp.start()
        hilo_video.start()
        
        return hilo_udp, hilo_video
    
    def _recibir_video_udp(self):
        sock = self.obtener_socket_udp(self.port)
        buffer = bytearray()
        expected_size = None
        ultimo_frame = time.time()
        sin_frames = 0
        
        while self.control_event.is_set():
            try:
                data, _ = sock.recvfrom(65535)
                
                # Primer paquete: tamaño (4 bytes)
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
                            # vaciar cola antigua
                            try:
                                while True:
                                    self.frame_queue.get_nowait()
                            except Exception:
                                pass
                            
                            try:
                                self.frame_queue.put_nowait(frame)
                                ultimo_frame = time.time()
                                sin_frames = 0
                            except Exception:
                                pass
                        
                        expected_size = None
                        buffer = bytearray()
                    
                    elif len(buffer) > expected_size + 50000:
                        # Buffer demasiado grande, resetear
                        buffer = bytearray()
                        expected_size = None
            
            except socket.timeout:
                if len(buffer) > 0:
                    buffer = bytearray()
                    expected_size = None
                
                sin_frames += 1
                if sin_frames == 5:
                    print("⚠️ Sin video (¿ESP32 CAM desconectado?)")
            
            except Exception:
                buffer = bytearray()
                expected_size = None
        
        sock.close()
    
    def _dibujar_interfaz_moderna(self, frame):
        """Dibuja interfaz moderna con estadísticas adaptada al tamaño"""
        h, w = frame.shape[:2]
        
        # Panel superior compacto - Estadísticas
        panel_altura = min(60, int(h * 0.2))
        cv2.rectangle(frame, (0, 0), (w, panel_altura), (30, 30, 30), -1)
        cv2.rectangle(frame, (0, 0), (w, panel_altura), (0, 255, 0), 1)
        
        # Título compacto
        titulo_size = min(0.5, w / 400)
        cv2.putText(frame, "ROVER VISION AI", (5, 15),
                   cv2.FONT_HERSHEY_SIMPLEX, titulo_size, (0, 255, 0), 1)
        
        # Stats en una línea
        stats_size = min(0.4, w / 600)
        stats_y = 35
        cv2.putText(frame, f"FPS:{self.fps:.0f}", (5, stats_y),
                   cv2.FONT_HERSHEY_SIMPLEX, stats_size, (255, 255, 255), 1)
        
        cv2.putText(frame, f"Obj:{len(self.detecciones)}", (int(w*0.25), stats_y),
                   cv2.FONT_HERSHEY_SIMPLEX, stats_size, (255, 255, 255), 1)
        
        # Estado YOLO
        estado_yolo = "Y:ON" if self.yolo_enabled else "Y:OFF"
        color_yolo = (0, 255, 0) if self.yolo_enabled else (128, 128, 128)
        cv2.putText(frame, estado_yolo, (int(w*0.5), stats_y),
                   cv2.FONT_HERSHEY_SIMPLEX, stats_size, color_yolo, 1)
        
        # Estado seguimiento (compacto)
        if self.seguimiento_activo:
            banner_h = min(40, int(h * 0.15))
            cv2.rectangle(frame, (0, h-banner_h), (w, h), (0, 100, 255), -1)
            cv2.rectangle(frame, (0, h-banner_h), (w, h), (0, 200, 255), 2)
            texto_size = min(0.5, w / 500)
            cv2.putText(frame, f"TRACK: {self.objeto_seguir.upper()}", 
                       (5, h-int(banner_h/2)+5), cv2.FONT_HERSHEY_SIMPLEX, texto_size, (255, 255, 255), 1)
        
        # Panel lateral - Lista de objetos (solo si hay espacio)
        if len(self.detecciones) > 0 and w > 400:
            item_h = min(20, int(h * 0.08))
            panel_w = min(150, int(w * 0.4))
            panel_x = w - panel_w - 5
            panel_y = panel_altura + 5
            total_h = min(len(self.detecciones) * item_h + 15, h - panel_altura - 50)
            
            cv2.rectangle(frame, (panel_x, panel_y), (w-5, panel_y + total_h), 
                         (40, 40, 40), -1)
            cv2.rectangle(frame, (panel_x, panel_y), (w-5, panel_y + total_h), 
                         (0, 255, 0), 1)
            
            text_size = min(0.35, w / 800)
            max_items = min(len(self.detecciones), int(total_h / item_h) - 1)
            
            for i, det in enumerate(self.detecciones[:max_items]):
                y = panel_y + 15 + i * item_h
                cv2.putText(frame, f"{det['clase'][:8]}: {det['conf']:.0f}%", 
                           (panel_x + 5, y), cv2.FONT_HERSHEY_SIMPLEX, text_size, (255, 255, 255), 1)
        
        # Controles en la parte inferior (compacto)
        if not self.seguimiento_activo:
            ctrl_h = min(18, int(h * 0.07))
            cv2.rectangle(frame, (0, h-ctrl_h), (w, h), (20, 20, 20), -1)
            ctrl_size = min(0.35, w / 700)
            controles = "D:YOLO A:Track TAB:Obj R:Rot ESC:Exit"
            cv2.putText(frame, controles, (5, h-5),
                       cv2.FONT_HERSHEY_SIMPLEX, ctrl_size, (200, 200, 200), 1)
        
        return frame
    
    def _mostrar_video_moderno(self):
        """Muestra video con interfaz moderna"""
        cv2.namedWindow("Rover Vision AI", cv2.WINDOW_AUTOSIZE)
        
        tiempo_fps = time.time()
        frames_fps = 0
        rotacion = 0
        
        while self.control_event.is_set():
            try:
                frame = self.frame_queue.get(timeout=0.05)
                
                if frame is not None and frame.size > 0:
                    # Aplicar rotación
                    if rotacion == 90:
                        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                    elif rotacion == 180:
                        frame = cv2.rotate(frame, cv2.ROTATE_180)
                    elif rotacion == 270:
                        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
                    
                    # Detección YOLO (solo si está habilitado)
                    if self.yolo_enabled and self.model is not None:
                        try:
                            # Confianza 0.45 para reducir falsos positivos
                            results = self.model.predict(frame, verbose=False, conf=0.45, iou=0.5)
                            
                            # Extraer detecciones
                            self.detecciones = []
                            confianzas = []
                            
                            for box in results[0].boxes:
                                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                                conf = float(box.conf[0])
                                cls = int(box.cls[0])
                                clase = results[0].names[cls]
                                
                                self.detecciones.append({
                                    'bbox': (int(x1), int(y1), int(x2), int(y2)),
                                    'conf': conf * 100,
                                    'clase': clase
                                })
                                confianzas.append(conf * 100)
                            
                            # Calcular confianza promedio
                            self.confianza_promedio = np.mean(confianzas) if confianzas else 0
                            
                            # Dibujar bounding boxes
                            frame = results[0].plot()
                            
                            # Seguimiento automático
                            h, w = frame.shape[:2]
                            self.seguir_objeto(self.detecciones, w, h)
                            
                        except Exception:
                            # Si YOLO falla, continuar mostrando video sin detección
                            self.detecciones = []
                    else:
                        # Limpiar detecciones si YOLO está desactivado
                        self.detecciones = []
                    
                    # Dibujar interfaz
                    frame = self._dibujar_interfaz_moderna(frame)
                    
                    # Calcular FPS
                    frames_fps += 1
                    if time.time() - tiempo_fps >= 1.0:
                        self.fps = frames_fps
                        frames_fps = 0
                        tiempo_fps = time.time()
                    
                    self.frame_actual = frame
                    cv2.imshow("Rover Vision AI", frame)
                
            except Exception:
                # Mostrar último frame válido o pantalla en gris con mensaje
                if self.frame_actual is not None:
                    cv2.imshow("Rover Vision AI", self.frame_actual)
                else:
                    # Crear frame gris con mensaje de espera
                    placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
                    placeholder[:] = (50, 50, 50)
                    cv2.putText(placeholder, "Esperando video del ESP32...", (120, 220),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
                    cv2.putText(placeholder, "Verifica que la camara este encendida", (100, 260),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 150), 1)
                    cv2.imshow("Rover Vision AI", placeholder)
            
            # Controles
            key = cv2.waitKey(1) & 0xFF
            
            if key == 27:  # ESC
                print("🛑 Cerrando...")
                if self.seguimiento_activo:
                    self.enviar_comando("stop")
                self.control_event.clear()
                break
            
            elif key == ord('d') or key == ord('D'):
                self.yolo_enabled = not self.yolo_enabled
                print(f"{'✅' if self.yolo_enabled else '❌'} YOLO: {'ON' if self.yolo_enabled else 'OFF'}")
            
            elif key == ord('a') or key == ord('A'):
                self.seguimiento_activo = not self.seguimiento_activo
                if not self.seguimiento_activo:
                    self.enviar_comando("stop")
                print(f"{'🎯' if self.seguimiento_activo else '⏸️'} Seguimiento: {'ACTIVO' if self.seguimiento_activo else 'DESACTIVADO'}")
            
            elif key == 9:  # TAB
                self.indice_objeto = (self.indice_objeto + 1) % len(self.objetos_disponibles)
                self.objeto_seguir = self.objetos_disponibles[self.indice_objeto]
                print(f"🎯 Objeto a seguir: {self.objeto_seguir}")
            
            elif key == ord('r') or key == ord('R'):
                rotacion = (rotacion + 90) % 360
                print(f"🔄 Rotación: {rotacion}°")
        
        # Detener rover al salir
        if self.seguimiento_activo:
            for _ in range(3):
                self.enviar_comando("stop")
                time.sleep(0.1)
        
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        
        cv2.destroyAllWindows()


def main():
    import signal
    
    print("=" * 70)
    print("🎨 ROVER VISION AI - INTERFAZ MODERNA CON SEGUIMIENTO AUTÓNOMO")
    print("=" * 70)
    print("📹 Puerto UDP: 5005")
    print("\n⌨️  CONTROLES:")
    print("   D → Activar/Desactivar YOLO")
    print("   A → Activar/Desactivar Seguimiento Automático")
    print("   TAB → Cambiar objeto a seguir")
    print("   R → Rotar cámara")
    print("   ESC → Salir")
    print("\n🎯 OBJETOS DISPONIBLES PARA SEGUIR:")
    print("   person, car, bicycle, dog, cat, bottle, cell phone, laptop")
    print("=" * 70)
    print()
    
    control_event = threading.Event()
    control_event.set()
    
    def signal_handler(sig, frame):
        print("\n\n🛑 Deteniendo...")
        control_event.clear()
    
    signal.signal(signal.SIGINT, signal_handler)
    
    camara = CamaraModerna(control_event, port=5005)
    hilo_udp, hilo_video = camara.start()
    
    try:
        hilo_udp.join()
        hilo_video.join()
    except KeyboardInterrupt:
        control_event.clear()
    
    print("✅ Programa terminado")


if __name__ == "__main__":
    main()
