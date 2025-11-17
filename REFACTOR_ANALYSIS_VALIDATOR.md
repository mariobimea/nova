# Refactorización: DataAnalyzer + AnalysisValidator

**Fecha**: 2025-11-17
**Estado**: ✅ Completado y testeado

---

## 🎯 Objetivo

Resolver los problemas de falsos negativos en el sistema multiagente:

1. **DataAnalyzer**: Solo analizar data "opaca" (PDFs base64, CSVs largos), no data ya visible
2. **Truncamiento**: Preservar dicts/listas normales completos, truncar SOLO strings largos
3. **AnalysisValidator**: Ser permisivo, aceptar insights mínimos/parciales

---

## 📦 Cambios Implementados

### 1. DataAnalyzer (`src/core/agents/data_analyzer.py`)

#### **A. Truncamiento Inteligente (`_summarize_value()`)**

**ANTES**:
- Truncaba strings > 100 chars → `"<string: N chars>"`
- Truncaba listas a max 2 items → Perdía información
- Max depth = 2 → Demasiado superficial

**DESPUÉS**:
- ✅ Detecta tipos específicos:
  - PDFs base64: `<base64 PDF: N chars, starts with JVBERi>`
  - Imágenes PNG: `<base64 image (PNG): N chars, starts with iVBOR>`
  - Imágenes JPEG: `<base64 image (JPEG): N chars, starts with /9j/>`
  - CSVs largos: `<CSV data: N chars, ~N lines>`
  - Bytes: `<bytes PDF: N bytes>`, etc.

- ✅ Preserva data legible:
  - Strings < 500 chars → Completos
  - Strings 500-1000 chars → Preview de 100 chars
  - Dicts/listas normales → Completos (hasta depth=4)
  - Listas >100 items → Primeros 5 + mensaje
  - Valores falsy (0, False, [], {}) → Preservados

**Resultado**: El LLM puede leer dicts/listas normales, solo se truncan archivos binarios/largos.

#### **B. Prompt Mejorado**

**AGREGADO**:
```
🎯 TU ROL: Analizar SOLO data truncada

El schema del contexto YA muestra la mayoría de la información.
TU TRABAJO es analizar ÚNICAMENTE valores truncados con marcadores como:
- "<base64 PDF: N chars, starts with JVBERi>"
- "<CSV data: N chars, ~N lines>"
- "<long string: N chars>"

✅ DEBES analizar (valores truncados):
   - PDFs en base64 → Decodificar, páginas, texto
   - Imágenes en base64 → Dimensiones, formato
   - CSVs largos → Estructura, columnas

❌ NO DEBES analizar (valores ya visibles):
   - Strings cortos/medios
   - Dicts/listas normales
   - Números, booleanos
```

**Resultado**: El LLM no genera código para "analizar" strings que ya están visibles.

#### **C. Validación en `parse_insights()`**

**AGREGADO**:
```python
# Validar que insights sea un dict
if not isinstance(insights, dict):
    return {
        "type": "error",
        "error": f"Insights must be dict, got {type(insights).__name__}",
        "raw_value": str(insights)[:200]
    }
```

**Resultado**: Detecta temprano si el código retornó formato incorrecto.

---

### 2. AnalysisValidator (`src/core/agents/analysis_validator.py`)

#### **Criterios de Validación - RELAJADOS**

**ANTES** (demasiado estricto):
```
🔴 INVÁLIDO si:
1. Sin estructura
2. Type desconocido → type = "unknown"
3. Metadata vacía → TODAS las keys vacías/null
4. Error de ejecución
```

**DESPUÉS** (permisivo):
```
🔴 INVÁLIDO SOLO si:
1. Crash de ejecución → Traceback de Python
2. Sin output estructurado → No es dict
3. Error SIN metadata → Solo {"error": "..."} sin info

🟢 VÁLIDO si:
1. Retorna dict estructurado → Aunque sea {"type": "pdf"}
2. Describe algo → Aunque sea parcial
3. Valores falsy OK → 0, False, [] son info ÚTIL
4. Type unknown CON contexto → {"type": "unknown", "reason": "..."} es VÁLIDO
5. Error CON metadata → {"error": "...", "partial_info": {...}} es VÁLIDO
```

**Ejemplos de insights VÁLIDOS** (ahora acepta):
- ✅ `{"type": "pdf", "pages": 0}` → PDF vacío (falsy OK)
- ✅ `{"type": "email", "attachments": []}` → Sin attachments (lista vacía OK)
- ✅ `{"type": "unknown", "reason": "corrupted"}` → Explica por qué (OK)
- ✅ `{"type": "pdf", "size": 1024}` → Mínimo pero útil (OK)

**Resultado**: Menos falsos negativos, solo rechaza crashes reales.

---

### 3. CodeGenerator (`src/core/agents/code_generator.py`)

**Mismo truncamiento inteligente** que DataAnalyzer para consistencia.

---

### 4. Orchestrator (`src/core/agents/orchestrator.py`)

#### **Logging Mejorado**

**AGREGADO** en retry loop cuando AnalysisValidator rechaza:
```python
self.logger.warning(f"⚠️ {error_msg}")
self.logger.warning(f"   📊 Insights rechazados:")
self.logger.warning(f"   {json.dumps(insights, indent=6)}")

if suggestions:
    self.logger.warning(f"   💡 Suggestions del validator:")
    for i, sug in enumerate(suggestions, 1):
        self.logger.warning(f"      {i}. {sug}")
```

**Resultado**: Mejor visibilidad para debugging.

---

## ✅ Tests Ejecutados

**Archivo**: `test_truncamiento_inteligente.py`

```
✅ TEST 1: Dict/Lista normal → Preservado completo
✅ TEST 2: PDF base64 → Truncado con metadata
✅ TEST 3: Lista >100 items → Truncada a 5 items + mensaje
✅ TEST 4: CSV largo → Detectado y truncado
✅ TEST 5: String mediano → Preview incluido
✅ TEST 6: Valores falsy → Preservados correctamente
✅ TEST 7: Depth profundo → Limitado a max_depth=4
```

**Resultado**: ✅ Todos los tests pasan

---

## 📊 Impacto Esperado

### **ANTES** (problemas):
1. ❌ Dicts/listas truncados → LLM no podía leer data estructurada
2. ❌ DataAnalyzer analizaba TODO → Código innecesario
3. ❌ AnalysisValidator muy estricto → Rechazaba insights válidos
4. ❌ Loops de retry infinitos → Falsos negativos

### **DESPUÉS** (soluciones):
1. ✅ Dicts/listas completos → LLM lee toda la estructura
2. ✅ DataAnalyzer solo analiza data truncada → Código eficiente
3. ✅ AnalysisValidator permisivo → Acepta insights mínimos
4. ✅ Menos retries innecesarios → Solo retry en crashes reales

---

## 🔧 Archivos Modificados

1. ✅ `src/core/agents/data_analyzer.py`
   - `_summarize_value()` - Truncamiento inteligente
   - `_generate_analysis_code()` - Prompt mejorado
   - `parse_insights()` - Validación agregada

2. ✅ `src/core/agents/analysis_validator.py`
   - `_build_prompt()` - Criterios permisivos

3. ✅ `src/core/agents/code_generator.py`
   - `_summarize_value()` - Mismo truncamiento que DataAnalyzer

4. ✅ `src/core/agents/orchestrator.py`
   - Logging mejorado en retry loop
   - Import de `json` agregado

5. ✅ `test_truncamiento_inteligente.py` (nuevo)
   - Tests completos de validación

---

## 🎯 Próximos Pasos

1. **Testing en producción**:
   - Monitorear logs para ver si AnalysisValidator sigue rechazando
   - Verificar que DataAnalyzer no analiza data ya visible
   - Confirmar que dicts/listas llegan completos

2. **Casos edge**:
   - Emails sin attachments → Debe ser VÁLIDO
   - PDFs corruptos → Debe ser VÁLIDO (con type="unknown")
   - Data vacía → Debe ser VÁLIDO (valores falsy OK)

3. **Optimizaciones** (si es necesario):
   - Ajustar límite de 100 items para listas
   - Ajustar límite de 1000 chars para strings
   - Agregar más tipos detectables (XML, JSON, etc.)

---

## 📝 Notas Técnicas

### **Detección de Tipos en Base64**

Los strings base64 se detectan por sus magic bytes:
- PDF: `JVBERi` (magic bytes de "%PDF-1")
- PNG: `iVBOR` (magic bytes de "\x89PNG\r\n")
- JPEG: `/9j/` (magic bytes de "\xff\xd8\xff")

### **Max Depth**

Aumentado de 2 → 4 para permitir estructuras más profundas:
```python
{
  "level1": {
    "level2": {
      "level3": {
        "level4": {...}  # ← Hasta aquí se preserva
      }
    }
  }
}
```

### **Límite de Listas**

- Lista < 100 items → Completa
- Lista ≥ 100 items → Primeros 5 + mensaje `"... (+N more items)"`

---

**End of Document**
