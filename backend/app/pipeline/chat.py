"""Stage 11: GraphRAG chat. Retrieve claims, follow claim edges, fetch quotes, answer with citations."""
from ..clients import gemini
from ..db import ex, q, vec
from . import prompts
from .stages import CLAIM_Q


def answer(ws, question):
    e = gemini.embed([question])[0]
    top = [str(r["id"]) for r in q(
        "SELECT c.id FROM claims c JOIN papers p ON p.id=c.paper_id WHERE c.workspace_id=%s AND p.kept AND c.embedding IS NOT NULL "
        "ORDER BY c.embedding <=> %s::vector LIMIT 8", (ws, vec(e)))]
    if not top:
        return {"answer": "There are no extracted claims in this workspace yet.", "uncertainty": "", "citations": []}
    ids = set(top)
    hop = q("SELECT claim_a, claim_b FROM claim_edges WHERE workspace_id=%s AND (claim_a = ANY(%s::uuid[]) OR claim_b = ANY(%s::uuid[]))",
            (ws, top, top))
    for r in hop:                                          # one hop along claim edges
        ids.update((str(r["claim_a"]), str(r["claim_b"])))
    ordered = top + [i for i in ids if i not in top]
    ordered = ordered[:20]
    rows = {str(r["id"]): r for r in q(CLAIM_Q, (ordered,))}
    label = {cid: f"C{i + 1}" for i, cid in enumerate(ordered) if cid in rows}
    ctx = "\n".join(f"[{label[c]}] ({rows[c]['p_title']}, {rows[c]['p_year']}; {rows[c]['text_level']}) {rows[c]['claim_text']} "
                    f"| population: {rows[c]['population']} | duration: {rows[c]['duration']} | measure: {rows[c]['measure']} "
                    f"| quote: \"{rows[c]['quote']}\"" for c in label)
    edges = q("SELECT claim_a, claim_b, label, reason FROM claim_edges WHERE workspace_id=%s AND claim_a = ANY(%s::uuid[]) AND claim_b = ANY(%s::uuid[])",
              (ws, list(label), list(label)))
    etxt = "\n".join(f"{label[str(x['claim_a'])]} vs {label[str(x['claim_b'])]}: {x['label']}. {x['reason']}" for x in edges)
    d = gemini.generate_json(prompts.chat(question, ctx, etxt), system=prompts.CHAT_SYSTEM)
    text = d.get("answer", "")
    by_label = {v: k for k, v in label.items()}
    used = [l for l in by_label if f"[{l}]" in text]
    cites = [{"label": l, "claim_id": by_label[l], "paper": rows[by_label[l]]["p_title"], "paper_id": str(rows[by_label[l]]["paper_id"]),
              "quote": rows[by_label[l]]["quote"], "location": rows[by_label[l]]["location"]} for l in used]
    ex("INSERT INTO chat_messages (workspace_id, role, content) VALUES (%s,'user',%s)", (ws, question))
    ex("INSERT INTO chat_messages (workspace_id, role, content, cited_claims) VALUES (%s,'assistant',%s,%s::uuid[])",
       (ws, text, [c["claim_id"] for c in cites]))
    return {"answer": text, "uncertainty": d.get("uncertainty", ""), "citations": cites}
