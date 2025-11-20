"""
🎓 CAPTURA DE DATASET DESDE EL ROVER
Captura imágenes desde la cámara del rover y etiquétalas en categorías
"""
import socket
import struct
import cv2
import numpy as np
import os
from datetime import datetime
import time


def obtener_socket_udp(port, rcvbuf=8388608):
    """Configura socket UDP para recibir video"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, rcvbuf)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", port))
    sock.settimeout(1.0)
    return sock


class DatasetCapture:
    def __init__(self, dataset_path="dataset_rover", port=5005):
        self.port = port
        self.dataset_path = dataset_path
        self.categorias = {
            '1': 'excavacion',
            '2': 'construccion',
            '3': 'peligro',
            '4': 'zona_libre',
            '5': 'objetivo',
            '6': 'obstaculo',
            '7': 'otro'
        }
        
        # Emojis para cada categoría
        self.emojis = {
            'excavacion': '⛏️',
            'construccion': '🏗️',
            'peligro': '⚠️',
            'zona_libre': '✅',
            'objetivo': '🎯',
            'obstaculo': '🚧',
            'otro': '📦'
        }
        
        # Contadores
        self.contadores = {cat: 0 for cat in self.categorias.values()}
        
        # Crear directorios si no existen
        self._crear_directorios()
        
        # Cargar contadores existentes
        self._cargar_contadores()
        
        print("=" * 70)
        print("  📸 CAPTURA DE DATASET DESDE EL ROVER")
        print("=" * 70)
        print(f"📁 Dataset guardado en: {os.path.abspath(self.dataset_path)}")
        print(f"🎥 Puerto UDP: {self.port}")
        print("=" * 70)
        print("\n📋 CATEGORÍAS DISPONIBLES:")
        for key, cat in self.categorias.items():
            emoji = self.emojis[cat]
            count = self.contadores[cat]
            print(f"  [{key}] {emoji} {cat.upper():15} ({count} imágenes)")
        print("\n⌨️  CONTROLES:")
        print("  1-7     → Capturar imagen en categoría")
        print("  R       → Rotar cámara 90°")
        print("  S       → Ver estadísticas")
        print("  ESC     → Salir")
        print("=" * 70 + "\n")
    
    def _crear_directorios(self):
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
        print(f"✅ {emoji} Guardada en '{categoria}': {filename} (Total: {self.contadores[categoria]})")
    
    def mostrar_estadisticas(self):
        """Muestra estadísticas del dataset"""
        print("\n" + "=" * 70)
        print("  📊 ESTADÍSTICAS DEL DATASET")
        print("=" * 70)
        
        total = sum(self.contadores.values())
        print(f"\n📦 TOTAL DE IMÁGENES: {total}\n")
        
        for categoria in sorted(self.categorias.values()):
            emoji = self.emojis[categoria]
            count = self.contadores[categoria]
            if total > 0:
                porcentaje = (count / total) * 100
                barra = "█" * int(porcentaje / 2) + "░" * (50 - int(porcentaje / 2))
                print(f"{emoji} {categoria.upper():15} │ {barra} │ {count:4} ({porcentaje:5.1f}%)")
            else:
                print(f"{emoji} {categoria.upper():15} │ {'░' * 50} │    0 (  0.0%)")
        
        print("\n" + "=" * 70 + "\n")
    
    def recibir_video_udp(self):
        """Recibe video UDP y permite capturar imágenes"""
        sock = obtener_socket_udp(self.port)
        
        buffer = bytearray()
        expected_size = None
        frame_actual = None
        rotacion = 0
        
        cv2.namedWindow("CAPTURA DE DATASET - Rover", cv2.WINDOW_AUTOSIZE)
        
        # Texto de ayuda en pantalla
        ultima_captura = ""
        tiempo_ultima_captura = 0
        
        while True:
            try:
                # Recibir datos UDP
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
                            if rotacion == 90:
                                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                            elif rotacion == 180:
                                frame = cv2.rotate(frame, cv2.ROTATE_180)
                            elif rotacion == 270:
                                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
                            
                            frame_actual = frame.copy()
                        
                        expected_size = None
                        buffer = bytearray()
            
            except socket.timeout:
                pass
            except Exception as e:
                pass
            
            # Mostrar frame con overlay
            if frame_actual is not None:
                display_frame = frame_actual.copy()
                
                # Panel de información
                overlay = display_frame.copy()
                h, w = display_frame.shape[:2]
                
                # Fondo semitransparente para el texto
                cv2.rectangle(overlay, (0, 0), (w, 120), (0, 0, 0), -1)
                cv2.addWeighted(overlay, 0.6, display_frame, 0.4, 0, display_frame)
                
                # Título
                cv2.putText(display_frame, "CAPTURA DE DATASET", (10, 25),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                # Instrucciones
                cv2.putText(display_frame, "Presiona 1-7 para capturar", (10, 50),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                cv2.putText(display_frame, "R=Rotar | S=Stats | ESC=Salir", (10, 70),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                
                # Total de imágenes
                total = sum(self.contadores.values())
                cv2.putText(display_frame, f"Total: {total} imagenes", (10, 95),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                
                # Rotación actual
                cv2.putText(display_frame, f"Rotacion: {rotacion}", (10, 115),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                
                # Mensaje de última captura (desaparece después de 2 segundos)
                if ultima_captura and (time.time() - tiempo_ultima_captura < 2):
                    cv2.putText(display_frame, ultima_captura, (w // 2 - 150, h // 2),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                
                cv2.imshow("CAPTURA DE DATASET - Rover", display_frame)
            
            # Procesar teclas
            key = cv2.waitKey(1) & 0xFF
            
            if key == 27:  # ESC
                print("\n🛑 Saliendo...")
                break
            
            elif key == ord('r') or key == ord('R'):
                rotacion = (rotacion + 90) % 360
                print(f"🔄 Rotación: {rotacion}°")
            
            elif key == ord('s') or key == ord('S'):
                self.mostrar_estadisticas()
            
            elif chr(key) in self.categorias:
                if frame_actual is not None:
                    categoria = self.categorias[chr(key)]
                    self.guardar_imagen(frame_actual, categoria)
                    emoji = self.emojis[categoria]
                    ultima_captura = f"{emoji} Capturada: {categoria.upper()}"
                    tiempo_ultima_captura = time.time()
                else:
                    print("⚠️ No hay frame disponible")
        
        sock.close()
        cv2.destroyAllWindows()
        
        # Mostrar estadísticas finales
        self.mostrar_estadisticas()
        print("✅ Dataset capturado exitosamente")
        print(f"📁 Ubicación: {os.path.abspath(self.dataset_path)}\n")


def main():
    """Función principal"""
    # Configuración
    DATASET_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "dataset_rover")
    PORT = 5005
    
    # Crear capturador
    capturador = DatasetCapture(dataset_path=DATASET_PATH, port=PORT)
    
    # Iniciar captura
    capturador.recibir_video_udp()


if __name__ == "__main__":
    main()
