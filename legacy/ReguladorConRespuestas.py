import socket
import random
from datetime import datetime


def registrar_log(mensaje, respuesta):
    """ Registra las consultas recibidas y respuestas enviadas en un archivo de log con codificación UTF-8. """
    with open("log_consultas.txt", "a", encoding="utf-8") as log:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.write(f"[{timestamp}] {mensaje}\n")
        log.write(f"           → Respuesta: {respuesta}\n\n")


# Diccionario de códigos de mensaje según la norma UNE 135401-4
CODIGOS_MENSAJES = {
    0x20: "Petición de detectores (DET)",
    0x33: "Solicitud de hora en tiempo real (HTR)",
    0x40: "Petición de hora en tiempo real (PRH)",
    0xB4: "Consulta de estado del regulador",
    0xB5: "Consulta de parámetros de configuración",
    0xB6: "Consulta de tablas de programación",
    0xB7: "Consulta de alarmas activas",
    0x91: "Consulta de sincronización",
    0x94: "Consulta de datos de tráfico",
    0x148: "Consulta de estado del sistema",
}

# Códigos de control
STX = b"\x02"
ETX = b"\x03"
ACK = b"\x06"
NACK = b"\x15"


def calcular_checksum(mensaje):
    """ Calcula el checksum como XOR de todos los bytes excepto STX y ETX. """
    checksum = 0
    for byte in mensaje[1:-1]:  # Omitir STX y ETX
        checksum ^= byte
    return checksum.to_bytes(1, 'big')


# Variable global para almacenar el plan actual
plan_actual = 2  # Inicia en el Plan 1

def generar_respuesta_estado_regulador(subregulador):
    """ Responde a la consulta de estado del regulador con los datos del plan actual """

    # Planes preconfigurados
    planes = {
        1: {"ciclo": 50, "grupos": 4, "fases": [22, 20], "estructura": 1, "transitorio": 8, "desfase": 0},
        2: {"ciclo": 70, "grupos": 4, "fases": [32, 30], "estructura": 1, "transitorio": 8, "desfase": 0},
        3: {"ciclo": 90, "grupos": 4, "fases": [50, 32], "estructura": 1, "transitorio": 8, "desfase": 0}
    }

    # Datos del plan actual
    plan = planes[plan_actual]

    print(f"📊 Estado del regulador: Reportando Plan {plan_actual}")
    print(f"🚦 Grupos: {plan['grupos']} | ⏳ Ciclo: {plan['ciclo']}s | Fases: {plan['fases'][0]}-{plan['fases'][1]}s")
    print(
        f"🏗️ Estructura: {plan['estructura']} | 🔄 Transitorio: {plan['transitorio']}s | ⏳ Desfase: {plan['desfase']}s")

    # Construcción del mensaje de respuesta con los datos del plan actual
    respuesta = STX + bytes([
        subregulador, 0xB4, plan_actual, plan["grupos"], plan["ciclo"],
        plan["fases"][0], plan["fases"][1], plan["estructura"],
        plan["transitorio"], plan["desfase"]
    ])
    respuesta += calcular_checksum(respuesta) + ETX  # Añadir checksum y ETX

    return respuesta


def generar_respuesta_configuracion(subregulador):
    """ Genera la respuesta a la consulta de parámetros de configuración (Código 181 - 0xB5) """

    # Datos fijos según la solicitud
    modo_control = 1  # 1 = Local
    estado_representacion = 2  # 2 = Colores
    funcionamiento = 0  # 0 = Tiempos fijos

    plan_actual = 1  # Plan en uso
    ciclo = 60  # Ciclo de semáforos (60 segundos)
    estructura = 1  # Número de estructura en uso
    tabla_minimos = 1  # Tabla de tiempos mínimos
    tabla_transitorios = 1  # Tabla de tiempos de transitorios
    desfases = 5  # Tiempo de desfase
    duracion_fases = 30  # Duración de fases en segundos
    duracion_minima = 10  # Duración mínima de fase en segundos

    print(f"🔧 Parámetros del regulador:")
    print(f"⚙️ Modo de control: Local")
    print(f"🎨 Estado de representación: Colores")
    print(f"⏳ Funcionamiento: Tiempos fijos")
    print(f"📋 Plan actual: {plan_actual}")
    print(f"⏲️ Ciclo: {ciclo} s")
    print(f"📑 Estructura: {estructura}")
    print(f"📊 Tabla de mínimos: {tabla_minimos}")
    print(f"🔄 Tabla de transitorios: {tabla_transitorios}")
    print(f"⏱️ Desfases: {desfases} s")
    print(f"🕒 Duración de fases: {duracion_fases} s")
    print(f"🕑 Duración mínima de fase: {duracion_minima} s")

    # Construcción del mensaje de respuesta con los datos fijos
    respuesta = STX + bytes([
        subregulador, 0xB5, modo_control, estado_representacion, funcionamiento,
        plan_actual, ciclo, estructura, tabla_minimos, tabla_transitorios,
        desfases, duracion_fases, duracion_minima
    ])
    respuesta += calcular_checksum(respuesta) + ETX  # Añadir checksum y ETX al final

    return respuesta


def generar_respuesta_sincronizacion(subregulador):
    """ Genera la respuesta a la consulta de sincronización (Código 145 - 0x91). """

    # Datos fijos
    modo_sincronizacion = 1  # 1 = Coordinado con reloj interno
    diferencia_tiempo = 0  # Diferencia con la central (en segundos)

    # Obtener la hora actual del sistema
    now = datetime.now()
    hora, minuto, segundo = now.hour, now.minute, now.second

    print(f"🔄 Sincronización del regulador:")
    print(f"🕒 Hora actual: {hora:02}:{minuto:02}:{segundo:02}")
    print(f"🛰️ Modo de sincronización: Coordinado con reloj interno")
    print(f"⏳ Diferencia con la central: {diferencia_tiempo} segundos")

    # Construcción del mensaje de respuesta
    respuesta = STX + bytes([
        subregulador, 0x91, modo_sincronizacion, diferencia_tiempo,
        hora, minuto, segundo
    ])
    respuesta += calcular_checksum(respuesta) + ETX  # Añadir checksum y ETX al final

    return respuesta


def generar_respuesta_tablas_programacion(subregulador):
    """ Genera la respuesta completa a la consulta de tablas de programación (Código 182 - 0xB6). """

    # Definir los tres planes semafóricos
    planes = [
        {"id": 1, "ciclo": 50, "grupos": 4, "fases": [22, 20], "estructura": 1, "transitorio": 8, "desfase": 0, "minimo": 20, "maximo": 50},
        {"id": 2, "ciclo": 70, "grupos": 4, "fases": [32, 30], "estructura": 1, "transitorio": 8, "desfase": 0, "minimo": 30, "maximo": 70},
        {"id": 3, "ciclo": 90, "grupos": 4, "fases": [50, 32], "estructura": 1, "transitorio": 8, "desfase": 0, "minimo": 40, "maximo": 90}
    ]

    print(f"📋 Tablas de programación:")
    for plan in planes:
        print(f"🟢 Plan {plan['id']}: Ciclo {plan['ciclo']}s, Grupos {plan['grupos']}")
        print(f"   🔹 Fases: {plan['fases'][0]}-{plan['fases'][1]}s, 🏗️ Estructura: {plan['estructura']}")
        print(f"   🔄 Transitorio: {plan['transitorio']}s, ⏳ Desfase: {plan['desfase']}s")
        print(f"   ⏱️ Tiempo mínimo de fase: {plan['minimo']}s, ⏳ Tiempo máximo: {plan['maximo']}s")

    # Construcción del mensaje de respuesta
    respuesta = STX + bytes([subregulador, 0xB6])  # Iniciar mensaje con subregulador y código

    for plan in planes:
        respuesta += bytes([
            plan["id"], plan["grupos"], plan["ciclo"], plan["fases"][0], plan["fases"][1],
            plan["estructura"], plan["transitorio"], plan["desfase"], plan["minimo"], plan["maximo"]
        ])

    respuesta += calcular_checksum(respuesta) + ETX  # Añadir checksum y ETX al final

    return respuesta


def extraer_mensajes(data):
    """ Extrae y separa múltiples mensajes en un solo paquete TCP. """
    mensajes = []
    buffer = bytearray()

    for byte in data:
        buffer.append(byte)
        if byte == 0x03:  # ETX indica el fin del mensaje
            mensajes.append(bytes(buffer))
            buffer.clear()

    return mensajes


def generar_respuesta_tablas_programacion(subregulador):
    """ Genera la respuesta completa a la consulta de tablas de programación (Código 182 - 0xB6). """

    # Definir los tres planes semafóricos
    planes = [
        {"id": 1, "ciclo": 50, "grupos": 4, "fases": [22, 20], "estructura": 1, "transitorio": 8, "desfase": 0, "minimo": 20, "maximo": 50},
        {"id": 2, "ciclo": 70, "grupos": 4, "fases": [32, 30], "estructura": 1, "transitorio": 8, "desfase": 0, "minimo": 30, "maximo": 70},
        {"id": 3, "ciclo": 90, "grupos": 4, "fases": [50, 32], "estructura": 1, "transitorio": 8, "desfase": 0, "minimo": 40, "maximo": 90}
    ]

    print(f"📋 Tablas de programación:")
    for plan in planes:
        print(f"🟢 Plan {plan['id']}: Ciclo {plan['ciclo']}s, Grupos {plan['grupos']}")
        print(f"   🔹 Fases: {plan['fases'][0]}-{plan['fases'][1]}s, 🏗️ Estructura: {plan['estructura']}")
        print(f"   🔄 Transitorio: {plan['transitorio']}s, ⏳ Desfase: {plan['desfase']}s")
        print(f"   ⏱️ Tiempo mínimo de fase: {plan['minimo']}s, ⏳ Tiempo máximo: {plan['maximo']}s")

    # Construcción del mensaje de respuesta
    respuesta = STX + bytes([subregulador, 0xB6])  # Iniciar mensaje con subregulador y código

    for plan in planes:
        respuesta += bytes([
            plan["id"], plan["grupos"], plan["ciclo"], plan["fases"][0], plan["fases"][1],
            plan["estructura"], plan["transitorio"], plan["desfase"], plan["minimo"], plan["maximo"]
        ])

    respuesta += calcular_checksum(respuesta) + ETX  # Añadir checksum y ETX al final

    return respuesta


def establecer_plan(subregulador, datos):
    """ Procesa la orden de selección de plan (Código 146 - 0x92). """

    global plan_actual

    if len(datos) < 1:
        print("⚠️ Error: No se especificó número de plan en la orden.")
        return NACK  # Responder con NACK si el mensaje no tiene datos

    nuevo_plan = datos[0]  # Extraer el número de plan del mensaje

    if nuevo_plan not in [1, 2, 3]:
        print(f"⚠️ Error: Plan {nuevo_plan} no válido.")
        return NACK  # Enviar NACK si el plan no es válido

    plan_actual = nuevo_plan  # Actualizar el plan activo

    print(f"✅ Cambio de plan exitoso. Nuevo plan: {plan_actual}")

    # Construcción del mensaje de confirmación
    respuesta = STX + bytes([subregulador, 0x92, plan_actual])
    respuesta += calcular_checksum(respuesta) + ETX  # Añadir checksum y ETX

    return respuesta


def decodificar_mensaje(data):
    """ Decodifica los mensajes recibidos según la norma UNE 135401-4. """

    print(f"📩 Mensaje crudo en hexadecimal: {data.hex()}")  # Depuración

    if len(data) < 3:
        print("⚠️ Mensaje descartado: demasiado corto para ser válido")
        return None, None  # No procesar este mensaje

    if not data.startswith(STX) or not (data.endswith(ETX) or data.endswith(b"\x04")):
        print("⚠️ Formato incorrecto, falta STX o ETX/EOT")
        return "Mensaje inválido", NACK

    num_subregulador = data[1]
    codigo_mensaje = data[2]
    descripcion_mensaje = CODIGOS_MENSAJES.get(codigo_mensaje, "Código desconocido")

    # Si el mensaje tiene exactamente 5 bytes, el byte 3 es un dato
    if len(data) == 5:
        datos = data[3:4]  # Extraemos solo 1 byte como datos
    else:
        datos = data[3:-2]  # Extraer datos excluyendo STX, ETX y checksum

    datos_hex = datos.hex() if datos else "Ninguno"

    traduccion = f"Subregulador: {num_subregulador}, Código: {codigo_mensaje} ({descripcion_mensaje}), Datos: {datos_hex}"

    # Generar respuesta según el código recibido
    if codigo_mensaje == 0xB4:  # Consulta de estado del regulador
        respuesta = generar_respuesta_estado_regulador(num_subregulador)
    elif codigo_mensaje == 0xB5:  # Consulta de parámetros de configuración
        respuesta = generar_respuesta_configuracion(num_subregulador)
    elif codigo_mensaje == 0xB6:  # Consulta de tablas de programación
        respuesta = generar_respuesta_tablas_programacion(num_subregulador)
    elif codigo_mensaje == 0x91:  # Consulta de sincronización
        respuesta = generar_respuesta_sincronizacion(num_subregulador)
    elif codigo_mensaje == 0x92:  # Orden de cambio de plan
        respuesta = establecer_plan(num_subregulador, datos)
    else:
        respuesta = ACK if modo_operacion == "A" else None  # Modo A responde con ACK, modo B puede no responder

    # Registrar en log
    if respuesta:
        registrar_log(mensaje, respuesta.hex())

    return traduccion, respuesta


# Configuración del regulador
IP_REGULADOR = "192.168.100.218"
puerto_input = input("Ingrese el puerto de comunicación (o presione Enter para asignar uno aleatorio): ")
PUERTO = int(puerto_input) if puerto_input.isdigit() else random.randint(5000, 6000)

# Preguntar por el modo de operación (A o B)
modo_operacion = input("Seleccione el modo de operación (A/B): ").strip().upper()
while modo_operacion not in ["A", "B"]:
    modo_operacion = input("Opción inválida. Seleccione el modo de operación (A/B): ").strip().upper()

# Configuración del socket TCP
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((IP_REGULADOR, PUERTO))
server_socket.listen(5)  # Permitir hasta 5 conexiones simultáneas

print(f"\n🌐 Regulador iniciado en {IP_REGULADOR}:{PUERTO}, operación: {modo_operacion}")
print("\n📡 Esperando conexiones de la central...")

while True:
    conn, addr = server_socket.accept()  # Aceptar conexión entrante
    print(f"📡 Conexión establecida con {addr}")

    while True:
        try:
            data = conn.recv(1024)  # Recibir datos
            if not data:
                break  # Si no hay datos, cerrar la conexión

            mensaje, respuesta = decodificar_mensaje(data)
            if mensaje:
                print(f"📩 Mensaje recibido de {addr}: {mensaje}")

            if respuesta:
                conn.sendall(respuesta)
                print(f"📤 Enviando respuesta: {respuesta.hex()}")

        except Exception as e:
            print(f"⚠️ Error en la conexión con {addr}: {e}")
            break  # Si hay un error, cerrar la conexión

    conn.close()
    print(f"🔌 Conexión cerrada con {addr}")
