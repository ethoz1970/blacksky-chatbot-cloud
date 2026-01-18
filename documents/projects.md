# Blacksky Project Portfolio

## Summary

Blacksky LLC has delivered enterprise platforms for 18+ years.

- **Federal agencies served**: Treasury, DOT, NIH, FDA, OSHA, SEC, FSIS, HHS, USAID, Department of Education
- **Fortune 500 clients**: Vanguard, Mastercard, Blue Cross Blue Shield
- **Platform migrations led**: 15+
- **Users served**: 50M+
- **Security clearances**: Active, including NIH background check

---

## Featured AI Projects

### Maurice - AI Sales Agent (Live)

Maurice is Blacksky's production AI sales assistant - a conversational AI that qualifies leads, answers questions about services, and captures prospect information through natural dialogue. He's live at blackskymedia.org, handling real sales conversations 24/7.

**Key features:**
- Streaming responses with real-time typing
- RAG retrieval for accurate information from knowledge base
- Lead scoring - automatically classifies visitors as hot, warm, or cool
- User memory - recognizes returning visitors
- Semantic fact extraction from conversations

**Technologies**: Python, FastAPI, Llama 3.1 70B (Together AI), Sentence Transformers, Pinecone, PostgreSQL, Railway

### Ife - Internal Coding Intelligence

Ife (Yoruba for "clarity") is Blacksky's private RAG-based coding assistant that provides Claude-level guidance while keeping proprietary code secure. Ife knows Blacksky's codebase, conventions, and architecture.

**Key capabilities:**
- Contextual coding assistance trained on Blacksky's codebase
- Institutional knowledge about documentation and conventions
- Developer support without external API calls

**Technologies**: Local LLM (Llama-based), Custom RAG pipeline, ChromaDB, Python

### Seth - Privacy-Preserving Therapy LLM (Beta)

Seth is a privacy-preserving therapy LLM that actually learns from conversations while keeping user data private through blockchain-based anonymization. Mental health support that improves through use - without surveillance.

**Innovation:** Uses Ethereum network protocols to mask user PII while still allowing the model to learn. Privacy is architectural, not just policy.

**Technologies**: Custom LLM architecture, Ethereum network protocols, Python

### Poly Sci Fi - Civic Technology Platform (Live)

Poly Sci Fi is a civic technology platform that tracks every member of Congress in real-time. Designed to transform passive news consumers into active participants in democracy.

**Current features:**
- Real-time congressional tracking - all 535 members
- Live updates via Congress.gov API
- Member profiles with voting records and committee assignments
- News tracking and coverage per representative

**Technologies**: Next.js, React, TypeScript, Python, FastAPI, PostgreSQL, Google Cloud Platform

### Hip-Hop Voice AI - Cultural Preservation

Voice-cloned conversational AI that preserves the voice, personality, and cultural knowledge of a legendary hip-hop figure. Combines RAG with voice synthesis for interactive cultural archiving.

**Architecture:**
- Brain Node: Llama 3 with RAG for knowledge retrieval
- Bridge Node: Middleware for personality orchestration
- Voice Node: Coqui XTTS v2 for voice cloning
- 100% local deployment on MacBook Pro M3

**Technologies**: Llama 3 via Ollama, LanceDB, Coqui XTTS v2, OpenAI Whisper, Python, FastAPI

---

## Recent Federal AI Projects

### Production AI Translation API - USDA FSIS (2024)

Architected custom RESTful API connecting Drupal 10 to Azure AI Translation Services for real-time multilingual content delivery.

**Key accomplishments:**
- Real-time translation across 5 languages (English, Spanish, French, Portuguese, Chinese)
- Deployed on Azure Kubernetes Service with Redis Cluster caching
- Sub-second translation response times
- FISMA-compliant with federal data protection protocols

**Technologies**: Python, PHP, Drupal 10, Azure AI Translation Services, Kubernetes, Redis Cluster

---

## Federal Agency Projects

### USDA Food Safety and Inspection Service (2024-Present)

Led architectural design and implementation of enterprise-scale Drupal 10 platform modernization.

**Key accomplishments:**
- Redis Cluster architecture on Azure Kubernetes Service, improving response times by 70%
- AI-powered translation service for 15+ languages
- Custom JSON API framework for microservices architecture
- Kubernetes deployment pipeline reducing infrastructure costs by 40%

**Technologies**: Drupal 10, PHP, Kubernetes, Redis Cluster, Azure Cloud, Apache Solr

### Department of Health and Human Services (2024)

Led Drupal 9 to 10 upgrade for critical HHS content management system serving public health information.

**Key accomplishments:**
- Upgrade pathway for 50+ custom modules and 100+ contributed modules
- Backward-compatible API layer for external health information systems
- Automated testing framework reducing regression issues by 80%
- Zero-downtime migration maintaining 24/7 availability

**Technologies**: Drupal 9/10, PHP, Apache Solr, Acquia Cloud, AWS

### National Institute of Nursing Research - NIH (2023-2024)

Architected Drupal 8 to 10 migration for NIH research institute. Required federal security clearance.

**Key accomplishments:**
- FISMA-compliant architecture meeting NIH security standards
- Custom integration layer connecting NIH research databases
- Apache Solr search for complex research publication queries

**Technologies**: Drupal 10, PHP, Apache Solr, Acquia Cloud, AWS

### USAID Environmental Database (2022-2023)

Led complete architectural transformation of USAID's Environmental Database, modernizing a legacy PHP application into enterprise-grade Drupal 10. Solo reverse-engineered the undocumented legacy system for 7 months before expanding to lead a team.

**Key accomplishments:**
- 7 months solo reverse engineering of legacy PHP with minimal documentation
- Microservices-based integration layer reducing data latency by 75%
- Apache Solr search across 50,000+ records with sub-second response times
- Led team of 2 (front-end engineer + junior dev) for final 4 months
- 60% reduction in production defects through quality leadership
- Delivered under budget and ahead of schedule

**Technologies**: Drupal 10, PHP, Apache Solr, Acquia Cloud, Microservices API integrations

### Texas Department of Health and Human Services (2022)

Migrated two legacy ASP.NET sites to unified Drupal 9 platform.

**Key accomplishments:**
- Unified content architecture consolidating two separate systems
- Content workflows improving publishing efficiency by 50%

**Technologies**: Drupal 9, PHP, Apache Solr, Acquia Cloud

### U.S. Department of Treasury (2020)

Led 9-month engagement as Senior Architect, migrating 6 legacy SharePoint sites to a unified Drupal 8 platform for treasury.gov. Built custom API layer integrating legacy XML with modern JSON APIs.

**Key accomplishments:**
- 6 SharePoint sites consolidated into 1 unified Drupal platform
- 15,000+ documents migrated with 98% metadata fidelity
- 200+ content creators configured with role-based access and editorial workflows
- 92% reduction in deployment time (3 days → 4 hours) via Jenkins CI/CD
- Custom modules for document management, data visualization, and webforms
- Real-time data feeds connecting Treasury backend systems

**Technologies**: Drupal 8, PHP, JavaScript, SharePoint, Jenkins CI/CD, Acquia Cloud, Custom JSON/XML APIs

### U.S. Department of Transportation (2019-2020)

Architected OST permitting dashboard integrating geospatial data for infrastructure projects exceeding $100M.

**Key accomplishments:**
- ArcGIS integration visualizing 500+ active infrastructure projects
- Multi-API orchestration for 15 federal and state agencies
- Drupal 7 to 8 migration maintaining operational uptime

**Technologies**: Drupal 7/8, PHP, ArcGIS API, Socrata API, GeoJSON

### U.S. Securities and Exchange Commission (2017)

Led technical improvements for SEC.gov establishing modern development workflows.

**Key accomplishments:**
- Introduced agile practices: pull requests, peer code reviews, automated testing
- Implemented Behat automated testing framework

**Technologies**: Drupal 8, PHP, Composer, Behat, Acquia Cloud

### Federal Student Aid - IFAP.ed.gov (2018)

Architected enterprise server infrastructure integrating Drupal 8 with Oracle 11g.

**Key accomplishments:**
- Drupal 8 integration with Oracle 11g enterprise database
- OAuth third-party authorization meeting federal security guidelines
- 3 environments with complete infrastructure redundancy

**Technologies**: Drupal 8, PHP, Oracle 11g, OAuth

---

## Fortune 500 Projects

### Vanguard Financial Services (2020-2021)

Led technical transformation from monolithic Drupal 8 to headless architecture.

**Key accomplishments:**
- RESTful API layer serving content to Angular frontend
- Content export system reducing API response times by 40%
- Drupal 8 to 9 upgrade with headless architecture without service interruption

**Technologies**: Drupal 9, PHP, RESTful APIs, Angular, Acquia Cloud, AWS

### Mastercard (2021-2022)

Built custom bulk upload system for efficient file processing and content management.

**Key accomplishments:**
- Bulk upload of hundreds of files with automated validation
- File processing pipeline with unzip, naming verification, automated node creation

**Technologies**: Drupal 9, PHP, Acquia Cloud, Docker

### Blue Cross Blue Shield (2022)

Designed comprehensive notification and alert system for BCBS Connect member portal.

**Key accomplishments:**
- Real-time notification system for member communications
- Notification delivery framework with customizable alert types
- Delivered within 3-month timeline

**Technologies**: Drupal 9, PHP, Lando, Acquia Cloud, Docker

### National Gallery of Art (2024)

Complete platform migration from legacy Adobe CMS to modern Drupal 10.

**Key accomplishments:**
- Migration of 10,000+ art collection records with 99% data fidelity
- Content model supporting complex art metadata and multilingual content
- Enhanced search with Apache Solr faceted browsing
- Reduced publishing time by 60%

**Technologies**: Drupal 10, PHP, Apache Solr, Acquia Cloud

### World Bank Open Data Platform (2019)

Cloud-integrated open data platform using Drupal 7 DKAN distribution.

**Key accomplishments:**
- AWS and Azure cloud integration
- RESTful API for third-party data harvesting

**Technologies**: Drupal 7, DKAN, PHP, AWS, Azure

---

## Media & Commercial Projects

### Billboard.com (2013-2014)

Led initiative bringing Billboard.com in-house from failed overseas outsourcing. Serving 5M+ monthly visitors.

**Key accomplishments:**
- Rescued platform from overseas consulting company
- Improved site performance by 65% through Memcache caching
- Custom modules for Kaltura video-on-demand

**Technologies**: Drupal 7, PHP, MySQL, Memcache, REST APIs, Kaltura

### ShareMyLesson.com - American Federation of Teachers (2018)

Built social functionality and recommendation systems for educational resource platform.

**Key accomplishments:**
- Recommendation engine for educational content discovery
- Social features: following, notifications, activity feeds

**Technologies**: Drupal 7/8, PHP, JavaScript, Behat, Acquia Cloud

---

## Personal Projects

### Poly Sci Fi - Congressional Directory (2024)

Full-stack civic technology application for legislative information. Poly Sci Fi tracks every member of Congress in real-time.

**Key accomplishments:**
- Next.js frontend with Python FastAPI backend on Google Cloud Platform
- RESTful API integrating Congress.gov for all 535 members of Congress
- Advanced filtering and search capabilities

**Technologies**: Next.js, React, Python, FastAPI, Congress.gov API, GCP
