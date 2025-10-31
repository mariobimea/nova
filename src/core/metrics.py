"""
Metrics Collection for NOVA

Provides system health metrics including:
- Workflow execution statistics
- Error rates
- Executor health (circuit breaker status)
- Database connectivity
- Redis connectivity
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from ..models.execution import Execution
from ..models.workflow import Workflow
from .circuit_breaker import e2b_circuit_breaker

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Collects and aggregates metrics for NOVA system.

    Provides:
    - Workflow execution stats (total, success, failed, pending)
    - Error rates (last hour, last 24 hours)
    - Circuit breaker status
    - System health indicators
    """

    def __init__(self, db_session: Session):
        """
        Initialize metrics collector.

        Args:
            db_session: SQLAlchemy database session
        """
        self.db_session = db_session

    def get_execution_stats(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get workflow execution statistics.

        Args:
            hours: Number of hours to look back (default: 24)

        Returns:
            Dict with execution stats:
            - total: Total executions
            - completed: Successfully completed
            - failed: Failed executions
            - pending: Still running
            - success_rate: Percentage of successful executions
        """
        try:
            since = datetime.utcnow() - timedelta(hours=hours)

            # Count executions by status
            stats = self.db_session.query(
                Execution.status,
                func.count(Execution.id).label("count")
            ).filter(
                Execution.created_at >= since
            ).group_by(Execution.status).all()

            # Aggregate results
            result = {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "pending": 0,
                "success_rate": 0.0
            }

            for status, count in stats:
                result["total"] += count
                if status == "completed":
                    result["completed"] = count
                elif status == "failed":
                    result["failed"] = count
                elif status in ("pending", "running"):
                    result["pending"] += count

            # Calculate success rate
            if result["total"] > 0:
                result["success_rate"] = round(
                    (result["completed"] / result["total"]) * 100, 2
                )

            return result

        except Exception as e:
            logger.error(f"Failed to get execution stats: {e}")
            return {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "pending": 0,
                "success_rate": 0.0,
                "error": str(e)
            }

    def get_error_rate(self, hours: int = 1) -> Dict[str, Any]:
        """
        Get error rate for recent executions.

        Args:
            hours: Number of hours to look back (default: 1)

        Returns:
            Dict with error rate info:
            - total_executions: Total executions in period
            - failed_executions: Failed executions
            - error_rate: Percentage of failed executions
        """
        try:
            since = datetime.utcnow() - timedelta(hours=hours)

            total = self.db_session.query(func.count(Execution.id)).filter(
                Execution.created_at >= since
            ).scalar() or 0

            failed = self.db_session.query(func.count(Execution.id)).filter(
                and_(
                    Execution.created_at >= since,
                    Execution.status == "failed"
                )
            ).scalar() or 0

            error_rate = round((failed / total * 100), 2) if total > 0 else 0.0

            return {
                "period_hours": hours,
                "total_executions": total,
                "failed_executions": failed,
                "error_rate": error_rate
            }

        except Exception as e:
            logger.error(f"Failed to get error rate: {e}")
            return {
                "period_hours": hours,
                "total_executions": 0,
                "failed_executions": 0,
                "error_rate": 0.0,
                "error": str(e)
            }

    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """
        Get E2B circuit breaker status.

        Returns:
            Dict with circuit breaker info:
            - state: CLOSED, OPEN, or HALF_OPEN
            - failure_count: Current failure count
            - failure_threshold: Max failures before opening
            - is_healthy: True if CLOSED, False if OPEN
        """
        try:
            status = e2b_circuit_breaker.get_status()
            return {
                "state": status["state"],
                "failure_count": status["failure_count"],
                "failure_threshold": status["failure_threshold"],
                "is_healthy": status["state"] == "CLOSED"
            }

        except Exception as e:
            logger.error(f"Failed to get circuit breaker status: {e}")
            return {
                "state": "UNKNOWN",
                "failure_count": 0,
                "failure_threshold": 0,
                "is_healthy": False,
                "error": str(e)
            }

    def get_workflow_stats(self) -> Dict[str, Any]:
        """
        Get workflow statistics.

        Returns:
            Dict with workflow stats:
            - total_workflows: Total workflows in system
            - active_workflows: Workflows that have executions
        """
        try:
            total = self.db_session.query(func.count(Workflow.id)).scalar() or 0

            # Count workflows with at least one execution
            active = self.db_session.query(
                func.count(func.distinct(Execution.workflow_id))
            ).scalar() or 0

            return {
                "total_workflows": total,
                "active_workflows": active
            }

        except Exception as e:
            logger.error(f"Failed to get workflow stats: {e}")
            return {
                "total_workflows": 0,
                "active_workflows": 0,
                "error": str(e)
            }

    def get_database_health(self) -> Dict[str, Any]:
        """
        Check database connectivity.

        Returns:
            Dict with database health:
            - connected: True if database is reachable
            - response_time_ms: Query response time
        """
        import time

        try:
            start = time.time()
            # Simple query to check connectivity
            self.db_session.execute("SELECT 1").fetchone()
            response_time = round((time.time() - start) * 1000, 2)

            return {
                "connected": True,
                "response_time_ms": response_time
            }

        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "connected": False,
                "response_time_ms": None,
                "error": str(e)
            }

    def get_all_metrics(self) -> Dict[str, Any]:
        """
        Get all system metrics.

        Returns:
            Dict with all metrics:
            - timestamp: Current UTC timestamp
            - executions: Execution stats (24 hours)
            - error_rate: Error rate (1 hour)
            - circuit_breaker: E2B circuit breaker status
            - workflows: Workflow statistics
            - database: Database health
        """
        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "executions": self.get_execution_stats(hours=24),
            "error_rate": self.get_error_rate(hours=1),
            "circuit_breaker": self.get_circuit_breaker_status(),
            "workflows": self.get_workflow_stats(),
            "database": self.get_database_health()
        }


def check_system_health(db_session: Session) -> Dict[str, Any]:
    """
    Convenience function to check overall system health.

    Args:
        db_session: SQLAlchemy database session

    Returns:
        Dict with health status:
        - healthy: True if all components are healthy
        - components: Status of each component
        - issues: List of detected issues
    """
    collector = MetricsCollector(db_session)
    metrics = collector.get_all_metrics()

    issues = []
    components = {}

    # Check database
    db_health = metrics["database"]
    components["database"] = db_health["connected"]
    if not db_health["connected"]:
        issues.append("Database connection failed")

    # Check circuit breaker
    cb_status = metrics["circuit_breaker"]
    components["executor"] = cb_status["is_healthy"]
    if not cb_status["is_healthy"]:
        issues.append(f"E2B executor circuit breaker is {cb_status['state']}")

    # Check error rate
    error_rate = metrics["error_rate"]["error_rate"]
    components["error_rate"] = error_rate < 50.0  # Alert if >50% errors
    if error_rate >= 50.0:
        issues.append(f"High error rate: {error_rate}%")

    # Overall health
    healthy = all(components.values())

    return {
        "healthy": healthy,
        "components": components,
        "issues": issues if issues else None,
        "metrics": metrics
    }
