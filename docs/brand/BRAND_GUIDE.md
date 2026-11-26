# RAMVORA brand guide

**RAMVORA** is the public brand of Divine Group Holdings LLC's technology business. The
first product is the **RAMVORA Invoice Intelligence API**. The brand is built to extend to
future products.

- **Tagline:** *Built for what's next.*
- **Personality:** trustworthy, intelligent, modern, ambitious.
- **Positioning:** premium, powerful, innovative, professional, international.

> The legal entity is unchanged: **Divine Group Holdings LLC**. Using "RAMVORA" publicly
> as a trade name may require a trade-name (DBA) registration, and a trademark clearance
> search is recommended before launch (see the end of this guide).

## Logo

| Asset | File | Use |
|---|---|---|
| Wordmark, ink | `ramvora-wordmark.svg` | Light backgrounds (documents, invoices, email body) |
| Wordmark, white | `ramvora-wordmark-white.svg` | Dark backgrounds (dashboard header, slides) |
| Monogram | `ramvora-mark.svg` | App icon, favicon, social avatar |

- **Construction:**
  - a geometric monoline wordmark drawn as vector paths, so it looks identical
    everywhere and doesn't depend on a font being installed;
  - every letter sits on exactly the same cap height and baseline, with flat tops and
    flat stroke ends, so pointed letters (A, M, V) are no taller or shorter than the
    others. Only the O overshoots very slightly, as round letters must to look the
    same size;
  - both **A**s are drawn as open **Λ** forms (no crossbar), echoing the **V**. This is
    the brand's signature detail;
  - the monogram is a white **R** on an ink tile, with a small accent square marking
    "what's next".
- **Clear space:** at least the height of the letter R on every side.
- **Minimum size:** wordmark 80 px wide on screen (20 mm in print); monogram 16 px.
- **Don't:**
  - stretch, rotate or outline the logo;
  - add shadows or gradients;
  - recolour it outside the palette;
  - retype it in another font;
  - put it on busy photos;
  - add a crossbar to the A.
- In running text, write the name in capitals: **RAMVORA**. The product is "RAMVORA
  Invoice Intelligence API".

## Colour

| Role | Name | Hex | Use |
|---|---|---|---|
| Primary | Ink | `#0B1220` | Headers, logo, primary text on light |
| Text | Slate | `#1B2533` | Body text |
| Secondary text | Steel | `#5E6B7D` | Captions, muted text |
| Surface | Mist | `#F4F6F9` | Page background |
| Divider | Line | `#E3E7EE` | Borders, rules |
| Accent | Signal Blue | `#2F5BFF` | Primary actions, links, focus (use sparingly) |
| Accent, hover | Deep Signal | `#1E40D8` | Hover and pressed states |
| Highlight | Aurum | `#C8A55A` | Small premium highlights (eyebrow labels); never large areas |

Body text on Mist or White meets WCAG AA contrast. Don't put Signal Blue text on Ink.

## Typography

- **Primary:** Inter where available, falling back to the platform UI fonts (SF Pro,
  Segoe UI, Roboto, Helvetica, Arial). The dashboard uses this system stack because its
  security policy loads no external fonts.
- **Headings:** bold (650–700), slightly tight letter-spacing (−0.01 to −0.02 em).
- **Eyebrow labels:** 12 px uppercase, wide letter-spacing (0.22 em), in Aurum.
- **Code and data** (API keys, JSON): monospace (`ui-monospace`, SF Mono, Menlo, Consolas).

## Voice

- Clear, precise and calm. Confident without hype.
- Say what the product does and doesn't do. Human review is part of the promise.
- **Never claim accuracy percentages** until measured, and never imply automatic
  classification, duty calculation or customs filing.
- Write in international English, and keep sentences short for non-native readers.
  Spanish materials use the same tone.

**Examples:**
- **Do:** "Structured invoice data, ready for review."
- **Don't:** "99% accurate AI that does your customs for you."

## Imagery

Minimal and typographic. Prefer product screenshots, clean data tables and simple
diagrams. **Avoid** generic AI imagery (glowing brains, robots), cartoons, stock
handshakes and busy gradients.

## Where the brand appears (implemented)

- **Dashboard** (`/dashboard`): ink header with the white wordmark, tagline, Aurum eyebrow,
  Signal Blue primary buttons, monogram favicon.
- **API documentation** (`/docs`): title "RAMVORA Invoice Intelligence API", with the
  tagline in the description.
- **API root** (`/`): name, version and tagline. `/health` reports `ramvora-api`.
- **Emails:** branded layout (ink header with a text wordmark, footer with product name and
  tagline). Inline styles only, with no images or external resources, so they work in all
  email programs.
- **Documentation and templates:** README, operations guides, strategy documents,
  outreach templates.

## Before going fully public (owner actions)

1. **Trademark clearance:** search USPTO, WIPO Global Brand Database and key markets.
   A preliminary web search found no "RAMVORA" mark, but similar marks exist (e.g.
   "RAMORA" for software services in the US). Get a professional opinion.
2. **Trade-name (DBA) registration** for Divine Group Holdings LLC trading as RAMVORA.
3. **Domains and handles:** secure the main domains and social handles.
4. **Professional logo review (optional):** this wordmark is a production-ready starting
   point. A designer can refine spacing and letterforms, and supply print files.
