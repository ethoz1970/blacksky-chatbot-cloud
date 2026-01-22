-- Ife Testing Tables Migration
-- These tables support conversation analysis and fine-tuning data collection

-- Conversation Logs Table
-- Stores detailed logs of all conversation turns for analysis
CREATE TABLE IF NOT EXISTS conversation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id VARCHAR(255) NOT NULL,
    turn_number INTEGER NOT NULL DEFAULT 1,
    user_message TEXT NOT NULL,
    assistant_response TEXT NOT NULL,
    rag_results TEXT,  -- JSON array of RAG retrieval results
    metadata TEXT,  -- JSON object with additional context
    response_time_ms REAL,
    quality_score REAL,
    scenario_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_convlogs_conversation_id ON conversation_logs(conversation_id);
CREATE INDEX IF NOT EXISTS idx_convlogs_created_at ON conversation_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_convlogs_scenario_id ON conversation_logs(scenario_id);
CREATE INDEX IF NOT EXISTS idx_convlogs_quality_score ON conversation_logs(quality_score);

-- Weak Points Table
-- Stores identified weak points in Maurice's responses
CREATE TABLE IF NOT EXISTS weak_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id VARCHAR(255) NOT NULL,
    conversation_log_id INTEGER REFERENCES conversation_logs(id),
    turn_number INTEGER NOT NULL DEFAULT 1,
    weak_point_type VARCHAR(100) NOT NULL,
    severity VARCHAR(50) NOT NULL DEFAULT 'medium',  -- low, medium, high
    context TEXT,  -- Description of the weak point
    user_query TEXT NOT NULL,
    assistant_response TEXT NOT NULL,
    suggested_improvement TEXT,
    reviewed BOOLEAN DEFAULT FALSE,
    reviewer_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_weakpoints_conversation_id ON weak_points(conversation_id);
CREATE INDEX IF NOT EXISTS idx_weakpoints_type ON weak_points(weak_point_type);
CREATE INDEX IF NOT EXISTS idx_weakpoints_severity ON weak_points(severity);
CREATE INDEX IF NOT EXISTS idx_weakpoints_reviewed ON weak_points(reviewed);
CREATE INDEX IF NOT EXISTS idx_weakpoints_created_at ON weak_points(created_at);

-- Fine-Tuning Examples Table
-- Stores curated examples for model fine-tuning
CREATE TABLE IF NOT EXISTS fine_tuning_examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    weak_point_id INTEGER REFERENCES weak_points(id),
    conversation_log_id INTEGER REFERENCES conversation_logs(id),
    messages TEXT NOT NULL,  -- JSON array of message objects
    system_prompt TEXT,  -- Optional custom system prompt
    approved BOOLEAN DEFAULT FALSE,
    approval_notes TEXT,
    quality_rating INTEGER,  -- 1-5 rating of example quality
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    approved_by VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_finetuning_approved ON fine_tuning_examples(approved);
CREATE INDEX IF NOT EXISTS idx_finetuning_weakpoint ON fine_tuning_examples(weak_point_id);
CREATE INDEX IF NOT EXISTS idx_finetuning_created_at ON fine_tuning_examples(created_at);

-- Test Scenarios Table
-- Stores predefined test scenarios for systematic testing
CREATE TABLE IF NOT EXISTS test_scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),  -- e.g., "general", "technical", "sales", "edge_case"
    test_messages TEXT NOT NULL,  -- JSON array of test messages
    expected_behaviors TEXT,  -- JSON object describing expected response characteristics
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_scenarios_category ON test_scenarios(category);
CREATE INDEX IF NOT EXISTS idx_scenarios_active ON test_scenarios(active);

-- Test Runs Table
-- Stores results of test scenario runs
CREATE TABLE IF NOT EXISTS test_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id VARCHAR(255) UNIQUE NOT NULL,
    scenario_id VARCHAR(255) REFERENCES test_scenarios(scenario_id),
    status VARCHAR(50) DEFAULT 'running',  -- running, completed, failed
    total_tests INTEGER DEFAULT 0,
    passed_tests INTEGER DEFAULT 0,
    failed_tests INTEGER DEFAULT 0,
    avg_quality_score REAL,
    avg_response_time_ms REAL,
    results TEXT,  -- JSON object with detailed results
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_testruns_scenario ON test_runs(scenario_id);
CREATE INDEX IF NOT EXISTS idx_testruns_status ON test_runs(status);
CREATE INDEX IF NOT EXISTS idx_testruns_started ON test_runs(started_at);

-- RAG Retrieval Logs Table
-- Detailed logs of RAG retrievals for analysis
CREATE TABLE IF NOT EXISTS rag_retrieval_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_log_id INTEGER REFERENCES conversation_logs(id),
    query TEXT NOT NULL,
    results_count INTEGER DEFAULT 0,
    avg_relevance_score REAL,
    top_result_score REAL,
    top_result_source VARCHAR(255),
    results TEXT,  -- JSON array of retrieval results
    retrieval_time_ms REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_raglogs_conversation ON rag_retrieval_logs(conversation_log_id);
CREATE INDEX IF NOT EXISTS idx_raglogs_created_at ON rag_retrieval_logs(created_at);

-- Metrics Snapshots Table
-- Stores periodic snapshots of system metrics
CREATE TABLE IF NOT EXISTS metrics_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    period VARCHAR(50) DEFAULT 'hourly',  -- hourly, daily, weekly
    total_conversations INTEGER DEFAULT 0,
    total_messages INTEGER DEFAULT 0,
    avg_quality_score REAL,
    avg_response_time_ms REAL,
    weak_points_count INTEGER DEFAULT 0,
    high_severity_count INTEGER DEFAULT 0,
    fine_tuning_examples_count INTEGER DEFAULT 0,
    metrics_data TEXT  -- JSON object with detailed metrics
);

CREATE INDEX IF NOT EXISTS idx_metrics_time ON metrics_snapshots(snapshot_time);
CREATE INDEX IF NOT EXISTS idx_metrics_period ON metrics_snapshots(period);
