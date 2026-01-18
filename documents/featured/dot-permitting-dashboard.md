# U.S. Department of Transportation - Permitting Dashboard

## Overview

Led an 11-month engagement (May 2019 - March 2020) as Senior Consultant and Lead Backend Developer, modernizing the Office of the Secretary (OST) permitting dashboard. The project combined platform migration, GIS visualization, and complex multi-API orchestration to create an interactive view of 500+ infrastructure projects across the United States.

## The Challenge

DOT needed to modernize their permitting dashboard to:

- **Migrate from legacy platform** - Drupal 7 codebase needed upgrade to Drupal 8
- **Visualize project data geographically** - 500+ infrastructure projects needed map-based interface
- **Integrate multiple data sources** - Project data lived in multiple external systems (Socrata, ARCGIS, internal)
- **Support multiple DOT websites** - Site building across various DOT properties

The existing system couldn't provide the geographic visualization stakeholders needed to understand infrastructure investment patterns across the country.

## Blacksky's Approach

**Drupal 7 to Drupal 8 Migration**
- Code modernization upgrading custom modules to Drupal 8 patterns
- Content migration moving existing permit and project data
- Theme conversion to Drupal 8 theming system
- Implemented proper config export/import workflow

**ARCGIS Integration**
- Interactive maps displaying 500+ infrastructure projects geographically
- Project clustering for readability at different zoom levels
- Toggleable layers for different project types
- Click-through details linking markers to full project information
- Geographic filtering by state, region, or custom boundaries

**Multi-API Orchestration**
Built integration layer connecting multiple external data sources:
- **Socrata** - Open data platform (JSON)
- **ARCGIS** - Geographic services (GeoJSON, WMS)
- **Internal Systems** - Permit data (CSV, JSON)

Orchestration challenges solved:
- Data normalization from different sources into unified schema
- Caching strategy reducing API calls while maintaining freshness
- Graceful degradation when upstream APIs fail
- Rate limiting respecting API quotas across all sources

## Key Accomplishments

- **Platform migration** - Drupal 7 to Drupal 8 with custom modules
- **500+ infrastructure projects** visualized on interactive ARCGIS maps
- **3+ external APIs** orchestrated into unified data layer
- **Multiple data formats** normalized (JSON, GeoJSON, WMS, CSV)
- **Multiple DOT websites** built and maintained
- **Geographic insights** - transformed tabular data into interactive maps

## Technologies

| Component | Technology |
|-----------|------------|
| CMS | Drupal 7 → Drupal 8 |
| Language | PHP, JavaScript |
| GIS | ARCGIS |
| Data Formats | JSON, GeoJSON, WMS, CSV |
| External APIs | Socrata, ARCGIS Services |
| Hosting | Acquia Cloud |

## Why This Project Matters

This project demonstrates Blacksky's ability to:

- **Execute platform migrations** - Drupal 7 to Drupal 8 with custom modules
- **Integrate GIS visualization** - ARCGIS maps with 500+ data points
- **Orchestrate multiple APIs** - Socrata, ARCGIS, internal systems unified
- **Handle diverse data formats** - JSON, GeoJSON, WMS, CSV normalized
- **Build for federal scale** - DOT-level security and performance requirements
- **Deliver geographic insights** - Transform tabular data into interactive maps

---

**Client:** U.S. Department of Transportation (Office of the Secretary)
**Industry:** Federal Government / Transportation
**Role:** Senior Consultant / Lead Backend Developer
**Timeline:** May 2019 - March 2020 (11 months)
**Status:** Completed
