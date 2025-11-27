console.log("🕹 MODO REAL MQTT VÍA WEBSOCKET — Velocidades basadas en PWM 800-2000");

// ================================
// CONFIGURACIÓN
// ================================
const PWM_MIN = 800;
const PWM_MAX = 2000;
const VELOCIDAD_MAX = 6.0; // cm/s

const ACELERACION = 20;
const FACTOR_FRENADO = 0.92;

// Regla de 3: PWM a cm/s
function pwmToCm(pwm) {
  if (pwm < PWM_MIN) return 0;
  const pwmNorm = pwm - PWM_MIN;
  const rangoPwm = PWM_MAX - PWM_MIN;
  return (pwmNorm / rangoPwm) * VELOCIDAD_MAX;
}

// ================================
// WEBSOCKET CONEXIÓN
// ================================
let ws = null;
let mqttVelocidades = [0, 0, 0, 0, 0, 0]; // cm/s de cada rueda
let comandoActual = "stop";
let pwmActual = 800;

function conectarWebSocket() {
  ws = new WebSocket("ws://localhost:8765");
  
  ws.onopen = () => {
    console.log("✅ WebSocket conectado - Recibiendo datos MQTT");
  };
  
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      
      if (data.velocidades && Array.isArray(data.velocidades)) {
        mqttVelocidades = data.velocidades;
      }
      
      if (data.comando) {
        comandoActual = data.comando;
      }
      
      if (data.pwm !== undefined) {
        pwmActual = data.pwm;
      }
      
    } catch (e) {
      console.warn("Error parseando WebSocket:", e);
    }
  };
  
  ws.onerror = (error) => {
    console.error("❌ Error WebSocket:", error);
  };
  
  ws.onclose = () => {
    console.log("⚠️ WebSocket desconectado. Reconectando en 3s...");
    setTimeout(conectarWebSocket, 3000);
  };
}

// Iniciar conexión
conectarWebSocket();

// ================================
// VARIABLES PARA ANIMACIÓN
// ================================
let rotaciones = [0, 0, 0, 0, 0, 0];
let rotacionObjetivo = [0, 0, 0, 0, 0, 0];

const llantas = [w1, w2, w3, w4, w5, w6];
const velLabels = [v1, v2, v3, v4, v5, v6];

// ================================
// ANIMACIÓN DE RUEDAS
// ================================
const VELOCIDAD_ANIMACION = 18;

function animar() {
  llantas.forEach((wheel, i) => {
    let velReal = mqttVelocidades[i]; // cm/s desde MQTT vía WebSocket
    
    // Si hay velocidad → girar
    if (velReal !== 0) {
      rotaciones[i] += Math.sign(velReal) * VELOCIDAD_ANIMACION;
      rotacionObjetivo[i] = rotaciones[i];
    } else {
      // Reset suave sin deformación
      rotaciones[i] += (0 - rotaciones[i]) * 0.1;
    }
    
    wheel.style.transform = `rotateX(${rotaciones[i]}deg)`;
    velLabels[i].innerText = Math.abs(velReal).toFixed(2) + " cm/s";
  });
  
  requestAnimationFrame(animar);
}

animar();

console.log("🚗 Interfaz iniciada - Esperando datos MQTT...");
