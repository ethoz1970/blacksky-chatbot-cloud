# Plan: Enhanced Admin Dashboard - Users Page

## Overview
Add a dedicated Users page (`/admin/users`) that focuses on user management with full history viewing, auth method filtering, and user tracking capabilities.

## Current State
- `/admin` - Leads dashboard (sorted by lead score, focused on sales)
- `/admin/traffic` - Q&A exchanges (paginated message pairs)
- Missing: A user-centric view showing all users with their full context

## Proposed Solution

### 1. New Endpoint: `/admin/users`

A dedicated users page with:

**Filtering Options:**
- Auth method filter: All | Soft | Hard (Medium) | Anonymous
- Status filter: All | New | Contacted | Qualified | Converted | Archived
- Search: Name, email, company
- Sort by: Last seen, Created at, Conversation count, Name

**User Table Columns:**
| Column | Description |
|--------|-------------|
| Auth | Icon/badge showing auth method (lock=hard, user=soft, ?=anon) |
| Name | User name (clickable to expand) |
| Email | Email if available |
| Company | Company if extracted |
| Conversations | Count of total conversations |
| Facts | Count of extracted facts |
| Last Seen | When they last interacted |
| Created | When first seen |

**User Detail Modal (click on user):**
- Full profile: name, email, phone, company, auth method, interest level
- All extracted facts with confidence scores
- Complete conversation timeline (all conversations, all messages)
- Lead score history across conversations
- Quick actions: Edit notes, Change status, Delete user

### 2. Database Function: `get_all_users()`

New function in database.py:
```python
def get_all_users(
    auth_method: str = None,  # 'soft', 'medium', 'google', or None for all
    status: str = None,
    search: str = None,
    sort_by: str = 'last_seen',  # last_seen, created_at, name, conversations
    sort_order: str = 'desc',
    limit: int = 100,
    offset: int = 0
) -> dict:
    """
    Returns:
    {
        "users": [
            {
                "id": "uuid",
                "name": "John",
                "email": "john@example.com",
                "company": "Acme",
                "auth_method": "soft",
                "status": "qualified",
                "interest_level": "Gold",
                "created_at": "2024-01-01",
                "last_seen": "2024-01-15",
                "conversation_count": 5,
                "fact_count": 3,
                "total_messages": 24
            }
        ],
        "total": 150,
        "page": 1,
        "total_pages": 2
    }
    """
```

### 3. Database Function: `get_user_full_profile()`

Enhanced user detail function:
```python
def get_user_full_profile(user_id: str) -> dict:
    """
    Returns complete user profile for admin view:
    {
        "user": {
            "id", "name", "email", "phone", "company",
            "auth_method", "status", "interest_level", "notes",
            "created_at", "last_seen"
        },
        "facts": [
            {"type": "role", "value": "CTO", "confidence": 0.95, "source_text": "..."}
        ],
        "conversations": [
            {
                "id": 1,
                "created_at": "2024-01-15",
                "summary": "...",
                "lead_score": 3,
                "message_count": 12,
                "messages": [{"role": "user", "content": "..."}, ...]
            }
        ],
        "stats": {
            "total_conversations": 5,
            "total_messages": 48,
            "avg_lead_score": 2.4,
            "first_contact": "2024-01-01",
            "days_since_first_contact": 15
        }
    }
    """
```

### 4. UI Design

**Color coding for auth methods:**
- Hard login: Green badge (#6d6)
- Soft login: Blue badge (#68d)
- Anonymous: Gray badge (#666)

**Page layout:**
```
+----------------------------------------------------------+
| Users Dashboard                    [Leads] [Traffic]      |
+----------------------------------------------------------+
| Auth: [All v]  Status: [All v]  Sort: [Last Seen v]      |
| Search: [____________________]   Showing 45 of 150        |
+----------------------------------------------------------+
| Auth | Name          | Email           | Conv | Last Seen |
|------|---------------|-----------------|------|-----------|
| [H]  | John Smith    | john@acme.com   |  5   | 2 hrs ago |
| [S]  | Jane Doe      | -               |  3   | 1 day ago |
| [?]  | ANON[01-15]   | -               |  1   | 3 days    |
+----------------------------------------------------------+
```

**Detail modal:**
```
+----------------------------------------------------------+
| John Smith                                          [X]   |
+----------------------------------------------------------+
| Auth: Hard Login    Status: Qualified    Interest: Gold   |
| Email: john@acme.com    Phone: 555-1234                   |
| Company: Acme Corp      First seen: Jan 1, 2024           |
+----------------------------------------------------------+
| EXTRACTED FACTS                                           |
| Role: CTO (95% confidence)                                |
| Budget: $100k-200k (80% confidence)                       |
| Timeline: Q2 2025 (90% confidence)                        |
+----------------------------------------------------------+
| CONVERSATION HISTORY                                      |
| [Jan 15] Score: 3 - Discussed AI integration (12 msgs)    |
|   > User: Hi, I'm interested in...                        |
|   > Maurice: Welcome! I'd be happy to...                  |
| [Jan 10] Score: 2 - Initial inquiry (8 msgs)              |
|   > User: What services do you offer?                     |
|   > Maurice: Blacksky specializes in...                   |
+----------------------------------------------------------+
| [Edit Notes]  [Change Status v]  [Delete User]            |
+----------------------------------------------------------+
```

### 5. Implementation Steps

1. **Add database functions** (database.py)
   - `get_all_users()` with filtering/sorting/pagination
   - `get_user_full_profile()` for detail modal

2. **Add API endpoint** (server.py)
   - `GET /admin/users` - Main users page
   - `GET /admin/users/{user_id}` - User detail JSON endpoint

3. **Build HTML page** (server.py)
   - Filter bar with auth method, status, search, sort
   - User table with pagination
   - Detail modal with full history
   - JavaScript for filtering, modal loading, pagination

4. **Update navigation**
   - Add "Users" link to existing admin pages
   - Update header to show current page

### 6. Files to Modify

| File | Changes |
|------|---------|
| `database.py` | Add `get_all_users()`, `get_user_full_profile()` |
| `server.py` | Add `/admin/users` route, `/admin/users/{user_id}` API |

### 7. Navigation Update

Add to all admin pages:
```html
<div class="actions">
    <a href="/admin?password={password}" class="btn">Leads</a>
    <a href="/admin/users?password={password}" class="btn">Users</a>
    <a href="/admin/traffic?password={password}" class="btn">Traffic</a>
</div>
```

## Summary

This adds a user-focused admin view that complements the existing leads (sales-focused) and traffic (message-focused) dashboards. The key differentiators:

- **Leads**: Sorted by lead score, focused on sales conversion
- **Users**: Sorted by auth method/activity, focused on user management
- **Traffic**: Sorted by time, focused on Q&A content review
