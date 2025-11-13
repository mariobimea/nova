"""
MultiAgentOrchestrator - Coordinador central de todos los agentes.

Responsabilidad:
    Coordinar la ejecución de todos los agentes y gestionar el flujo completo.

Características:
    - Gestiona ExecutionState y ContextState
    - Retry inteligente (max 3 intentos, solo repite CodeGenerator)
    - Metadata completa de todos los agentes
"""

from typing import Dict
import logging
from dataclasses import asdict

from .state import ExecutionState, ContextState
from .input_analyzer import InputAnalyzerAgent
from .data_analyzer import DataAnalyzerAgent
from .code_generator import CodeGeneratorAgent
from .code_validator import CodeValidatorAgent
from .output_validator import OutputValidatorAgent
from ..e2b.executor import E2BExecutor

logger = logging.getLogger(__name__)


class MultiAgentOrchestrator:
    """Coordinador central de todos los agentes"""

    def __init__(
        self,
        input_analyzer: InputAnalyzerAgent,
        data_analyzer: DataAnalyzerAgent,
        code_generator: CodeGeneratorAgent,
        code_validator: CodeValidatorAgent,
        output_validator: OutputValidatorAgent,
        e2b_executor: E2BExecutor,
        max_retries: int = 3
    ):
        self.input_analyzer = input_analyzer
        self.data_analyzer = data_analyzer
        self.code_generator = code_generator
        self.code_validator = code_validator
        self.output_validator = output_validator
        self.e2b = e2b_executor
        self.max_retries = max_retries
        self.logger = logger

    async def execute_workflow(
        self,
        task: str,
        context: Dict,
        timeout: int = 60
    ) -> Dict:
        """
        Ejecuta el workflow completo con todos los agentes.

        Args:
            task: Tarea a resolver (en lenguaje natural)
            context: Contexto inicial
            timeout: Timeout para ejecución en E2B

        Returns:
            {
                ...context_actualizado,
                "_ai_metadata": {...execution_state}
            }
        """
        # 1. Inicializar estados
        execution_state = ExecutionState()
        context_state = ContextState(
            initial=context.copy(),
            current=context.copy()
        )

        self.logger.info(f"🚀 Iniciando workflow: '{task[:50]}...'")

        try:
            # 2. InputAnalyzer (UNA SOLA VEZ)
            self.logger.info("📊 Ejecutando InputAnalyzer...")
            input_analysis = await self.input_analyzer.execute(task, context_state)

            if not input_analysis.success:
                raise Exception(f"InputAnalyzer falló: {input_analysis.error}")

            execution_state.input_analysis = input_analysis.data
            execution_state.add_timing("InputAnalyzer", input_analysis.execution_time_ms)

            # 3. DataAnalyzer (UNA SOLA VEZ, si es necesario)
            if input_analysis.data["needs_analysis"]:
                self.logger.info("🔬 Ejecutando DataAnalyzer...")
                data_analysis = await self.data_analyzer.execute(context_state)

                if not data_analysis.success:
                    raise Exception(f"DataAnalyzer falló: {data_analysis.error}")

                execution_state.data_analysis = data_analysis.data
                execution_state.add_timing("DataAnalyzer", data_analysis.execution_time_ms)
                context_state.data_insights = data_analysis.data

            # 4. Loop de generación → validación → ejecución → validación
            success = False
            for attempt in range(1, self.max_retries + 1):
                execution_state.attempts = attempt
                self.logger.info(f"🔄 Intento {attempt}/{self.max_retries}")

                try:
                    # 4.1 CodeGenerator
                    self.logger.info("💻 Generando código...")
                    code_gen = await self.code_generator.execute(
                        task=task,
                        context_state=context_state,
                        error_history=execution_state.errors
                    )

                    if not code_gen.success:
                        execution_state.add_error("code_generation", code_gen.error)
                        continue

                    execution_state.code_generation = code_gen.data
                    execution_state.add_timing("CodeGenerator", code_gen.execution_time_ms)

                    # 4.2 CodeValidator (pre-ejecución)
                    self.logger.info("🔍 Validando código...")
                    code_val = await self.code_validator.execute(
                        code=code_gen.data["code"],
                        context=context_state.current
                    )

                    if not code_val.success:
                        execution_state.add_error("code_validation_error", code_val.error)
                        continue

                    execution_state.code_validation = code_val.data
                    execution_state.add_timing("CodeValidator", code_val.execution_time_ms)

                    if not code_val.data["valid"]:
                        # Retry con feedback del validator
                        error_msg = f"Código inválido: {', '.join(code_val.data['errors'])}"
                        self.logger.warning(f"⚠️ {error_msg}")
                        execution_state.add_error("code_validation", error_msg)
                        continue

                    # 4.3 E2B Execution
                    self.logger.info("⚡ Ejecutando código en E2B...")
                    try:
                        updated_context = await self.e2b.execute_code(
                            code=code_gen.data["code"],
                            context=context_state.current,
                            timeout=timeout
                        )
                        context_state.current = updated_context
                        execution_state.execution_result = {"status": "success"}
                    except Exception as e:
                        error_msg = f"Error en E2B: {str(e)}"
                        self.logger.error(f"❌ {error_msg}")
                        execution_state.add_error("execution", error_msg)
                        continue

                    # 4.4 OutputValidator (post-ejecución)
                    self.logger.info("✅ Validando resultado...")
                    output_val = await self.output_validator.execute(
                        task=task,
                        context_before=context_state.initial,
                        context_after=context_state.current
                    )

                    if not output_val.success:
                        execution_state.add_error("output_validation_error", output_val.error)
                        continue

                    execution_state.output_validation = output_val.data
                    execution_state.add_timing("OutputValidator", output_val.execution_time_ms)

                    if not output_val.data["valid"]:
                        # Retry con feedback del validator
                        error_msg = f"Output inválido: {output_val.data['reason']}"
                        self.logger.warning(f"⚠️ {error_msg}")
                        execution_state.add_error("output_validation", error_msg)
                        continue

                    # ¡ÉXITO!
                    success = True
                    self.logger.info(f"🎉 Workflow completado exitosamente en intento {attempt}")
                    break

                except Exception as e:
                    error_msg = f"Error inesperado en intento {attempt}: {str(e)}"
                    self.logger.error(f"❌ {error_msg}")
                    execution_state.add_error("unexpected", error_msg)

                    if attempt == self.max_retries:
                        raise

            if not success:
                raise Exception(f"Workflow falló después de {self.max_retries} intentos")

            # 5. Retornar resultado + metadata
            result = {
                **context_state.current,
                "_ai_metadata": execution_state.to_dict()
            }

            self.logger.info(f"✅ Workflow completado. Total time: {execution_state.get_total_time_ms():.2f}ms")
            return result

        except Exception as e:
            self.logger.error(f"💥 Workflow falló: {str(e)}")
            # Retornar contexto original + metadata del error
            return {
                **context_state.initial,
                "_ai_metadata": {
                    **execution_state.to_dict(),
                    "final_error": str(e),
                    "status": "failed"
                }
            }
