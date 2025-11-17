"""
MultiAgentOrchestrator - Coordinador central de todos los agentes.

Responsabilidad:
    Coordinar la ejecución de todos los agentes y gestionar el flujo completo.

Características:
    - Gestiona ExecutionState y ContextState
    - Retry inteligente (max 3 intentos, solo repite CodeGenerator)
    - Metadata completa de todos los agentes
    - Registro granular de cada paso para Chain of Work Steps
"""

from typing import Dict, List, Optional
import logging
import time
import json
from datetime import datetime
from dataclasses import asdict

from .state import ExecutionState, ContextState
from .base import AgentResponse
from .input_analyzer import InputAnalyzerAgent
from .data_analyzer import DataAnalyzerAgent
from .code_generator import CodeGeneratorAgent
from .code_validator import CodeValidatorAgent
from .output_validator import OutputValidatorAgent
from .analysis_validator import AnalysisValidatorAgent
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
        analysis_validator: AnalysisValidatorAgent,
        e2b_executor: E2BExecutor,
        max_retries: int = 3
    ):
        self.input_analyzer = input_analyzer
        self.data_analyzer = data_analyzer
        self.code_generator = code_generator
        self.code_validator = code_validator
        self.output_validator = output_validator
        self.analysis_validator = analysis_validator
        self.e2b = e2b_executor
        self.max_retries = max_retries
        self.logger = logger

    def _summarize_context_for_step(self, context: Dict) -> Dict:
        """
        Resume el contexto para guardarlo en steps (evita guardar PDFs/data pesada).

        Args:
            context: Contexto completo

        Returns:
            Contexto resumido (strings largos truncados)
        """
        summary = {}

        for key, value in context.items():
            if isinstance(value, str):
                if len(value) > 200:
                    # Truncar strings largos (PDFs en base64, emails, etc.)
                    summary[key] = f"<string: {len(value)} chars>"
                else:
                    summary[key] = value
            elif isinstance(value, bytes):
                # Bytes (PDFs, imágenes)
                summary[key] = f"<bytes: {len(value)} bytes>"
            elif isinstance(value, (list, dict)):
                # Listas/dicts: mostrar tipo y cantidad
                summary[key] = f"<{type(value).__name__}: {len(value)} items>"
            elif isinstance(value, (int, float, bool)):
                # Números y booleanos: mantener valor real
                summary[key] = value
            else:
                # Otros tipos: mostrar tipo
                summary[key] = f"<{type(value).__name__}>"

        return summary

    def _create_step_record(
        self,
        step_number: int,
        step_name: str,
        agent_name: str,
        attempt_number: int,
        agent_response: AgentResponse,
        input_data: Dict,
        generated_code: Optional[str] = None,
        sandbox_id: Optional[str] = None
    ) -> Dict:
        """
        Crea un registro de step para guardar en chain_of_work_steps.

        Este método extrae toda la información relevante de la respuesta del agente
        y la formatea para persistencia en la base de datos.

        Args:
            step_number: Número secuencial del paso (1-6)
            step_name: Nombre del paso ("input_analysis", "code_generation", etc.)
            agent_name: Nombre del agente ("InputAnalyzer", "CodeGenerator", etc.)
            attempt_number: Número de intento (1-3)
            agent_response: Respuesta del agente (AgentResponse)
            input_data: Datos de entrada que recibió el agente (YA debe estar resumido)
            generated_code: Código generado (solo para CodeGenerator, DataAnalyzer)
            sandbox_id: ID del sandbox E2B (solo para E2BExecutor)

        Returns:
            Dict con toda la metadata del step para persistir
        """
        # Preparar output_data (sin código duplicado)
        output_data = agent_response.data if agent_response.success else None

        # Si es CodeGenerator, remover 'code' del output_data (ya está en generated_code)
        if agent_name == "CodeGenerator" and output_data and isinstance(output_data, dict):
            output_data = {k: v for k, v in output_data.items() if k != "code"}

        step_record = {
            "step_number": step_number,
            "step_name": step_name,
            "agent_name": agent_name,
            "attempt_number": attempt_number,
            "input_data": input_data,
            "output_data": output_data,
            "generated_code": generated_code,
            "sandbox_id": sandbox_id,
            "status": "success" if agent_response.success else "failed",
            "error_message": agent_response.error if not agent_response.success else None,
            "execution_time_ms": agent_response.execution_time_ms,
            "timestamp": datetime.utcnow()
        }

        # Agregar AI metadata si existe
        if agent_response.data and isinstance(agent_response.data, dict):
            # Model usado
            step_record["model_used"] = agent_response.data.get("model")

            # Tokens y costo (para AI agents)
            if "tokens" in agent_response.data:
                tokens = agent_response.data["tokens"]
                step_record["tokens_input"] = tokens.get("input")
                step_record["tokens_output"] = tokens.get("output")

            if "cost_usd" in agent_response.data:
                step_record["cost_usd"] = agent_response.data["cost_usd"]

            # Tool calls (solo CodeGenerator con RAG)
            if "tool_calls" in agent_response.data:
                step_record["tool_calls"] = agent_response.data["tool_calls"]

        return step_record

    async def execute_workflow(
        self,
        task: str,
        context: Dict,
        timeout: int = 60,
        node_type: Optional[str] = None
    ) -> Dict:
        """
        Ejecuta el workflow completo con todos los agentes.

        Args:
            task: Tarea a resolver (en lenguaje natural)
            context: Contexto inicial
            timeout: Timeout para ejecución en E2B
            node_type: Tipo de nodo ("action", "decision", etc.) - opcional

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

        # 🔥 NUEVO: Lista para registrar todos los steps
        steps_to_persist: List[Dict] = []

        self.logger.info(f"🚀 Iniciando workflow: '{task[:50]}...'")

        try:
            # 2. InputAnalyzer (UNA SOLA VEZ)
            self.logger.info("📊 Ejecutando InputAnalyzer...")
            input_analysis = await self.input_analyzer.execute(task, context_state)

            # 🔥 Registrar step 1: InputAnalyzer
            steps_to_persist.append(
                self._create_step_record(
                    step_number=1,
                    step_name="input_analysis",
                    agent_name="InputAnalyzer",
                    attempt_number=1,
                    agent_response=input_analysis,
                    input_data={
                        "task": task,
                        "context": self._summarize_context_for_step(context_state.current)
                    }
                )
            )

            if not input_analysis.success:
                raise Exception(f"InputAnalyzer falló: {input_analysis.error}")

            execution_state.input_analysis = input_analysis.data
            execution_state.add_timing("InputAnalyzer", input_analysis.execution_time_ms)

            # 3. DataAnalyzer (CON RETRY LOOP, si es necesario)
            if input_analysis.data["needs_analysis"]:
                analysis_success = False
                analysis_errors = []  # Para feedback loop

                for analysis_attempt in range(1, self.max_retries + 1):
                    self.logger.info(f"🔬 DataAnalyzer intento {analysis_attempt}/{self.max_retries}")

                    try:
                        # 3.1 DataAnalyzer genera código de análisis
                        self.logger.info("💻 Generando código de análisis...")
                        data_analysis = await self.data_analyzer.execute(
                            context_state=context_state,
                            error_history=analysis_errors
                        )

                        # Registrar step 2: DataAnalyzer
                        steps_to_persist.append(
                            self._create_step_record(
                                step_number=2,
                                step_name="data_analysis",
                                agent_name="DataAnalyzer",
                                attempt_number=analysis_attempt,
                                agent_response=data_analysis,
                                input_data={
                                    "context": self._summarize_context_for_step(context_state.current),
                                    "error_history": analysis_errors,
                                    "hint": input_analysis.data.get("reasoning")
                                },
                                generated_code=data_analysis.data.get("analysis_code") if data_analysis.success else None
                            )
                        )

                        if not data_analysis.success:
                            error_msg = f"DataAnalyzer falló: {data_analysis.error}"
                            self.logger.warning(f"⚠️ {error_msg}")
                            analysis_errors.append({
                                "stage": "data_analysis_generation",
                                "error": error_msg,
                                "attempt": analysis_attempt
                            })
                            continue

                        # 3.2 CodeValidator valida código de análisis
                        self.logger.info("🔍 Validando código de análisis...")
                        code_val = await self.code_validator.execute(
                            code=data_analysis.data["analysis_code"],
                            context=context_state.current
                        )

                        # Registrar step 2.1: CodeValidator (análisis)
                        steps_to_persist.append(
                            self._create_step_record(
                                step_number=2,  # mismo step_number pero diferente step_name
                                step_name="analysis_code_validation",
                                agent_name="CodeValidator",
                                attempt_number=analysis_attempt,
                                agent_response=code_val,
                                input_data={
                                    "code": data_analysis.data["analysis_code"],
                                    "context_keys": list(context_state.current.keys())
                                }
                            )
                        )

                        if not code_val.success or not code_val.data["valid"]:
                            error_msg = f"Código de análisis inválido: {', '.join(code_val.data.get('errors', []))}"
                            self.logger.warning(f"⚠️ {error_msg}")
                            analysis_errors.append({
                                "stage": "analysis_code_validation",
                                "error": error_msg,
                                "attempt": analysis_attempt
                            })
                            continue

                        # 3.3 E2B execution del código de análisis
                        self.logger.info("⚡ Ejecutando código de análisis en E2B...")
                        e2b_start = time.time()

                        try:
                            insights_result = await self.e2b.execute_code(
                                code=data_analysis.data["analysis_code"],
                                context=context_state.current,
                                timeout=30
                            )
                            e2b_time_ms = (time.time() - e2b_start) * 1000

                            # Parsear insights usando el método público del DataAnalyzer
                            insights = self.data_analyzer.parse_insights(insights_result)

                            # Registrar step 2.2: E2B Execution (análisis)
                            e2b_response = AgentResponse(
                                success=True,
                                data={"insights": insights},
                                execution_time_ms=e2b_time_ms
                            )

                            steps_to_persist.append(
                                self._create_step_record(
                                    step_number=2,
                                    step_name="analysis_execution",
                                    agent_name="E2BExecutor",
                                    attempt_number=analysis_attempt,
                                    agent_response=e2b_response,
                                    input_data={
                                        "code_summary": f"<code: {len(data_analysis.data['analysis_code'])} chars>"
                                    }
                                )
                            )

                        except Exception as e:
                            error_msg = f"Error ejecutando análisis en E2B: {str(e)}"
                            self.logger.error(f"❌ {error_msg}")
                            e2b_time_ms = (time.time() - e2b_start) * 1000

                            # Registrar step 2.2: E2B Execution (failed)
                            e2b_response = AgentResponse(
                                success=False,
                                error=error_msg,
                                execution_time_ms=e2b_time_ms
                            )

                            steps_to_persist.append(
                                self._create_step_record(
                                    step_number=2,
                                    step_name="analysis_execution",
                                    agent_name="E2BExecutor",
                                    attempt_number=analysis_attempt,
                                    agent_response=e2b_response,
                                    input_data={
                                        "code_summary": f"<code: {len(data_analysis.data['analysis_code'])} chars>"
                                    }
                                )
                            )

                            analysis_errors.append({
                                "stage": "analysis_execution",
                                "error": error_msg,
                                "attempt": analysis_attempt
                            })
                            continue

                        # 3.4 AnalysisValidator valida los insights
                        self.logger.info("✅ Validando insights...")
                        insights_val = await self.analysis_validator.execute(
                            task=task,
                            insights=insights,
                            context_schema=self._summarize_context_for_step(context_state.current),
                            analysis_code=data_analysis.data["analysis_code"]
                        )

                        # Registrar step 2.3: AnalysisValidator
                        steps_to_persist.append(
                            self._create_step_record(
                                step_number=2,
                                step_name="analysis_validation",
                                agent_name="AnalysisValidator",
                                attempt_number=analysis_attempt,
                                agent_response=insights_val,
                                input_data={
                                    "task": task,
                                    "insights": insights
                                }
                            )
                        )

                        if not insights_val.success or not insights_val.data["valid"]:
                            error_msg = f"Insights inválidos: {insights_val.data.get('reason', 'unknown')}"

                            # 🔥 NUEVO: Logging detallado para debugging
                            self.logger.warning(f"⚠️ {error_msg}")
                            self.logger.warning(f"   📊 Insights rechazados:")
                            self.logger.warning(f"   {json.dumps(insights, indent=6, ensure_ascii=False)}")

                            suggestions = insights_val.data.get("suggestions", [])
                            if suggestions:
                                self.logger.warning(f"   💡 Suggestions del validator:")
                                for i, sug in enumerate(suggestions, 1):
                                    self.logger.warning(f"      {i}. {sug}")

                            # Agregar suggestions al feedback
                            analysis_errors.append({
                                "stage": "analysis_validation",
                                "error": error_msg,
                                "suggestions": suggestions,
                                "attempt": analysis_attempt
                            })
                            continue

                        # ¡ÉXITO!
                        analysis_success = True
                        context_state.data_insights = insights

                        # 🔥 NUEVO: Guardar el reasoning del AnalysisValidator
                        # Esto le da al CodeGenerator contexto sobre QUÉ SIGNIFICAN los insights
                        context_state.analysis_validation = {
                            "valid": insights_val.data.get("valid", True),
                            "reason": insights_val.data.get("reason", ""),
                            "suggestions": insights_val.data.get("suggestions", [])
                        }

                        execution_state.data_analysis = {
                            **data_analysis.data,
                            "insights": insights
                        }
                        execution_state.add_timing("DataAnalyzer", data_analysis.execution_time_ms)
                        self.logger.info(f"🎉 DataAnalyzer completado en intento {analysis_attempt}")
                        break

                    except Exception as e:
                        error_msg = f"Error inesperado en DataAnalyzer intento {analysis_attempt}: {str(e)}"
                        self.logger.error(f"❌ {error_msg}")
                        analysis_errors.append({
                            "stage": "unexpected",
                            "error": error_msg,
                            "attempt": analysis_attempt
                        })

                        if analysis_attempt == self.max_retries:
                            raise

                # Si falló después de todos los intentos
                if not analysis_success:
                    raise Exception(f"DataAnalyzer falló después de {self.max_retries} intentos")

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
                        error_history=execution_state.errors,
                        node_type=node_type  # Pass node type to code generator
                    )

                    # 🔥 Registrar step 3: CodeGenerator
                    steps_to_persist.append(
                        self._create_step_record(
                            step_number=3,
                            step_name="code_generation",
                            agent_name="CodeGenerator",
                            attempt_number=attempt,
                            agent_response=code_gen,
                            input_data={
                                "task": task,
                                "context": self._summarize_context_for_step(context_state.current),
                                "data_insights": context_state.data_insights,
                                "analysis_validation": context_state.analysis_validation,  # 🔥 NUEVO: Incluir validation reasoning
                                "error_history": execution_state.errors
                            },
                            generated_code=code_gen.data.get("code") if code_gen.success else None
                        )
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

                    # 🔥 Registrar step 4: CodeValidator
                    steps_to_persist.append(
                        self._create_step_record(
                            step_number=4,
                            step_name="code_validation",
                            agent_name="CodeValidator",
                            attempt_number=attempt,
                            agent_response=code_val,
                            input_data={
                                "code": code_gen.data["code"],
                                "context_keys": list(context_state.current.keys())
                            }
                        )
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
                    e2b_start = time.time()
                    sandbox_id = None  # TODO: Capturar del executor si es posible

                    try:
                        updated_context = await self.e2b.execute_code(
                            code=code_gen.data["code"],
                            context=context_state.current,
                            timeout=timeout
                        )

                        # 🔥 NUEVO: Detectar si E2B retornó un error en lugar de lanzar excepción
                        if isinstance(updated_context, dict) and updated_context.get("_execution_error"):
                            # E2B ejecutó pero el código crasheó
                            error_msg = updated_context.get("_error_message", "Unknown E2B error")
                            stderr = updated_context.get("_stderr", "")
                            stdout = updated_context.get("_stdout", "")
                            exit_code = updated_context.get("_exit_code", -1)

                            self.logger.error(f"❌ {error_msg}")

                            # Agregar error detallado al historial para feedback al CodeGenerator
                            execution_state.add_error(
                                "execution",
                                f"{error_msg}\n\nStderr:\n{stderr}\n\nStdout:\n{stdout}"
                            )

                            e2b_time_ms = (time.time() - e2b_start) * 1000

                            # Registrar step 5: E2B Execution (failed con detalles)
                            e2b_response = AgentResponse(
                                success=False,
                                error=error_msg,
                                data={
                                    "stderr": stderr,
                                    "stdout": stdout,
                                    "exit_code": exit_code
                                },
                                execution_time_ms=e2b_time_ms
                            )

                            steps_to_persist.append(
                                self._create_step_record(
                                    step_number=5,
                                    step_name="e2b_execution",
                                    agent_name="E2BExecutor",
                                    attempt_number=attempt,
                                    agent_response=e2b_response,
                                    input_data={
                                        "code_summary": f"<code: {len(code_gen.data['code'])} chars>",
                                        "context": self._summarize_context_for_step(context_state.current)
                                    },
                                    sandbox_id=sandbox_id
                                )
                            )

                            # NO continue aquí - queremos que el OutputValidator vea el error
                            # y lo valide como inválido, agregando el stderr al feedback
                            execution_state.execution_result = {
                                "status": "failed",
                                "stderr": stderr,
                                "stdout": stdout
                            }

                        else:
                            # Ejecución exitosa
                            # 🔥 NUEVO: Extraer stderr/stdout/exit_code antes de actualizar contexto
                            stderr = updated_context.pop("_stderr", "")
                            stdout = updated_context.pop("_stdout", "")
                            exit_code = updated_context.pop("_exit_code", 0)

                            # MERGE context updates with current context
                            # This preserves existing keys that weren't modified
                            context_state.current.update(updated_context)

                            # 🔥 NUEVO: SIEMPRE guardar stderr/stdout (incluso en éxito)
                            execution_state.execution_result = {
                                "status": "success",
                                "exit_code": exit_code,
                                "stderr": stderr,
                                "stdout": stdout
                            }

                            e2b_time_ms = (time.time() - e2b_start) * 1000

                            # 🔥 Registrar step 5: E2B Execution (success)
                            e2b_response = AgentResponse(
                                success=True,
                                data={"context_updates": updated_context},
                                execution_time_ms=e2b_time_ms
                            )

                            steps_to_persist.append(
                                self._create_step_record(
                                    step_number=5,
                                    step_name="e2b_execution",
                                    agent_name="E2BExecutor",
                                    attempt_number=attempt,
                                    agent_response=e2b_response,
                                    input_data={
                                        "code_summary": f"<code: {len(code_gen.data['code'])} chars>",
                                        "context": self._summarize_context_for_step(context_state.current)
                                    },
                                    sandbox_id=sandbox_id
                                )
                            )

                    except Exception as e:
                        error_msg = f"Error en E2B: {str(e)}"
                        self.logger.error(f"❌ {error_msg}")
                        execution_state.add_error("execution", error_msg)

                        e2b_time_ms = (time.time() - e2b_start) * 1000

                        # 🔥 Registrar step 5: E2B Execution (failed)
                        e2b_response = AgentResponse(
                            success=False,
                            error=error_msg,
                            data={},  # 🔥 FIX: AgentResponse requiere data parameter
                            execution_time_ms=e2b_time_ms
                        )

                        steps_to_persist.append(
                            self._create_step_record(
                                step_number=5,
                                step_name="e2b_execution",
                                agent_name="E2BExecutor",
                                attempt_number=attempt,
                                agent_response=e2b_response,
                                input_data={
                                    "code_summary": f"<code: {len(code_gen.data['code'])} chars>",
                                    "context": self._summarize_context_for_step(context_state.current)
                                },
                                sandbox_id=sandbox_id
                            )
                        )

                        continue

                    # 4.4 OutputValidator (post-ejecución)
                    self.logger.info("✅ Validando resultado...")
                    output_val = await self.output_validator.execute(
                        task=task,
                        context_before=context_state.initial,
                        context_after=context_state.current,
                        generated_code=code_gen.data["code"],
                        execution_result=execution_state.execution_result  # 🔥 NUEVO: Pasar stderr/stdout
                    )

                    # 🔥 Registrar step 6: OutputValidator
                    steps_to_persist.append(
                        self._create_step_record(
                            step_number=6,
                            step_name="output_validation",
                            agent_name="OutputValidator",
                            attempt_number=attempt,
                            agent_response=output_val,
                            input_data={
                                "task": task,
                                "context_before": self._summarize_context_for_step(context_state.initial),
                                "context_after": self._summarize_context_for_step(context_state.current),
                                "code_summary": f"<code: {len(code_gen.data['code'])} chars>"
                            }
                        )
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

                        # 🔥 NUEVO: Si el OutputValidator extrajo un python_error, agregarlo al feedback
                        python_error = output_val.data.get("python_error")
                        if python_error:
                            error_msg += f"\n\n**Error de Python detectado:**\n{python_error}"
                            self.logger.error(f"🐍 Python error: {python_error}")

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

            # 5. Retornar resultado + metadata + STEPS
            result = {
                **context_state.current,
                "_ai_metadata": {
                    **execution_state.to_dict(),
                    "_steps": steps_to_persist  # 🔥 NUEVO: Steps para persistir en DB
                }
            }

            self.logger.info(
                f"✅ Workflow completado. Total time: {execution_state.get_total_time_ms():.2f}ms, "
                f"Steps registrados: {len(steps_to_persist)}"
            )
            return result

        except Exception as e:
            self.logger.error(f"💥 Workflow falló: {str(e)}")
            # Retornar contexto original + metadata del error + STEPS
            return {
                **context_state.initial,
                "_ai_metadata": {
                    **execution_state.to_dict(),
                    "_steps": steps_to_persist,  # 🔥 Incluir steps incluso en error
                    "final_error": str(e),
                    "status": "failed"
                }
            }
