@echo off
chcp 65001 >nul
color 0A

echo ===============================================================
echo   🤖 ROVER CONTROL SYSTEM - LAUNCHER
echo ===============================================================
echo.

:: Obtener ruta absoluta del script
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Configuración
set "MQTT_DIR=%SCRIPT_DIR%python-services\mqtt"
set "CAMERA_DIR=%SCRIPT_DIR%python-services\camera"
set "CONTROL_DIR=%SCRIPT_DIR%python-services\control"

echo [1/3] Iniciando Broker MQTT...
start "Broker MQTT - Rover" cmd /k "cd /d "%MQTT_DIR%" && python broker_mqtt.py"
timeout /t 2 /nobreak >nul

echo [2/3] Iniciando Camara con YOLO...
start "Camara YOLO - Rover" cmd /k "cd /d "%CAMERA_DIR%" && python camera_client.py"
timeout /t 3 /nobreak >nul

echo [3/3] Iniciando Control por Teclado...
start "Control Teclado - Rover" cmd /k "cd /d "%CONTROL_DIR%" && python "teclado y camara juntos.py""

echo.
echo ===============================================================
echo   ✅ SISTEMA INICIADO
echo ===============================================================
echo.
echo   Se abrieron 3 ventanas:
echo   1. 🌐 Broker MQTT (servidor)
echo   2. 📹 Camara (presiona D para YOLO, R para rotar)
echo   3. 🎮 Control (flechas para mover)
echo.
echo   ⚠️  IMPORTANTE para activar YOLO:
echo      1. Haz clic en ventana "ESP32-CAM"
echo      2. Presiona tecla D
echo      3. Verás "YOLO: ON" en pantalla
echo.
echo ===============================================================
echo   Presiona cualquier tecla para cerrar esta ventana...
echo ===============================================================
pause >nul
