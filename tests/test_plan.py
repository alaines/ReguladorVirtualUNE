"""Test de selección automática de plan por horario"""
from datetime import datetime
from modules.estado_regulador import EstadoRegulador
from modules.generador_respuestas import GeneradorRespuestas

estado = EstadoRegulador()
ahora = datetime.now()

print(f"Hora actual: {ahora.strftime('%H:%M')}")
print(f"Plan seleccionado: {estado.plan_actual}")
print(f"Modo control: {estado.modo_control}")

# Mostrar configuración del plan
plan_cfg = estado.get_plan_config()
print(f"Plan config: {plan_cfg.get('nombre', '?')}")
print(f"Horarios: {plan_cfg.get('horarios', [])}")

# Probar mensaje B9
estados = estado.get_estado_grupos()
print(f"\nEstados grupos: {estados}")

msg = GeneradorRespuestas.mensaje_estado_grupos(estado, 129)
print(f"Mensaje B9: {msg.hex()}")

# Verificar si los bytes tienen bit 7
for i, b in enumerate(msg):
    if i >= 3 and i < len(msg)-2:  # Solo datos
        tiene_bit7 = (b & 0x80) != 0
        print(f"  Byte {i}: 0x{b:02X} - bit7: {tiene_bit7}")
