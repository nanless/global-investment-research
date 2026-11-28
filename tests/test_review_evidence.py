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
        self.calculation = "同口径的前后两个收益率相差 7 个基点。"
        self.inference = "若利率继续上行，久期风险可能扩大。"
        self.policy_briefs = [
            {"id": "rates", "headline": '报告使用 "上一交易日" 的同口径收益率。',
             "summary": "晚班报告只使用美国财政部公布的已完成交易日利率。",
             "source_url": self.verified_source, "home_featured": True},
            {"id": "fed", "headline": "纽约联储公布上一工作日的有效联邦基金利率。",
             "summary": "有效联邦基金利率按上一工作日的成交样本计算并由纽约联储发布。",
             "source_url": "https://www.newyorkfed.org/markets/reference-rates/effr", "home_featured": True},
            {"id": "unfeatured", "headline": "其他资讯只在相关市场页显示。",
             "summary": "相同利率在美股收盘时段的市场监测清单中也会展示。",
             "affected_markets": ["us_stock"], "source_url": self.verified_source, "home_featured": False},
            {"id": "internal", "headline": "非新闻页范围的观察只供数据库使用。",
             "summary": "这项区域国债观察暂不显示在新闻雷达。",
             "affected_markets": ["rates_bonds_core"],
             "source_url": self.verified_source, "home_featured": False},
        ]
        paths = {
            market: f"daily/2026-11-27_1800_{market}_r2.md" for market in review_evidence.MARKETS
        }
        paths["a_share"] = self.eq_daily.removeprefix("equity/")
        paths["us_stock"] = self.us_daily.removeprefix("equity/")
        for path in (*review_evidence.FIXED_PATHS, self.gold_daily, *(f"equity/{p}" for p in paths.values())):
            self.write(path, "Fixture content\n")
        for path in (self.gold_daily, self.us_daily):
            self.write(path, f"{self.excerpt} [利率表]({self.verified_source})\n{self.calculation}\n{self.inference}\n")
        self.write(review_evidence.POLICY_CALENDAR_PATH, json.dumps({"policy_briefs": self.policy_briefs}))
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
        claims = [
            {
                "file": path, "excerpt": excerpt, "kind": kind, "source_file": path,
                "source_url": self.verified_source, "verification": "核对发布日期与对应交易日。",
            }
            for path in (self.gold_daily, self.us_daily)
            for kind, excerpt in (
                ("fact", self.excerpt), ("calculation", self.calculation), ("inference", self.inference),
            )
        ]
        claims.extend({
            "file": review_evidence.POLICY_CALENDAR_PATH, "source_file": review_evidence.POLICY_CALENDAR_PATH,
            "excerpt": brief["summary"], "policy_brief_id": brief["id"], "kind": "fact",
            "source_url": brief["source_url"], "verification": "核对发布时点和原公告的统计范围。",
        } for brief in self.policy_briefs[:3])
        checks["primary_sources"].update({
            "files": [self.gold_daily, self.us_daily, review_evidence.POLICY_CALENDAR_PATH],
            "source_urls": list(dict.fromkeys(claim["source_url"] for claim in claims)),
            "claims": claims,
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
        claims = closure["checks"]["primary_sources"]["claims"]
        claims[:] = [entry for entry in claims if not (entry["file"] == self.us_daily and entry["kind"] == "calculation")]
        with self.assertRaisesRegex(ValueError, "must review a fact, calculation and inference"):
            self.validate(closure, candidate)
        claims[:] = [entry for entry in claims if entry["file"] != self.us_daily]
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

    def test_published_policy_claims_must_check_the_card_summary_and_its_own_source(self):
        candidate = self.inspect()
        self.assertEqual(candidate["featured_policy_briefs"], [
            {"id": brief["id"], "headline": brief["headline"], "source_urls": [brief["source_url"]]}
            for brief in self.policy_briefs[:2]
        ])
        self.assertEqual(candidate["published_policy_briefs"], [
            {"id": brief["id"], "headline": brief["headline"], "summary": brief["summary"],
             "source_urls": [brief["source_url"]]}
            for brief in self.policy_briefs[:3]
        ])
        self.validate(self.receipt(candidate)["review_closure"], candidate)

        closure = self.receipt(candidate)["review_closure"]
        claims = closure["checks"]["primary_sources"]["claims"]
        claims[-2]["source_url"] = self.verified_source
        with self.assertRaisesRegex(ValueError, "source URL does not belong to policy brief fed"):
            self.validate(closure, candidate)

        closure = self.receipt(candidate)["review_closure"]
        claims = closure["checks"]["primary_sources"]["claims"]
        claims[-1]["excerpt"] = self.policy_briefs[0]["headline"]
        with self.assertRaisesRegex(ValueError, "headline or summary of its policy_brief_id"):
            self.validate(closure, candidate)

        closure = self.receipt(candidate)["review_closure"]
        claims = closure["checks"]["primary_sources"]["claims"]
        claims[-1]["kind"] = "inference"
        with self.assertRaisesRegex(ValueError, "missing summary facts for published policy briefs: unfeatured"):
            self.validate(closure, candidate)

        closure = self.receipt(candidate)["review_closure"]
        closure["checks"]["primary_sources"]["claims"][-1]["excerpt"] = self.policy_briefs[2]["headline"]
        with self.assertRaisesRegex(ValueError, "missing summary facts for published policy briefs: unfeatured"):
            self.validate(closure, candidate)

        closure = self.receipt(candidate)["review_closure"]
        closure["checks"]["primary_sources"]["claims"].pop()
        with self.assertRaisesRegex(ValueError, "missing summary facts for published policy briefs: unfeatured"):
            self.validate(closure, candidate)

    def test_one_excerpt_cannot_count_as_two_types_with_different_urls(self):
        source2 = self.policy_briefs[1]["source_url"]
        gold = self.root / self.gold_daily
        self.write(self.gold_daily, gold.read_text() + f"[辅助行情]({source2})\n")
        candidate = self.inspect()
        for excerpt in (self.excerpt, self.excerpt[:-1], self.excerpt[2:-2]):
            with self.subTest(excerpt=excerpt):
                closure = self.receipt(candidate)["review_closure"]
                calculation = closure["checks"]["primary_sources"]["claims"][1]
                calculation.update(excerpt=excerpt, source_url=source2)
                with self.assertRaisesRegex(ValueError, "same claim excerpt as multiple kinds"):
                    self.validate(closure, candidate)

    def test_policy_claim_can_quote_its_complete_multiline_summary(self):
        self.policy_briefs[0]["summary"] = "前一段汇总普通国债。\n\n之后的摘要说明实际利率。"
        self.write(review_evidence.POLICY_CALENDAR_PATH, json.dumps({"policy_briefs": self.policy_briefs}))
        candidate = self.inspect()
        closure = self.receipt(candidate)["review_closure"]
        self.validate(closure, candidate)
        closure["checks"]["primary_sources"]["claims"][-3]["excerpt"] = self.policy_briefs[0]["summary"].splitlines()[0]
        with self.assertRaisesRegex(ValueError, "missing summary facts for published policy briefs: rates"):
            self.validate(closure, candidate)

    def test_every_published_policy_source_needs_its_own_fact_including_the_main_link(self):
        extra = "https://www.federalreserve.gov/releases/h41/current/"
        brief = self.policy_briefs[0]
        brief["source_urls"] = [extra]
        self.write(review_evidence.POLICY_CALENDAR_PATH, json.dumps({"policy_briefs": self.policy_briefs}))
        candidate = self.inspect()
        closure = self.receipt(candidate)["review_closure"]
        with self.assertRaisesRegex(ValueError, r"unverified published policy source.*rates"):
            self.validate(closure, candidate)

        check = closure["checks"]["primary_sources"]
        original = next(row for row in check["claims"] if row.get("policy_brief_id") == "rates")
        extra_fact = dict(original, source_url=extra, excerpt="公布的已完成交易日利率")
        check["source_urls"].append(extra)
        check["claims"].append(extra_fact)
        self.validate(closure, candidate)

        # A full-summary receipt citing only the supplement must still review the main URL.
        original["source_url"] = extra
        with self.assertRaisesRegex(ValueError, r"unverified published policy source.*rates"):
            self.validate(closure, candidate)

    def test_resolved_backfill_must_link_the_exact_current_fact_and_source(self):
        candidate = self.inspect()
        closure = self.receipt(candidate)["review_closure"]
        recheck = {
            "kind": "data_caveats", "id": "overnight_rates", "status": "resolved",
            "source_url": self.verified_source, "note": "已经核对待披露的原始利率表。",
        }
        closure["backfill_rechecks"] = [recheck]
        with self.assertRaisesRegex(ValueError, "resolved backfill overnight_rates.*file and excerpt"):
            self.validate(closure, candidate)

        recheck.update(file=self.gold_daily, excerpt=self.inference)
        with self.assertRaisesRegex(ValueError, "resolved backfill overnight_rates.*verified fact or calculation"):
            self.validate(closure, candidate)
        recheck.update(excerpt=self.excerpt, source_url=self.policy_briefs[1]["source_url"])
        with self.assertRaisesRegex(ValueError, "resolved backfill overnight_rates.*verified fact or calculation"):
            self.validate(closure, candidate)
        recheck["source_url"] = self.verified_source
        self.validate(closure, candidate)

    def test_distinct_claim_excerpts_can_share_part_of_their_text(self):
        self.excerpt = "已公布的当日收益率使用相同统计口径。"
        self.calculation = "使用相同统计口径复算后，二者相差七个基点。"
        for rel in (self.gold_daily, self.us_daily):
            self.write(rel, f"{self.excerpt} [利率表]({self.verified_source})\n{self.calculation}\n{self.inference}\n")
        candidate = self.inspect()
        self.validate(self.receipt(candidate)["review_closure"], candidate)

    def test_markdown_source_must_be_a_renderable_link_target(self):
        source2 = self.policy_briefs[1]["source_url"]
        for markup in (
            f"[同时提到 {self.verified_source} 的链接]({source2})",
            f"`[原始利率]({self.verified_source})`",
            f"[原始利率]`分隔内容`({self.verified_source})",
            f"[   ]({self.verified_source})",
            f"<code>[原始利率]({self.verified_source})</code>",
            f"<strong>[原始利率]({self.verified_source})</strong>",
            f"<{self.verified_source}>",
            f"原始文件 {self.verified_source}",
        ):
            with self.subTest(markup=markup):
                self.write(self.gold_daily, f"{self.excerpt} {markup}\n{self.calculation}\n{self.inference}\n")
                candidate = self.inspect()
                with self.assertRaisesRegex(ValueError, "does not match a citation link target"):
                    self.validate(self.receipt(candidate)["review_closure"], candidate)

    def test_markdown_claim_cannot_appear_only_in_the_hidden_link_target(self):
        hidden = "only-a-hidden-clause-in-a-link"
        before = (self.root / self.gold_daily).read_text()
        self.write(self.gold_daily, before + f"[背景]({self.verified_source}?q={hidden})\n")
        candidate = self.inspect()
        closure = self.receipt(candidate)["review_closure"]
        closure["checks"]["primary_sources"]["claims"][0]["excerpt"] = hidden
        with self.assertRaisesRegex(ValueError, "excerpt does not match"):
            self.validate(closure, candidate)

    def test_backtick_code_uses_the_same_boundaries_as_the_portal(self):
        for rel in (self.gold_daily, self.us_daily):
            previous = (self.root / rel).read_text(encoding="utf-8")
            with self.subTest(rel=rel):
                self.write(rel, f"{self.excerpt}\n    ```text\n[利率表]({self.verified_source})\n\t```\n"
                                f"{self.calculation}\n{self.inference}\n")
                candidate = self.inspect()
                with self.assertRaisesRegex(ValueError, "does not match a citation link target"):
                    self.validate(self.receipt(candidate)["review_closure"], candidate)
                self.write(rel, "````text\n示例代码\n```end\n" + previous)
                candidate = self.inspect()
                self.validate(self.receipt(candidate)["review_closure"], candidate)
            self.write(rel, previous)

    def test_historical_slot_revisions_keep_the_original_receipt_contract(self):
        candidate = self.inspect()
        closure = self.receipt(candidate)["review_closure"]
        primary = closure["checks"]["primary_sources"]
        primary["claims"] = [
            entry for entry in primary["claims"] if entry["file"] in (self.gold_daily, self.us_daily)
            and entry["kind"] != "calculation"
        ]
        primary["source_urls"] = [self.verified_source]
        for edition in ("2026-11-28_1800", "2026-11-28_1800_r2"):
            with self.subTest(edition=edition):
                legacy_candidate = {**candidate, "edition_id": edition}
                self.validate(closure, legacy_candidate)

    def test_backfill_recheck_is_required_before_ingestion_and_on_exact_commit(self):
        def git(*args):
            return subprocess.check_output(
                ["git", "-c", "user.name=Review Test", "-c", "user.email=review@example.invalid", *args],
                cwd=self.root, text=True,
            ).strip()

        previous = "2026-11-28_1800"
        gold_path = review_evidence.BACKFILL_STATE_PATHS["gold"]
        equity_path = review_evidence.STATE_PATH
        current_equity = json.loads((self.root / equity_path).read_bytes())
        self.write(gold_path, json.dumps({"edition_id": previous, "data_caveats": [
            {"id": "overnight_rates", "market": "gold", "item": "等待利率原表", "next_review": "2026-11-30_1800"},
        ]}))
        self.write(equity_path, json.dumps({**current_equity, "edition_id": previous, "pending_backfills": [
            {"market": "us_stock", "item": "等待融资数据", "due_session": "2026-11-30_1800"},
        ]}))
        git("init", "-q")
        git("add", "gold", "equity")
        git("commit", "-qm", "Previous edition with pending source data")
        base = git("rev-parse", "HEAD")

        self.write(gold_path, json.dumps({"edition_id": self.edition, "data_caveats": []}))
        self.write(equity_path, json.dumps({**current_equity, "pending_backfills": [
            {"market": "us_stock", "item": "等待融资数据", "due_session": "2026-11-30_1800"},
        ]}))
        candidate = self.inspect()
        self.assertEqual(candidate["previous_backfills"]["gold"][0]["id"], "overnight_rates")
        self.assertTrue(candidate["previous_backfills"]["equity"][0]["id"].startswith("legacy-"))

        missing = self.receipt(candidate)
        self.write(self.patch, json.dumps(missing))
        with self.assertRaisesRegex(ValueError, "overnight_rates disappeared"):
            patch_state_dbs.append_gold_rsi(self.root)
        self.assertEqual(json.loads((self.root / self.metrics).read_bytes())["runs"], [])

        # A real commit with a valid candidate digest but missing closure must still fail.
        equity_metrics = "equity/state/rsi_metrics.json"
        for key in (self.metrics, equity_metrics):
            self.write(key, json.dumps({"score_dimensions": self.dimensions, "runs": [missing]}))
        git("add", "gold", "equity")
        git("commit", "-qm", "Incorrectly dropped a pending backfill")
        rejected = git("rev-parse", "HEAD")
        with patch.object(edition_run, "ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "overnight_rates disappeared"):
                edition_run.check_edition_reviews(self.edition, sha=rejected, base_sha=base)

        closed = self.receipt(candidate)
        closed["review_closure"]["backfill_rechecks"] = [{
            "kind": "data_caveats", "id": "overnight_rates", "status": "resolved",
            "source_url": self.verified_source, "note": "已核对上一个交易日的完整利率原表。",
            "file": self.gold_daily, "excerpt": self.excerpt,
        }]
        self.write(self.metrics, json.dumps({"score_dimensions": self.dimensions, "runs": [closed]}))
        git("add", self.metrics)
        git("commit", "-qm", "Record the verified disposition")
        accepted = git("rev-parse", "HEAD")
        with patch.object(edition_run, "ROOT", self.root):
            edition_run.check_edition_reviews(self.edition, sha=accepted, base_sha=base)

    def test_backfill_carry_and_roll_forward_preserve_market_identifier_and_evidence(self):
        legacy_edition = "2026-11-28_1800"
        row = {"market": "us_stock", "item": "等待融资数据", "due_session": self.edition}
        previous = json.dumps({"edition_id": legacy_edition, "pending_backfills": [row]}).encode()
        prior_id = next(iter(review_evidence.previous_backfills(self.edition, "equity", previous).values()))["id"]
        evidence = {"kind": "pending_backfills", "id": prior_id, "status": "still_pending",
                    "source_url": self.verified_source, "note": "原始网页仍未公布该交易日的完整数据。"}

        def verify(current_rows, decision=None, baseline=previous):
            closure = {"backfill_rechecks": [decision]} if decision else {}
            current = json.dumps({"edition_id": self.edition, "pending_backfills": current_rows}).encode()
            review_evidence.validate_backfill_rechecks(closure, self.edition, "equity", baseline, current)

        deferred = dict(row, due_session="2026-11-29_1130")
        with self.assertRaisesRegex(ValueError, "requires a still_pending recheck"):
            verify([deferred])
        verify([deferred], evidence)
        verify([dict(deferred, id=prior_id, item="补查原始融资公告")], evidence)
        with self.assertRaisesRegex(ValueError, "cannot change market"):
            verify([dict(deferred, id=prior_id, market="hk_stock")], evidence)
        with self.assertRaisesRegex(ValueError, "specific public HTTPS evidence"):
            verify([deferred], dict(evidence, source_url="https://home.treasury.gov/"))
        with self.assertRaisesRegex(ValueError, "slot after the current edition"):
            verify([row], evidence)
        with self.assertRaisesRegex(ValueError, "remain open after a resolved recheck"):
            verify([deferred], dict(evidence, status="resolved"))
        future = json.dumps({"edition_id": legacy_edition, "pending_backfills": [deferred]}).encode()
        verify([deferred], baseline=future)
        with self.assertRaisesRegex(ValueError, "requires a still_pending recheck"):
            verify([dict(deferred, id=prior_id, item="更换成下一周的申购资料")], baseline=future)
        verify([dict(deferred, id=prior_id, item="等待  融资数据")], evidence, baseline=future)
        self.assertEqual(review_evidence.previous_backfills("2026-11-28_1800_r2", "gold", b"legacy history"), {})

    def test_current_backfills_are_checked_without_prior_items(self):
        previous = b'{"edition_id":"2026-11-28_1800"}'
        row = {"market": "us_stock", "item": "首次登记融资资料", "due_session": self.edition}
        current = json.dumps({"edition_id": self.edition, "pending_backfills": [row]}).encode()
        with self.assertRaisesRegex(ValueError, "slot after the current edition"):
            review_evidence.validate_backfill_rechecks({}, self.edition, "equity", previous, current)
        with self.assertRaisesRegex(ValueError, "backfill_rechecks must be an array"):
            review_evidence.validate_backfill_rechecks({"backfill_rechecks": {}}, self.edition, "equity", previous, current)

    def test_caveat_rewording_cannot_change_reader_disclosure_without_recheck(self):
        row = {"id": "awaiting-daily", "market": "gold", "item": "等待原始日表", "next_review": "2026-11-29_1130",
               "detail": "原表尚未发布。", "impact": "暂不能判断当日价格。", "category": "delayed_official", "severity": "info"}
        previous = json.dumps({"edition_id": "2026-11-28_1800", "data_caveats": [row]}).encode()
        evidence = {"kind": "data_caveats", "id": row["id"], "status": "still_pending",
                    "source_url": self.verified_source, "note": "原始交易日表仍待公布，复核了对价格使用的影响。"}
        for field in ("detail", "impact", "category", "severity"):
            with self.subTest(field=field):
                current = json.dumps({"edition_id": self.edition, "data_caveats": [{**row, field: "changed"}]}).encode()
                with self.assertRaisesRegex(ValueError, "still_pending recheck"):
                    review_evidence.validate_backfill_rechecks({}, self.edition, "gold", previous, current)
                review_evidence.validate_backfill_rechecks(
                    {"backfill_rechecks": [evidence]}, self.edition, "gold", previous, current,
                )

    def test_same_slot_revision_cannot_drop_backfills_from_published_edition(self):
        row = {"id": "awaiting-daily", "market": "gold", "item": "等待原始日表", "next_review": "2026-11-29_1130"}
        previous = json.dumps({"edition_id": self.edition, "data_caveats": [row]}).encode()
        revised = self.edition + "_r2"
        current = json.dumps({"edition_id": revised, "data_caveats": []}).encode()
        with self.assertRaisesRegex(ValueError, "awaiting-daily disappeared"):
            review_evidence.validate_backfill_rechecks({}, revised, "gold", previous, current)

    def test_publication_review_gate_reads_the_exact_commit_and_rejects_changed_candidate(self):
        older = "equity/daily/archive/2026-11/2026-11-20_1800_hk_stock.md"
        self.write(older, "Reviewed older Hong Kong report\n")
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
        self.write(older, "Changed older Hong Kong report\n")
        git("add", older)
        git("commit", "-qm", "Changed an archived report outside the latest group")
        changed_archive = git("rev-parse", "HEAD")
        self.write(self.gold_daily, "Later correction，复核后再提交。\n")
        git("add", self.gold_daily)
        git("commit", "-qm", "Changed candidate")
        rejected = git("rev-parse", "HEAD")

        with self.assertRaisesRegex(ValueError, "candidate digest differs"):
            edition_run.check_edition_reviews(self.edition, root=self.root)
        with patch.object(edition_run, "ROOT", self.root):
            edition_run.check_edition_reviews(self.edition, sha=accepted)
            for sha in (changed_archive, rejected):
                with self.subTest(sha=sha), self.assertRaisesRegex(ValueError, "candidate digest differs"):
                    edition_run.check_edition_reviews(self.edition, sha=sha)

    def test_archive_move_is_not_an_edit_but_any_historical_change_invalidates_the_receipt(self):
        def git(*args):
            return subprocess.check_output(
                ["git", "-c", "user.name=Review Test", "-c", "user.email=review@example.invalid", *args],
                cwd=self.root, text=True,
            ).strip()

        day = "2026-11-20_1800"
        old_gold = f"gold/daily/{day}_晚报_黄金深度研报.md"
        old_equity = f"equity/daily/archive/2026-11/{day}_us_stock.md"
        archive_gold = f"gold/daily/archive/2026-11/{Path(old_gold).name}"
        self.write("gold/data_snapshot.json", json.dumps({"edition_id": self.edition}))
        self.write(old_gold, "历史黄金稿原文\n")
        self.write(old_equity, "历史美股稿原文\n")
        git("init", "-q")
        git("add", "gold", "equity")
        git("commit", "-qm", "Earlier daily reports")

        original = self.inspect()
        self.assertIn(old_gold, original["files"])
        self.assertIn(old_equity, original["files"])
        self.assertEqual(original["changed_historical_manuscripts"], [])
        (self.root / archive_gold).parent.mkdir(parents=True, exist_ok=True)
        (self.root / old_gold).rename(self.root / archive_gold)
        moved = self.inspect()
        self.assertEqual(moved["changed_historical_manuscripts"], [])
        self.assertEqual(moved["files"][archive_gold], original["files"][old_gold])

        closure = self.receipt(moved)["review_closure"]
        self.write(archive_gold, "移档时意外修改黄金历史稿\n")
        self.write(old_equity, "另一篇权益历史稿也被修改\n")
        edited = self.inspect()
        self.assertEqual(edited["changed_historical_manuscripts"], [
            {"path": old_equity, "status": "modified"},
            {"path": archive_gold, "status": "modified"},
        ])
        with self.assertRaisesRegex(ValueError, "candidate digest differs"):
            self.validate(closure, edited)

        self.write("gold/daily/scratch/" + Path(old_gold).name, "站点不构建的临时稿\n")
        self.assertEqual(self.inspect()["candidate_sha256"], edited["candidate_sha256"])
        (self.root / old_equity).unlink()
        self.assertIn({"path": old_equity, "status": "removed"}, self.inspect()["changed_historical_manuscripts"])

    def test_historical_addition_requires_claim_and_removal_reason_at_ingestion_and_published_commit(self):
        def git(*args):
            return subprocess.check_output(
                ["git", "-c", "user.name=Review Test", "-c", "user.email=review@example.invalid", *args],
                cwd=self.root, text=True,
            ).strip()

        old = "gold/daily/2026-11-20_1800_晚报_黄金深度研报.md"
        added = "equity/daily/archive/2026-11/2026-11-20_1800_hk_stock.md"
        self.write("gold/data_snapshot.json", json.dumps({"edition_id": self.edition}))
        self.write(old, "旧稿将随勘误移除。\n")
        git("init", "-q")
        git("add", "gold", "equity")
        git("commit", "-qm", "Approved baseline")
        base = git("rev-parse", "HEAD")
        (self.root / old).unlink()
        self.write(added, f"{self.excerpt} [利率表]({self.verified_source})\n")
        candidate = self.inspect()
        draft = self.receipt(candidate)
        self.write(self.patch, json.dumps(draft))
        with self.assertRaisesRegex(ValueError, "must cite evidence for a claim in the changed historical manuscript"):
            patch_state_dbs.append_gold_rsi(self.root)
        for rel in (self.metrics, "equity/state/rsi_metrics.json"):
            self.write(rel, json.dumps({"score_dimensions": self.dimensions, "runs": [draft]}))
        git("add", "gold", "equity")
        git("commit", "-qm", "Attempt to bypass older report review")
        with patch.object(edition_run, "ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "must cite evidence for a claim in the changed historical manuscript"):
                edition_run.check_edition_reviews(self.edition, sha=git("rev-parse", "HEAD"), base_sha=base)

        closure = draft["review_closure"]
        primary = closure["checks"]["primary_sources"]
        primary["files"].append(added)
        primary["claims"].append({**primary["claims"][0], "file": added, "source_file": added})
        for rel in (self.metrics, "equity/state/rsi_metrics.json"):
            self.write(rel, json.dumps({"score_dimensions": self.dimensions, "runs": [draft]}))
        git("add", self.metrics, "equity/state/rsi_metrics.json")
        git("commit", "-qm", "Fill missing article evidence")
        with patch.object(edition_run, "ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "must document why this historical manuscript was removed"):
                edition_run.check_edition_reviews(self.edition, sha=git("rev-parse", "HEAD"), base_sha=base)

        closure["historical_removals"] = [{"file": old, "reason": "旧稿交易日期错误，复核后撤下并在档案页保留更正说明。"}]
        for rel in (self.metrics, "equity/state/rsi_metrics.json"):
            self.write(rel, json.dumps({"score_dimensions": self.dimensions, "runs": [draft]}))
        git("add", self.metrics, "equity/state/rsi_metrics.json")
        git("commit", "-qm", "Record the reviewed archive correction and removal")
        with patch.object(edition_run, "ROOT", self.root):
            edition_run.check_edition_reviews(self.edition, sha=git("rev-parse", "HEAD"), base_sha=base)

    def test_archived_ledgers_rendered_in_scorecard_are_part_of_the_digest(self):
        read_by_scorecard = (
            "gold/daily/archive/CHANGELOG_2026_11.md",
            "gold/daily/archive/2026/old/AUDIT_LOG_2026_11.md",
            "equity/daily/archive/2026-11/CHANGELOG_2026_11.md",
        )
        for path in read_by_scorecard:
            self.write(path, "历史账本原文。\n")
        self.write("equity/daily/archive/AUDIT_LOG_2026_11.md", "不发布的权益审计文件。\n")
        original = self.inspect()
        self.assertTrue(set(read_by_scorecard) <= set(original["files"]))
        self.assertNotIn("equity/daily/archive/AUDIT_LOG_2026_11.md", original["files"])
        closure = self.receipt(original)["review_closure"]
        for path in read_by_scorecard:
            with self.subTest(path=path):
                self.write(path, "晚于盲审写入的账本改动。\n")
                with self.assertRaisesRegex(ValueError, "candidate digest differs"):
                    self.validate(closure, self.inspect())
                self.write(path, "历史账本原文。\n")


if __name__ == "__main__":
    unittest.main()
