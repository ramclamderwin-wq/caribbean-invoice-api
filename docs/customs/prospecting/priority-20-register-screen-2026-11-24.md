# Priority-20 prospect register screen — 24 November 2026

## Purpose and limits

This is a preliminary official-register screen of 20 Wave 1 / Priority A prospects from `prospects_100.csv`. It is **not approval to contact**. No messages were sent, no contact details were added, and the source CSV was not altered.

A register search result is recorded conservatively:
- **Listed / active entity** means the named entity appeared in the cited official register.
- **Possible name match** is not treated as identity confirmation.
- **No exact match located** means the name was not located in the public register search used; it does **not** prove the business is unregistered or unlicensed.
- A corporate registry entry is not proof of customs-broker authorisation.

## Official sources checked

- United States: [U.S. CBP Permitted Customs Brokers Listing](https://ace-accounts.cbp.gov/s/customs-broker-listing). CBP describes this as the way to check whether a broker is currently licensed and in active standing: [CBP guidance](https://www.help.cbp.gov/s/article/Article-1136?language=en_US).
- Canada: [CBSA list of licensed customs brokers](https://www.cbsa-asfc.gc.ca/services/cb-cd/cb-cd-eng.html).
- United Kingdom: [Companies House public register](https://find-and-update.company-information.service.gov.uk/). This verifies company-register details only; no UK customs-agent authorisation register match was established in this screen.
- Australia: [Australian Border Force brokerages list](https://www.abf.gov.au/licensing/brokers/brokerages). The page says its list was current as of 14 March 2025 and notes some brokers decline inclusion.

## Results

| Prospect ID | Prospect in source CSV | Country | Official-register screen | Result / next action |
|---|---|---|---|---|
| P001 | Advance Customs Brokers & Consulting LLC | United States | CBP permitted-broker listing | No exact match located in the public listing search. Do not mark licensed; confirm exact legal name and port with CBP. |
| P002 | Customs Brokerage Xpress, Inc. | United States | CBP permitted-broker listing | No exact match located in the public listing search. Confirm exact legal name and port with CBP. |
| P003 | Moving APT | United States | CBP permitted-broker listing | No exact match located. Its listing as a customs broker in a commercial directory is not enough to establish broker status. |
| P004 | Jet Import Brokers | United States | CBP permitted-broker listing | No exact match located. Confirm exact legal name and port with CBP. |
| P005 | Elyon Customs Broker | United States | CBP permitted-broker listing | No exact match located. Confirm exact legal name and port with CBP. |
| P014 | Welke Customs Brokers | Canada | CBSA licensed-broker list | **Listed** as “Welke Customs Brokers Ltd.” Website shown by CBSA: welke.com. Confirm legal entity and operating contact before outreach. |
| P015 | HOC (name as listed; verify full name) | Canada | CBSA licensed-broker list | No exact match located under “HOC”. Full legal name is missing; resolve identity before any contact. |
| P016 | General Customs Brokers | Canada | CBSA licensed-broker list | No exact match located under this name. Resolve exact legal name before any contact. |
| P018 | Courtney Agencies Ltd. | Canada | CBSA licensed-broker list | **Listed** as “Courtney Agencies Ltd.” Website shown by CBSA: courtney.ca. Confirm contact and relevance. |
| P019 | Pacific Customs Brokers (pcb.ca) | Canada | CBSA licensed-broker list | **Listed** as “Pacific Customs Brokers Ltd.” Website shown by CBSA: pcb.ca. Confirm exact legal entity and contact. |
| P024 | Supreme Freight Services Limited | United Kingdom | Companies House | **Active company record**: company no. 02006494; incorporated 3 April 1986; SIC 52290 (other transportation support activities). This is not proof of customs-agent authorisation. |
| P025 | Global Container Services | United Kingdom | Companies House | **Active company record** found as “Global Container Services Limited”, company no. 01730642; incorporated 9 June 1983; SIC 52290. Confirm this is the same business as the prospect entry; customs-agent authorisation not established. |
| P027 | Barrington Freight | United Kingdom | Companies House | **Active company record** found as “Barrington Freight Ltd”, company no. 06060302; incorporated 22 January 2007; SIC 50200. Confirm this is the same business; customs-agent authorisation not established. |
| P028 | KWL Logistics | United Kingdom | Companies House | No exact legal-entity match established in this screen. Obtain exact company name/number from the business website before proceeding. |
| P029 | Customs Clearance Agents UK - AAA | United Kingdom | Companies House | No exact legal-entity match established. Appears to be a trading-style description; obtain the legal entity name before proceeding. |
| P044 | Power Customs | Australia | Australian Border Force brokerages list | **Possible name match only**: ABF lists “Power Customs Services Pty. Ltd.” The prospect name is shorter and identity is not confirmed. Verify it is the same business before marking listed. |
| P045 | Cargoconnect | Australia | Australian Border Force brokerages list | No exact match located in the public list search. Confirm legal entity; note ABF says some brokers decline inclusion. |
| P046 | Bloomcorp | Australia | Australian Border Force brokerages list | No exact match located in the public list search. Confirm legal entity; note ABF says some brokers decline inclusion. |
| P047 | CFFWORLD Transport | Australia | Australian Border Force brokerages list | No exact match located in the public list search. Confirm legal entity; note ABF says some brokers decline inclusion. |
| P048 | International Cargo Express (ICE) | Australia | Australian Border Force brokerages list | **Listed under a likely legal-entity form**: “International Cargo Express Pty. Limited”. Confirm the prospect's website/legal footer matches this entity before treating it as the same business. |

## Screen summary

- 20 prospects screened across 4 countries (5 per country).
- Canada: 3 exact names appear on the CBSA licensed-broker list.
- United Kingdom: 3 active Companies House entities identified; customs-agent authorisation was not established by this company-register check.
- Australia: 1 likely legal-entity match and 1 possible name match on the ABF list; both require identity cross-check. The ABF list is dated 14 March 2025.
- United States: no exact name match was located in the public CBP listing search for these five candidates; this is not a definitive negative licence determination.
- **0 prospects are approved for contact by this screen.** The CSV's `owner_approval_to_contact` remains `no`.

## Recommended cleanup before batch 1

1. Keep the three Canadian CBSA-listed firms as the strongest register-confirmed names, subject to current website/contact validation.
2. Confirm the Australian legal-entity crosswalk for International Cargo Express and Power Customs Services before deciding whether they correspond to P048 and P044.
3. For the three UK entities, verify customs-clearance service on their current official websites and record the precise legal entity; Companies House status alone is not a customs licence.
4. Replace or repair ambiguous names (HOC, General Customs Brokers, AAA) and any US prospects that cannot be tied to a CBP listing.
5. Do not send outreach until the owner approves the batch and the legal/consent prerequisites in the pilot plan are satisfied.

## Source references

- CBP licensed-broker check guidance: https://www.help.cbp.gov/s/article/Article-1136?language=en_US
- CBP public listing: https://ace-accounts.cbp.gov/s/customs-broker-listing
- CBSA official licensed-broker list: https://www.cbsa-asfc.gc.ca/services/cb-cd/cb-cd-eng.html
- Supreme Freight Services Ltd, Companies House no. 02006494: https://find-and-update.company-information.service.gov.uk/company/02006494
- Global Container Services Ltd, Companies House no. 01730642: https://find-and-update.company-information.service.gov.uk/company/01730642
- Barrington Freight Ltd, Companies House no. 06060302: https://find-and-update.company-information.service.gov.uk/company/06060302
- Australian Border Force brokerages list: https://www.abf.gov.au/licensing/brokers/brokerages
