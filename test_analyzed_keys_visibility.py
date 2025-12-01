#!/usr/bin/env python3
"""
Test para verificar que _analyzed_keys NO se trunca en InputAnalyzer.
"""

from src.core.agents.input_analyzer import InputAnalyzerAgent
from openai import AsyncOpenAI
import os

# Mock context (similar al ejemplo que compartiste)
context = {
    "email_from": "mario <mario@bimea.es>",
    "email_subject": "yesyes",
    "email_date": "Fri, 28 Nov 2025 14:06:22 +0100",
    "attachments": [
        {
            "filename": "invoice.pdf",
            "data": "JVBERi0xLjQKJeLjz9MKMyAwIG9iago8..."  # PDF base64
        }
    ],
    "has_pdf_decision": "true",
    "_analyzed_keys": [
        "email_from",
        "email_subject",
        "email_date",
        "has_pdf_decision"
        # Nota: "attachments" NO está aquí, por lo que SÍ necesita análisis
    ]
}

print("=" * 80)
print("TEST: Verificar que _analyzed_keys NO se trunca")
print("=" * 80)

# Crear InputAnalyzer (sin cliente real, solo para usar _summarize_context)
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", "fake-key"))
analyzer = InputAnalyzerAgent(client)

# Resumir contexto
summary = analyzer._summarize_context(context)

print("\n1️⃣ Contexto ORIGINAL:")
print(f"   _analyzed_keys: {context['_analyzed_keys']}")
print(f"   attachments: {type(context['attachments']).__name__} with {len(context['attachments'])} items")

print("\n2️⃣ Contexto RESUMIDO (lo que ve el LLM):")
print(f"   _analyzed_keys: {summary['_analyzed_keys']}")
print(f"   attachments: {summary['attachments']}")

print("\n3️⃣ Verificación:")

# _analyzed_keys debe estar completo (NO truncado)
if isinstance(summary["_analyzed_keys"], list):
    if summary["_analyzed_keys"] == context["_analyzed_keys"]:
        print(f"   ✅ _analyzed_keys NO se truncó (lista completa con {len(summary['_analyzed_keys'])} items)")
    else:
        print(f"   ❌ _analyzed_keys se modificó incorrectamente")
else:
    print(f"   ❌ FALLO: _analyzed_keys se truncó a: {summary['_analyzed_keys']}")

# Verificar que el LLM puede saber si 'attachments' necesita análisis
if isinstance(summary["_analyzed_keys"], list):
    if "attachments" in summary["_analyzed_keys"]:
        print(f"   ℹ️  'attachments' está en _analyzed_keys → NO necesita análisis")
    else:
        print(f"   ℹ️  'attachments' NO está en _analyzed_keys → SÍ necesita análisis")
        print(f"   ✅ El LLM puede detectar correctamente que 'attachments' necesita análisis")

print("\n4️⃣ Lo que el LLM verá en el prompt:")
import json
print(json.dumps(summary, indent=2, ensure_ascii=False))

print("\n" + "=" * 80)
print("Resultado: El LLM ahora puede ver EXACTAMENTE qué keys fueron analizadas")
print("=" * 80)
