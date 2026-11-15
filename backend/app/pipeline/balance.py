"""Pure helpers (no database, network or API keys) that keep the evidence map from showing only agreeable sources.

Three places in the pipeline used to favour agreement without anyone intending it:
  1. search queries were all phrased like the question, so critical papers were never retrieved;
  2. every cut-off (candidate cap, top-N by similarity, top-N claim pairs by similarity) rewards papers/claims
     that look like the question or like each other, and near-paraphrases are the most similar pairs of all;
  3. gaps lived only in a separate tab, never on the map.
"""
import re

CONFLICT_LABELS = ("genuine_contradiction", "apparent_contradiction")
TENSION_LABELS = CONFLICT_LABELS + ("unresolved",)
_GAP_PREFIX = "not found in the papers examined:"


def reserve_quota(items, is_priority, cap, share):
    """Pick up to `cap` items, keeping the input order, but guarantee that `share` of the slots go to priority
    items (when that many exist). Used so papers found by critical-angle searches are not crowded out by the
    papers that most resemble the question. Deterministic."""
    items = list(items)
    if cap is None or len(items) <= cap:
        return items
    want = min(int(round(cap * max(0.0, min(1.0, share)))), sum(1 for x in items if is_priority(x)))
    chosen, used = set(), 0
    for i, x in enumerate(items):
        if used >= want:
            break
        if is_priority(x):
            chosen.add(i)
            used += 1
    for i in range(len(items)):
        if len(chosen) >= cap:
            break
        chosen.add(i)
    return [x for i, x in enumerate(items) if i in chosen]


def fallback_critical_queries(base_queries, limit=3):
    """Deterministic critical-angle queries used when the model does not return any."""
    base = next((b.strip() for b in base_queries if b and b.strip()), "")
    if not base:
        return []
    suffixes = ("no significant effect null results", "limitations criticism", "failed replication contradictory findings",
                "adverse effects negative outcomes")
    return [f"{base} {s}" for s in suffixes][:limit]


def clean_queries(values, limit):
    seen, out = set(), []
    if isinstance(values, str):
        values = [values]
    for v in values or []:
        v = (v or "").strip() if isinstance(v, str) else ""
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out[:limit]


def gap_angle(sector, n_sectors):
    """Centre of the wedge that sub-question `sector` owns (matches layout.assign_angles)."""
    n = max(1, int(n_sectors or 1))
    return ((int(sector) + 0.5) * 360.0 / n) % 360


def gap_sector(description, sub_questions):
    """Older workspaces have no gap metadata: recover the sub-question index from the flag text."""
    d = (description or "").lower()
    if d.startswith(_GAP_PREFIX):
        d = d[len(_GAP_PREFIX):]
    best, best_len = None, 0
    for i, sq in enumerate(sub_questions or []):
        s = (sq or "").strip().lower()
        if s and s in d and len(s) > best_len:
            best, best_len = i, len(s)
    return best


def has_dissent(claims, conflict_edge_exists):
    """Do the claims on one topic contain anything other than uniform agreement?
    claims: dicts with direction/significance. Heuristic: a null/mixed/non-significant result, opposite directions,
    or a verified conflict edge between them."""
    dirs = {c.get("direction") for c in claims if c.get("direction") in ("increase", "decrease")}
    if len(dirs) > 1 or conflict_edge_exists:
        return True
    return any(c.get("direction") in ("no_effect", "mixed") or c.get("significance") == "not_significant" for c in claims)


def summarize_edges(rows):
    """rows: dicts with label, pa, pb (paper ids). -> (claim-level counts, papers touched by each conflict kind)."""
    counts, touched = {}, {}
    for r in rows:
        lab = r["label"]
        counts[lab] = counts.get(lab, 0) + 1
        if lab in TENSION_LABELS:
            for pid in (str(r["pa"]), str(r["pb"])):
                d = touched.setdefault(pid, {})
                d[lab] = d.get(lab, 0) + 1
    return counts, touched


def paper_conflict_level(touched_for_paper):
    """'genuine' > 'apparent' > 'open' (unresolved only) > None."""
    t = touched_for_paper or {}
    if t.get("genuine_contradiction"):
        return "genuine"
    if t.get("apparent_contradiction"):
        return "apparent"
    if t.get("unresolved"):
        return "open"
    return None


def short(s, n=90):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"
