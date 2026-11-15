"""Relevance scoring helpers and radial layout. Relevance is a navigation aid, NOT a truth score."""
import math

R_MIN = 0.14   # normalized radius of the most relevant paper (the question node sits at 0)
R_MAX = 1.0

W_COSINE, W_OUTCOME, W_CENTRAL, W_EVIDENCE = 0.45, 0.20, 0.20, 0.15


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def radius(rel, rmin=R_MIN, rmax=R_MAX):
    """Closer to the center = more relevant."""
    return rmin + (1 - clamp(rel)) * (rmax - rmin)


def minmax(values):
    if not values:
        return []
    lo, hi = min(values), max(values)
    return [0.5 for _ in values] if hi - lo < 1e-9 else [(v - lo) / (hi - lo) for v in values]


def design_score(design):
    d = (design or "").lower()
    for kw, s in (("meta-analy", 1.0), ("systematic review", 1.0), ("randomi", 0.9), ("rct", 0.9),
                  ("trial", 0.75), ("cohort", 0.6), ("quasi", 0.6), ("cross-sectional", 0.4),
                  ("survey", 0.35), ("case", 0.25), ("review", 0.4), ("simulation", 0.3)):
        if kw in d:
            return s
    return 0.3 if d else 0.2


def evidence_strength(design, sample_n, text_level):
    n = min(1.0, math.log10(max(sample_n or 1, 1)) / 3)     # 1000+ participants = 1.0
    t = 1.0 if text_level == "full" else 0.5
    return round(0.5 * design_score(design) + 0.3 * n + 0.2 * t, 4)


def relevance(cos_n, outcome_match, centrality_n, evidence):
    return clamp(W_COSINE * cos_n + W_OUTCOME * outcome_match + W_CENTRAL * centrality_n + W_EVIDENCE * evidence)


def assign_angles(groups, n_sectors):
    """groups: {sector: [paper_id sorted by relevance desc]} -> {paper_id: angle in degrees}.
    Each sub-question owns an equal angular wedge; papers are spread evenly inside it."""
    n_sectors = max(1, n_sectors)
    width = 360.0 / n_sectors
    out = {}
    for s, ids in groups.items():
        m = len(ids)
        for k, pid in enumerate(ids):
            out[pid] = (s * width + (k + 0.5) * width / m) % 360
    return out


def child_angles(parent_angle, count, step=11.0):
    """Second-ring papers fan out around their parent's angle."""
    return [(parent_angle + (k - (count - 1) / 2) * step) % 360 for k in range(count)]
