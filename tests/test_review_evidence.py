import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import edition_run, patch_state_dbs, review_evidence


class ReviewEvidenceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.edition = "2026-11-29_0730"
        self.gold_daily = "gold/daily/2026-11-29_0730_早报_黄金深度研报.md"
        self.eq_daily = "equity/daily/archive/2026-11/2026-11-27_1800_a_share_r2.md"
        self.us_daily = "equity/daily/2026-11-29_0730_us_stock.md"
        self.verified_source = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates"
        self.excerpt = "美国财政部在官方利率表上公布当日收益率。"
        self.inference = "若利率继续上行，久期风险可能扩大。"
        paths = {
            market: f"daily/2026-11-27_1800_{market}_r2.md" for market in review_evidence.MARKETS
        }
        paths["a_share"] = self.eq_daily.removeprefix("equity/")
        paths["us_stock"] = self.us_daily.removeprefix("equity/")
        for path in (*review_evidence.FIXED_PATHS, self.gold_daily, *(f"equity/{p}" for p in paths.values())):
            self.write(path, "Fixture content\n")
        for path in (self.gold_daily, self.us_daily):
            self.write(path, f"{self.excerpt} [利率表]({self.verified_source})\n{self.inference}\n")
        self.write(review_evidence.STATE_PATH, json.dumps({
            "edition_id": self.edition, "markets": {
                market: {"latest_daily": path} for market, path in paths.items()
            },
        }))
        self.metrics = "gold/daily/rsi_metrics.json"
        self.patch = "gold/daily/_rsi_patch.json"
        self.dimensions = tuple(f"dimension_{index}" for index in range(6))
        self.write(self.metrics, json.dumps({"score_dimensions": self.dimensions, "runs": []}))

    def write(self, rel, content):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def receipt(self, candidate):
        checks = {
            check: {"evidence": f"Reviewed {check}", "files": [self.gold_daily]}
            for check in review_evidence.CHECK_IDS
        }
        checks["cross_track"]["files"] = ["gold/data_snapshot.json", review_evidence.STATE_PATH]
        checks["primary_sources"].update({
            "files": [self.gold_daily, self.us_daily],
            "source_urls": [self.verified_source],
            "claims": [{
                "file": path, "excerpt": excerpt, "kind": kind, "source_file": path,
                "source_url": self.verified_source, "verification": "核对发布日期与对应交易日。",
            } for path in (self.gold_daily, self.us_daily) for kind, excerpt in (
                ("fact", self.excerpt), ("inference", self.inference),
            )],
        })
        return {
            "run_id": self.edition,
            "scores": {dimension: 5 for dimension in self.dimensions},
            "total_score": 30,
            "max_score": 30,
            "review_closure": {
                "reviewer_completed": True,
                "findings": [],
                "candidate_sha256": candidate["candidate_sha256"],
                "checks": checks,
            },
        }

    def inspect(self):
        return patch_state_dbs.inspect_state_dbs(self.root, "review-candidate")

    def validate(self, closure, candidate):
        review_evidence.validate_receipt(closure, candidate, "Gold", read=lambda path: (self.root / path).read_bytes())

    def test_stale_receipt_fails_and_re_review_preserves_prior_result(self):
        first = self.receipt(self.inspect())
        self.write(self.patch, json.dumps(first))
        patch_state_dbs.append_gold_rsi(self.root, keep_patch=True)
        original_bytes = (self.root / self.metrics).read_bytes()
        patch_state_dbs.append_gold_rsi(self.root, keep_patch=True)
        self.assertEqual((self.root / self.metrics).read_bytes(), original_bytes)

        self.write(self.eq_daily, "Corrected close for the carried-forward market\n")
        with self.assertRaisesRegex(ValueError, "candidate digest differs"):
            patch_state_dbs.append_gold_rsi(self.root)
        self.assertEqual((self.root / self.metrics).read_bytes(), original_bytes)

        second = self.receipt(self.inspect())
        self.write(self.patch, json.dumps(second))
        patch_state_dbs.append_gold_rsi(self.root)
        [current] = json.loads((self.root / self.metrics).read_bytes())["runs"]
        self.assertEqual(current["review_closure"], second["review_closure"])
        self.assertEqual(current["superseded_reviews"], [first])

    def test_partial_and_out_of_candidate_check_evidence_are_rejected(self):
        candidate = self.inspect()
        closure = self.receipt(candidate)["review_closure"]
        del closure["checks"]["primary_sources"]
        with self.assertRaisesRegex(ValueError, "exactly these five checks"):
            self.validate(closure, candidate)

        closure = self.receipt(candidate)["review_closure"]
        closure["checks"]["cross_track"]["files"] = ["not-reviewed.md"]
        with self.assertRaisesRegex(ValueError, "candidate file paths"):
            self.validate(closure, candidate)

        for url in (
            "https://example.invalid/notice", "https://financial.example.com/notice",
            "https://research.local/notice", "https://home.treasury.gov:bad/notice",
            "https://home.treasury.gov/",
            "https://www..treasury.gov/notice", "https://-www.treasury.gov/notice",
            "https://home.treasury.gov/%JH",
        ):
            with self.subTest(url=url):
                closure = self.receipt(candidate)["review_closure"]
                closure["checks"]["primary_sources"]["source_urls"] = [url]
                with self.assertRaisesRegex(ValueError, "public HTTPS source URLs"):
                    self.validate(closure, candidate)

    def test_claims_must_identify_real_excerpt_and_attached_source_for_each_new_manuscript(self):
        candidate = self.inspect()
        self.assertEqual(candidate["current_manuscripts"], [self.gold_daily, self.us_daily])
        for bad_key, value, message in (
            ("excerpt", "猜测下周一定上涨。", "excerpt does not match"),
            ("verification", "ok", "substantive excerpt and verification note"),
            ("kind", "confirmed_forecast", "requires kind"),
            ("source_url", self.verified_source.removesuffix("-rates"), "does not match a citation"),
        ):
            with self.subTest(bad_key=bad_key):
                closure = self.receipt(candidate)["review_closure"]
                sources = closure["checks"]["primary_sources"]
                sources["claims"][0][bad_key] = value
                if bad_key == "source_url":
                    sources["source_urls"].append(value)
                with self.assertRaisesRegex(ValueError, message):
                    self.validate(closure, candidate)

        closure = self.receipt(candidate)["review_closure"]
        closure["checks"]["primary_sources"]["claims"].pop()
        with self.assertRaisesRegex(ValueError, "an observed fact or calculation and an inference"):
            self.validate(closure, candidate)
        closure["checks"]["primary_sources"]["claims"].pop()
        with self.assertRaisesRegex(ValueError, "missing claims for current manuscripts"):
            self.validate(closure, candidate)

        self.write(self.gold_daily, f"<!-- {self.excerpt} {self.verified_source} -->\n")
        candidate = self.inspect()
        with self.assertRaisesRegex(ValueError, "excerpt does not match"):
            self.validate(self.receipt(candidate)["review_closure"], candidate)

        self.write(self.gold_daily, f"```text\n{self.excerpt}\n{self.verified_source}\n```\n")
        candidate = self.inspect()
        with self.assertRaisesRegex(ValueError, "excerpt does not match"):
            self.validate(self.receipt(candidate)["review_closure"], candidate)

    def test_publication_review_gate_reads_the_exact_commit_and_rejects_changed_candidate(self):
        receipt = self.receipt(self.inspect())
        for path in (self.metrics, "equity/state/rsi_metrics.json"):
            self.write(path, json.dumps({"runs": [receipt]}))
        self.write("gold/daily/scratch/" + Path(self.gold_daily).name, "Draft outside the publication tree\n")
        edition_run.check_edition_reviews(self.edition, root=self.root)

        def git(*args):
            return subprocess.check_output(
                ["git", "-c", "user.name=Review Test", "-c", "user.email=review@example.invalid", *args],
                cwd=self.root, text=True,
            ).strip()

        git("init", "-q")
        git("add", "gold", "equity")
        git("commit", "-qm", "Reviewed content")
        accepted = git("rev-parse", "HEAD")
        self.write(self.gold_daily, "Later correction，复核后再提交。\n")
        git("add", self.gold_daily)
        git("commit", "-qm", "Changed candidate")
        rejected = git("rev-parse", "HEAD")

        with self.assertRaisesRegex(ValueError, "candidate digest differs"):
            edition_run.check_edition_reviews(self.edition, root=self.root)
        with patch.object(edition_run, "ROOT", self.root):
            edition_run.check_edition_reviews(self.edition, sha=accepted)
            with self.assertRaisesRegex(ValueError, "candidate digest differs"):
                edition_run.check_edition_reviews(self.edition, sha=rejected)


if __name__ == "__main__":
    unittest.main()
