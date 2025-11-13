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
from datetime import datetime
from dataclasses import asdict

from .state import ExecutionState, ContextState
from .base import AgentResponse
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
            input_data: Datos de entrada que recibió el agente
            generated_code: Código generado (solo para CodeGenerator, DataAnalyzer)
            sandbox_id: ID del sandbox E2B (solo para E2BExecutor)

        Returns:
            Dict con toda la metadata del step para persistir
        """
        step_record = {
            "step_number": step_number,
            "step_name": step_name,
            "agent_name": agent_name,
            "attempt_number": attempt_number,
            "input_data": input_data,
            "output_data": agent_response.data if agent_response.success else None,
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
                        "context_keys": list(context.keys())
                    }
                )
            )

            if not input_analysis.success:
                raise Exception(f"InputAnalyzer falló: {input_analysis.error}")

            execution_state.input_analysis = input_analysis.data
            execution_state.add_timing("InputAnalyzer", input_analysis.execution_time_ms)

            # 3. DataAnalyzer (UNA SOLA VEZ, si es necesario)
            if input_analysis.data["needs_analysis"]:
                self.logger.info("🔬 Ejecutando DataAnalyzer...")
                data_analysis = await self.data_analyzer.execute(context_state)

                # 🔥 Registrar step 2: DataAnalyzer
                steps_to_persist.append(
                    self._create_step_record(
                        step_number=2,
                        step_name="data_analysis",
                        agent_name="DataAnalyzer",
                        attempt_number=1,
                        agent_response=data_analysis,
                        input_data={
                            "context": context_state.current,
                            "hint": input_analysis.data.get("reasoning")
                        },
                        generated_code=data_analysis.data.get("analysis_code") if data_analysis.success else None
                    )
                )

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
                                "context": context_state.current,
                                "data_insights": context_state.data_insights,
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
                        context_state.current = updated_context
                        execution_state.execution_result = {"status": "success"}

                        e2b_time_ms = (time.time() - e2b_start) * 1000

                        # 🔥 Registrar step 5: E2B Execution (success)
                        from .base import AgentResponse
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
                                    "code": code_gen.data["code"],
                                    "context": context_state.current
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
                        from .base import AgentResponse
                        e2b_response = AgentResponse(
                            success=False,
                            error=error_msg,
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
                                    "code": code_gen.data["code"],
                                    "context": context_state.current
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
                        context_after=context_state.current
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
                                "context_before": context_state.initial,
                                "context_after": context_state.current
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
