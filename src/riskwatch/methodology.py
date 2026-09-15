"""Accumulated analytical methodology for the RiskWatch root scenario.

This module is deliberately deterministic: it records the analytical method used by
RiskWatch rather than allowing each model call to invent its own research procedure.
"""

SCENARIO_ID = "prisoner_mobilization"

# Research order: primary state documents first; independent reporting is used to
# corroborate and to reveal implementation that may not appear in central documents.
SOURCE_TIERS = {
    "T1_PRIMARY": (
        "publication.pravo.gov.ru", "kremlin.ru", "government.ru", "mil.ru",
        "fsin.gov.ru", "minjust.gov.ru", "duma.gov.ru", "council.gov.ru",
        "zakupki.gov.ru", "gov.ru", "epp.genproc.gov.ru"
    ),
    "T2_OFFICIAL_REGIONAL": (
        "regional executive authorities", "regional government", "regional governor",
        "regional FSIN/UFСIN", "regional prosecutor", "regional procurement"
    ),
    "T3_INDEPENDENT": (
        "reuters.com", "interfax.ru", "rbc.ru", "kommersant.ru", "tass.ru", "ria.ru",
        "zona.media"
    ),
    "T4_OPEN_SOCIAL": ("t.me", "vk.com", "youtube.com"),
}

# Source rules: one source family is not independent corroboration merely because
# the story appears on many sites. A primary document remains stronger than its
# subsequent retellings.
SOURCE_RULES = (
    "Prefer the original document over a report quoting it.",
    "Treat wire copies, syndicated stories, screenshots and identical reposts as one evidence family.",
    "Two genuinely independent domains are stronger than many copies of one source.",
    "Official confirmation and independent reporting answer different questions: the former establishes state action; the latter can corroborate implementation or reveal discrepancies.",
    "Anonymous or unsourced claims are leads, not confirmation.",
    "A social-media post can trigger a search for the underlying document or event, but cannot by itself establish the root scenario.",
)

# The chain is a hypothesis to test, not an assumed inevitability.
STAGES = (
    (0, "baseline", "No scenario-specific actionable signal."),
    (1, "legal_policy_signal", "Law, decree, order, public instruction or authoritative policy change relevant to the target population."),
    (2, "administrative_preparation", "Concrete preparation: instructions, lists, eligibility procedures, interagency coordination, reporting or assigned responsibility."),
    (3, "organization_logistics", "Operational preparation: staffing, procurement, facilities, medical/selection arrangements, transport or coordinated local implementation."),
    (4, "operational_implementation", "Observable implementation affecting the target population, before the final outcome is independently confirmed."),
    (5, "root_scenario", "Directly confirmed mobilization/recruitment/contracting/transfer into military service of men from correctional institutions or equivalent places of deprivation of liberty."),
)

POSITIVE_INDICATORS = (
    "explicit federal or regional decision naming prisoners/convicts/correctional institutions as a target population",
    "official instructions to FSIN/UFСIN or correctional institutions concerning military service",
    "creation or activation of selection/medical/registration procedures specifically for prisoners",
    "lists, reporting forms, quotas, eligibility criteria or interagency orders tied to the target population",
    "documented coordination between FSIN, Ministry of Defence, military commissariats or other responsible bodies concerning prisoners",
    "procurement, facilities, staffing, transport or medical preparation that is specifically and credibly linked to the target population",
    "independent regional confirmations showing the same operational measure in different jurisdictions",
    "actual transfer, contracting, enlistment, training or service of identified prisoners, confirmed by a reliable source",
)

NEGATIVE_INDICATORS = (
    "explicit official exclusion of prisoners/correctional institutions from the relevant procedure",
    "formal cancellation, suspension or withdrawal of an earlier target-specific instruction",
    "absence of an expected implementation step after a sufficiently long and observable lead time",
    "credible evidence that reported activity concerns ordinary civilian conscription or another population instead of prisoners",
    "credible evidence that an apparent preparation was unrelated to military recruitment",
    "a single sensational report contradicted by primary documents and independent evidence",
)

EXPECTED_TRANSITIONS = {
    1: ("administrative instruction", "responsible body", "procedure/eligibility", "reporting or lists"),
    2: ("local implementation", "personnel/medical/selection", "coordination", "logistics"),
    3: ("observable operational action", "target population contact", "movement/training/contracting"),
    4: ("direct outcome confirmation",),
}

SEARCH_SEQUENCE = (
    "1. Define the exact root scenario and deadline/horizon.",
    "2. Search primary federal legal/policy sources for direct decisions and enabling rules.",
    "3. Search FSIN/UFСIN and regional government sources for implementation instructions.",
    "4. Search procurement, staffing, medical, transport and other administrative traces for target-specific preparation.",
    "5. Search independent reporting for corroboration, contradictions and facts absent from official summaries.",
    "6. Search regional sources in parallel to detect geographic concentration or independent convergence.",
    "7. Trace every strong claim back to the original document/event and collapse reposts into one family.",
    "8. Look deliberately for disconfirming evidence and missing expected transitions.",
    "9. Reconstruct the temporal/causal chain and distinguish observed facts from inference.",
    "10. Forecast the next observable step separately from the probability of the root scenario.",
)

HEURISTICS = (
    "Do not equate discussion, legislation about a general category, or media volume with implementation.",
    "A target-specific administrative action is more informative than a general political statement.",
    "A chain of different action types is stronger than repeated evidence of the same type.",
    "Geographically independent implementation is stronger than multiple reports from one region.",
    "The closer an observed action is to the target population and the operational endpoint, the greater its evidentiary relevance.",
    "Absence of a normally necessary next step is negative evidence only when the step should be observable within the tested horizon.",
    "Do not infer hidden preparation merely from silence; hidden preparation requires indirect, independently converging traces.",
    "Contradictory primary evidence must be surfaced rather than averaged away.",
    "Probability is not a score of how alarming the evidence looks. It is a forecast that must later be checked against the realized outcome.",
    "Multiple model calls from the same provider are not independent evidence.",
)

OUTPUT_RULES = (
    "Always answer the root scenario as YES, NO or UNKNOWN.",
    "Keep raw model probability separate from empirically calibrated probability.",
    "Keep next-step probability separate from root-scenario probability.",
    "Never call an uncalibrated model number a measured probability.",
    "If evidence is insufficient, prefer UNKNOWN over a forced directional answer.",
    "Every material conclusion must identify the evidence events supporting it.",
)

METHODOLOGY_TEXT = "\n".join((
    "ACCUMULATED RISKWATCH ANALYTICAL METHODOLOGY",
    "ROOT SCENARIO: prisoner_mobilization",
    "SOURCE TIERS:", *[f"{k}: {', '.join(v)}" for k, v in SOURCE_TIERS.items()],
    "SOURCE RULES:", *[f"- {x}" for x in SOURCE_RULES],
    "STAGES:", *[f"{n}: {name} — {desc}" for n, name, desc in STAGES],
    "POSITIVE INDICATORS:", *[f"+ {x}" for x in POSITIVE_INDICATORS],
    "NEGATIVE INDICATORS:", *[f"- {x}" for x in NEGATIVE_INDICATORS],
    "SEARCH SEQUENCE:", *SEARCH_SEQUENCE,
    "HEURISTICS:", *[f"- {x}" for x in HEURISTICS],
    "OUTPUT RULES:", *[f"- {x}" for x in OUTPUT_RULES],
))
