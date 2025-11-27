console.log("🕹 MODO SIMULACIÓN + MODO REAL MQTT — Frenado progresivo + Reset perfecto");

// ================================
// CONFIGURACIÓN
// ================================
const PWM_MAX = 2000;
const VELOCIDAD_MAX = 6.8;

const ACELERACION = 20;
const FACTOR_FRENADO = 0.92;

function pwmToCm(pwm) {
  return (pwm * VELOCIDAD_MAX) / PWM_MAX;
}

// ================================
// MODOS
// ================================
let modo = "simulacion"; 
// valores = "simulacion" o "real"

// ================================
// MQTT CONFIG
// ================================
let mqttVelocidades = [0, 0, 0, 0, 0, 0]; // velocidades reales por rueda EN cm/s desde MQTT

// Cliente MQTT
const client = mqtt.connect("wss://test.mosquitto.org:8081");

// Al conectar
client.on("connect", () => {
  console.log("📡 MQTT Conectado (modo real disponible)");
  client.subscribe("carro/velocidades");
});

// Al recibir mensaje
client.on("message", (topic, message) => {
  if (topic === "carro/velocidades") {
    try {
      let data = JSON.parse(message.toString());

      // Debe venir como array: [v1, v2, v3, v4, v5, v6]
      if (Array.isArray(data) && data.length === 6) {
        mqttVelocidades = data;
      }

    } catch (e) {
      console.warn("MQTT JSON inválido");
    }
  }
});

// ================================
// VARIABLES SIMULACIÓN
// ================================
let comandoActual = "stop";
let velocidadPWM = 0;

let rotaciones = [0, 0, 0, 0, 0, 0];
let rotacionObjetivo = [0, 0, 0, 0, 0, 0];

const llantas = [w1, w2, w3, w4, w5, w6];
const velLabels = [v1, v2, v3, v4, v5, v6];

// ================================
// TECLAS (SOLO SIMULACIÓN)
// ================================
let tecla = { up:false, down:false, left:false, right:false };

document.addEventListener("keydown", e => {
  if (modo !== "simulacion") return;

  if (e.key === "ArrowUp")    tecla.up = true;
  if (e.key === "ArrowDown")  tecla.down = true;
  if (e.key === "ArrowLeft")  tecla.left = true;
  if (e.key === "ArrowRight") tecla.right = true;
});

document.addEventListener("keyup", e => {
  if (modo !== "simulacion") return;

  if (e.key === "ArrowUp")    tecla.up = false;
  if (e.key === "ArrowDown")  tecla.down = false;
  if (e.key === "ArrowLeft")  tecla.left = false;
  if (e.key === "ArrowRight") tecla.right = false;

  if (!tecla.up && !tecla.down && !tecla.left && !tecla.right) {
      comandoActual = "stop";
  }
});

// ================================
// COMANDOS SIMULACIÓN
// ================================
function actualizarComando() {
  if (modo !== "simulacion") return;

  if (tecla.up) comandoActual = "forward";
  else if (tecla.down) comandoActual = "backward";
  else if (tecla.left) comandoActual = "left";
  else if (tecla.right) comandoActual = "right";
}

// ================================
// ACELERACIÓN / FRENADO SIMULACIÓN
// ================================
function actualizarVelocidad() {
  if (modo !== "simulacion") return;

  if (comandoActual !== "stop") {
    velocidadPWM += ACELERACION;
    if (velocidadPWM > PWM_MAX) velocidadPWM = PWM_MAX;
  } else {
    velocidadPWM *= FACTOR_FRENADO;
    if (velocidadPWM < 1.5) velocidadPWM = 0;
  }
}

// ================================
// VELOCIDAD POR RUEDA — MODO SIMULACIÓN
// ================================
function velocidadRealSim(i) {
  let vel = pwmToCm(velocidadPWM);

  const izquierdas = [0, 2, 4];
  const esIzquierda = izquierdas.includes(i);

  switch (comandoActual) {
    case "forward":  return vel;
    case "backward": return -vel;
    case "left":     return esIzquierda ? vel : -vel;
    case "right":    return esIzquierda ? -vel : vel;
    default:         return 0;
  }
}

// ================================
// ANIMACIÓN (SIMULACIÓN + MQTT)
// ================================
const VELOCIDAD_ANIMACION = 18;

function animar() {

  if (modo === "simulacion") {
    actualizarComando();
    actualizarVelocidad();
  }

  llantas.forEach((wheel, i) => {

    let velReal = 
      modo === "simulacion"
        ? velocidadRealSim(i)
        : mqttVelocidades[i];   // <- MQTT REAL

    // Si hay velocidad → girar normal
    if (velReal !== 0) {
      rotaciones[i] += Math.sign(velReal) * VELOCIDAD_ANIMACION;
      rotacionObjetivo[i] = rotaciones[i];
    } else {
      // reset suave sin deformación
      rotaciones[i] += (0 - rotaciones[i]) * 0.1;
    }

    wheel.style.transform = `rotateX(${rotaciones[i]}deg)`;
    velLabels[i].innerText = velReal.toFixed(2);

  });

  requestAnimationFrame(animar);
}

animar();


// ================================
// CAMBIAR MODO
// ================================
function setModo(nuevoModo) {
  if (nuevoModo !== "real" && nuevoModo !== "simulacion") return;
  modo = nuevoModo;

  if (modo === "simulacion") {
    console.log("🚗 MODO SIMULACIÓN ACTIVADO");
  } else {
    console.log("📡 MODO REAL MQTT ACTIVADO");
  }
}
