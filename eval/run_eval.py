"""Score the verifier against hand-labeled claim pairs.

Usage:  python eval/run_eval.py WORKSPACE_ID [eval/gold_set.csv]
gold_set.csv columns: quote_a, quote_b, expected_label  (a distinctive substring of each claim's quote is enough;
expected_label is one of supports_compatible, genuine_contradiction, apparent_contradiction, related_not_comparable, unresolved)
Run from the backend/ folder's environment (needs DATABASE_URL), e.g.  cd backend && python ../eval/run_eval.py <id>
"""
import csv
import sys

from app.db import q


def main():
    ws = sys.argv[1]
    path = sys.argv[2] if len(sys.argv) > 2 else "../eval/gold_set.csv"
    edges = q("SELECT e.label, ca.quote AS qa, cb.quote AS qb FROM claim_edges e JOIN claims ca ON ca.id=e.claim_a "
              "JOIN claims cb ON cb.id=e.claim_b WHERE e.workspace_id=%s", (ws,))
    total = hit = missing = 0
    for row in csv.DictReader(open(path, newline="")):
        a, b = row["quote_a"].strip().lower(), row["quote_b"].strip().lower()
        found = next((e for e in edges if (a in e["qa"].lower() and b in e["qb"].lower()) or (a in e["qb"].lower() and b in e["qa"].lower())), None)
        total += 1
        if not found:
            missing += 1
            print(f"NOT FOUND  {a[:50]} | {b[:50]}")
        elif found["label"] == row["expected_label"].strip():
            hit += 1
        else:
            print(f"MISMATCH   expected {row['expected_label']}, got {found['label']}: {a[:50]} | {b[:50]}")
    print(f"\nMatched {hit} of {total} hand-labeled pairs ({missing} pairs were never matched or verified).")


if __name__ == "__main__":
    main()
