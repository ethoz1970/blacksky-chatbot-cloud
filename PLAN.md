# Plan: Featured Projects System for Maurice's RAG

## Current State

**Documents folder structure:**
```
documents/
├── about.md           # Company overview
├── Bruce_Lee_Quotes.md # Philosophy (Maurice personality)
├── engagement.md      # How engagements work
├── faq.md            # FAQs
├── mario.md          # Founder bio
├── projects.md       # All projects in one file (240 lines)
├── services.md       # Service offerings
├── war.md            # Strategy quotes
└── 48_laws_of_power.md # Business philosophy
```

**Current RAG behavior:**
- All documents chunked into 500-char pieces
- Top 3 chunks returned per query
- No prioritization - all documents equal weight

**Problem:**
- Projects are all in one file with minimal detail
- Maurice can mention projects but lacks deep context
- No way to highlight flagship work

---

## Proposed Solution: Featured Projects

### 1. New Folder Structure

```
documents/
├── company/
│   ├── about.md
│   ├── mario.md
│   ├── services.md
│   ├── engagement.md
│   └── faq.md
├── philosophy/
│   ├── Bruce_Lee_Quotes.md
│   ├── 48_laws_of_power.md
│   └── war.md
├── projects/
│   └── projects_summary.md    # Brief list of all projects (current projects.md condensed)
└── featured/                  # NEW: Deep-dive featured projects
    ├── _template.md           # Template for new featured projects
    ├── usda-fsis-ai-translation.md
    ├── hip-hop-chatbot.md
    ├── treasury-sharepoint-migration.md
    ├── vanguard-headless.md
    └── billboard-rescue.md
```

### 2. Featured Project Document Template

Each featured project gets its own detailed markdown file:

```markdown
# [Project Name] - [Client]

## Overview
[2-3 sentence executive summary]

## The Challenge
[What problem did the client face? Why did they need Blacksky?]

## Our Approach
[How did Blacksky tackle this? What was the strategy?]

## Key Accomplishments
- [Specific, quantifiable achievement]
- [Specific, quantifiable achievement]
- [Specific, quantifiable achievement]

## Technologies Used
[List of technologies with brief context on why each was chosen]

## Results & Impact
[Measurable outcomes - percentages, time saved, users served, etc.]

## Why This Matters
[What makes this project notable? Why should a prospect care?]

## Client Context
- Industry: [Government/Finance/Healthcare/etc.]
- Timeline: [Duration]
- Team Size: [If relevant]
- Security: [Clearances required, compliance standards]
```

### 3. Recommended 5 Featured Projects

Based on variety, impact, and sales relevance:

| # | Project | Why Feature It |
|---|---------|----------------|
| 1 | **USDA FSIS AI Translation** | Recent AI work, federal, shows cutting-edge capabilities |
| 2 | **Hip Hop Chatbot** | Demonstrates full LLM stack (fine-tuning, RAG, voice AI) |
| 3 | **Treasury SharePoint Migration** | Large-scale federal, 15k+ docs, enterprise credibility |
| 4 | **Vanguard Headless** | Fortune 500, modern architecture, proves corporate chops |
| 5 | **Billboard Rescue** | Story of saving a failing project, 5M+ users, memorable |

**Alternative candidates for future expansion:**
- National Gallery of Art (10k art records, cultural institution)
- NIH NINR (security clearance, healthcare)
- DOT Permitting (GIS/mapping, infrastructure)
- World Bank (international, open data)

### 4. RAG Enhancement Options

**Option A: Simple (Recommended for now)**
- Just reorganize documents into folders
- RAG will naturally find featured projects when relevant
- No code changes needed

**Option B: Priority Weighting**
- Tag featured project chunks with metadata
- Boost featured results in search ranking
- Requires minor RAG code changes

**Option C: Contextual Routing**
- Detect "project" or "case study" intent in queries
- Search featured folder first for project questions
- More complex, better for later

### 5. Implementation Steps

**Phase 1: Content Creation**
1. Create new folder structure
2. Write the `_template.md` for future projects
3. Expand 5 featured projects from summaries to full documents
4. Condense `projects.md` into `projects_summary.md` (keep brief mentions of non-featured)

**Phase 2: RAG Update**
1. Clear existing ChromaDB index
2. Reload documents from new structure
3. Test queries to verify featured projects surface well

**Phase 3: Process Documentation**
1. Document how to add new featured projects
2. Create checklist for "promoting" a project to featured status

---

## Process: Adding a New Featured Project

**When to feature a project:**
- Recent completion (last 1-2 years)
- Demonstrates a key capability
- Has compelling metrics/story
- Relevant to target prospects

**Steps:**
1. Copy `documents/featured/_template.md`
2. Rename to `{client-slug}-{project-type}.md`
3. Fill in all sections with specific details
4. Run `python rag.py load` to re-index
5. Test with sample questions

---

## Questions for You

Before implementing, I'd like to confirm:

1. **Are these the right 5 projects to feature?** Or would you prefer different ones?

2. **How detailed should featured projects be?**
   - ~500 words (current level + context)
   - ~1000 words (full case study)
   - ~2000 words (comprehensive with quotes/timeline)

3. **Should we implement RAG priority weighting?** Or keep it simple for now?

4. **Do you want me to write the featured project content?** Or will you provide the details?

---

## Expected Outcome

After implementation, Maurice will be able to:
- Give detailed answers about the 5 featured projects
- Reference specific metrics, challenges, and outcomes
- Tell compelling project "stories" not just list facts
- Still mention other projects from the summary file
- Have a clear process for adding more featured projects over time
