# Iran Protest News Sources Research

*Research Date: January 8, 2026*

This document outlines the best news sources for covering Iran protests, their accessibility, and integration options for the Telegram News Summarizer Bot.

## Table of Contents

- [Overview](#overview)
- [Tier 1: Telegram Channels (Direct Integration)](#tier-1-telegram-channels-direct-integration)
- [Tier 2: International News Outlets (Web Scraping Required)](#tier-2-international-news-outlets-web-scraping-required)
- [Tier 3: Human Rights Organizations](#tier-3-human-rights-organizations)
- [Integration Options](#integration-options)
- [Technical Considerations](#technical-considerations)
- [Sources](#sources)

---

## Overview

The 2025-2026 Iranian protests began on December 28, 2025, triggered by economic conditions including the rial plunging to record lows. As of January 2026, protests have spread to 285+ locations across 92 cities in 27 provinces, with significant casualties and over 2,000 arrests reported.

**Key Challenge:** Iranian state media provides minimal coverage, and journalists face severe restrictions. This makes international and diaspora news sources essential for accurate reporting.

---

## Tier 1: Telegram Channels (Direct Integration)

These channels can be added directly to `config/channels.yaml` using the existing bot infrastructure.

### Persian-Language Channels

| Channel | Telegram Handle | Subscribers | Description | Reliability |
|---------|-----------------|-------------|-------------|-------------|
| **Iran International** | `iranintltv` | ~895,000 | 24-hour Persian news network based in London. Comprehensive protest coverage with on-ground sources. | ⭐⭐⭐⭐⭐ |
| **BBC Persian** | `bbcpersian` | ~766,000 | Official BBC Persian service. Well-verified reporting with global correspondent network. | ⭐⭐⭐⭐⭐ |
| **Radio Farda** | `radiofarda` | ~500,000+ | RFE/RL Persian service based in Prague. *Note: Operations suspended March 2025 - verify status.* | ⭐⭐⭐⭐ |
| **VOA Farsi** | `farsivoa` | ~400,000+ | Voice of America Persian service. US government-funded but editorially independent. | ⭐⭐⭐⭐ |

### English-Language Channels

| Channel | Telegram Handle | Description | Reliability |
|---------|-----------------|-------------|-------------|
| **Iran International English** | `IranIntl_En` | English version of Iran International. First 24/7 English news service for Iran. | ⭐⭐⭐⭐⭐ |
| **Press TV** | `presstv` | Iranian state media (English). Useful for official government perspective. | ⭐⭐ (state media) |
| **IRNA English** | `Irna_en` | Islamic Republic News Agency. Official state news. | ⭐⭐ (state media) |

### Channel Details

#### Iran International (`iranintltv`)
- **Website:** https://www.iranintl.com
- **Founded:** May 2017
- **Base:** London, UK
- **Contact:** @intlmedia_bot (Telegram), bama@iranintl.com
- **Notes:** The Iranian regime has imposed judicial restrictions against staff due to protest coverage. Considered the most influential diaspora Persian news network.

#### BBC Persian (`bbcpersian`)
- **Website:** https://www.bbc.com/persian
- **Founded:** 1940
- **Base:** London, UK
- **Contact:** @BBCShoma (Telegram)
- **Notes:** Uses "social circumvention strategy" to bypass Iranian censorship. Relies heavily on citizen journalists and Telegram followers for on-ground reporting.

#### Radio Farda (`radiofarda`)
- **Website:** https://www.radiofarda.com
- **Founded:** December 2002
- **Base:** Prague, Czech Republic
- **Funding:** US Congress via USAGM
- **Contact:** @fardagram, +420725970000
- **⚠️ Status Warning:** In March 2025, USAGM terminated grants to RFE/RL. Programming may be suspended or limited. Verify current operational status before adding.

#### VOA Farsi (`farsivoa`)
- **Website:** https://www.voanews.com/persian
- **Base:** Washington, DC
- **Funding:** US government (Voice of America)
- **Notes:** 24-hour satellite TV channel VOA365, plus web and social media platforms.

---

## Tier 2: International News Outlets (Web Scraping Required)

These outlets provide excellent Iran coverage but do not maintain Iran-specific Telegram channels. Integration would require building a web scraping or RSS module.

### Wire Services & Major Outlets

| Outlet | Iran Coverage | Data Access Method | RSS/API |
|--------|---------------|-------------------|---------|
| **Reuters** | Excellent - wire service with Middle East bureau | RSS via third-party (rss.app) | No official RSS |
| **Associated Press** | Excellent - primary wire service | Via news aggregators | Limited |
| **The Guardian** | Good - in-depth analysis pieces | RSS: `theguardian.com/world/rss` | ✅ Official RSS |
| **Al Jazeera** | Excellent - strong Middle East focus | RSS available | ✅ Official RSS |
| **NPR** | Good - US perspective with analysis | RSS available | ✅ Official RSS |
| **CNN** | Good - breaking news focus | Limited RSS | Partial |
| **PBS NewsHour** | Good - AP wire + analysis | RSS available | ✅ Official RSS |
| **CBS News** | Good - breaking news | RSS available | ✅ Official RSS |
| **New York Times** | Excellent - in-depth reporting | Paywall, limited RSS | Partial |
| **Wall Street Journal** | Good - business/economic angle | Paywall | Partial |

### RSS Feed URLs

```
# The Guardian - World News
https://www.theguardian.com/world/rss

# Al Jazeera - Middle East
https://www.aljazeera.com/xml/rss/all.xml

# NPR - World
https://feeds.npr.org/1004/rss.xml

# PBS NewsHour - World
https://www.pbs.org/newshour/feeds/rss/world
```

### News API Option

**NewsAPI.org** (https://newsapi.org) provides a unified API to search multiple news sources:
- Supports keyword filtering (e.g., "Iran protests")
- Returns structured JSON
- Free tier: 100 requests/day
- Covers: Reuters, BBC, Al Jazeera, CNN, and 80,000+ sources

---

## Tier 3: Human Rights Organizations

These organizations provide the most authoritative data on casualties, arrests, and human rights violations. They are essential sources but require web scraping.

### Primary Organizations

| Organization | Base | Focus | Website | Data Quality |
|--------------|------|-------|---------|--------------|
| **HRANA** | Washington, DC | On-ground network, arrest/casualty tracking | https://www.en-hrana.org | ⭐⭐⭐⭐⭐ |
| **Iran Human Rights (IHR)** | Oslo, Norway | Death toll, executions, political prisoners | https://iranhr.net | ⭐⭐⭐⭐⭐ |
| **Human Rights Watch** | New York | Policy reports, documentation | https://www.hrw.org/middle-east/north-africa/iran | ⭐⭐⭐⭐⭐ |
| **Amnesty International** | London | Prisoner advocacy, urgent actions | https://www.amnesty.org/en/location/middle-east-and-north-africa/iran/ | ⭐⭐⭐⭐⭐ |

### Citizen Journalism Collectives

| Organization | Platform | Focus | Notes |
|--------------|----------|-------|-------|
| **1500Tasvir** | Twitter/Instagram (@1500tasvir) | Protest videos, citizen reports | Founded after 2019 protests. Anonymous collective with members inside Iran. ~100K followers. |

### Organization Details

#### HRANA (Human Rights Activists News Agency)
- **Founded:** 2006
- **Structure:** Network of contacts inside Iran
- **Key Data:** Location-by-location protest tracking, arrest counts, casualty reports
- **Current Reporting (Jan 2026):**
  - 285+ protest locations across 92 cities
  - 2,000+ arrests documented
  - Detailed minor arrest data (ages 15-17)
- **Unique Value:** Only organization with systematic on-ground presence

#### Iran Human Rights (IHR)
- **Founded:** 2007
- **Director:** Mahmood Amiry-Moghaddam
- **Key Data:** Execution tracking, protest death toll
- **Current Reporting (Jan 2026):**
  - 45+ protesters killed (including 8 children)
  - Hundreds injured
  - Documents use of military-grade weapons against protesters

---

## Integration Options

### Option A: Telegram-Only (Minimal Changes)

Add channels directly to `config/channels.yaml`:

```yaml
channels:
  # Existing channels
  - iraborsnews
  - kaborsnews

  # Iran Protest Coverage - Persian
  - iranintltv       # Iran International (Persian) - ~895K subscribers
  - bbcpersian       # BBC Persian - ~766K subscribers
  - farsivoa         # VOA Farsi
  # - radiofarda     # Radio Farda - verify operational status first

  # Iran Protest Coverage - English
  - IranIntl_En      # Iran International English

  # Optional: State media (for official perspective)
  # - presstv        # Press TV (Iranian state media)
  # - Irna_en        # IRNA English (Iranian state media)
```

**Pros:**
- No code changes required
- Immediate implementation
- High-quality, frequently updated content

**Cons:**
- Limited to sources with Telegram channels
- Misses major Western outlets (Guardian, Reuters, etc.)
- No human rights organization data

### Option B: Add RSS/Web Scraping Module

Create new components to fetch from non-Telegram sources:

**New Files:**
- `src/rss_reader.py` - RSS feed fetcher using `feedparser`
- `src/web_scraper.py` - Website scraper for HRANA, IHR
- `config/rss_feeds.yaml` - RSS feed configuration

**Dependencies to Add:**
```toml
[project.dependencies]
feedparser = "^6.0.0"
beautifulsoup4 = "^4.12.0"
httpx = "^0.27.0"  # or use existing aiohttp
```

**Architecture:**
```
┌─────────────────┐     ┌─────────────────┐
│ TelegramReader  │     │   RSSReader     │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     │
              ┌──────▼──────┐
              │ Aggregator  │
              └──────┬──────┘
                     │
              ┌──────▼──────┐
              │ Summarizer  │
              └──────┬──────┘
                     │
              ┌──────▼──────┐
              │ TelegramBot │
              └─────────────┘
```

**Pros:**
- Comprehensive coverage from all source types
- Access to Western media and human rights data
- More robust news aggregation

**Cons:**
- Significant development effort
- RSS feeds may have delays vs Telegram
- Web scraping can break with site changes
- Rate limiting considerations

### Option C: NewsAPI Integration

Use NewsAPI.org as a single integration point for web sources:

**New File:**
- `src/news_api_reader.py`

**Configuration:**
```yaml
# config/news_api.yaml
api_key: ${NEWSAPI_KEY}
keywords:
  - "Iran protests"
  - "Iran demonstrations"
  - "Tehran protests"
sources:
  - reuters
  - bbc-news
  - al-jazeera-english
  - cnn
```

**Pros:**
- Single API for 80,000+ sources
- Structured data, no scraping needed
- Keyword filtering built-in

**Cons:**
- Free tier limited to 100 requests/day
- May not include all desired sources
- Adds external dependency

---

## Technical Considerations

### Telegram Channel Access

1. **Public vs Private Channels:** All listed channels are public and don't require membership to read
2. **Rate Limits:** Pyrogram handles Telegram rate limits automatically
3. **Message Volume:** Iran International and BBC Persian post frequently (50-100+ messages/day during major events)

### Content Considerations

1. **Language:** Most content is Persian; English channels available but less comprehensive
2. **Verification:** Citizen journalism content may need verification
3. **Bias:** Be aware of funding sources (US government for VOA/Radio Farda, unknown for Iran International)
4. **State Media:** Press TV and IRNA represent Iranian government perspective

### Legal/Ethical

1. **Terms of Service:** Ensure RSS/scraping complies with source ToS
2. **Attribution:** Credit sources in summaries
3. **Caching:** Respect cache headers and avoid excessive requests

---

## Sources

### News Coverage
- [Al Jazeera - Five things you need to know about protests in Iran](https://www.aljazeera.com/news/2026/1/2/five-things-you-need-to-know-about-protests-in-iran-2)
- [CNN - Iran protests: internet blackout as nationwide turmoil spreads](https://www.cnn.com/2026/01/08/middleeast/how-irans-protests-spread-intl)
- [NPR - Security forces clash with protesters in Iran's main market](https://www.npr.org/2026/01/07/g-s1-104862/protesters-iran)
- [PBS NewsHour - What to know about the intensifying protests](https://www.pbs.org/newshour/world/what-to-know-about-the-intensifying-protests-shaking-iran-and-putting-pressure-on-its-theocracy)

### Academic Research
- [News loopholing: Telegram news as portable alternative media](https://pmc.ncbi.nlm.nih.gov/articles/PMC8715841/) - Journal of Computational Social Science

### Human Rights Organizations
- [HRANA - Human Rights Activists News Agency](https://www.en-hrana.org/)
- [Human Rights Watch - Iran](https://www.hrw.org/news/2026/01/06/iranian-authorities-brutally-repressing-protests)

### Telegram Channels
- [Iran International Telegram](https://t.me/iranintltv)
- [BBC Persian Telegram](https://t.me/bbcpersian)
- [Radio Farda Telegram](https://t.me/radiofarda)
- [VOA Farsi Telegram](https://t.me/farsivoa)
- [Iran International English Telegram](https://t.me/IranIntl_En)

### Tools & APIs
- [NewsAPI.org](https://newsapi.org/)
- [TGStat Iran Telegram Directory](https://ir.tgstat.com/)
- [Feedspot Reuters RSS Feeds](https://rss.feedspot.com/reuters_rss_feeds/)
