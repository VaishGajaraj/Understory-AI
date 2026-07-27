# Understory as a company: government demand and the dual-use question

**Status: research memo, 2026-07-27. Not a decision, and not a plan of record.**
Companion to [PRODUCTIZATION.md](PRODUCTIZATION.md), which concluded there is no
commercial buyer for degradation alerts today and that the civilian money is
philanthropic. This asks a narrower question: **does US government demand change
that**, and what would a dual-use path actually involve?

It contains things that conflict with [GOVERNANCE.md](GOVERNANCE.md). Those
conflicts are named explicitly rather than smoothed over. Nothing here has been
acted on.

## The short version

Government demand upgrades the picture from *"philanthropy or nothing"* to
*"philanthropy, plus equity-free civilian R&D money available now, plus a real
but slow defense analytics market that buys from incumbents and purpose-built
sensors."*

It does **not** create an 18-month revenue business for one or two people.

Three findings drive that:

1. **Someone does now pay for change-detection analytics.** NGA's Luno A
   ($290M ceiling, 10 vendors) and Luno B ($200M ceiling, 13 vendors) buy
   unclassified commercial GEOINT analytics, and in February 2026 a **$5M task
   order for "global change detection"** went to Vantor under Luno B. That
   answers a question PRODUCTIZATION.md left open — but the buyers are
   incumbents already on the vehicle.
2. **The physics is already militarized and already funded.** SAR coherent
   change detection has been a US military technique for two decades (Sandia's
   lineage; IED-emplacement detection fielded since 2009). DoD SBIR money is
   *currently* funding a company to build "L-band SAR for sub-canopy tactical
   ISR… wide-area change detection of vehicle and equipment movements and
   weapons installations." That is this project's method statement with the
   nouns changed.
3. **The calibrated-data gate opened on 2026-07-20** — a week before this memo.
   The re-validation PRODUCTIZATION.md calls mandatory is now reachable, which
   makes benchmark-first cheaper than it was when that document was written.

## Does government buy this?

### Civilian — compatible with governance as written

GOVERNANCE.md excludes *defense*, not *government*. These channels raise no
conflict at all:

| Source | Amount | Shape |
|---|---|---|
| **NASA ROSES / NISAR DART** | grant | Funds the science directly — the most on-mission federal money available to this project |
| NASA SBIR | $225K Phase I → $850K Phase II | Equity-free |
| NSF SBIR | $305K → $1.25M | Equity-free |
| USDA SBIR (NIFA) | ~$175K Phase I | Equity-free |

**SBIR is open again.** Authorization lapsed 2025-09-30 — the longest disruption
in the program's 43-year history — and was reauthorized through **FY2031** in
March/April 2026 (~$6B). The reauthorization added mandatory national-security
vetting of applicants' foreign ties, which now touches even civilian eligibility
diligence.

The realistic ceiling: **1–2 Phase I wins over 18 months = $150K–$625K**, at
**15–25% win rates** (10–15% for first-time applicants). That is runway, not a
business. Phase III/production is the 2–4 year mark.

**What is *not* a channel:** NASA's CSDA buys data from constellation
*operators*, not third-party analytics. USDA Forest Service money is shaped as
labor-services support to GTAC/FIA — an $80M remote-sensing BPA went to an
incumbent geospatial services firm — which a solo analytics startup enters only
by subcontracting. **USAID is gone**: it ceased implementing foreign assistance
on 2025-07-01, so any tropical-monitoring-for-development thesis that assumed it
is dead. State-level money is wildfire-shaped, not degradation-shaped.

### Defense and intelligence — where the value actually is

| Vehicle | Buys | Size |
|---|---|---|
| NGA **Luno A / B** | Unclassified commercial GEOINT **analytics** | $290M / $200M ceilings; $5M task orders |
| NGA **BIG-ST BAA** | Research white papers | Phased R&D; **closes 2026-12-14** |
| NRO **EOCL** | Imagery **data from operators** | ~$6B program (Maxar $3.2B, BlackSky ~$1B) |
| **DIU** CSO | Dual-use prototypes (OTs) | ~120 days to award |
| **AFWERX** SBIR | Company-defined dual-use R&D | $50–150K → $1.25M → STRATFI $3–15M |
| **In-Q-Tel** | Equity + work program | $500K–$3M/deal |

Two structural facts matter more than the numbers. **NRO buys data from
satellite operators** — an analytics-only company has nothing to sell it. **NGA
is the analytics buyer**, and its Luno vendors are primes and established EO
firms; a new entrant's path is subcontracting or SBIR/BIG-ST, not a direct award.

**A defense customer would not buy NISAR alerts.** Twelve-day cadence, no
tasking, and an acquisition plan an adversary can read. The commercial SAR fleet
under NRO contract (Capella, ICEYE, Umbra) is X-band, which does not penetrate
canopy — which is precisely why DoD is funding purpose-built L-band sensors
through SBIR rather than buying the capability commercially.

So what is defense-relevant here is **the method and its measured error
statistics over vegetated terrain** — exactly what the benchmark produces —
portable to airborne FOPEN or a future L-band source. Which leads to the
uncomfortable structural point below.

## The tensions, stated plainly

1. **GOVERNANCE.md forbids this under this name.** It declares defense out of
   scope for "this repository, its partnerships, and its communications." Any
   defense pursuit therefore *requires* a separate entity; doing it as Understory
   violates the project's own versioned norms.
2. **"Terrain, not people" is a policy overlay on symmetric physics.** The funded
   military uses of this exact technique — vehicle tracks, equipment movement,
   IED emplacement — are activity monitoring. The repo's physics argument (a
   12-day revisit makes this an infrastructure instrument, not a surveillance
   one) protects *NISAR-based products*. It does not protect the method.
3. **The dual-use transfer has already happened, by license.** Apache-2.0 and
   CC-BY 4.0 mean defense actors can use the code and labels today without
   asking. Governance controls the founder's *participation and endorsement* —
   nothing else. Any "our data won't be used for X" policy is unenforceable.
4. **The open-config convention open-sources the know-how.** "Thresholds live in
   benchmark config YAML, never hardcoded" is good science and it publishes the
   exact tuning a company would otherwise own. A deliberate decision about what
   stays open post-incorporation is needed *before* it matters, and that decision
   will be visible to the community.
5. **"Conservative by default" is what IC analytics buyers want.** High
   precision, low false-alarm — the engineering is compatible, only the identity
   is not. That makes drift *easier*, not harder, which is worth naming as a risk
   rather than a convenience.
6. **A PBC charter would convert a later pivot into a fiduciary problem.** If the
   stated public benefit is civilian-forest-shaped, defense work later is a
   charter question, not just a comms one. Choose the benefit statement knowing
   that.
7. **At headcount 1, "separate identity" is sequencing, not structure.** Entity
   paperwork is cheap and the precedents are unambiguous (Planet Labs Federal,
   ICEYE US, Descartes Labs Government). But two credible identities need two
   people or two calendar phases — the founder's time, not the org chart, is the
   real contamination channel. PRODUCTIZATION.md already found that 0.3–0.5 FTE
   of operations forecloses the benchmark; a defense BD motion costs at least
   that.

## Is the credibility fear justified?

**Partly — and it is concentrated, not diffuse.**

No documented case surfaced of an EO company losing conservation partnerships
over defense work. The counter-evidence is strong: Planet grew defense and
intelligence revenue >50% year-over-year in FY2026 while remaining the
conservation community's default imagery source. ICEYE put a satellite under
Ukrainian military control in 2022 and still runs civilian flood and insurance
lines. Umbra runs defense revenue alongside a CC-BY open-data program
researchers use happily. And NICFI's end was a **procurement accident** — the
re-procurement was canceled in September 2025 after a losing bidder's legal
challenge was upheld — not a boycott.

But the general case understates the risk for *this project's* named partners.
GOVERNANCE.md's sensitive-location norms exist because indigenous territorial
monitoring and community patrols can be endangered by location data. A WRI or a
university collaborator will not blink at NGA-adjacent work. A Pará territorial-
monitoring NGO reasonably might. The risk is concentrated in exactly the partner
class the project was designed to serve.

## What the evidence supports

**Finish and publish the calibrated-data benchmark; pursue civilian ROSES/SBIR
in parallel; defer the defense decision until the benchmark exists.**

The reasoning: civilian SBIR and ROSES pay for the benchmark work itself,
equity-free, without a product, and without touching a single line of
GOVERNANCE.md. That is genuinely new since PRODUCTIZATION.md and it is available
now. Deferring the defense question until publication means the result is
protected, the method is proven or killed by its own criteria, and — if it
passed — the landscape above shows exactly which doors exist and a separate
entity can be formed for the purpose, with real sensitivity numbers to justify
it. That is what the repo's own scope guard anticipated.

**The strongest argument against deferring:** NGA's BIG-ST BAA closes
2026-12-14, and Descartes Labs is the cautionary tale in the other direction —
~$100M raised, $17M revenue, multiple eight-figure government contracts, and a
fire-sale in August 2022. Government-first does not de-risk a business.

**One adjacent-pivot precedent worth keeping in view:** Overstory started as
forest monitoring, found its paying customer in utility vegetation management,
and has raised ~$75M. The company that exists is rarely the benchmark that
started it.

## Regulatory reality (verified)

- **Published open-source software is not subject to the EAR** (15 CFR
  §§734.3(b), 734.7). While the repo stays public, the current codebase is
  outside export control.
- **The exception to watch:** BIS's 2020 rule controlling software that
  automates geospatial imagery analysis *by training deep convolutional neural
  networks* (ECCN 0Y521). The v0 detector is deliberately non-ML statistics and
  sits outside it; a proprietary ML v1 would need a classification review. The
  current status of that control was not verified — check with export counsel
  before any proprietary ML release.
- **NOAA CRSRA licensing does not apply.** 15 CFR Part 960 governs *operators of
  remote-sensing space systems*, not analytics over someone else's public data.
- **A facility clearance cannot be obtained speculatively.** An FCL requires
  sponsorship by an agency or cleared prime under a contract that needs access;
  3–6 months typical, routinely 180+ days. Early entry points (AFWERX open
  topics, DIU CSOs, BIG-ST white papers, Luno) are unclassified.
- **Foreign investment complicates everything downstream.** FOCI mitigation adds
  months before any clearance, and the 2026 SBIR reauthorization now screens all
  applicants' foreign ties.

## What could not be verified

Recorded because a memo that hides its own uncertainty is worse than none.

- Enactment date of the SBIR reauthorization (both chambers passed March 2026;
  secondary sources report signature ~2026-04-14). Confirm at congress.gov
  before relying on it in a proposal.
- Current status of the 2020 ECCN 0Y521 geospatial-AI software control.
- Whether/when NGA will re-open Luno A/B to new vendors — the on-ramp is the
  whole question for a new entrant.
- Planet's EOCL contract value (never disclosed).
- Dollar values of the USFS FIA BPA suite; current FIA appropriation.
- Typical DIU OT award size (timelines verified, values are not centrally
  published).
- Whether defense SBIR Phase I awards ever require clearances (program design
  says no; not verified against a solicitation clause).
- Tribal forestry (BIA/638), MCC and State ESF forest procurement — not
  researched.
- USGS/NOAA analytic purchasing for forests — nothing found; reported as a gap,
  not a negative finding.
- Any documented case of a conservation partner severing ties with an EO company
  over defense work — none found. The concentrated-risk argument above is
  inference, not evidence.
