@echo off
REM ============================================================================
REM Script para ejecutar el Proxy Sniffer UNE
REM ============================================================================
REM 
REM CONFIGURACIÓN:
REM - El proxy se ejecuta en ESTA PC
REM - El proxy escucha en puerto 19000
REM - El proxy reenvía al regulador real en 172.17.10.103:19000
REM
REM ⚠️ PASOS PARA USAR:
REM 
REM 1. Obtener la IP de esta PC:
REM    - Ejecutar: ipconfig
REM    - Anotar la IPv4 Address (ejemplo: 192.168.100.50)
REM
REM 2. Ejecutar este script (el proxy empezará a escuchar)
REM
REM 3. Configurar TEMPORALMENTE la central:
REM    - Cambiar IP destino de 172.17.10.103 a [IP_DE_ESTA_PC]
REM    - Mantener puerto 19000
REM
REM 4. Conectar la central (el proxy capturará todo)
REM
REM 5. Al terminar:
REM    - Ctrl+C para detener el proxy
REM    - Restaurar IP en la central: 172.17.10.103
REM
REM El log se guardará en: sniffer_log_YYYYMMDD_HHMMSS.txt
REM ============================================================================

echo.
echo ====================================================================
echo  PROXY SNIFFER UNE 135401-4
echo ====================================================================
echo.
echo  1. IP de esta PC (usar ipconfig para obtenerla)
echo  2. Configurar central para conectarse a [IP_ESTA_PC]:19000
echo  3. El proxy reenviará al regulador 172.17.10.103:19000
echo.
echo  Presiona cualquier tecla cuando estés listo...
echo ====================================================================
echo.
pause

echo.
echo Obteniendo IP de esta PC...
echo.
ipconfig | findstr /i "IPv4"
echo.
echo ====================================================================
echo  Configura la central con una de estas IPs en puerto 19000
echo ====================================================================
echo.
pause

cd /d "%~dp0"
python ProxySnifferUNE.py --regulador-ip 172.17.10.103 --regulador-puerto 19000 --puerto-local 19000

echo.
echo ====================================================================
echo  PROXY DETENIDO
echo ====================================================================
echo.
echo  Recuerda restaurar la IP del regulador (172.17.10.103) en la central
echo.
pause
