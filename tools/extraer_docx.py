import docx
import sys

# Leer el documento DOCX
doc = docx.Document('docs/UNE_135401-42003_IN_unlocked.docx')

# Extraer todo el texto
texto_completo = []
for para in doc.paragraphs:
    texto_completo.append(para.text)

# Guardar en archivo
with open('docs/UNE_extraido.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(texto_completo))

print("✅ Texto extraído correctamente a docs/UNE_extraido.txt")
print(f"Total de párrafos: {len(texto_completo)}")
