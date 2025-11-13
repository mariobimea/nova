"""
CodeValidatorAgent - Valida código sin usar IA.

Responsabilidad:
    Validar código ANTES de ejecutarlo usando parsing estático.

Características:
    - Modelo: N/A (parsing con AST)
    - Ejecuciones: Después de cada generación
    - Tool calling: NO
    - Costo: $0 (gratis e instantáneo)
"""

import ast
import re
from typing import Dict, List, Set, Tuple
import logging

from .base import BaseAgent, AgentResponse


class CodeValidatorAgent(BaseAgent):
    """Valida código Python usando análisis estático (sin IA)"""

    def __init__(self):
        super().__init__("CodeValidator")

        # Imports peligrosos que no permitimos
        self.dangerous_imports = {
            "os", "subprocess", "sys", "shutil", "pathlib",
            "socket", "urllib", "http", "ftplib"
        }

        # Python built-ins que están disponibles sin importar
        # Esto evita falsos positivos al validar código generado
        import builtins
        self.python_builtins = set(dir(builtins))

        # Módulos que están pre-instalados en E2B template y son seguros
        # Estos NO deben reportarse como "imports peligrosos"
        self.safe_modules = {
            # E2B Template packages (ver e2b.Dockerfile)
            "fitz",           # PyMuPDF (PDF processing)
            "requests",       # HTTP/APIs
            "pandas",         # Data analysis
            "PIL",            # Pillow (Image processing)
            "psycopg2",       # PostgreSQL
            "dotenv",         # python-dotenv

            # Python stdlib (siempre disponibles)
            "json", "re", "base64", "csv", "email", "io",
            "imaplib", "smtplib", "ssl", "datetime", "time",
            "collections", "itertools", "functools", "math",
            "hashlib", "hmac", "uuid", "tempfile", "mimetypes",

            # Submódulos comunes
            "email.mime", "email.header", "email.utils",
            "pandas.io", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont"
        }

    async def execute(self, code: str, context: Dict) -> AgentResponse:
        """
        Valida código antes de ejecutarlo.

        Args:
            code: Código Python a validar
            context: Contexto disponible para el código

        Returns:
            AgentResponse con:
                - valid: bool
                - errors: List[str]
                - checks_passed: List[str]
        """
        try:
            errors = []
            checks_passed = []

            # 1. Validar sintaxis
            syntax_valid, syntax_error = self._check_syntax(code)
            if syntax_valid:
                checks_passed.append("syntax")
            else:
                errors.append(f"Syntax error: {syntax_error}")

            # Solo continuar si la sintaxis es válida
            if not syntax_valid:
                return self._create_response(
                    success=True,  # La validación se ejecutó correctamente
                    data={
                        "valid": False,
                        "errors": errors,
                        "checks_passed": checks_passed
                    },
                    execution_time_ms=0.0
                )

            # Parsear código
            tree = ast.parse(code)

            # 2. Validar variables no definidas
            undefined_vars = self._check_undefined_variables(tree)
            if not undefined_vars:
                checks_passed.append("variables")
            else:
                for var, line in undefined_vars:
                    errors.append(f"Variable '{var}' usada en línea {line} pero no definida")

            # 3. Validar acceso a context
            context_errors = self._check_context_access(tree, context)
            if not context_errors:
                checks_passed.append("context_access")
            else:
                errors.extend(context_errors)

            # 4. Validar imports
            dangerous = self._check_imports(tree)
            if not dangerous:
                checks_passed.append("imports")
            else:
                errors.append(f"Imports peligrosos detectados: {dangerous}")

            # 5. Validar que no haya operaciones peligrosas
            dangerous_ops = self._check_dangerous_operations(tree)
            if not dangerous_ops:
                checks_passed.append("operations")
            else:
                errors.extend(dangerous_ops)

            valid = len(errors) == 0

            if valid:
                self.logger.info(f"✅ Código válido - Checks passed: {checks_passed}")
            else:
                self.logger.warning(f"❌ Código inválido - Errors: {len(errors)}")

            return self._create_response(
                success=True,  # La validación se ejecutó correctamente
                data={
                    "valid": valid,
                    "errors": errors,
                    "checks_passed": checks_passed
                },
                execution_time_ms=0.0
            )

        except Exception as e:
            self.logger.error(f"Error en CodeValidator: {str(e)}")
            return self._create_response(
                success=False,
                error=str(e),
                execution_time_ms=0.0
            )

    def _check_syntax(self, code: str) -> Tuple[bool, str]:
        """Valida sintaxis Python"""
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, f"Línea {e.lineno}: {e.msg}"

    def _check_undefined_variables(self, tree: ast.AST) -> List[Tuple[str, int]]:
        """
        Detecta variables usadas pero no definidas.

        Retorna: Lista de (variable_name, line_number)
        """
        defined_vars = {"context"}  # context siempre está disponible
        undefined = []

        # Primero, recoger todos los imports y defines
        class DefineCollector(ast.NodeVisitor):
            def visit_Import(self, node):
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    defined_vars.add(name)
                self.generic_visit(node)

            def visit_ImportFrom(self, node):
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    defined_vars.add(name)
                self.generic_visit(node)

            def visit_Name(self, node):
                if isinstance(node.ctx, ast.Store):
                    defined_vars.add(node.id)
                self.generic_visit(node)

            def visit_comprehension(self, node):
                # Variables de loop comprehension
                if isinstance(node.target, ast.Name):
                    defined_vars.add(node.target.id)
                self.generic_visit(node)

        DefineCollector().visit(tree)

        # Luego, buscar usos de variables no definidas
        python_builtins = self.python_builtins  # Referencia local para closure

        class VariableVisitor(ast.NodeVisitor):
            def visit_Name(self, node):
                if isinstance(node.ctx, ast.Load):
                    if node.id not in defined_vars:
                        # Ignorar built-ins de Python (Exception, isinstance, str, print, etc.)
                        if node.id not in python_builtins:
                            undefined.append((node.id, node.lineno))
                self.generic_visit(node)

        VariableVisitor().visit(tree)
        return undefined

    def _check_context_access(self, tree: ast.AST, context: Dict) -> List[str]:
        """
        Valida que accesos a context usen keys que existen.

        Busca patrones como: context['key'] o context.get('key')
        """
        errors = []
        context_keys = set(context.keys())

        class ContextVisitor(ast.NodeVisitor):
            def visit_Subscript(self, node):
                # Detectar context['key'] - solo validar LECTURA, no escritura
                if isinstance(node.value, ast.Name) and node.value.id == "context":
                    if isinstance(node.slice, ast.Constant):
                        key = node.slice.value
                        # Solo validar si es Load (lectura), no Store (escritura)
                        if isinstance(node.ctx, ast.Load) and key not in context_keys:
                            errors.append(
                                f"Línea {node.lineno}: Acceso a context['{key}'] pero esa key no existe. "
                                f"Keys disponibles: {list(context_keys)}"
                            )
                self.generic_visit(node)

            def visit_Call(self, node):
                # Detectar context.get('key')
                if isinstance(node.func, ast.Attribute):
                    if (isinstance(node.func.value, ast.Name) and
                        node.func.value.id == "context" and
                        node.func.attr == "get"):
                        if node.args and isinstance(node.args[0], ast.Constant):
                            key = node.args[0].value
                            if key not in context_keys:
                                errors.append(
                                    f"Línea {node.lineno}: context.get('{key}') pero esa key no existe"
                                )
                self.generic_visit(node)

        ContextVisitor().visit(tree)
        return errors

    def _check_imports(self, tree: ast.AST) -> Set[str]:
        """
        Detecta imports peligrosos.

        Permite imports de:
        - Python stdlib seguros (json, re, datetime, etc.)
        - E2B template packages (fitz, pandas, PIL, etc.)

        Bloquea imports peligrosos:
        - os, subprocess, sys (acceso al sistema)
        - socket, urllib, http (acceso a red sin control)
        """
        dangerous = set()
        dangerous_imports = self.dangerous_imports  # Referencia local
        safe_modules = self.safe_modules  # Referencia local

        class ImportVisitor(ast.NodeVisitor):
            def visit_Import(self, node):
                for alias in node.names:
                    # Extraer el módulo raíz (e.g., "email.mime.text" → "email")
                    root_module = alias.name.split('.')[0]

                    # Solo reportar si es peligroso Y NO está en safe_modules
                    if root_module in dangerous_imports and root_module not in safe_modules:
                        dangerous.add(alias.name)

            def visit_ImportFrom(self, node):
                if node.module:
                    # Extraer el módulo raíz
                    root_module = node.module.split('.')[0]

                    # Solo reportar si es peligroso Y NO está en safe_modules
                    if root_module in dangerous_imports and root_module not in safe_modules:
                        dangerous.add(node.module)

        ImportVisitor().visit(tree)
        return dangerous

    def _check_dangerous_operations(self, tree: ast.AST) -> List[str]:
        """Detecta operaciones peligrosas como exec(), eval(), etc."""
        errors = []
        dangerous_funcs = {"exec", "eval", "compile", "__import__"}

        class DangerousVisitor(ast.NodeVisitor):
            def visit_Call(self, node):
                if isinstance(node.func, ast.Name):
                    if node.func.id in dangerous_funcs:
                        errors.append(
                            f"Línea {node.lineno}: Uso de función peligrosa '{node.func.id}()' no permitido"
                        )
                self.generic_visit(node)

        DangerousVisitor().visit(tree)
        return errors
