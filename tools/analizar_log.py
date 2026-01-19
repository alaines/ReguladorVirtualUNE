#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analizador del log del sniffer para extraer información del regulador real
"""

import re
from collections import defaultdict, Counter

LOG_FILE = "sniffer_log_20260114_165843.txt"

def analizar_log():
    """Analiza el log completo y genera resumen del regulador"""
    
    # Contadores
    codigos_central = Counter()
    codigos_regulador = Counter()
    
    # Datos específicos
    planes_detectados = set()
    ciclos_detectados = set()
    grupos_estados = []
    alarmas = []
    parametros_config = []
    tablas_programacion = []
    
    # Info de sincronización
    sync_data = []
    
    print("📊 Analizando log del regulador real...\n")
    
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print(f"Total de líneas: {len(lines)}")
    
    for i, line in enumerate(lines):
        # Detectar dirección y código
        if "C→R" in line and "Sub:" in line:
            # Mensaje de central
            match = re.search(r'0x([0-9A-F]{2})', line)
            if match:
                codigo = match.group(1)
                codigos_central[codigo] += 1
        
        elif "R→C" in line and "Sub:" in line:
            # Mensaje de regulador
            match = re.search(r'0x([0-9A-F]{2})', line)
            if match:
                codigo = match.group(1)
                codigos_regulador[codigo] += 1
                
                # Extraer datos específicos según el código
                if codigo == "91":  # Sincronización
                    # Buscar líneas siguientes con Plan, Hora, Segundos
                    if i+1 < len(lines) and "Plan:" in lines[i+1]:
                        plan_match = re.search(r'Plan: (\d+)', lines[i+1])
                        if plan_match:
                            planes_detectados.add(int(plan_match.group(1)))
                    if i+3 < len(lines) and "Segundos ciclo:" in lines[i+3]:
                        ciclo_match = re.search(r'Segundos ciclo: (\d+)', lines[i+3])
                        if ciclo_match:
                            ciclos_detectados.add(int(ciclo_match.group(1)))
                    
                    # Guardar info completa de sincronización
                    sync_info = {"line": i}
                    for j in range(1, 5):
                        if i+j < len(lines):
                            sync_info[f"data{j}"] = lines[i+j].strip()
                    sync_data.append(sync_info)
                
                elif codigo == "B4":  # Estado/Alarmas
                    if i+1 < len(lines):
                        alarmas.append(lines[i:i+4])
                
                elif codigo == "B5":  # Parámetros configuración
                    if i+1 < len(lines):
                        parametros_config.append(lines[i:i+3])
                
                elif codigo == "B6":  # Tablas programación
                    if i+1 < len(lines):
                        tablas_programacion.append(lines[i:i+10])
                
                elif codigo == "B9":  # Estado grupos
                    if i+1 < len(lines) and "Grupos:" in lines[i+1]:
                        grupos_estados.append(lines[i+1].strip())
    
    # ========== RESUMEN ==========
    print("\n" + "="*70)
    print("RESUMEN DEL REGULADOR REAL (Modo A)")
    print("="*70)
    
    print("\n📤 CÓDIGOS ENVIADOS POR LA CENTRAL:")
    for codigo, count in codigos_central.most_common(10):
        nombre = get_nombre_codigo(codigo)
        print(f"   0x{codigo}: {nombre:40s} - {count:5d} veces")
    
    print("\n📥 CÓDIGOS ENVIADOS POR EL REGULADOR:")
    for codigo, count in codigos_regulador.most_common(10):
        nombre = get_nombre_codigo(codigo)
        print(f"   0x{codigo}: {nombre:40s} - {count:5d} veces")
    
    print(f"\n🎯 PLANES DETECTADOS: {sorted(planes_detectados)}")
    print(f"⏱️  CICLOS DETECTADOS: {sorted(ciclos_detectados)} segundos")
    
    # Mostrar ejemplos de sincronización
    print("\n📍 EJEMPLOS DE SINCRONIZACIÓN (primeros 3):")
    for sync in sync_data[:3]:
        print(f"\n   Línea {sync['line']}:")
        for key in sorted([k for k in sync.keys() if k.startswith('data')]):
            print(f"      {sync[key]}")
    
    # Mostrar ejemplos de estado de grupos
    print("\n🚦 EJEMPLOS DE ESTADO DE GRUPOS (primeros 5):")
    for i, grupo in enumerate(grupos_estados[:5], 1):
        print(f"   {i}. {grupo}")
    
    # Mostrar alarmas
    print("\n⚠️  EJEMPLOS DE ESTADO/ALARMAS (0xB4):")
    if alarmas:
        for linea in alarmas[0][:3]:
            print(f"   {linea.strip()}")
    else:
        print("   (No se encontraron respuestas 0xB4)")
    
    # Mostrar parámetros
    print("\n⚙️  EJEMPLOS DE PARÁMETROS CONFIG (0xB5):")
    if parametros_config:
        for linea in parametros_config[0][:3]:
            print(f"   {linea.strip()}")
    else:
        print("   (No se encontraron respuestas 0xB5)")
    
    # Mostrar tablas
    print("\n📋 EJEMPLOS DE TABLAS PROGRAMACIÓN (0xB6):")
    if tablas_programacion:
        for linea in tablas_programacion[0][:5]:
            print(f"   {linea.strip()}")
    else:
        print("   (No se encontraron respuestas 0xB6)")
    
    print("\n" + "="*70)
    
    # Guardar resumen detallado
    with open("RESUMEN_REGULADOR_REAL.txt", 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write("ANÁLISIS DETALLADO DEL REGULADOR REAL\n")
        f.write("="*70 + "\n\n")
        
        f.write("CÓDIGOS DE LA CENTRAL:\n")
        for codigo, count in codigos_central.most_common():
            nombre = get_nombre_codigo(codigo)
            f.write(f"   0x{codigo}: {nombre:40s} - {count:5d} veces\n")
        
        f.write("\n\nCÓDIGOS DEL REGULADOR:\n")
        for codigo, count in codigos_regulador.most_common():
            nombre = get_nombre_codigo(codigo)
            f.write(f"   0x{codigo}: {nombre:40s} - {count:5d} veces\n")
        
        f.write(f"\n\nPLANES: {sorted(planes_detectados)}\n")
        f.write(f"CICLOS: {sorted(ciclos_detectados)}\n")
        
        f.write("\n\nESTADO DE GRUPOS (muestra):\n")
        for grupo in grupos_estados[:20]:
            f.write(f"{grupo}\n")
    
    print("\n✅ Resumen guardado en: RESUMEN_REGULADOR_REAL.txt")

def get_nombre_codigo(codigo_hex):
    """Retorna el nombre del código"""
    codigos = {
        "91": "Sincronización",
        "B4": "Estado regulador/Alarmas",
        "B5": "Parámetros configuración",
        "B6": "Tablas programación",
        "B7": "Incompatibilidades",
        "B9": "Estado grupos",
        "D1": "Selección plan",
        "94": "Datos de tráfico",
    }
    return codigos.get(codigo_hex, "Desconocido")

if __name__ == "__main__":
    analizar_log()
