"""Prompt builders. The non-negotiable rules live here, in one place."""
import json

LABELS = ["supports_compatible", "genuine_contradiction", "apparent_contradiction",
          "related_not_comparable", "unresolved"]

EXTRACT_SYSTEM = (
    "You extract testable scientific findings from a paper for an evidence-mapping tool. "
    "The 'quote' must be copied VERBATIM from the supplied text (one or two sentences, no paraphrase, no ellipses). "
    "Never guess: use null or 'not_reported' for anything the paper does not state. Return JSON only."
)

VERIFY_SYSTEM = (
    "You judge how two scientific claims relate. Compare ONLY the supplied fields and quotes. "
    "A non-significant result does NOT refute a significant one. Never infer that 'not significant' means 'no effect'. "
    "If populations, durations, measures or methods differ in a way that could explain different results, "
    "use apparent_contradiction, not genuine_contradiction. If comparability is unclear, use unresolved. "
    "Abstract-only evidence must lower your confidence. Return JSON only."
)

CHAT_SYSTEM = (
    "You answer questions about a body of research using ONLY the numbered claims provided. "
    "Cite claims inline like [C3]. State what is uncertain or missing. Never say a paper is simply right or wrong; "
    "explain what each result does and does not show. If the claims do not answer the question, say so."
)


def understand(question):
    return (
        "A researcher asks: " + json.dumps(question) + "\n"
        "Return JSON with keys: population (string), intervention (string), outcome (string), comparison (string), "
        "outcome_families (list of 2-5 short strings, e.g. 'test scores', 'retention'), "
        "search_queries (3-5 scholarly search queries), "
        "sub_questions (3-6 distinct sub-questions that together cover the question)."
    )


def extract(p, text, level):
    meta = f"Title: {p['title']}\nYear: {p['year']}\nText level: {level} ({'full text' if level == 'full' else 'abstract only'})"
    return (
        meta + "\n\nExtract 3 to 6 distinct, testable findings (results, not background). Return JSON: "
        '{"claims":[{"claim_text":"one normalized sentence","intervention":"","outcome":"","outcome_family":"",'
        '"direction":"increase|decrease|no_effect|mixed","significance":"significant|not_significant|not_reported",'
        '"effect_size":"as reported or not_reported","population":"","sample_n":integer or null,"design":"",'
        '"duration":"","measure":"","limitations":"as stated by the authors, or empty","quote":"VERBATIM","location":"page or section"}]}'
        "\n\nPAPER TEXT:\n" + text
    )


def _fields(c):
    keys = ("claim_text", "intervention", "outcome", "direction", "significance", "effect_size",
            "population", "sample_n", "design", "duration", "measure", "limitations")
    return {k: c.get(k) for k in keys}


def verify(a, b, comp, pa, pb):
    return (
        "Claim A (" + f"{a['p_title']}, {a['p_year']}; text: {a['text_level']}" + "):\n" + json.dumps(_fields(a), default=str) +
        "\nQuote A: " + json.dumps(a["quote"]) + "\nSurrounding passage A: " + pa +
        "\n\nClaim B (" + f"{b['p_title']}, {b['p_year']}; text: {b['text_level']}" + "):\n" + json.dumps(_fields(b), default=str) +
        "\nQuote B: " + json.dumps(b["quote"]) + "\nSurrounding passage B: " + pb +
        "\n\nComparability checklist (null = unknown): " + json.dumps(comp) +
        "\n\nReturn JSON: {\"label\": one of " + json.dumps(LABELS) + ", "
        "\"factors\": list from [population, duration, measure, method, sample_size, statistical_power, other] that plausibly explain any difference, "
        "\"confidence\": number 0-1, \"reason\": \"2-3 sentences, plain language, mention which conditions differ\"}"
    )


def selfcheck(a, b, first):
    return (
        "A first pass labeled these claims genuine_contradiction: " + json.dumps(first, default=str) +
        "\nClaim A: " + json.dumps(_fields(a), default=str) + "\nClaim B: " + json.dumps(_fields(b), default=str) +
        "\nTry to explain the disagreement by differences in population, duration, measure, method, or power. "
        'Return JSON: {"confirm": true|false, "downgrade_to": "apparent_contradiction"|"unresolved"|null, "note": "one sentence"}. '
        "Confirm only if the studies are truly comparable on all of those."
    )


def chat(question, ctx, edges):
    return (
        "QUESTION: " + question + "\n\nCLAIMS:\n" + ctx + "\n\nRELATIONSHIPS BETWEEN CLAIMS:\n" + (edges or "(none)") +
        '\n\nReturn JSON: {"answer": "text with inline [C#] citations", "uncertainty": "what is unresolved or missing"}'
    )


def impact_summary(title, items):
    return (
        "A new paper titled " + json.dumps(title) + " was added to an evidence map. Its comparisons with earlier findings:\n" +
        json.dumps(items, default=str)[:12000] +
        '\n\nWrite a 3-5 sentence plain-language summary of which earlier findings it strengthens, challenges, qualifies, '
        'or leaves unanswered. Do not say any paper is right or wrong. Return JSON: {"summary": "..."}'
    )
