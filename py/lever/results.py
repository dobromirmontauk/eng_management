"""CSV output and summary table printing."""

import csv
from collections import defaultdict
from datetime import datetime

from grader import CRITERIA_KEYS, CRITERIA_HEADERS


class ResultWriter:
    """Writes candidate results to a CSV file, flushing after each row."""

    CSV_FIELDS = ["name", "opportunity_id", "posting"] + CRITERIA_KEYS + [
        "total", "result", "action", "input_tokens", "output_tokens",
        "input_cost", "output_cost", "total_cost", "reasoning"]

    def __init__(self):
        self.csv_path = f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self._file = open(self.csv_path, "w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=self.CSV_FIELDS)
        self._writer.writeheader()
        self._file.flush()
        self.results = []  # in-memory list for summary

    def write_skip(self, name: str, opp_id: str, action: str, reason: str,
                   posting: str = ""):
        self.results.append({
            "name": name, "score": 0, "scores": {}, "passed": None,
            "action": action, "reasoning": reason, "posting": posting,
        })
        self._writer.writerow({
            "name": name, "opportunity_id": opp_id, "posting": posting,
            "total": 0, "result": "N/A", "action": action, "reasoning": reason,
        })
        self._file.flush()

    def write_grade(self, name: str, opp_id: str, grade_result, passed: bool,
                    status: str, action: str, posting: str = ""):
        self.results.append({
            "name": name, "score": grade_result.score, "scores": grade_result.scores,
            "passed": passed, "action": action, "reasoning": grade_result.reasoning,
            "total_cost": grade_result.total_cost, "posting": posting,
        })
        csv_row = {
            "name": name, "opportunity_id": opp_id, "posting": posting,
            "total": grade_result.score, "result": status, "action": action,
            "input_tokens": grade_result.input_tokens,
            "output_tokens": grade_result.output_tokens,
            "input_cost": f"{grade_result.input_cost:.6f}",
            "output_cost": f"{grade_result.output_cost:.6f}",
            "total_cost": f"{grade_result.total_cost:.6f}",
            "reasoning": grade_result.reasoning,
        }
        csv_row.update({k: grade_result.scores.get(k, 0) for k in CRITERIA_KEYS})
        self._writer.writerow(csv_row)
        self._file.flush()

    def close(self):
        self._file.close()

    def print_summary(self):
        self.close()
        print(f"\nResults saved to {self.csv_path}\n")
        criteria_hdr = " ".join(f"{h:<5}" for h in CRITERIA_HEADERS)
        print("=" * 100)
        print("SUMMARY")
        print("=" * 100)
        print(f"{'Name':<25} {criteria_hdr} {'Total':<6} {'Result':<6} {'Action':<10}")
        print("-" * 100)
        for r in sorted(self.results, key=lambda r: r["score"], reverse=True):
            display_name = r["name"][:23] + ".." if len(r["name"]) > 25 else r["name"]
            if r["scores"]:
                scores_str = " ".join(f"{r['scores'].get(k, 0):<5}" for k in CRITERIA_KEYS)
            else:
                scores_str = " ".join(f"{'—':<5}" for _ in CRITERIA_KEYS)
            status = "PASS" if r["passed"] else ("FAIL" if r["passed"] is not None else "N/A")
            print(f"{display_name:<25} {scores_str} {r['score']:<6} {status:<6} {r['action']:<10}")

        passed_count = sum(1 for r in self.results if r["passed"] is True)
        failed_count = sum(1 for r in self.results if r["passed"] is False)
        skipped_count = sum(1 for r in self.results if r["passed"] is None)
        total_cost = sum(r.get("total_cost", 0) for r in self.results)
        print(f"\nTotal: {len(self.results)} | Passed: {passed_count} | Failed: {failed_count} | Skipped: {skipped_count} | Cost: ${total_cost:.4f}")

        # Per-posting breakdown
        by_posting = defaultdict(list)
        for r in self.results:
            by_posting[r.get("posting", "unknown")].append(r)

        if len(by_posting) > 1 or (len(by_posting) == 1 and list(by_posting.keys())[0]):
            print(f"\n{'=' * 100}")
            print("BY POSTING")
            print(f"{'=' * 100}")
            print(f"{'Posting':<45} {'Total':<7} {'Pass':<7} {'Fail':<7} {'Arch%':<7} {'Adv%':<7} {'Cost':<10}")
            print("-" * 100)
            for posting, rows in sorted(by_posting.items()):
                display = posting[:43] + ".." if len(posting) > 45 else (posting or "unknown")
                n = len(rows)
                p = sum(1 for r in rows if r["passed"] is True)
                f = sum(1 for r in rows if r["passed"] is False)
                archived = sum(1 for r in rows if r["action"] == "archived")
                advanced = sum(1 for r in rows if r["action"] == "advanced")
                cost = sum(r.get("total_cost", 0) for r in rows)
                arch_pct = f"{archived/n*100:.0f}%" if n else "—"
                adv_pct = f"{advanced/n*100:.0f}%" if n else "—"
                print(f"{display:<45} {n:<7} {p:<7} {f:<7} {arch_pct:<7} {adv_pct:<7} ${cost:.4f}")
