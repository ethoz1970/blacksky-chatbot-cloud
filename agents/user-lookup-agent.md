# User/Lead Lookup Agent

## Purpose

This MCP agent allows Maurice to query the PostgreSQL database to retrieve information about users, their conversation history, extracted facts, and lead scores. It enables Maurice to "remember" returning users and provide personalized, context-aware responses.

## Database Connection

```
DATABASE_URL from environment variable
PostgreSQL: postgresql://user:pass@host:5432/database
```

## Database Schema

### Table: `users`

```sql
CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,          -- UUID
    name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(50),
    company VARCHAR(255),
    status VARCHAR(20) DEFAULT 'new',    -- new, contacted, qualified, converted, archived
    notes TEXT,
    created_at TIMESTAMP,
    last_seen TIMESTAMP,
    google_id VARCHAR(255),
    google_email VARCHAR(255),
    google_name VARCHAR(255),
    auth_method VARCHAR(20) DEFAULT 'soft',  -- soft, medium, google
    password_hash VARCHAR(255),
    interest_level VARCHAR(20)           -- Gold, Silver, Bronze
);
```

### Table: `conversations`

```sql
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY,
    user_id VARCHAR(36) REFERENCES users(id),
    messages TEXT,                       -- JSON array of {role, content, timestamp}
    summary TEXT,                        -- AI-generated summary
    interests TEXT,                      -- JSON array of detected interests
    lead_score INTEGER DEFAULT 1,        -- 1-5 scale
    started_at TIMESTAMP,
    ended_at TIMESTAMP
);
```

### Table: `user_facts`

```sql
CREATE TABLE user_facts (
    id INTEGER PRIMARY KEY,
    user_id VARCHAR(36) REFERENCES users(id),
    fact_type VARCHAR(50),               -- role, budget, timeline, company_size, etc.
    fact_value TEXT,
    confidence FLOAT,                    -- 0.0 to 1.0
    source_text TEXT,                    -- Original text that extracted this fact
    extracted_at TIMESTAMP
);
```

**Fact Types:**
- `role` - Job title (CTO, CEO, VP Engineering, Developer, etc.)
- `budget` - Budget range ($50k-$100k, $100k+, etc.)
- `timeline` - Project timeline (Q2 2025, next month, ASAP, etc.)
- `company_size` - Number of employees
- `project_type` - What they want to build (mobile app, web platform, API, etc.)
- `industry` - Their industry (healthcare, fintech, government, etc.)
- `pain_point` - Their challenges (scaling, security, modernization, etc.)
- `decision_stage` - Where they are (researching, evaluating, ready to hire)

## Tools to Implement

### 1. `lookup_user_by_name`

Search for users by name (partial match).

**Input:**
```json
{
  "name": "John"
}
```

**Output:**
```json
{
  "found": true,
  "users": [
    {
      "id": "uuid-123",
      "name": "John Smith",
      "email": "john@acme.com",
      "company": "Acme Corp",
      "status": "qualified",
      "last_seen": "2024-01-15T10:30:00Z",
      "interest_level": "Gold"
    }
  ]
}
```

**SQL:**
```sql
SELECT id, name, email, company, status, last_seen, interest_level
FROM users
WHERE LOWER(name) LIKE LOWER('%' || $1 || '%')
ORDER BY last_seen DESC
LIMIT 10;
```

---

### 2. `lookup_user_by_email`

Search for users by email (exact or partial match).

**Input:**
```json
{
  "email": "john@acme.com"
}
```

**Output:**
```json
{
  "found": true,
  "user": {
    "id": "uuid-123",
    "name": "John Smith",
    "email": "john@acme.com",
    "company": "Acme Corp",
    "status": "qualified",
    "last_seen": "2024-01-15T10:30:00Z"
  }
}
```

---

### 3. `lookup_user_by_company`

Search for all users from a specific company.

**Input:**
```json
{
  "company": "Acme"
}
```

**Output:**
```json
{
  "found": true,
  "company": "Acme Corp",
  "users": [
    {"id": "uuid-123", "name": "John Smith", "role": "CTO"},
    {"id": "uuid-456", "name": "Jane Doe", "role": "VP Engineering"}
  ]
}
```

---

### 4. `get_user_context`

Get full context for a user including facts and recent conversations.

**Input:**
```json
{
  "user_id": "uuid-123"
}
```

**Output:**
```json
{
  "user": {
    "id": "uuid-123",
    "name": "John Smith",
    "email": "john@acme.com",
    "company": "Acme Corp",
    "status": "qualified",
    "interest_level": "Gold"
  },
  "facts": {
    "role": {"value": "CTO", "confidence": 0.95},
    "budget": {"value": "$100k-$200k", "confidence": 0.8},
    "timeline": {"value": "Q2 2025", "confidence": 0.9},
    "project_type": {"value": "AI chatbot platform", "confidence": 0.85},
    "industry": {"value": "Healthcare", "confidence": 0.95},
    "pain_point": {"value": "Legacy system modernization", "confidence": 0.7}
  },
  "recent_conversations": [
    {
      "date": "2024-01-15",
      "summary": "Discussed AI integration for patient portal",
      "interests": ["AI/ML", "Healthcare compliance", "HIPAA"],
      "lead_score": 4
    }
  ],
  "total_conversations": 3
}
```

**SQL (multiple queries):**
```sql
-- Get user
SELECT * FROM users WHERE id = $1;

-- Get facts
SELECT fact_type, fact_value, confidence
FROM user_facts
WHERE user_id = $1
ORDER BY confidence DESC;

-- Get recent conversations
SELECT summary, interests, lead_score, started_at
FROM conversations
WHERE user_id = $1
ORDER BY started_at DESC
LIMIT 5;
```

---

### 5. `get_conversation_history`

Get detailed conversation history for a user.

**Input:**
```json
{
  "user_id": "uuid-123",
  "limit": 3
}
```

**Output:**
```json
{
  "conversations": [
    {
      "id": 42,
      "date": "2024-01-15",
      "summary": "Discussed AI integration for patient portal",
      "interests": ["AI/ML", "Healthcare compliance"],
      "lead_score": 4,
      "message_count": 12
    }
  ]
}
```

---

### 6. `get_leads_by_score`

Get all leads with a minimum lead score.

**Input:**
```json
{
  "min_score": 4,
  "status": "qualified"
}
```

**Output:**
```json
{
  "leads": [
    {
      "user_id": "uuid-123",
      "name": "John Smith",
      "company": "Acme Corp",
      "lead_score": 5,
      "last_conversation": "2024-01-15",
      "interests": ["AI/ML", "Enterprise"]
    }
  ],
  "total": 15
}
```

---

### 7. `search_users_by_fact`

Find users with specific characteristics.

**Input:**
```json
{
  "fact_type": "industry",
  "fact_value": "healthcare"
}
```

**Output:**
```json
{
  "users": [
    {
      "id": "uuid-123",
      "name": "John Smith",
      "company": "Acme Healthcare",
      "fact_value": "Healthcare",
      "confidence": 0.95
    }
  ]
}
```

**SQL:**
```sql
SELECT u.id, u.name, u.company, uf.fact_value, uf.confidence
FROM users u
JOIN user_facts uf ON u.id = uf.user_id
WHERE uf.fact_type = $1
  AND LOWER(uf.fact_value) LIKE LOWER('%' || $2 || '%')
ORDER BY uf.confidence DESC;
```

---

### 8. `get_user_timeline`

Get a timeline of all interactions with a user.

**Input:**
```json
{
  "user_id": "uuid-123"
}
```

**Output:**
```json
{
  "timeline": [
    {"date": "2024-01-10", "event": "First contact", "type": "conversation"},
    {"date": "2024-01-12", "event": "Discussed pricing", "type": "conversation"},
    {"date": "2024-01-15", "event": "Status changed to qualified", "type": "status_change"},
    {"date": "2024-01-15", "event": "Budget fact extracted: $100k-$200k", "type": "fact"}
  ]
}
```

---

## Example Use Cases

### Use Case 1: Returning User Recognition

**User says:** "Hi, I'm John from Acme"

**Maurice calls:** `lookup_user_by_name("John")` + filters by company "Acme"

**Maurice responds:** "John! Good to hear from you again. Last time we talked about AI integration for your patient portal. Have you made progress on the HIPAA compliance review?"

---

### Use Case 2: Context Injection

**User says:** "What were we discussing last time?"

**Maurice calls:** `get_user_context(user_id)`

**Maurice responds:** "We were exploring how to modernize your legacy system with AI capabilities. You mentioned a Q2 timeline and a budget around $100k-$200k. Want to pick up where we left off?"

---

### Use Case 3: Company Intelligence

**User says:** "I work at Acme Corp"

**Maurice calls:** `lookup_user_by_company("Acme Corp")`

**Maurice responds:** "Ah, Acme Corp! I've spoken with a few folks from your team. Are you working with John Smith on the patient portal project, or is this something different?"

---

### Use Case 4: Lead Prioritization

**Internal trigger:** Dashboard requests hot leads

**Maurice calls:** `get_leads_by_score(min_score=4, status="qualified")`

**Returns:** List of high-intent prospects for follow-up

---

## Integration with Maurice

When Maurice detects these triggers, call the appropriate tool:

| Trigger | Tool to Call |
|---------|--------------|
| User provides name | `lookup_user_by_name` |
| User provides email | `lookup_user_by_email` |
| User mentions company | `lookup_user_by_company` |
| Returning user detected | `get_user_context` |
| "What did we discuss" | `get_conversation_history` |
| Admin requests leads | `get_leads_by_score` |
| "Anyone else from [industry]" | `search_users_by_fact` |

---

## Response Formatting

When returning data to Maurice, format it as natural context:

**Instead of:**
```json
{"name": "John", "budget": "$100k", "timeline": "Q2"}
```

**Return:**
```
Returning user: John Smith (CTO at Acme Corp)
- Budget: $100k-$200k (high confidence)
- Timeline: Q2 2025
- Interest: AI/ML integration, Healthcare compliance
- Last conversation: Discussed patient portal modernization
- Lead score: 4/5 (high intent)
```

This allows Maurice to naturally incorporate the context into his response.

---

## Error Handling

```json
{
  "found": false,
  "message": "No users found matching 'John' at 'Acme'"
}
```

```json
{
  "error": true,
  "message": "Database connection failed",
  "code": "DB_CONNECTION_ERROR"
}
```

---

## Security Notes

- Read-only access to database (no INSERT/UPDATE/DELETE)
- Sanitize all inputs to prevent SQL injection
- Don't expose raw user IDs in responses to end users
- Log all queries for audit purposes
- Respect data retention policies

---

## Implementation Notes

1. Use connection pooling for PostgreSQL
2. Cache frequently accessed users (5 min TTL)
3. Index columns: `name`, `email`, `company`, `user_id` (on all tables)
4. Return confidence scores so Maurice can caveat uncertain info
5. Limit results to prevent large response payloads
