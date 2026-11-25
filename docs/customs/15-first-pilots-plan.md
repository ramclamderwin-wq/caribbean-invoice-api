# 15. Customer acquisition plan: the first 3–5 paying pilots

**Goal:** 3–5 paying concierge pilots (US$249 each, proposed) from customs brokers and
freight forwarders in at least 3 countries, within about 8 weeks of the first outreach.

**Status:** no messages sent and no customers yet. All funnel rates below are
**assumptions to measure**, not predictions.

## Assets ready (built 2026-11-25)

| Asset | Where |
|---|---|
| 100 researched prospects (unverified), 16 countries | `prospecting/prospects_100.csv` |
| Outreach templates in English and Spanish (drafts) | `templates/outreach_en.md`, `templates/outreach_es.md` |
| Interview questionnaire | `09-interview-questionnaire.md` |
| Synthetic demo and a 10-minute demo script | `/demo` |
| One-command pilot tool | `python -m app.pilot_run` |
| Tracking sheets, feedback process, gate report | `tracking/`, `scripts/validation_gates.py` |
| Pilot agreement and consent form (drafts for counsel) | `legal/` |

## Funnel (assumptions to replace with real numbers)

```
100 researched  ->  ~70 verified (register + website)
                ->  ~60 contacted in 3 batches of 20       (reply rate assumed 15-25%)
                ->  ~10-15 discovery calls  (+ 5-10 from the founder's network and referrals)
                ->  ~8 send consented sample invoices      (free demonstration on their documents)
                ->  ~5 see results and receive a pilot offer
                ->  3-5 paid pilots                          (target)
```

If the reply rate is below 10% after batch 1, change the message or the segment before
sending batch 2. Don't just send more.

## Week-by-week plan

| Week | Owner actions | Claude / prep actions | Approval checkpoint |
|---|---|---|---|
| 0 (now) | Review templates and drafts. Choose sender name and address. Engage counsel for the legal drafts | Done: list, templates, demo, tools, trackers | **Approve templates and batch 1** |
| 1 | Verify priority-A prospects (register + website). Pick batch 1: 20 prospects, no more than 40% from one country, brokers and forwarders. Send after approval. Contact 5–10 network leads | Help verify, personalise drafts per prospect (for your approval) | Approve each batch |
| 2 | Discovery calls. Ask for 3–5 sample invoices with the signed consent form. Send batch 2 (adjusted if needed) | Run samples with `pilot_run` (rules engine); prepare the results pack per prospect | Consent form approved by counsel before receiving real invoices |
| 3 | More calls. Send results to prospects ("here are your invoices as structured data"). Batch 3 | Benchmark on consented samples; propose AI test if rules results are weak | **Approve AI testing** (if needed): about US$10, API key |
| 4 | Pilot offers to the 5–8 warmest prospects | Final pilot agreement (after counsel); onboarding checklist | **Approve pilot price and terms** |
| 5–8 | Run pilots: daily processing, review, delivery; weekly calls | Process, log errors and minutes, weekly summaries | Approve any change in scope or price |

## The offer

1. **Free:** "We'll process 3–5 of your real commercial invoices (with consent) and show
   you the structured result." This costs us minutes, not money, with the rules engine.
2. **Paid pilot:**
   - 4 weeks, up to 150 invoices;
   - same-day turnaround;
   - every invoice checked by our team;
   - their spreadsheet layout;
   - **US$249**, credited if they subscribe (proposed; owner to approve).
3. **After the pilot:** subscription plans (hypotheses in `12-pricing-and-naming.md`),
   with a founding-customer discount in exchange for a testimonial and feedback.

## Handling objections (honest answers only)

| Objection | Answer |
|---|---|
| "Our volume is small." | "The pilot is capped at 150 invoices. If it doesn't save you time at your volume, you'll know in 4 weeks for $249." |
| "AI makes mistakes." | "That's why every value is checked against the invoice, both by us during the pilot and then by your team. We flag problems instead of hiding them." Show `demo-004`. |
| "Confidentiality." | Consent form and agreement: deletion within 30 days, no sharing, AI provider only if they opt in. |
| "We already have software." | "Which part still takes manual keying?" If nothing does, thank them, ask for a referral and move on. |
| "Can it classify or calculate duties?" | "No. We prepare clean invoice data; classification stays with your licensed staff." |

## Metrics to track weekly (from `tracking/`)

Contacts sent, replies, calls held (by country and segment), samples received with
consent, results packs sent, pilot offers, pilots paid, and the gate report output.

## Risks and how we'll notice

| Risk | Early signal | Response |
|---|---|---|
| Message doesn't resonate | Reply rate under 10% after 20 contacts | Rewrite around their words from calls; try another segment or country |
| Pain is real but elsewhere | Calls rank keying low | Pivot within customs (e.g. document chasing); re-run calls |
| Rules engine too weak on real invoices | Many errors on samples | Request AI test approval; compare with `compare_engines.py` |
| Legal delay | Counsel review takes weeks | Start counsel now; use only demo invoices until the consent form is approved |

## What needs the owner

1. Approve the outreach templates, sender identity, and each batch before sending.
2. Engage a lawyer to finalise the pilot agreement and consent form (and a Spanish
   version).
3. Approve the pilot price and terms before any offer.
4. Approve AI testing (about US$10) if rules results on consented samples aren't good
   enough.
5. Verify prospects on official registers before contact.
