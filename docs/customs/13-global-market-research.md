# 13. Global market research: regions, segments, willingness to pay

**Owner direction (2026-11-25):** Quillvora is a global company. Customs brokers and
importers are the first segment to investigate, not a geographic boundary. This document
compares regions and segments to choose where to start acquiring customers.

Market-size reports disagree widely because they define markets differently. Ranges are
shown, and all sources are listed at the end. **No customer evidence exists yet.**

## 1. Market size signals (facts)

| Signal | Value | Source |
|---|---|---|
| Global customs brokerage services market (2025) | about US$26–42 billion, growing ~4–8% a year; Asia-Pacific the largest region (~42% in one report) | Research and Markets, 360iResearch, Emergen, Dataintelo |
| Freight forwarding software market (2025) | estimates from ~US$0.5B to ~US$8.5B (definitions differ); growth ~9–12% a year; SME adoption rising via subscriptions | GMI, Emergen, LP Information, Research and Markets |
| Intelligent document processing, transport & logistics (2025) | about US$221M, ~35% annual growth (single source) | Grand View Research |
| Freight forwarding firms represented by FIATA | about 40,000 companies; WCA network 13,000+ member offices | FIATA / secondary sources, WCAworld |

## 2. Regions (facts and implications)

| Region | Evidence | Opportunity | Main challenge |
|---|---|---|---|
| **North America** | US: about 11,000–14,454 licensed brokers (CBP); **239,231 identified importers** (Census, 2024 prelim.). Canada: about 275–300 major brokers (CBSA testimony); CBSA publishes a licensed broker list. Mexico: about 820–860 licensed *agentes aduanales* (ANAM / legislative sources) | Largest willingness to pay; public broker lists; English (US/Canada) and Spanish (Mexico) | Most competition (AI entry tools integrated with ACE software) |
| **Europe & UK** | UK: 80% of 2025 customs declarations were filed by intermediaries; 4,880 declarants in 2025 (HMRC); HMRC publishes a list of customs agents. EU: 70% of trading enterprises are import-only (Eurostat, 2023) | Post-Brexit UK declarations, many intermediaries; multilingual invoices suit an AI engine | GDPR (DPA, possible EU data residency); many languages; national customs systems |
| **Asia-Pacific** | Largest share of customs brokerage revenue (~42%, one report); Australia and NZ have licensed broker regimes (counts not found) | Huge trade volumes; Australia/NZ/Singapore are English-speaking | Language diversity; local incumbents; price sensitivity in some markets |
| **Latin America** | Mexico ~830 *agentes aduanales*; Spanish already supported | Spanish-language advantage; underserved by US-centric tools (assumption) | Local systems; payment methods; Portuguese for Brazil |
| **Caribbean & other ASYCUDA countries** | ASYCUDA in about 102 countries and territories (UNCTAD); brokers required for larger imports in e.g. Jamaica | Fewer specialised tools (assumption); founder network (assumption) | Small markets each; one module among many, not the platform's basis |
| **Middle East & Africa** | Not researched in depth this round | Growing trade hubs (UAE, Saudi Arabia, Kenya, Nigeria) | Research needed |

## 3. Segments (evidence plus assumptions)

Scores run from 1 (low) to 5 (high); the total is the sum of the four scores (maximum 20). **Scores are hypotheses to be revised with interview data.**

| Segment | Job involving commercial invoices | Addressable count (evidence) | WTP | Reach | Competition (5 = least) | Product fit today | Total |
|---|---|---|---|---|---|---|---|
| **Customs brokers** | Key invoice data into declarations daily | US ~11–14k licensed; MX ~830; CA ~275–300 major; UK intermediaries file 80% | 5 | 4 (public lists, associations) | 2 (US crowded) | 5 | **16** |
| **Small/mid freight forwarders** (many offer customs) | Process invoices, packing lists, B/Ls for bookings and customs | ~40,000 firms in FIATA's network; WCA 13k offices | 4 | 4 (networks, directories) | 3 (enterprise TMS dominate, SMEs underserved) | 4 | **15** |
| **Mid-size importers** (many SKUs, in-house compliance) | Check supplier invoices, prepare data for broker, reconcile POs | US 239k identified importers (most small); EU 70% of traders import-only | 3 | 2 (diffuse; needs SEO/self-serve) | 3 | 4 | **12** |
| **Software vendors / partners** (forwarding, brokerage, ERP) | Embed extraction via API | Dozens to hundreds of vendors | 4 (per deal) | 2 (long sales cycles) | 2 | 3 (needs proven accuracy) | **11** (later) |
| **3PL / logistics companies** | Multi-document processing at volume | Overlaps forwarders | 4 | 2 (enterprise sales) | 2 | 3 | **11** |
| **Exporters** | *Create* commercial invoices (generation, not extraction) | Large | 2 | 3 | 3 | 1 (different product) | **9** |
| **General international businesses / AP teams** | Accounts payable invoice capture | Very large | 2 | 3 | 1 (Dext, Hubdoc, AutoEntry, ERPs) | 3 | **9** |

## 4. Conclusions (recommendations)

1. **Primary initial segment: "trade-document processors"**, meaning customs brokers plus
   small and mid-size freight forwarders that handle customs. They have the highest
   willingness to pay, a daily use case, public lists that make them reachable, and the
   best fit with the current product.
2. **Secondary:** mid-size importers through self-serve and search, once the product is
   self-serve.
3. **Later:**
   - software partners via the API, after accuracy is proven;
   - 3PLs via enterprise sales;
   - exporters only if a document-generation product is added, which would be a
     separate decision.
4. **Not a target:** general accounts-payable invoice capture. It's crowded and the
   product doesn't stand out there.
5. **Regions:** start where acquisition is cheapest and the language is already supported:
   - English-speaking North America, the UK, Australia/NZ and Singapore;
   - Spanish-speaking Mexico and Latin America;
   - the Caribbean, through the founder's network where it helps.
   Interview across several of these at once (see `03-first-market.md`). Expand into
   Europe and Asia as the AI engine's language coverage is proven and privacy terms are
   ready.

## 5. Evidence still missing

- Licensed broker counts for Australia, NZ, Singapore, Brazil and EU member states.
- Typical invoices per month and minutes per invoice by segment and region (interviews).
- What forwarders and brokers currently pay for document tools (interviews; vendor quotes).
- Share of commercial invoices by language and quality (from collected samples).

## Sources for this document

- Customs brokerage market size: https://www.researchandmarkets.com/report/customs-broker , https://www.giiresearch.com/report/ires1866964-customs-brokerage-services-market-by-service-type.html , https://emergenresearch.com/industry-report/customs-brokerage-market , https://dataintelo.com/report/global-customs-brokerage-and-coordination-services-market
- Freight forwarding software market: https://www.gminsights.com/industry-analysis/freight-forwarding-software-market , https://www.emergenresearch.com/jp/industry-report/freight-forwarding-software-market , https://www.researchandmarkets.com/reports/6067950/freight-forwarding-software-global-strategic
- Logistics IDP: https://www.grandviewresearch.com/horizon/statistics/intelligent-document-processing-market/end-use/transportation-logistics/global
- FIATA: https://en.wikipedia.org/wiki/International_Federation_of_Freight_Forwarders_Associations , https://fiata.org/n/fiata-grows-in-size-serving-an-ever-increasing-number ; WCAworld: https://fiata.org/n/wcaworld-joins-fiata-as-newest-platinum-partner/
- US importers (Census, 2024 preliminary): https://www.census.gov/foreign-trade/Press-Release/edb/2024prelimprofile.pdf ; US brokers: https://www.cbp.gov/node/77830 , https://www.trade.gov/customs-brokers-and-freight-forwarders
- Canada: https://www.cbsa-asfc.gc.ca/services/cb-cd/menu-eng.html , https://openparliament.ca/committees/international-trade/44-1/97/ted-gallivan-98/only
- Mexico: https://forbes.com.mx/?p=1285599 , https://espacioimasd.unach.mx/index.php/Inicio/article/download/390/1517/2255
- UK: https://www.gov.uk/government/statistics/customs-declarants-and-declaration-volumes-for-international-trade-in-2025/customs-declarants-and-declaration-volumes-for-international-trade-in-2025-commentary , list of customs agents: https://www.gov.uk/guidance/list-of-customs-agents-and-fast-parcel-operators
- EU: https://ec.europa.eu/eurostat/en/web/products-eurostat-news/w/ddn-20250625-1
- ASYCUDA: https://unctad.org/node/14541
