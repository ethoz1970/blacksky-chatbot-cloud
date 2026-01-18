# The World Bank - Open Data Platform

## Overview

Led a 4-month engagement (February 2019 - May 2019) as Site Architect, integrating cloud-based solutions with Drupal to enable open data publishing. The project leveraged the DKAN distribution to make World Bank data accessible as open-source feeds and through a searchable web interface.

## The Challenge

The World Bank generates massive amounts of development data - economic indicators, poverty statistics, health metrics, education data, and more across 189 member countries. This data needs to be:

- **Publicly accessible** - Open data commitment requires transparency
- **Machine-readable** - Researchers and developers need API access
- **Searchable** - Users need to find specific datasets quickly
- **Integrated with cloud infrastructure** - Scalable and reliable

The goal was to create a platform that served both human users browsing for data and machines consuming data programmatically.

## Blacksky's Approach

**Cloud Integration (AWS & Azure)**
- Architected integration between both cloud platforms and Drupal
- Hybrid approach leveraging best of both platforms
- Scalability designed for World Bank data volumes

**DKAN Implementation**
DKAN is a community-driven, open-source data management platform built on Drupal, designed specifically for publishing open data catalogs.

- Dataset management - upload, describe, and organize datasets
- DCAT-compliant metadata for discoverability
- In-browser data previews and visualization
- Automatic API endpoint generation for each dataset
- Harvest capabilities to pull data from external sources

**Open Data Feeds**
Configured World Bank data for open-source distribution:

| Feed Type | Purpose | Format |
|-----------|---------|--------|
| JSON APIs | Programmatic access for developers | JSON |
| GeoJSON | Geographic data for mapping | GeoJSON |
| WMS | Web Map Service for GIS integration | WMS |
| CSV Downloads | Bulk data for researchers | CSV |

The same underlying data serves researchers downloading CSV, developers building apps with JSON API, GIS analysts creating maps with WMS, and journalists visualizing trends with GeoJSON.

**Searchable Web Interface**
- Faceted search filtering by topic, country, date range, format
- Full-text search by keyword
- Rich dataset pages with metadata and previews
- Related dataset discovery
- Usage guides and API documentation

## Key Accomplishments

- **Multi-cloud integration** - AWS and Azure working together
- **4 feed formats** - JSON, GeoJSON, WMS, CSV serving diverse audiences
- **DKAN open data platform** - Full catalog implementation
- **Faceted search interface** - Powerful dataset discovery
- **DCAT-compliant metadata** - Standards-based discoverability
- **Automatic API generation** - Endpoints for every dataset

## Technologies

| Component | Technology |
|-----------|------------|
| CMS | Drupal 7 |
| Distribution | DKAN (Open Data Platform) |
| Cloud | AWS, Azure |
| Data Formats | JSON, GeoJSON, WMS, CSV |
| Hosting | Acquia Cloud |

## Why This Project Matters

This project demonstrates Blacksky's ability to:

- **Work with international institutions** - World Bank-level requirements and scale
- **Implement specialized distributions** - DKAN for open data publishing
- **Integrate multiple clouds** - AWS and Azure working together
- **Serve diverse audiences** - Same data, multiple formats for different users
- **Enable open data** - Making information accessible and machine-readable
- **Handle geographic data** - GeoJSON and WMS for mapping applications

---

**Client:** The World Bank
**Industry:** International Finance / Development
**Role:** Site Architect
**Timeline:** February 2019 - May 2019 (4 months)
**Status:** Completed
