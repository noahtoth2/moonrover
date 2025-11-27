import socket
import struct
import time
import threading
import cv2
import numpy as np
import os
from datetime import datetime
from ultralytics import YOLO


def obtener_socket_udp(port, rcvbuf=8388608):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, rcvbuf)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", port))
    sock.settimeout(1.0)
    return sock


class CameraClient:
    def __init__(self, control_event, port=5005, dataset_path="dataset_rover"):
        self.control_event = control_event
        self.port = port
        self.frame_queue = None
        self.frame_actual = None
        self.rotacion_actual = 0
        self.yolo_enabled = False
        self.model = None
        
        # Sistema de captura de dataset
        self.dataset_path = dataset_path
        self.modo_captura = False
        self.frame_capturado = None
        self.categorias = {
            '1': 'excavacion',
            '2': 'construccion',
            '3': 'peligro',
            '4': 'zona_libre',
            '5': 'objetivo',
            '6': 'obstaculo',
            '7': 'otro'
        }
        self.emojis = {
            'excavacion': '⛏️',
            'construccion': '🏗️',
            'peligro': '⚠️',
            'zona_libre': '✅',
            'objetivo': '🎯',
            'obstaculo': '🚧',
            'otro': '📦'
        }
        self.contadores = {cat: 0 for cat in self.categorias.values()}
        self._crear_directorios_dataset()
        self._cargar_contadores()
        
        # Cargar modelo YOLO
        print("🤖 Cargando modelo YOLOv11n (rápido)...")
        try:
            self.model = YOLO('yolo11n.pt')
            print("✅ Modelo YOLOv11n cargado correctamente")
        except Exception as e:
            print(f"⚠️ Error al cargar YOLO: {e}")
            print("   La detección de objetos no estará disponible")
    
    def _crear_directorios_dataset(self):
        """Crea estructura de directorios para el dataset"""
        if not os.path.exists(self.dataset_path):
            os.makedirs(self.dataset_path)
        
        for categoria in self.categorias.values():
            cat_path = os.path.join(self.dataset_path, categoria)
            if not os.path.exists(cat_path):
                os.makedirs(cat_path)
    
    def _cargar_contadores(self):
        """Cuenta imágenes existentes en cada categoría"""
        for categoria in self.categorias.values():
            cat_path = os.path.join(self.dataset_path, categoria)
            if os.path.exists(cat_path):
                archivos = [f for f in os.listdir(cat_path) if f.endswith(('.jpg', '.png'))]
                self.contadores[categoria] = len(archivos)
    
    def guardar_imagen(self, frame, categoria):
        """Guarda imagen en la categoría especificada"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{categoria}_{timestamp}.jpg"
        filepath = os.path.join(self.dataset_path, categoria, filename)
        
        cv2.imwrite(filepath, frame)
        self.contadores[categoria] += 1
        
        emoji = self.emojis[categoria]
        print(f"\n✅ {emoji} Guardada en '{categoria}': {filename}")
        print(f"   Total en {categoria}: {self.contadores[categoria]} imágenes")
        
        # Mostrar total general
        total = sum(self.contadores.values())
        print(f"   📦 TOTAL GENERAL: {total} imágenes\n")

    def start(self):
        # cola interna de frames (max 1 para baja latencia)
        import queue
        self.frame_queue = queue.Queue(maxsize=1)

        hilo_udp = threading.Thread(target=self._recibir_video_udp, daemon=True)
        hilo_video = threading.Thread(target=self._mostrar_video, daemon=True)

        hilo_udp.start()
        hilo_video.start()

        # no hacemos join aquí (daemon threads)
        return hilo_udp, hilo_video

    def _recibir_video_udp(self):
        sock = obtener_socket_udp(self.port)

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

    def _mostrar_video(self):
        cv2.namedWindow("ESP32-CAM", cv2.WINDOW_AUTOSIZE)

        while self.control_event.is_set():
            try:
                frame = self.frame_queue.get(timeout=0.05)

                if frame is not None and frame.size > 0:
                    # Aplicar rotación primero
                    if self.rotacion_actual == 90:
                        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                    elif self.rotacion_actual == 180:
                        frame = cv2.rotate(frame, cv2.ROTATE_180)
                    elif self.rotacion_actual == 270:
                        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

                    # Aplicar detección YOLO si está activada
                    if self.yolo_enabled and self.model is not None:
                        try:
                            results = self.model.predict(frame, verbose=False, conf=0.25)
                            frame = results[0].plot()  # Dibuja bounding boxes y labels
                            
                            # Indicador visual en pantalla
                            cv2.putText(frame, "YOLO: ON", (10, 30), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                            cv2.putText(frame, f"Objetos: {len(results[0].boxes)}", (10, 60), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                        except Exception as e:
                            # Mostrar error en pantalla
                            cv2.putText(frame, f"YOLO ERROR: {str(e)[:30]}", (10, 30), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                    else:
                        # Indicador cuando YOLO está OFF
                        if not self.yolo_enabled:
                            cv2.putText(frame, "YOLO: OFF (Presiona D)", (10, 30), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (128, 128, 128), 2)
                    
                    # Modo captura: Mostrar instrucciones
                    if self.modo_captura:
                        # Fondo semitransparente
                        overlay = frame.copy()
                        h, w = frame.shape[:2]
                        cv2.rectangle(overlay, (0, h-180), (w, h), (0, 0, 0), -1)
                        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
                        
                        # Instrucciones
                        cv2.putText(frame, "CAPTURA - Elige categoria:", (10, h-150), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                        cv2.putText(frame, "1:Excavacion 2:Construccion 3:Peligro 4:Zona Libre", (10, h-120), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                        cv2.putText(frame, "5:Objetivo 6:Obstaculo 7:Otro | ESC:Cancelar", (10, h-95), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                        
                        # Contadores
                        total = sum(self.contadores.values())
                        cv2.putText(frame, f"Total imagenes: {total}", (10, h-60), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                        
                        # Mini resumen
                        resumen = f"1:{self.contadores['excavacion']} 2:{self.contadores['construccion']} 3:{self.contadores['peligro']} 4:{self.contadores['zona_libre']}"
                        cv2.putText(frame, resumen, (10, h-35), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
                        resumen2 = f"5:{self.contadores['objetivo']} 6:{self.contadores['obstaculo']} 7:{self.contadores['otro']}"
                        cv2.putText(frame, resumen2, (10, h-10), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
                    else:
                        # Indicador de captura disponible
                        total = sum(self.contadores.values())
                        if total > 0:
                            cv2.putText(frame, f"Dataset: {total} imgs (ESPACIO=Capturar)", (10, 90), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                    self.frame_actual = frame
                    cv2.imshow("ESP32-CAM", frame)
            except Exception:
                if self.frame_actual is not None:
                    cv2.imshow("ESP32-CAM", self.frame_actual)

            key = cv2.waitKey(1) & 0xFF
            
            # Modo captura activo - esperar categoría
            if self.modo_captura:
                if key == 27:  # ESC - Cancelar captura
                    self.modo_captura = False
                    self.frame_capturado = None
                    print("❌ Captura cancelada\n")
                elif chr(key) in self.categorias:
                    # Guardar en categoría seleccionada
                    categoria = self.categorias[chr(key)]
                    if self.frame_capturado is not None:
                        self.guardar_imagen(self.frame_capturado, categoria)
                        self.modo_captura = False
                        self.frame_capturado = None
            
            # Modo normal
            else:
                if key == 27:  # ESC - Salir
                    self.control_event.clear()
                    break
                elif key == ord(' '):  # ESPACIO - Capturar
                    if self.frame_actual is not None:
                        self.frame_capturado = self.frame_actual.copy()
                        self.modo_captura = True
                        print("\n" + "=" * 60)
                        print("📸 FOTO CAPTURADA - Selecciona categoría:")
                        print("=" * 60)
                        for k, cat in self.categorias.items():
                            emoji = self.emojis[cat]
                            count = self.contadores[cat]
                            print(f"  [{k}] {emoji} {cat.upper():15} ({count} imágenes)")
                        print("\n  [ESC] Cancelar")
                        print("=" * 60 + "\n")
                elif key == ord('r') or key == ord('R'):
                    self.rotacion_actual = (self.rotacion_actual + 90) % 360
                    print(f"🔄 Rotación: {self.rotacion_actual}°")
                elif key == ord('d') or key == ord('D'):
                    self.yolo_enabled = not self.yolo_enabled
                    print("\n" + "=" * 50)
                    if self.yolo_enabled:
                        print("🤖 DETECCIÓN DE OBJETOS ACTIVADA ✅")
                        print("   - Verás bounding boxes en objetos detectados")
                        print("   - Indicador 'YOLO: ON' en pantalla")
                    else:
                        print("⚪ DETECCIÓN DE OBJETOS DESACTIVADA ❌")
                        print("   - Video normal sin detección")
                    print("=" * 50 + "\n")

        cv2.destroyAllWindows()


def start_camera(control_event, port=5005):
    cam = CameraClient(control_event, port=port)
    return cam.start()


# ============================
# EJECUCIÓN INDEPENDIENTE
# ============================
if __name__ == "__main__":
    import signal
    
    print("=" * 60)
    print("📹 CLIENTE DE CÁMARA ROVER CON IA + CAPTURA DATASET")
    print("=" * 60)
    print("🎥 Puerto UDP: 5005")
    print("⌨️  ESPACIO → Capturar imagen para dataset")
    print("⌨️  D → Activar/desactivar YOLO")
    print("⌨️  R → Rotar cámara (0° → 90° → 180° → 270°)")
    print("⌨️  ESC → Salir")
    print("=" * 60)
    print("")
    
    control_event = threading.Event()
    control_event.set()
    
    # Manejar Ctrl+C
    def signal_handler(sig, frame):
        print("\n\n🛑 Deteniendo cámara...")
        control_event.clear()
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Iniciar cámara
    hilo_udp, hilo_video = start_camera(control_event, port=5005)
    
    # Esperar a que terminen
    try:
        hilo_udp.join()
        hilo_video.join()
    except KeyboardInterrupt:
        control_event.clear()
    
    print("✅ Cámara detenida")
