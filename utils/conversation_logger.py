"""
Comprehensive conversation logging for Ife testing.
Logs all conversation turns with RAG context, metrics, and analysis.
"""
import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
from functools import wraps


class ConversationLogger:
    """Comprehensive conversation logging for Ife testing."""

    def __init__(self, log_path: str = None):
        self.log_path = Path(log_path or os.getenv("CONVERSATION_LOG_PATH", "./logs/conversations"))
        self.log_path.mkdir(parents=True, exist_ok=True)
        self.verbose = os.getenv("ENABLE_VERBOSE_LOGGING", "false").lower() == "true"
        self.log_rag = os.getenv("LOG_RAG_RETRIEVALS", "false").lower() == "true"
        self.log_tokens = os.getenv("LOG_LLM_TOKENS", "false").lower() == "true"

        # Uncertainty markers for analysis
        self.uncertainty_markers = [
            "I'm not sure", "I don't know", "might be", "possibly",
            "I think", "unclear", "unsure", "I believe", "perhaps",
            "could be", "may be", "not certain", "I'm uncertain"
        ]

        # Quality indicators
        self.quality_keywords = {
            "professional": ["thank you", "please", "assist", "help", "happy to"],
            "informative": ["because", "since", "therefore", "specifically"],
            "engaging": ["great question", "interesting", "let me explain"]
        }

    def log_conversation_turn(
        self,
        conversation_id: str,
        user_message: str,
        assistant_response: str,
        rag_results: Optional[List[dict]] = None,
        response_time_ms: Optional[float] = None,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """Log a complete conversation turn with all context."""

        # Build analysis
        analysis = self._analyze_response(user_message, assistant_response, rag_results, response_time_ms)

        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "conversation_id": conversation_id,
            "user_message": user_message,
            "assistant_response": assistant_response,
            "response_time_ms": response_time_ms,
            "metadata": metadata or {},
            "analysis": analysis
        }

        # Include RAG results if logging enabled
        if self.log_rag and rag_results:
            log_entry["rag_results"] = rag_results

        # Write to conversation-specific file
        log_file = self.log_path / f"{conversation_id}.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        # Also append to daily aggregate
        daily_log = self.log_path / f"{datetime.utcnow().date()}.jsonl"
        with open(daily_log, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        if self.verbose:
            print(f"[LOG] Conversation {conversation_id}: quality={analysis['quality_score']:.2f}, "
                  f"weak_points={len(analysis.get('weak_points', []))}")

        return log_entry

    def _analyze_response(
        self,
        user_message: str,
        response: str,
        rag_results: Optional[List[dict]],
        response_time_ms: Optional[float] = None
    ) -> Dict:
        """Analyze response quality and detect weak points."""

        # Basic metrics
        response_length = len(response)
        word_count = len(response.split())

        # Uncertainty detection
        uncertainty_count = sum(
            1 for marker in self.uncertainty_markers
            if marker.lower() in response.lower()
        )

        # Quality keyword presence
        quality_presence = {}
        for category, keywords in self.quality_keywords.items():
            quality_presence[category] = any(
                kw.lower() in response.lower() for kw in keywords
            )

        # RAG analysis
        rag_docs_used = len(rag_results) if rag_results else 0
        rag_relevance_avg = 0.0
        if rag_results:
            scores = [r.get("score", 0) for r in rag_results if "score" in r]
            rag_relevance_avg = sum(scores) / len(scores) if scores else 0.0

        # Response length analysis
        is_too_short = response_length < 50
        is_too_long = response_length > 2000
        is_appropriate_length = not is_too_short and not is_too_long

        # Detect weak points
        weak_points = []

        if uncertainty_count >= 2:
            weak_points.append({
                "type": "high_uncertainty",
                "severity": "medium",
                "detail": f"Found {uncertainty_count} uncertainty markers"
            })

        if is_too_short:
            weak_points.append({
                "type": "response_too_short",
                "severity": "high",
                "detail": f"Response is only {response_length} characters"
            })

        if is_too_long:
            weak_points.append({
                "type": "response_too_long",
                "severity": "low",
                "detail": f"Response is {response_length} characters"
            })

        if response_time_ms and response_time_ms > 5000:
            weak_points.append({
                "type": "slow_response",
                "severity": "medium",
                "detail": f"Response took {response_time_ms:.0f}ms"
            })

        if rag_docs_used > 0 and rag_relevance_avg < 0.5:
            weak_points.append({
                "type": "low_rag_relevance",
                "severity": "medium",
                "detail": f"RAG relevance score: {rag_relevance_avg:.2f}"
            })

        # Check for potential hallucination indicators
        if rag_docs_used == 0 and any(word in user_message.lower() for word in
                                       ["blacksky", "services", "portfolio", "work", "projects"]):
            weak_points.append({
                "type": "potential_hallucination_risk",
                "severity": "high",
                "detail": "Domain-specific question without RAG context"
            })

        # Calculate quality score
        quality_score = self._calculate_quality_score(
            uncertainty_count=uncertainty_count,
            is_appropriate_length=is_appropriate_length,
            is_too_short=is_too_short,
            quality_presence=quality_presence,
            rag_relevance=rag_relevance_avg,
            weak_points_count=len(weak_points),
            response_time_ms=response_time_ms
        )

        return {
            "response_length": response_length,
            "word_count": word_count,
            "response_time_ms": response_time_ms,
            "uncertainty_count": uncertainty_count,
            "rag_documents_retrieved": rag_docs_used,
            "rag_relevance_score": rag_relevance_avg,
            "quality_presence": quality_presence,
            "quality_score": quality_score,
            "weak_points": weak_points,
            "is_too_short": is_too_short,
            "is_too_long": is_too_long
        }

    def _calculate_quality_score(
        self,
        uncertainty_count: int,
        is_appropriate_length: bool,
        is_too_short: bool,
        quality_presence: Dict[str, bool],
        rag_relevance: float,
        weak_points_count: int,
        response_time_ms: Optional[float]
    ) -> float:
        """Calculate overall quality score from 0-1."""
        score = 1.0

        # Deductions
        score -= 0.1 * uncertainty_count  # -0.1 per uncertainty marker
        if not is_appropriate_length:
            score -= 0.15
        if is_too_short:
            score -= 0.25  # Extra penalty for too short
        if rag_relevance > 0 and rag_relevance < 0.5:
            score -= 0.15
        if response_time_ms and response_time_ms > 5000:
            score -= 0.1
        score -= 0.05 * weak_points_count  # -0.05 per weak point

        # Bonuses
        quality_bonus = sum(0.05 for v in quality_presence.values() if v)
        score += quality_bonus

        return max(0.0, min(1.0, score))

    def get_conversation_log(self, conversation_id: str) -> List[Dict]:
        """Retrieve all log entries for a conversation."""
        log_file = self.log_path / f"{conversation_id}.jsonl"
        if not log_file.exists():
            return []

        entries = []
        with open(log_file, "r") as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))
        return entries

    def get_daily_log(self, date: str = None) -> List[Dict]:
        """Retrieve all log entries for a specific date."""
        if date is None:
            date = datetime.utcnow().strftime("%Y-%m-%d")

        log_file = self.log_path / f"{date}.jsonl"
        if not log_file.exists():
            return []

        entries = []
        with open(log_file, "r") as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))
        return entries

    def get_weak_points_summary(self, date: str = None) -> Dict:
        """Get summary of weak points from logs."""
        entries = self.get_daily_log(date)

        weak_points_by_type = {}
        weak_points_by_severity = {"low": 0, "medium": 0, "high": 0}
        total_conversations = len(set(e["conversation_id"] for e in entries))
        total_weak_points = 0

        for entry in entries:
            for wp in entry.get("analysis", {}).get("weak_points", []):
                wp_type = wp.get("type", "unknown")
                weak_points_by_type[wp_type] = weak_points_by_type.get(wp_type, 0) + 1
                severity = wp.get("severity", "low")
                if severity in weak_points_by_severity:
                    weak_points_by_severity[severity] += 1
                total_weak_points += 1

        return {
            "date": date or datetime.utcnow().strftime("%Y-%m-%d"),
            "total_conversations": total_conversations,
            "total_entries": len(entries),
            "total_weak_points": total_weak_points,
            "weak_points_by_type": weak_points_by_type,
            "weak_points_by_severity": weak_points_by_severity
        }

    def export_for_fine_tuning(
        self,
        min_quality: float = 0.8,
        exclude_weak_points: bool = True,
        date: str = None
    ) -> List[Dict]:
        """Export high-quality conversations for fine-tuning."""
        entries = self.get_daily_log(date) if date else []

        # If no date specified, get all logs
        if not date:
            for log_file in self.log_path.glob("*.jsonl"):
                if log_file.stem != "daily":
                    with open(log_file, "r") as f:
                        for line in f:
                            if line.strip():
                                entries.append(json.loads(line))

        # Filter for high quality
        fine_tuning_examples = []
        for entry in entries:
            quality = entry.get("analysis", {}).get("quality_score", 0)
            weak_points = entry.get("analysis", {}).get("weak_points", [])

            if quality >= min_quality:
                if exclude_weak_points and weak_points:
                    continue

                fine_tuning_examples.append({
                    "messages": [
                        {"role": "user", "content": entry["user_message"]},
                        {"role": "assistant", "content": entry["assistant_response"]}
                    ]
                })

        return fine_tuning_examples


def log_chat_interaction(logger: ConversationLogger):
    """Decorator to automatically log chat interactions."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            result = func(*args, **kwargs)
            elapsed_ms = (time.time() - start_time) * 1000

            # Extract relevant info from args/kwargs
            # This assumes the function signature includes these params
            user_message = kwargs.get("user_message") or (args[0] if args else "")
            conversation_id = kwargs.get("conversation_id", "unknown")

            if isinstance(result, str):
                logger.log_conversation_turn(
                    conversation_id=conversation_id,
                    user_message=user_message,
                    assistant_response=result,
                    response_time_ms=elapsed_ms
                )

            return result
        return wrapper
    return decorator


# Global logger instance
_logger = None


def get_logger() -> ConversationLogger:
    """Get or create the global conversation logger instance."""
    global _logger
    if _logger is None:
        _logger = ConversationLogger()
    return _logger
