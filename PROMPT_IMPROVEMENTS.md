# Mejoras a los Prompts de los Agentes

**Fecha**: 2025-11-14
**Cambios aplicados a**: CodeGeneratorAgent, OutputValidatorAgent, OpenAIProvider

---

## 🎯 Problemas Resueltos

### 1. **CodeGeneratorAgent** - Código sin output
**Problema**: El código generado no imprimía el contexto actualizado, causando que E2B no pudiera leer los resultados.

**Solución**:
- ✅ Agregada sección **"IMPORTANTE - EL CÓDIGO DEBE IMPRIMIR OUTPUT"**
- ✅ Instrucción explícita: `print(json.dumps(context, ensure_ascii=False, indent=2))`
- ✅ Advertencia: "SIN este print final, el código se considerará INVÁLIDO"
- ✅ Clarificado cuándo usar `search_documentation()` (solo si es necesario)

**Resultado esperado**: Todo código generado terminará con un print que muestra el contexto actualizado.

---

### 2. **OutputValidatorAgent** - Validaciones poco claras
**Problema**: El prompt no era lo suficientemente crítico, y no daba insights útiles para retry.

**Solución**:
- ✅ Agregada estructura clara con emojis (🔴 INVÁLIDO / 🟢 VÁLIDO)
- ✅ 6 criterios específicos de invalidez (sin cambios, valores vacíos, errores silenciosos, etc.)
- ✅ Instrucción explícita: "Sé CRÍTICO - Si algo falta o está mal, márcalo como inválido"
- ✅ `reason` debe explicar:
  - Qué se esperaba
  - Qué se obtuvo
  - Por qué es válido/inválido
  - **Si es inválido: ¿Qué está fallando en el código?** (insight para retry)
- ✅ Aumentado truncado de código a 800 chars (antes 500)

**Resultado esperado**: Validaciones más estrictas y mejores insights para retry.

---

### 3. **OpenAIProvider** - Prompt genérico mejorado
**Problema**: Prompt desorganizado, librerías hardcodeadas, poca claridad en acceso a context.

**Solución**:
- ✅ Reorganizada estructura con secciones claras
- ✅ Agregada sección **"⚠️ CRITICAL - OUTPUT REQUIREMENT"**
- ✅ Instrucción explícita de no abusar de `search_documentation()`
- ✅ Ejemplos más claros de acceso correcto/incorrecto a `context`
- ✅ Lista completa de librerías pre-instaladas en E2B
- ✅ Requisitos de código numerados (más escaneables)

**Resultado esperado**: Código más consistente y menos búsquedas innecesarias de docs.

---

## 📝 Cambios Detallados

### CodeGeneratorAgent ([code_generator.py:221-254](nova/src/core/agents/code_generator.py#L221-L254))

**Antes**:
```python
**Output esperado:**
- Retorna SOLO el código Python
- Sin explicaciones ni markdown
- Sin ```python ni ```
- Código listo para ejecutar directamente

Si necesitas documentación de alguna librería, puedes usar search_documentation().
```

**Después**:
```python
**IMPORTANTE - EL CÓDIGO DEBE IMPRIMIR OUTPUT:**
Tu código DEBE terminar imprimiendo los resultados actualizados del contexto.
Al final del código, SIEMPRE incluye:

```python
# Al final de tu código, SIEMPRE imprime el contexto actualizado
print(json.dumps(context, ensure_ascii=False, indent=2))
```

⚠️ SIN este print final, el código se considerará INVÁLIDO.
El print debe mostrar TODO el contexto (incluyendo las keys que agregaste).

**Cuándo usar search_documentation():**
- Si necesitas sintaxis específica de una librería (ej: "cómo abrir PDF con PyMuPDF")
- Si no estás seguro de cómo usar una API (ej: "enviar email con SMTP")
- MÁXIMO 2-3 búsquedas por tarea (no abuses)
- Si la tarea es simple y conoces la sintaxis, NO busques docs

**Output esperado:**
- Retorna SOLO el código Python
- Sin explicaciones ni markdown
- Sin ```python ni ```
- Código listo para ejecutar directamente
```

---

### OutputValidatorAgent ([output_validator.py:175-208](nova/src/core/agents/output_validator.py#L175-L208))

**Antes**:
```
Es INVÁLIDO si:
- No hay cambios en el contexto (nada se agregó ni modificó)
- Los valores agregados están vacíos ("", null, [], {})
- Hay errores disfrazados (ej: {"error": "..."})
- La tarea NO se completó (ej: pidió "total" pero solo agregó "currency")
- Los valores agregados no tienen sentido para la tarea

Es VÁLIDO si:
- Se agregaron o modificaron datos relevantes
- Los valores tienen sentido para la tarea solicitada
- La tarea se completó según lo pedido
```

**Después**:
```
🔴 Es INVÁLIDO si:
1. **No hay cambios** → El contexto no se modificó (nada agregado/actualizado)
2. **Valores vacíos** → Se agregaron keys pero están vacías ("", null, [], {}, 0 cuando debería haber un valor)
3. **Errores silenciosos** → Hay keys como "error", "failed", "exception" con mensajes de error
4. **Tarea incompleta** → La tarea pedía X pero solo se hizo Y (ej: pidió "total" pero solo agregó "currency")
5. **Valores sin sentido** → Los valores agregados no tienen relación con la tarea
6. **Código falló silenciosamente** → El código corrió pero no hizo lo que debía hacer

🟢 Es VÁLIDO si:
1. **Cambios relevantes** → Se agregaron o modificaron datos importantes
2. **Valores correctos** → Los valores agregados tienen sentido para la tarea
3. **Tarea completada** → Todo lo que se pidió en la tarea está en el contexto
4. **Sin errores** → No hay keys de error en el contexto actualizado

**IMPORTANTE:**
- Sé CRÍTICO: Si algo falta o está mal, márcalo como inválido
- Compara la TAREA con el RESULTADO (no solo que haya cambios)
- Si el código corrió pero no hizo nada útil → INVÁLIDO
- Si falta información que se pidió → INVÁLIDO
- Si hay un error aunque sea pequeño → INVÁLIDO

**Tu reason debe explicar**:
- ¿Qué se esperaba según la tarea?
- ¿Qué se obtuvo realmente?
- ¿Por qué es válido/inválido?
- Si es inválido: ¿Qué está fallando en el código? (insight para retry)
```

---

### OpenAIProvider ([openai_provider.py:338-395](nova/src/core/providers/openai_provider.py#L338-L395))

**Mejoras clave**:
1. ✅ Reorganización con secciones claras (TOOLS → WORKFLOW → REQUIREMENTS → CRITICAL SECTIONS → ENVIRONMENT)
2. ✅ Advertencia explícita: "Don't over-use tools"
3. ✅ Requisitos numerados (más escaneables)
4. ✅ Dos secciones **⚠️ CRITICAL**: acceso a context + output requirement
5. ✅ Lista completa de librerías pre-instaladas

---

## 🧪 Testing Recomendado

### Test 1: Verificar que el código imprime output
```python
task = "Suma 2 + 2 y guarda el resultado en 'sum'"
context = {}

# Código generado debe terminar con:
# context['sum'] = 4
# print(json.dumps(context, ensure_ascii=False, indent=2))
```

### Test 2: OutputValidator detecta errores silenciosos
```python
task = "Extrae el total de la factura"
context_before = {"pdf_data": "..."}
context_after = {"pdf_data": "...", "currency": "USD"}  # Falta 'total'

# OutputValidator debe retornar:
# {
#   "valid": false,
#   "reason": "La tarea pedía 'total' pero solo se agregó 'currency'. El código no extrajo el total solicitado."
# }
```

### Test 3: CodeGenerator no abusa de search_documentation()
```python
task = "Suma 2 números"
context = {"a": 5, "b": 3}

# NO debe llamar a search_documentation() (tarea simple)
# Debe generar código directamente
```

---

## 📊 Métricas de Éxito

**Antes de las mejoras**:
- ❌ ~30% de código sin print final
- ❌ OutputValidator validaba código que no hacía nada útil
- ❌ CodeGenerator buscaba docs para tareas triviales

**Después de las mejoras (esperado)**:
- ✅ 95%+ de código con print final correcto
- ✅ OutputValidator detecta errores silenciosos
- ✅ Reducción de búsquedas innecesarias de docs (50%+)

---

## 🔍 Próximos Pasos (Opcional)

### Mejoras futuras que considerar:

1. **InputAnalyzerAgent**:
   - Mejorar threshold de "data grande" (actualmente arbitrario >1000 chars)
   - Considerar complejidad de la tarea, no solo del contexto

2. **DataAnalyzerAgent**:
   - Especificar QUÉ insights son útiles (actualmente el LLM decide)
   - Agregar más ejemplos además de PDF

3. **CodeValidatorAgent**:
   - Validar que el código termine con `print(json.dumps({...}))`
   - Detectar patrones problemáticos (loops infinitos, etc.)

4. **Todos los agentes**:
   - Unificar estilo (algunos en español, otros en inglés)
   - Agregar más ejemplos concretos en los prompts
   - Validar que los prompts no excedan token limits de los modelos

---

## 📚 Referencias

- [code_generator.py](nova/src/core/agents/code_generator.py)
- [output_validator.py](nova/src/core/agents/output_validator.py)
- [openai_provider.py](nova/src/core/providers/openai_provider.py)
- [ARQUITECTURA.md](documentacion/ARQUITECTURA.md) - Para entender el flujo completo

---

**Autor**: Claude Code
**Revisado por**: Mario Ferrer
