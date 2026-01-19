"""Analizar codificación de mensajes B9 del regulador real"""

mensajes = [
    ('0280B984818181BC03', 'G1:Ambar, G2:Apag, G3:Verde, G4:Apag, G5:Ambar, G6:Apag'),
    ('0280B981818181B903', 'G1:Ambar, G2:Apag, G3:Apag, G4:Verde, G5:Ambar, G6:Apag'),
    ('0280B981909081B903', 'G1:Ambar, G2:Apag, G3:Apag, G4:Verde, G5:Ambar, G6:Verde'),
    ('0280B990818190B903', 'G1:Ambar, G2:Verde, G3:Apag, G4:Apag, G5:Ambar, G6:Apag'),
]

print('Decodificacion de mensajes B9:')
print('=' * 70)

estados_2bit = {0: 'Off', 1: 'Ver', 2: 'Amb', 3: 'Roj'}

for msg_hex, esperado in mensajes:
    msg = bytes.fromhex(msg_hex)
    datos = msg[3:-2]  # Sin STX, sub, cod, chk, ETX
    
    print(f'Mensaje: {msg_hex}')
    print(f'Datos raw: {datos.hex()}')
    print(f'Esperado: {esperado}')
    
    # Decodificar (quitar bit 7)
    dec = [b & 0x7F for b in datos]
    print(f'Decodificado hex: {[hex(d) for d in dec]}')
    print(f'Decodificado bin: {[bin(d) for d in dec]}')
    
    # Interpretar como 4 grupos por byte (2 bits cada uno)
    # Bit order: G1-G2-G3-G4 de MSB a LSB
    grupos = []
    for i, b in enumerate(dec):
        g1 = (b >> 6) & 0x03
        g2 = (b >> 4) & 0x03
        g3 = (b >> 2) & 0x03
        g4 = b & 0x03
        base = i * 4 + 1
        grupos.append(f'G{base}:{estados_2bit[g1]}')
        grupos.append(f'G{base+1}:{estados_2bit[g2]}')
        grupos.append(f'G{base+2}:{estados_2bit[g3]}')
        grupos.append(f'G{base+3}:{estados_2bit[g4]}')
    
    print(f'4 grupos/byte (MSB->LSB): {grupos[:8]}')
    
    # Alternativa: bit order inverso
    grupos2 = []
    for i, b in enumerate(dec):
        g4 = (b >> 6) & 0x03
        g3 = (b >> 4) & 0x03
        g2 = (b >> 2) & 0x03
        g1 = b & 0x03
        base = i * 4 + 1
        grupos2.append(f'G{base}:{estados_2bit[g1]}')
        grupos2.append(f'G{base+1}:{estados_2bit[g2]}')
        grupos2.append(f'G{base+2}:{estados_2bit[g3]}')
        grupos2.append(f'G{base+3}:{estados_2bit[g4]}')
    
    print(f'4 grupos/byte (LSB->MSB): {grupos2[:8]}')
    print()
