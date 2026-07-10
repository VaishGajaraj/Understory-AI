# Governance and use norms

**Version 0.1.0** — versioned like the methodology, because norms that aren't written down erode.

## What this project is for

Understory detects **physical disturbance of terrain and vegetation** — logging roads, mining pits, clearings — to support forest protection: NGO and indigenous territorial monitoring, environmental enforcement, carbon-market integrity, and EUDR compliance. It is a civilian project. Defense applications are out of scope for this repository, its partnerships, and its communications.

## Norms, in force from the first release

1. **Terrain, not people.** The method detects ground-surface change. The project does not build, accept, or optimize features whose purpose is locating or tracking people. The 12-day revisit makes this an infrastructure-and-pattern instrument by physics, and the project keeps it that way by policy.
2. **Conservative by default.** Shipped alert feeds are thresholded high: a short list a partner can act on beats a comprehensive layer that costs them wasted field trips. A false alarm is not free — it is someone's boat trip.
3. **Honest uncertainty, always.** Every detection carries a calibrated confidence; every benchmark reports calibration error alongside precision. Overconfidence is treated as a defect of the same severity as a missed detection.
4. **Sensitive locations.** Where publishing an exact location could endanger field verifiers, expose community monitors' patrol patterns, or tip off actors under active enforcement, coordinates are coarsened or embargoed by agreement with the affected partner (`location_precision: coarsened` in the label schema). Partners decide; the project defaults to caution.
5. **Consent for case studies.** No partner's verification work, territory, or operational detail is published without their explicit consent.
6. **Negative results get published.** If the benchmark fails its kill criteria, the failure analysis ships anyway. The project's credibility is its honesty, not its numbers.

## Label library governance

The labeled event library is the project's most consequential asset and has its own review standard — see [packages/understory-labels/CONTRIBUTING.md](../packages/understory-labels/CONTRIBUTING.md). Editorial decisions (what counts as confirmed, what evidence suffices) are documented in public issues even while the maintainer count is one.

## Decision-making

Single maintainer, decisions in public GitHub issues. This document changes by pull request with the reasoning in the PR description, and the version bumps.
