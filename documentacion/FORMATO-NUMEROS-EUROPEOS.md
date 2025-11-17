# Formato de Números Europeos (Locale Español)

> **IMPORTANTE PARA RAG**: Este documento debe ser indexado para que CachedExecutor/AIExecutor generen código correcto al parsear montos de facturas.

---

## Problema Común

Al procesar facturas españolas, los agentes AI generan código que **convierte incorrectamente** números europeos a `float`.

**Bug típico:**
```python
# ❌ INCORRECTO:
amount = float("279,00".replace(',', ''))  # → 27900.0 (100x mayor!)
if amount > 1000:  # 27900 > 1000 → TRUE ❌ (debería ser FALSE)
    decision = 'true'
```

**Resultado:** Facturas de €279 se marcan como "mayor a €1000" cuando deberían ser "menor".

---

## Formato Europeo vs US

| Elemento | España/Europa | US/UK |
|---------|---------------|-------|
| **Separador decimal** | **Coma (,)** | Punto (.) |
| **Separador de miles** | **Punto (.)** | Coma (,) |

### Ejemplos

```
ESPAÑA:               US:
279,00 €      →       $279.00
1.234,56 €    →       $1,234.56
15.000,00 €   →       $15,000.00
```

---

## ✅ Conversión CORRECTA

### Para montos simples (sin separador de miles)
```python
amount_str = "279,00"
amount = float(amount_str.replace(',', '.'))  # ✅ 279.0
```

### Para montos con separador de miles
```python
amount_str = "1.234,56 €"

# Paso 1: Eliminar símbolo de moneda y espacios
cleaned = amount_str.replace('€', '').strip()  # "1.234,56"

# Paso 2: Eliminar separador de miles (punto)
cleaned = cleaned.replace('.', '')  # "1234,56"

# Paso 3: Reemplazar separador decimal (coma) por punto
cleaned = cleaned.replace(',', '.')  # "1234.56"

# Paso 4: Convertir a float
amount = float(cleaned)  # ✅ 1234.56
```

### Función reutilizable
```python
def parse_european_amount(amount_str: str) -> float:
    """
    Convierte monto en formato europeo a float.

    Args:
        amount_str: String con monto (ej: "1.234,56 €", "279,00")

    Returns:
        Float con el valor numérico

    Examples:
        >>> parse_european_amount("279,00 €")
        279.0
        >>> parse_european_amount("1.234,56")
        1234.56
        >>> parse_european_amount("15.000,00 €")
        15000.0
    """
    # Eliminar símbolos de moneda y espacios
    cleaned = amount_str.replace('€', '').replace('EUR', '').strip()

    # Eliminar separador de miles (.)
    cleaned = cleaned.replace('.', '')

    # Reemplazar separador decimal (,) por punto
    cleaned = cleaned.replace(',', '.')

    return float(cleaned)
```

---

## ❌ Errores COMUNES a evitar

### Error 1: Eliminar la coma sin reemplazarla
```python
# ❌ INCORRECTO:
amount = float("279,00".replace(',', ''))
# "279,00" → "27900" → 27900.0 ❌ (100x mayor!)
```

**Por qué falla:** La coma ES el separador decimal, eliminarla junta los dígitos.

### Error 2: No eliminar el separador de miles
```python
# ❌ INCORRECTO:
amount = float("1.234,56".replace(',', '.'))
# "1.234,56" → "1.234.56" → ValueError o 1.234 ❌
```

**Por qué falla:** Python interpreta el punto como decimal, no como separador de miles.

### Error 3: Asumir formato US
```python
# ❌ INCORRECTO (asume formato US):
amount = float("1.234,56")  # ValueError: invalid literal
```

**Por qué falla:** Python espera formato US (punto = decimal), el formato europeo da error.

---

## Casos de Uso: Decisiones con Montos

### Ejemplo: Verificar si monto > €1000

```python
# ✅ CORRECTO:
total_amount_str = context.get('total_amount', '0')

# Convertir formato europeo a float
total_amount = float(
    total_amount_str
    .replace('.', '')   # Eliminar separador de miles
    .replace(',', '.')  # Reemplazar decimal
    .replace('€', '')   # Eliminar símbolo
    .strip()            # Eliminar espacios
)

# Comparar
if total_amount > 1000:
    context['amount_decision'] = 'true'
else:
    context['amount_decision'] = 'false'

# Test cases:
# "279,00" → 279.0 → 279.0 > 1000? NO → 'false' ✅
# "1.500,00" → 1500.0 → 1500.0 > 1000? YES → 'true' ✅
# "999,99" → 999.99 → 999.99 > 1000? NO → 'false' ✅
```

---

## Extracción de Montos desde Texto OCR

### Pattern 1: Con símbolo de euro
```python
import re

text = "Total: 1.234,56 €"
match = re.search(r'([\d.,]+)\s*€', text)
if match:
    amount_str = match.group(1)  # "1.234,56"
    amount = float(amount_str.replace('.', '').replace(',', '.'))  # 1234.56 ✅
```

### Pattern 2: Sin símbolo
```python
text = "Total sin IVA: 230,58"
match = re.search(r'Total.*?:\s*([\d.,]+)', text)
if match:
    amount = float(match.group(1).replace(',', '.'))  # 230.58 ✅
```

### Pattern 3: Múltiples montos en factura
```python
text = """
Subtotal: 230,58 €
IVA (21%): 48,42 €
Total: 279,00 €
"""

# Buscar "Total:" seguido del monto
match = re.search(r'Total:\s*([\d.,]+)', text)
if match:
    total = float(match.group(1).replace(',', '.'))  # 279.0 ✅
```

---

## Test Cases para Validar

```python
test_cases = [
    ("279,00", 279.0),
    ("1.234,56", 1234.56),
    ("15.000,00", 15000.0),
    ("1.500.000,99", 1500000.99),
    ("0,50", 0.5),
    ("999,99 €", 999.99),
    ("1.000,00 €", 1000.0),
]

def parse_european_amount(s):
    return float(s.replace('.', '').replace(',', '.').replace('€', '').strip())

for input_str, expected in test_cases:
    result = parse_european_amount(input_str)
    assert result == expected, f"FAIL: {input_str} → {result} (expected {expected})"
    print(f"✅ {input_str:20s} → {result}")

# Output:
# ✅ 279,00               → 279.0
# ✅ 1.234,56            → 1234.56
# ✅ 15.000,00           → 15000.0
# ✅ 1.500.000,99        → 1500000.99
# ✅ 0,50                → 0.5
# ✅ 999,99 €            → 999.99
# ✅ 1.000,00 €          → 1000.0
```

---

## Resumen: Regla de Oro

**Para convertir monto europeo a Python float:**

```python
# ORDEN CORRECTO:
str
  .replace('.', '')    # 1. Eliminar separador de miles
  .replace(',', '.')   # 2. Reemplazar separador decimal
  .replace('€', '')    # 3. Eliminar símbolo moneda (opcional)
  .strip()             # 4. Eliminar espacios (opcional)

# Convertir
float(...)             # 5. Convertir a número
```

**Ejemplo completo:**
```python
"1.234,56 €"
  .replace('.', '')    → "1234,56 €"
  .replace(',', '.')   → "1234.56 €"
  .replace('€', '')    → "1234.56 "
  .strip()             → "1234.56"
float(...)             → 1234.56 ✅
```

**¡NUNCA hagas `.replace(',', '')` primero! Eso elimina el decimal.**

---

## Para el RAG: Keywords

`european number format`, `spanish locale`, `euro format`, `amount parsing`, `invoice processing`, `decimal comma`, `thousands separator`, `formato español`, `conversión montos`, `parse_european_amount`, `float conversion`
