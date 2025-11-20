"""
🚀 BROKER MQTT PURO EN PYTHON - TU PC ES EL SERVIDOR
Broker MQTT completo sin dependencias externas
"""

import socket
import threading
import struct
import time

# =================== CONFIGURACIÓN ===================
BROKER_HOST = "0.0.0.0"
BROKER_PORT = 1883

def obtener_ip_local():
    """Obtiene la IP local de la PC"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

# =================== BROKER MQTT SIMPLE ===================
class SimpleMQTTBroker:
    def __init__(self, host="0.0.0.0", port=1883):
        self.host = host
        self.port = port
        self.clients = {}  # {socket: client_info}
        self.subscriptions = {}  # {topic: [sockets]}
        self.running = True
        
    def iniciar(self):
        """Inicia el broker MQTT"""
        ip_local = obtener_ip_local()
        
        print("=" * 60)
        print("🚀 TU PC AHORA ES UN BROKER MQTT")
        print("=" * 60)
        print(f"📡 Escuchando en: {ip_local}:{self.port}")
        print(f"📋 Topic del rover: rover/control")
        print("")
        print("COPIA ESTAS IPs EN TUS ARCHIVOS:")
        print("-" * 60)
        print(f"  Python → MQTT_BROKER = '{ip_local}'")
        print(f"  ESP32  → mqtt_server = \"{ip_local}\"")
        print("-" * 60)
        print("")
        print("✅ Broker MQTT listo y corriendo")
        print("📊 Monitoreando mensajes...\n")
        print("⌨️  Presiona Ctrl+C para detener")
        print("=" * 60)
        print("")
        
        # Crear socket del servidor
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen(5)
        server.settimeout(1.0)  # Timeout para poder detectar Ctrl+C
        
        try:
            while self.running:
                try:
                    client_socket, addr = server.accept()
                    print(f"🔌 Nuevo cliente: {addr[0]}:{addr[1]}")
                    
                    # Crear hilo para manejar cliente
                    client_thread = threading.Thread(
                        target=self.manejar_cliente,
                        args=(client_socket, addr),
                        daemon=True
                    )
                    client_thread.start()
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"⚠️ Error aceptando cliente: {e}")
                        
        except KeyboardInterrupt:
            print("\n\n👋 Deteniendo broker...")
        finally:
            self.running = False
            server.close()
            print("✅ Broker detenido")
    
    def manejar_cliente(self, client_socket, addr):
        """Maneja un cliente MQTT"""
        try:
            client_socket.settimeout(60.0)
            self.clients[client_socket] = {"addr": addr, "id": None}
            
            while self.running:
                try:
                    # Leer paquete MQTT
                    data = client_socket.recv(4096)
                    if not data:
                        break
                    
                    # Procesar paquete MQTT
                    self.procesar_paquete(client_socket, data)
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    break
                    
        except Exception as e:
            pass
        finally:
            # Limpiar cliente
            if client_socket in self.clients:
                client_id = self.clients[client_socket].get("id", "unknown")
                print(f"❌ Cliente desconectado: {client_id} ({addr[0]})")
                del self.clients[client_socket]
            
            # Limpiar suscripciones
            for topic in list(self.subscriptions.keys()):
                if client_socket in self.subscriptions[topic]:
                    self.subscriptions[topic].remove(client_socket)
            
            try:
                client_socket.close()
            except:
                pass
    
    def procesar_paquete(self, client_socket, data):
        """Procesa un paquete MQTT"""
        if len(data) < 2:
            return
        
        packet_type = (data[0] >> 4) & 0x0F
        
        # CONNECT (1)
        if packet_type == 1:
            self.handle_connect(client_socket, data)
        
        # PUBLISH (3)
        elif packet_type == 3:
            self.handle_publish(client_socket, data)
        
        # SUBSCRIBE (8)
        elif packet_type == 8:
            self.handle_subscribe(client_socket, data)
        
        # PINGREQ (12)
        elif packet_type == 12:
            self.handle_pingreq(client_socket)
        
        # DISCONNECT (14)
        elif packet_type == 14:
            pass
    
    def handle_connect(self, client_socket, data):
        """Maneja CONNECT"""
        try:
            # Extraer client ID (simplificado)
            idx = 10  # Saltar header fijo de MQTT
            if len(data) > idx + 2:
                client_id_len = struct.unpack(">H", data[idx:idx+2])[0]
                client_id = data[idx+2:idx+2+client_id_len].decode('utf-8', errors='ignore')
                self.clients[client_socket]["id"] = client_id
                print(f"✅ CONNECT: {client_id}")
            
            # Enviar CONNACK (aceptar conexión)
            connack = bytes([0x20, 0x02, 0x00, 0x00])
            client_socket.send(connack)
            
        except Exception as e:
            print(f"⚠️ Error en CONNECT: {e}")
    
    def handle_subscribe(self, client_socket, data):
        """Maneja SUBSCRIBE"""
        try:
            # Extraer topic (simplificado - solo 1 topic)
            idx = 2  # Saltar header
            
            # Leer packet ID
            if len(data) < idx + 2:
                return
            packet_id = struct.unpack(">H", data[idx:idx+2])[0]
            idx += 2
            
            # Leer topic
            if len(data) < idx + 2:
                return
            topic_len = struct.unpack(">H", data[idx:idx+2])[0]
            idx += 2
            
            if len(data) < idx + topic_len:
                return
            topic = data[idx:idx+topic_len].decode('utf-8', errors='ignore')
            
            # Agregar suscripción
            if topic not in self.subscriptions:
                self.subscriptions[topic] = []
            if client_socket not in self.subscriptions[topic]:
                self.subscriptions[topic].append(client_socket)
            
            client_id = self.clients[client_socket].get("id", "unknown")
            print(f"📡 SUBSCRIBE: {client_id} → {topic}")
            
            # Enviar SUBACK
            suback = bytes([0x90, 0x03]) + struct.pack(">H", packet_id) + bytes([0x00])
            client_socket.send(suback)
            
        except Exception as e:
            print(f"⚠️ Error en SUBSCRIBE: {e}")
    
    def handle_publish(self, client_socket, data):
        """Maneja PUBLISH y retransmite a suscriptores"""
        try:
            # Extraer topic y mensaje
            idx = 2  # Saltar header (simplificado)
            
            # Leer topic
            if len(data) < idx + 2:
                return
            topic_len = struct.unpack(">H", data[idx:idx+2])[0]
            idx += 2
            
            if len(data) < idx + topic_len:
                return
            topic = data[idx:idx+topic_len].decode('utf-8', errors='ignore')
            idx += topic_len
            
            # El resto es el mensaje
            mensaje = data[idx:].decode('utf-8', errors='ignore')
            
            client_id = self.clients[client_socket].get("id", "unknown")
            print(f"📩 PUBLISH: {client_id} → [{topic}] {mensaje}")
            
            # Retransmitir a suscriptores
            if topic in self.subscriptions:
                for subscriber in self.subscriptions[topic]:
                    if subscriber != client_socket and subscriber in self.clients:
                        try:
                            subscriber.send(data)
                        except:
                            pass
            
        except Exception as e:
            print(f"⚠️ Error en PUBLISH: {e}")
    
    def handle_pingreq(self, client_socket):
        """Maneja PINGREQ (keepalive)"""
        try:
            # Enviar PINGRESP
            pingresp = bytes([0xD0, 0x00])
            client_socket.send(pingresp)
        except:
            pass

if __name__ == "__main__":
    broker = SimpleMQTTBroker(host=BROKER_HOST, port=BROKER_PORT)
    broker.iniciar()
