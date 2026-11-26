# Prospect research list

`prospects_100.csv` lists **100 real companies in 16 countries**, compiled 2026-11-25 from
public business directories, association directories and search results.

**Rules:**
- **Not contacted, and not approved for contact.** Nothing is sent without owner approval
  (`owner_approval_to_contact` = no).
- **Unverified.** Directory listings are self-reported. Before any outreach:
  1. confirm the company exists and does customs or forwarding work;
  2. check its licence on the official register below;
  3. find a business contact address on the company's own website.
- **No personal data is stored.** There are no individual names, personal emails or
  phone numbers. Add business contact routes only when you are ready to reach out, and
  follow local marketing and privacy law (e.g. CAN-SPAM, CASL, UK/EU GDPR and PECR).
- Some entries are larger firms (priority C), kept as benchmarks or later targets.

## Composition

| Segment | Count | Role |
|---|---|---|
| customs_broker | 55 | Primary |
| broker_forwarder (forwarders that also clear customs) | 26 | Primary |
| freight_forwarder | 9 | Primary |
| logistics_3pl | 6 | Additional |
| importer | 4 | Additional (see note) |

**Countries:**
- Mexico 14
- United States 12 (+2 Canada/US)
- Ireland 10
- Canada 9
- New Zealand 9
- Australia 7
- United Arab Emirates 7
- United Kingdom 6
- Netherlands 4
- South Africa 4
- Chile 4
- Belize 3
- Jamaica 3
- Colombia 2
- Singapore 2
- Trinidad and Tobago 2

**Priority:**
- **A:** small or independent broker or broker-forwarder (best first targets).
- **B:** forwarders, 3PLs and importers.
- **C:** larger firms.

**Wave:** follows `../03-first-market.md`.

## Official registers for verification (and for finding more prospects)

| Country | Register / directory |
|---|---|
| United States | CBP licensed broker information: https://www.cbp.gov/trade/programs-administration/customs-brokers ; NCBFAA member directory |
| Canada | CBSA list of licensed customs brokers: https://www.cbsa-asfc.gc.ca/services/cb-cd/menu-eng.html ; CSCB broker search: https://cscb.ca/customs-broker-search |
| United Kingdom | HMRC list of customs agents and fast parcel operators: https://www.gov.uk/guidance/list-of-customs-agents-and-fast-parcel-operators |
| Australia | Licensed customs brokers (Australian Border Force); licence information: https://ablis.business.gov.au/service/ag/customs-brokers-licence/38 |
| New Zealand | CBAFF business directory: https://cbaff.org.nz |
| Singapore | Singapore Customs (declaring agents): https://www.customs.gov.sg |
| Mexico | SAT/ANAM padrón de agentes aduanales |
| Colombia | DIAN agencias de aduanas: https://www.dian.gov.co/aduanas/opecomeexterior/Paginas/agenciaaduanera-.aspx |
| Chile | Servicio Nacional de Aduanas, agentes de aduana: https://www.aduana.cl |
| Jamaica | Jamaica Customs Agency approved list of customs brokers: https://jca.gov.jm/wp-content/uploads/2025/11/approved-list-of-customs-brokers-2024-2025.x61397.pdf |
| Belize | BELTRAIDE customs broker list: https://beltraide.bz/serviceproviders-custombrokers.html |
| Ireland | Revenue Commissioners (customs agents); Golden Pages listings |
| Netherlands | KvK (Chamber of Commerce) register |
| UAE | Dubai Customs / JAFZA registrations |
| South Africa | SARS registered clearing agents |

## Importers: a different method

Importers are hard to identify from directories, so only 4 are listed. Better sources for
the importer track, once the broker and forwarder track is running:

- **Referrals from brokers and forwarders.** Ask pilot customers which importers struggle
  with documents.
- **Trade associations** for importing industries (hardware, food, auto parts).
- **Import-record data services** (paid; requires owner approval).
- **Search content and self-serve sign-ups** once the website exists.

## How to use

1. Verify the priority-A rows first (register check plus company website). Update
   `licence_or_register_checked`.
2. Choose 20–30 prospects across at least 3 countries for the first outreach batch,
   with no more than 40% from one country.
3. Get owner approval (`owner_approval_to_contact` = yes) and send messages from
   `../templates/`.
4. Log every contact and interview in `../tracking/interviews.csv`.
