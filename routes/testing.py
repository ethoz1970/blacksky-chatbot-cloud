"""
Testing endpoints for Ife integration.
Provides APIs for injecting test conversations, analyzing responses,
and collecting weak points for fine-tuning.
"""
import os
import json
import time
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

# Only enable in testing environment
TESTING_ENABLED = os.getenv("ENABLE_TEST_ENDPOINTS", "false").lower() == "true"
CONVERSATION_LOG_PATH = Path(os.getenv("CONVERSATION_LOG_PATH", "./logs/conversations"))


class TestConversationRequest(BaseModel):
    """Request model for injecting test conversations."""
    user_message: str
    context: Optional[Dict[str, Any]] = None
    scenario_id: Optional[str] = None
    user_id: Optional[str] = None
    include_rag: bool = True


class TestConversationResponse(BaseModel):
    """Response model for test conversations."""
    conversation_id: str
    user_message: str
    assistant_response: str
    response_time_ms: float
    rag_results: Optional[List[Dict[str, Any]]] = None
    metrics: Dict[str, Any]


class ConversationAnalysis(BaseModel):
    """Model for conversation analysis results."""
    conversation_id: str
    weak_points: List[Dict[str, Any]]
    metrics: Dict[str, Any]
    quality_score: float


class WeakPoint(BaseModel):
    """Model for detected weak points."""
    id: str
    conversation_id: str
    turn_number: int
    weak_point_type: str
    severity: str  # low, medium, high
    context: str
    user_query: str
    assistant_response: str
    suggested_improvement: Optional[str] = None
    created_at: str


class FineTuningExample(BaseModel):
    """Model for fine-tuning examples."""
    id: str
    weak_point_id: Optional[str] = None
    messages: List[Dict[str, str]]
    approved: bool = False
    created_at: str


# In-memory storage for testing (will be replaced with DB in production)
_conversations: Dict[str, Dict] = {}
_weak_points: List[Dict] = []
_fine_tuning_examples: List[Dict] = []


router = APIRouter(prefix="/testing", tags=["testing"])


def _check_testing_enabled():
    """Check if testing endpoints are enabled."""
    if not TESTING_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Testing endpoints disabled. Set ENABLE_TEST_ENDPOINTS=true"
        )


def _analyze_response(
    user_message: str,
    assistant_response: str,
    rag_results: Optional[List[Dict]] = None,
    response_time_ms: float = 0
) -> Dict[str, Any]:
    """Analyze a response for quality metrics and weak points."""

    # Uncertainty markers that might indicate weak responses
    uncertainty_markers = [
        "I'm not sure", "I don't know", "might be", "possibly",
        "I think", "unclear", "unsure", "I believe", "perhaps",
        "could be", "may be", "not certain"
    ]

    # Quality indicators
    quality_indicators = {
        "professional_tone": True,
        "helpful": True,
        "on_topic": True,
        "appropriate_length": 50 <= len(assistant_response) <= 2000
    }

    # Check for uncertainty
    uncertainty_count = sum(
        1 for marker in uncertainty_markers
        if marker.lower() in assistant_response.lower()
    )

    # Check for empty or very short responses
    is_too_short = len(assistant_response.strip()) < 20
    is_too_long = len(assistant_response) > 3000

    # RAG relevance check
    rag_used = rag_results is not None and len(rag_results) > 0
    rag_relevance_score = 0.0
    if rag_results:
        # Average the relevance scores from RAG results
        scores = [r.get("score", 0) for r in rag_results if r.get("score")]
        rag_relevance_score = sum(scores) / len(scores) if scores else 0.0

    # Calculate quality score (0-1)
    quality_score = 1.0
    if uncertainty_count > 0:
        quality_score -= 0.1 * uncertainty_count
    if is_too_short:
        quality_score -= 0.3
    if is_too_long:
        quality_score -= 0.1
    if response_time_ms > 5000:  # Slow response
        quality_score -= 0.1
    quality_score = max(0.0, min(1.0, quality_score))

    # Detect weak points
    weak_points = []

    if uncertainty_count >= 2:
        weak_points.append({
            "type": "high_uncertainty",
            "severity": "medium",
            "detail": f"Response contains {uncertainty_count} uncertainty markers"
        })

    if is_too_short:
        weak_points.append({
            "type": "too_short",
            "severity": "high",
            "detail": f"Response only {len(assistant_response)} chars"
        })

    if is_too_long:
        weak_points.append({
            "type": "too_long",
            "severity": "low",
            "detail": f"Response is {len(assistant_response)} chars"
        })

    if rag_used and rag_relevance_score < 0.5:
        weak_points.append({
            "type": "low_rag_relevance",
            "severity": "medium",
            "detail": f"RAG relevance score: {rag_relevance_score:.2f}"
        })

    if not rag_used and any(word in user_message.lower() for word in ["blacksky", "service", "portfolio", "work"]):
        weak_points.append({
            "type": "missing_rag_context",
            "severity": "medium",
            "detail": "Question about Blacksky but no RAG context used"
        })

    return {
        "response_length": len(assistant_response),
        "response_time_ms": response_time_ms,
        "uncertainty_count": uncertainty_count,
        "rag_documents_retrieved": len(rag_results) if rag_results else 0,
        "rag_relevance_score": rag_relevance_score,
        "quality_score": quality_score,
        "quality_indicators": quality_indicators,
        "weak_points": weak_points,
        "is_too_short": is_too_short,
        "is_too_long": is_too_long
    }


@router.get("/status")
async def get_testing_status():
    """Check if testing endpoints are enabled and get system status."""
    return {
        "testing_enabled": TESTING_ENABLED,
        "environment": os.getenv("ENVIRONMENT", "unknown"),
        "log_path": str(CONVERSATION_LOG_PATH),
        "conversations_logged": len(_conversations),
        "weak_points_detected": len(_weak_points),
        "fine_tuning_examples": len(_fine_tuning_examples)
    }


@router.post("/conversation", response_model=TestConversationResponse)
async def inject_test_conversation(request: TestConversationRequest):
    """
    Inject a test conversation for Ife to analyze.
    Returns full conversation details with metrics.
    """
    _check_testing_enabled()

    # Import here to avoid circular imports
    from server import bot, get_user_context, get_or_create_user

    conversation_id = str(uuid.uuid4())
    user_id = request.user_id or f"ife-test-{conversation_id[:8]}"

    # Ensure user exists
    get_or_create_user(user_id)

    # Get user context if available
    user_context = None
    if request.context:
        user_context = request.context
    else:
        user_context = get_user_context(user_id)

    # Get RAG results if enabled
    rag_results = None
    if request.include_rag and bot.doc_store:
        try:
            chunks = bot.doc_store.search(request.user_message)
            rag_results = chunks
        except Exception as e:
            print(f"RAG search failed: {e}")

    # Generate response with timing
    start_time = time.time()
    try:
        response = bot.chat(request.user_message, user_context=user_context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat generation failed: {str(e)}")

    response_time_ms = (time.time() - start_time) * 1000

    # Analyze the response
    metrics = _analyze_response(
        request.user_message,
        response,
        rag_results,
        response_time_ms
    )

    # Store conversation
    conversation_data = {
        "id": conversation_id,
        "scenario_id": request.scenario_id,
        "user_id": user_id,
        "user_message": request.user_message,
        "assistant_response": response,
        "rag_results": rag_results,
        "metrics": metrics,
        "context": request.context,
        "created_at": datetime.utcnow().isoformat()
    }
    _conversations[conversation_id] = conversation_data

    # Log to file
    _log_conversation(conversation_data)

    # Store any detected weak points
    for i, wp in enumerate(metrics.get("weak_points", [])):
        weak_point = {
            "id": str(uuid.uuid4()),
            "conversation_id": conversation_id,
            "turn_number": 1,
            "weak_point_type": wp["type"],
            "severity": wp["severity"],
            "context": wp.get("detail", ""),
            "user_query": request.user_message,
            "assistant_response": response,
            "created_at": datetime.utcnow().isoformat()
        }
        _weak_points.append(weak_point)

    return TestConversationResponse(
        conversation_id=conversation_id,
        user_message=request.user_message,
        assistant_response=response,
        response_time_ms=round(response_time_ms, 2),
        rag_results=rag_results,
        metrics=metrics
    )


@router.post("/conversation/batch")
async def inject_batch_conversations(requests: List[TestConversationRequest]):
    """Inject multiple test conversations at once."""
    _check_testing_enabled()

    results = []
    for req in requests:
        try:
            result = await inject_test_conversation(req)
            results.append({"status": "success", "data": result})
        except Exception as e:
            results.append({"status": "error", "error": str(e)})

    return {
        "total": len(requests),
        "successful": sum(1 for r in results if r["status"] == "success"),
        "failed": sum(1 for r in results if r["status"] == "error"),
        "results": results
    }


@router.get("/conversations/{conversation_id}/analysis")
async def get_conversation_analysis(conversation_id: str):
    """Retrieve detailed analysis of a conversation."""
    _check_testing_enabled()

    if conversation_id not in _conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv = _conversations[conversation_id]

    # Get related weak points
    weak_points = [wp for wp in _weak_points if wp["conversation_id"] == conversation_id]

    return ConversationAnalysis(
        conversation_id=conversation_id,
        weak_points=weak_points,
        metrics=conv["metrics"],
        quality_score=conv["metrics"].get("quality_score", 0.0)
    )


@router.get("/conversations")
async def list_conversations(
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    scenario_id: Optional[str] = None,
    min_quality: Optional[float] = None,
    max_quality: Optional[float] = None
):
    """List all test conversations with optional filtering."""
    _check_testing_enabled()

    conversations = list(_conversations.values())

    # Apply filters
    if scenario_id:
        conversations = [c for c in conversations if c.get("scenario_id") == scenario_id]

    if min_quality is not None:
        conversations = [c for c in conversations if c["metrics"].get("quality_score", 0) >= min_quality]

    if max_quality is not None:
        conversations = [c for c in conversations if c["metrics"].get("quality_score", 1) <= max_quality]

    # Sort by creation time (newest first)
    conversations.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    # Paginate
    total = len(conversations)
    conversations = conversations[offset:offset + limit]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "conversations": conversations
    }


@router.get("/weak-points")
async def get_weak_points(
    limit: int = Query(100, le=500),
    severity: Optional[str] = None,
    weak_point_type: Optional[str] = None,
    reviewed: Optional[bool] = None
):
    """Get weak points identified in conversations."""
    _check_testing_enabled()

    weak_points = _weak_points.copy()

    # Apply filters
    if severity:
        weak_points = [wp for wp in weak_points if wp["severity"] == severity]

    if weak_point_type:
        weak_points = [wp for wp in weak_points if wp["weak_point_type"] == weak_point_type]

    # Sort by creation time (newest first)
    weak_points.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    return {
        "total": len(weak_points),
        "weak_points": weak_points[:limit],
        "types": list(set(wp["weak_point_type"] for wp in _weak_points)),
        "severity_counts": {
            "low": sum(1 for wp in _weak_points if wp["severity"] == "low"),
            "medium": sum(1 for wp in _weak_points if wp["severity"] == "medium"),
            "high": sum(1 for wp in _weak_points if wp["severity"] == "high")
        }
    }


@router.post("/weak-points/{weak_point_id}/fine-tuning-example")
async def create_fine_tuning_example(
    weak_point_id: str,
    improved_response: str
):
    """Create a fine-tuning example from a weak point with improved response."""
    _check_testing_enabled()

    # Find the weak point
    weak_point = next((wp for wp in _weak_points if wp["id"] == weak_point_id), None)
    if not weak_point:
        raise HTTPException(status_code=404, detail="Weak point not found")

    # Create fine-tuning example
    example = {
        "id": str(uuid.uuid4()),
        "weak_point_id": weak_point_id,
        "messages": [
            {"role": "user", "content": weak_point["user_query"]},
            {"role": "assistant", "content": improved_response}
        ],
        "approved": False,
        "created_at": datetime.utcnow().isoformat()
    }

    _fine_tuning_examples.append(example)

    return example


@router.get("/fine-tuning-examples")
async def get_fine_tuning_examples(
    approved_only: bool = False,
    limit: int = Query(100, le=1000)
):
    """Get fine-tuning examples for model improvement."""
    _check_testing_enabled()

    examples = _fine_tuning_examples.copy()

    if approved_only:
        examples = [ex for ex in examples if ex["approved"]]

    return {
        "total": len(examples),
        "approved": sum(1 for ex in _fine_tuning_examples if ex["approved"]),
        "examples": examples[:limit]
    }


@router.post("/fine-tuning-examples/{example_id}/approve")
async def approve_fine_tuning_example(example_id: str):
    """Approve a fine-tuning example."""
    _check_testing_enabled()

    for ex in _fine_tuning_examples:
        if ex["id"] == example_id:
            ex["approved"] = True
            return {"status": "approved", "example": ex}

    raise HTTPException(status_code=404, detail="Example not found")


@router.get("/fine-tuning-examples/export")
async def export_fine_tuning_examples(approved_only: bool = True):
    """Export fine-tuning examples in JSONL format."""
    _check_testing_enabled()

    examples = _fine_tuning_examples.copy()

    if approved_only:
        examples = [ex for ex in examples if ex["approved"]]

    # Convert to JSONL format suitable for fine-tuning
    jsonl_lines = []
    for ex in examples:
        jsonl_lines.append(json.dumps({"messages": ex["messages"]}))

    return {
        "format": "jsonl",
        "count": len(jsonl_lines),
        "data": "\n".join(jsonl_lines)
    }


@router.delete("/reset")
async def reset_testing_database():
    """Reset testing database - DANGEROUS, testing only."""
    _check_testing_enabled()

    global _conversations, _weak_points, _fine_tuning_examples

    counts = {
        "conversations_deleted": len(_conversations),
        "weak_points_deleted": len(_weak_points),
        "fine_tuning_examples_deleted": len(_fine_tuning_examples)
    }

    _conversations = {}
    _weak_points = []
    _fine_tuning_examples = []

    return {"status": "reset", **counts}


@router.get("/metrics/summary")
async def get_metrics_summary():
    """Get summary metrics across all test conversations."""
    _check_testing_enabled()

    if not _conversations:
        return {
            "total_conversations": 0,
            "avg_quality_score": 0,
            "avg_response_time_ms": 0,
            "weak_points_by_type": {},
            "weak_points_by_severity": {}
        }

    conversations = list(_conversations.values())

    # Calculate averages
    quality_scores = [c["metrics"].get("quality_score", 0) for c in conversations]
    response_times = [c["metrics"].get("response_time_ms", 0) for c in conversations]

    # Aggregate weak points
    weak_points_by_type = {}
    weak_points_by_severity = {"low": 0, "medium": 0, "high": 0}

    for wp in _weak_points:
        wp_type = wp["weak_point_type"]
        weak_points_by_type[wp_type] = weak_points_by_type.get(wp_type, 0) + 1
        weak_points_by_severity[wp["severity"]] += 1

    return {
        "total_conversations": len(conversations),
        "avg_quality_score": sum(quality_scores) / len(quality_scores) if quality_scores else 0,
        "avg_response_time_ms": sum(response_times) / len(response_times) if response_times else 0,
        "min_quality_score": min(quality_scores) if quality_scores else 0,
        "max_quality_score": max(quality_scores) if quality_scores else 0,
        "total_weak_points": len(_weak_points),
        "weak_points_by_type": weak_points_by_type,
        "weak_points_by_severity": weak_points_by_severity,
        "fine_tuning_examples_total": len(_fine_tuning_examples),
        "fine_tuning_examples_approved": sum(1 for ex in _fine_tuning_examples if ex["approved"])
    }


def _log_conversation(conversation_data: Dict):
    """Log conversation to file."""
    try:
        CONVERSATION_LOG_PATH.mkdir(parents=True, exist_ok=True)

        # Log to conversation-specific file
        conv_file = CONVERSATION_LOG_PATH / f"{conversation_data['id']}.json"
        with open(conv_file, "w") as f:
            json.dump(conversation_data, f, indent=2)

        # Append to daily aggregate
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        daily_file = CONVERSATION_LOG_PATH / f"{date_str}.jsonl"
        with open(daily_file, "a") as f:
            f.write(json.dumps(conversation_data) + "\n")

    except Exception as e:
        print(f"Failed to log conversation: {e}")
