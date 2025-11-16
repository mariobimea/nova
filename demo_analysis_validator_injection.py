#!/usr/bin/env python3
"""
Demo: Inyección de insights del AnalysisValidator al CodeGenerator

Este script demuestra cómo los insights del DataAnalyzer Y el reasoning
del AnalysisValidator se pasan juntos al CodeGenerator.
"""

from src.core.agents.state import ContextState

# Simular el flujo del orchestrator
def demo():
    print("=" * 80)
    print("DEMO: Inyección de insights del AnalysisValidator al CodeGenerator")
    print("=" * 80)
    print()

    # 1. Estado inicial
    initial_context = {
        "email_user": "test@example.com",
        "latest_email_data": {
            "attachments": [
                {
                    "filename": "invoice.pdf",
                    "data": "JVBERi0xLjQK..."  # PDF en base64 (truncado)
                }
            ]
        }
    }

    context_state = ContextState(
        initial=initial_context.copy(),
        current=initial_context.copy()
    )

    print("📦 PASO 1: Contexto inicial")
    print(f"   Keys: {list(context_state.current.keys())}")
    print()

    # 2. DataAnalyzer genera insights
    print("🔬 PASO 2: DataAnalyzer genera insights")
    data_insights = {
        "type": "pdf",
        "pages": 1,
        "has_text_layer": False,  # ⚠️ PDF escaneado, sin texto extraíble
        "filename": "invoice.pdf"
    }
    context_state.data_insights = data_insights
    print(f"   Insights: {data_insights}")
    print()

    # 3. AnalysisValidator valida y genera reasoning
    print("✅ PASO 3: AnalysisValidator valida insights y genera reasoning")
    analysis_validation = {
        "valid": True,
        "reason": (
            "El PDF tiene 1 página pero NO tiene capa de texto (has_text_layer=false). "
            "Esto es VÁLIDO porque indica que el PDF es una imagen escaneada y requiere OCR "
            "(Optical Character Recognition) para extraer el texto. El CodeGenerator debería "
            "usar EasyOCR o similar en lugar de PyMuPDF.get_text()."
        ),
        "suggestions": [
            "Usa EasyOCR para extraer texto de PDFs escaneados",
            "Convierte cada página a imagen y aplica OCR",
            "Verifica que EasyOCR esté disponible en el template"
        ]
    }
    context_state.analysis_validation = analysis_validation
    print(f"   Valid: {analysis_validation['valid']}")
    print(f"   Reason: {analysis_validation['reason'][:100]}...")
    print(f"   Suggestions: {len(analysis_validation['suggestions'])} sugerencias")
    print()

    # 4. CodeGenerator recibe AMBOS
    print("💻 PASO 4: CodeGenerator recibe el contexto completo")
    print()
    print("   El prompt del CodeGenerator ahora incluye:")
    print()
    print("   " + "─" * 76)
    print("   📊 INSIGHTS DEL DATANALYZER:")
    print(f"      {data_insights}")
    print()
    print("   " + "─" * 76)
    print("   🧠 ANÁLISIS DEL ANALYSISVALIDATOR:")
    print(f"      {analysis_validation['reason'][:200]}...")
    print()
    print("   " + "─" * 76)
    print("   💡 SUGERENCIAS:")
    for i, suggestion in enumerate(analysis_validation['suggestions'], 1):
        print(f"      {i}. {suggestion}")
    print("   " + "─" * 76)
    print()

    # 5. Resultado esperado
    print("🎯 PASO 5: Resultado esperado")
    print()
    print("   Con esta información, el CodeGenerator debería generar código que:")
    print("   ✅ Detecta que has_text_layer=false")
    print("   ✅ Entiende que necesita OCR (gracias al reasoning)")
    print("   ✅ Usa EasyOCR en lugar de PyMuPDF.get_text() (gracias a las suggestions)")
    print()
    print("   Código generado (ejemplo):")
    print("   " + "─" * 76)
    print("""
   import easyocr
   import fitz
   import base64
   from PIL import Image
   import io

   # Decodificar PDF
   pdf_bytes = base64.b64decode(context['latest_email_data']['attachments'][0]['data'])
   doc = fitz.open(stream=pdf_bytes, filetype="pdf")

   # Inicializar OCR
   reader = easyocr.Reader(['en', 'es'])

   # Extraer texto con OCR (porque has_text_layer=false)
   extracted_text = ""
   for page_num in range(len(doc)):
       page = doc[page_num]
       pix = page.get_pixmap()
       img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

       # OCR en la imagen
       result = reader.readtext(np.array(img))
       extracted_text += " ".join([text for (bbox, text, prob) in result])

   context['extracted_text'] = extracted_text
    """)
    print("   " + "─" * 76)
    print()

    print("=" * 80)
    print("✅ DEMO COMPLETADO")
    print("=" * 80)
    print()
    print("RESUMEN:")
    print("  • El DataAnalyzer detecta: 'has_text_layer: false'")
    print("  • El AnalysisValidator explica: 'necesita OCR porque es imagen escaneada'")
    print("  • El CodeGenerator recibe AMBOS y genera código con EasyOCR")
    print("  • Resultado: El workflow puede procesar PDFs escaneados correctamente")
    print()


if __name__ == "__main__":
    demo()
