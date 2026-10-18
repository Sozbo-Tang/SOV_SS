"""IMG-GEN 流水线测试：catalog 覆盖（含航空阵营回归）/ prompt 四类要点 /
sources 台账 / manifest 续跑 / validate 合成 fixture 过与拒 / dry-run 展开 /
qwen build_payload 两模式 / chroma-key / manual 后端收图。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "img_gen"))

import catalog as catalog_mod      # noqa: E402
import manifest as manifest_mod    # noqa: E402
import prompts as prompts_mod      # noqa: E402
import refs as refs_mod            # noqa: E402
import validate as validate_mod    # noqa: E402

from PIL import Image, ImageDraw


def _rgba_fixture(directory: Path, size=(1024, 1024),
                  ellipse=(154, 154, 870, 870), name="unit.png",
                  fill=(120, 118, 110, 255)) -> Path:
    """合成单位 fixture：灰面主体+椭圆 alpha（过校验的最小形状）。"""
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse(ellipse, fill=fill)
    p = Path(directory) / name
    img.save(p)
    return p


class TestCatalog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.units, cls.bgs = catalog_mod.load_catalogs()

    def test_coverage_67_10_5(self):
        ground = [e for e in self.units if e["kind"] == "units"]
        air = [e for e in self.units if e["kind"] == "air"]
        self.assertEqual(len(ground), 67)
        self.assertEqual(len(air), 10)
        self.assertEqual(len(self.bgs), 5)
        self.assertEqual(len(self.units) + len(self.bgs), 82)

    def test_air_faction_regression(self):
        """air_su.yaml 五机必须 SOVIET（曾因 '_su.' 判定写反全标 GERMAN）。"""
        by = {e["key"]: e for e in self.units if e["kind"] == "air"}
        for k in ("su_po2", "su_pe2", "su_il2m", "su_yak9", "su_li2"):
            self.assertIn(k, by, "缺苏联机 %s" % k)
            self.assertEqual(by[k]["faction"], "SOVIET")
        for k in ("ger_fw189", "ger_ju88", "ger_ju87d", "ger_fw190a", "ger_ju52"):
            self.assertIn(k, by)
            self.assertEqual(by[k]["faction"], "GERMAN")
        self.assertFalse(
            [k for k in by if k.startswith("ger_")
             and k[4:] in ("po2", "pe2", "il2m", "yak9", "li2")],
            "苏联机被错标德军键")

    def test_demo_deck_and_priority(self):
        demo = [e for e in self.units
                if str(e.get("in_demo_deck")).lower() == "true"]
        self.assertTrue(demo, "demo 卡组标记缺失")
        p0 = [e for e in self.units + self.bgs if e.get("priority") == "P0"]
        self.assertTrue(all(str(e.get("in_demo_deck")).lower() == "true"
                            or e["kind"] in ("air", "bg") for e in p0))
        for e in self.units + self.bgs:
            self.assertIn(e.get("priority"), ("P0", "P1"))
            # bg 条目按设计无 ref_group（refs_check 回退 key）
            self.assertTrue(e.get("ref_group") or e["kind"] == "bg",
                            "%s 无 ref_group" % e["key"])


class TestPrompts(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.units, cls.bgs = catalog_mod.load_catalogs()
        cls.by_key = {e["key"]: e for e in cls.units + cls.bgs}

    def _p(self, key, chroma=True):
        return prompts_mod.build_prompt(self.by_key[key], None, chroma=chroma)

    def test_unit_vehicle_gun_infantry_air(self):
        for key in ("su_t3485", "ger_pziv"):            # 车辆
            p = self._p(key)
            self.assertIn("top-down", p)
            self.assertIn("transparent background", p)
            self.assertIn("no text", p)
            self.assertIn("no flag", p)
        infantry = next(e for e in self.units if e["kind"] == "units"
                        and int(e.get("category", 2)) == 1)
        self.assertIn("infantry unit",
                      prompts_mod.build_prompt(infantry, None))   # 步兵班
        # R7 回归：侦察排等 cat=0 的步兵不能被判成车辆
        recon = next(e for e in self.units if e["key"] == "su_recon")
        rp = prompts_mod.build_prompt(recon, None)
        self.assertIn("infantry unit", rp)
        self.assertIn("recon squad", rp)
        self.assertNotIn("tracks/wheels", rp)
        gun = next(e for e in self.units
                   if prompts_mod.kind_tone(e) == "units-gun")
        self.assertIn("artillery piece",
                      prompts_mod.build_prompt(gun, None))        # 火炮
        self.assertIn("planform", self._p("su_il2m"))             # 航空

    def test_chroma_suffix_toggled(self):
        self.assertIn("#00FF00", self._p("su_t3485", chroma=True))
        self.assertNotIn("#00FF00", self._p("su_t3485", chroma=False))

    def test_negative_mentions_text_and_watermark(self):
        neg = prompts_mod.build_negative()
        for token in ("text", "watermark", "UI", "perspective"):
            self.assertIn(token, neg)

    def test_bg_terrain_mentions_control_image(self):
        self.assertIn("control image",
                      self._p("bagration_field_base", chroma=False))

    def test_refs_text_injection(self):
        p = prompts_mod.build_prompt(self.by_key["su_t3485"],
                                     ["T34-85.jpg"], chroma=True)
        self.assertIn("T34-85.jpg", p)
        self.assertIn("do not copy watermarks", p)


class TestSourcesLedger(unittest.TestCase):

    def test_sources_parse_and_files_on_disk(self):
        entries = refs_mod.parse_sources()
        self.assertGreaterEqual(len(entries), 30)
        groups = refs_mod.groups_with_refs()
        for rec in entries:
            self.assertIn("ref_group", rec)
            self.assertTrue(rec["url"].startswith(
                "https://commons.wikimedia.org/"), rec["url"])
            f = refs_mod.REFS_DIR / rec.get("file", "")
            self.assertTrue(f.is_file(), "台账有、盘上无：%s" % rec.get("file"))
            self.assertIn(rec["ref_group"], groups)

    def test_refs_check_p0_zero(self):
        units, bgs = catalog_mod.load_catalogs()
        self.assertEqual(refs_mod.refs_check(units + bgs, verbose=False), 0,
                         "P0 组仍有缺参考（blocking）")


class TestManifest(unittest.TestCase):

    def test_skip_done_and_force_reset(self):
        mf_path = manifest_mod.manifest_path("t_case")
        orig = mf_path.read_text(encoding="utf-8") if mf_path.is_file() else None
        try:
            mf = {"jobs": {}}
            manifest_mod.upsert(mf, {"key": "x#v0", "key_base": "x",
                                     "status": "validated",
                                     "output": "units/x.v0.png",
                                     "kind": "units"})
            self.assertEqual(len(mf["jobs"]), 1)
            manifest_mod.save("t_case", mf)
            loaded = manifest_mod.load("t_case")
            self.assertEqual(loaded["jobs"]["x#v0"]["status"], "validated")
            self.assertEqual(manifest_mod.skip_done(loaded, False), 0)
            self.assertEqual(manifest_mod.skip_done(loaded, True), 1)
            self.assertEqual(loaded["jobs"]["x#v0"]["status"], "pending")
        finally:
            if orig is not None:
                mf_path.write_text(orig, encoding="utf-8")
            elif mf_path.is_file():
                mf_path.unlink()


class TestValidate(unittest.TestCase):

    def test_unit_pass(self):
        with tempfile.TemporaryDirectory() as td:
            info = validate_mod.validate_unit(_rgba_fixture(Path(td)))
            self.assertEqual(info["size"], (1024, 1024))
            self.assertEqual(len(info["sha256"]), 64)

    def test_unit_rejects(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            small = _rgba_fixture(tmp, size=(512, 512), name="small.png")
            self.assertRaises(validate_mod.Invalid,
                              validate_mod.validate_unit, small)
            off = _rgba_fixture(tmp, ellipse=(10, 400, 500, 620), name="off.png")
            self.assertRaises(validate_mod.Invalid,
                              validate_mod.validate_unit, off)
            opaque = tmp / "opaque.png"
            Image.new("RGBA", (1024, 1024), (110, 108, 100, 255)).save(opaque)
            self.assertRaises(validate_mod.Invalid,
                              validate_mod.validate_unit, opaque)
            green = tmp / "green.png"
            img = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
            ImageDraw.Draw(img).ellipse((154, 154, 870, 870),
                                        fill=(0, 255, 0, 255))
            img.save(green)
            self.assertRaises(validate_mod.Invalid,
                              validate_mod.validate_unit, green)

    def test_bg_pass_and_reject(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            ok = tmp / "bg.png"
            Image.new("RGB", (2560, 1280), (90, 110, 80)).save(ok)
            info = validate_mod.validate_bg(ok, "bagration_field_base")
            self.assertEqual(info["size"], (2560, 1280))
            wrong = tmp / "wrong.png"
            Image.new("RGB", (1920, 1080), (90, 110, 80)).save(wrong)
            self.assertRaises(validate_mod.Invalid,
                              validate_mod.validate_bg, wrong,
                              "bagration_field_base")
            withalpha = tmp / "alpha.png"
            Image.new("RGBA", (2560, 1280), (90, 110, 80, 255)).save(withalpha)
            self.assertRaises(validate_mod.Invalid,
                              validate_mod.validate_bg, withalpha,
                              "bagration_field_base")

    def test_near_duplicates(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            a = _rgba_fixture(tmp, name="a.png")
            # 近重复=同几何灰度微变（实测 aHash 汉明 1）；几何微变会抖阈值，
            # 远异椭圆汉明 1400+
            b = _rgba_fixture(tmp, name="b.png", fill=(115, 113, 108, 255))
            c = _rgba_fixture(tmp, ellipse=(300, 300, 500, 500), name="c.png")
            dups = validate_mod.find_near_duplicates([a, b])
            self.assertTrue(dups and dups[0][2] <= 4)
            self.assertEqual(validate_mod.find_near_duplicates([a, c]), [])


class TestDryRun(unittest.TestCase):

    def test_jobs_and_payloads(self):
        import gen as gen_mod
        units, bgs = catalog_mod.load_catalogs()
        self.assertEqual(gen_mod.cmd_dry_run(units + bgs), 0)
        jobs = json.loads((gen_mod.OUT_ROOT / "jobs.json").read_text(
            encoding="utf-8"))["jobs"]
        self.assertEqual(len(jobs), 3 * 82)
        keys = {j["key"].split("#")[0] for j in jobs}   # dry-run 键含 #vN
        self.assertIn("su_il2m", keys)
        self.assertNotIn("ger_il2m", keys)            # 阵营回归在 dry-run 侧
        payloads = list((gen_mod.OUT_ROOT / "dry_run_payload")
                        .glob("*.payload.json"))
        self.assertEqual(len(payloads), 82)
        sample = json.loads((gen_mod.OUT_ROOT / "dry_run_payload" /
                             "su_t3485.payload.json").read_text(encoding="utf-8"))
        body = json.dumps(sample)
        self.assertNotIn("API_KEY", body)
        self.assertNotIn("api_key", body)
        self.assertEqual(sample["_meta"]["mode"], "reference")  # su_t3485 有参图


class TestQwenPayload(unittest.TestCase):

    def test_text2img_mode(self):
        from backends.qwen import build_payload
        payload = build_payload("a tank", "bad stuff", [], "1024*1024")
        self.assertEqual(payload["_meta"]["mode"], "text2img")
        content = payload["input"]["messages"][0]["content"]
        self.assertEqual(content, [{"text": "a tank"}])   # 无参考=纯文本
        self.assertNotIn("image", json.dumps(content))

    def test_reference_mode(self):
        from backends.qwen import build_payload
        with tempfile.TemporaryDirectory() as td:
            ref = Path(td) / "ref.jpg"
            Image.new("RGB", (32, 32), (10, 120, 10)).save(ref, format="JPEG")
            payload = build_payload("a tank", "bad", [ref], "1024*1024")
            content = payload["input"]["messages"][0]["content"]
            self.assertEqual(payload["_meta"]["mode"], "reference")
            imgs = [c for c in content if "image" in c]
            self.assertEqual(len(imgs), 1)              # 参图注入 data URI
            self.assertTrue(imgs[0]["image"].startswith(
                "data:image/jpeg;base64,"))


class TestChromaKey(unittest.TestCase):

    def test_green_removed_to_alpha(self):
        from backends.qwen import chroma_key
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src.png"
            img = Image.new("RGB", (256, 256), (0, 255, 0))
            ImageDraw.Draw(img).ellipse((64, 64, 192, 192), fill=(120, 110, 100))
            img.save(src)
            dst = Path(td) / "dst.png"
            chroma_key(src, dst)
            out = Image.open(dst).convert("RGBA")
            self.assertEqual(out.getpixel((2, 2))[3], 0)        # 纯绿→透明
            self.assertGreater(out.getpixel((128, 128))[3], 0)  # 主体保留


class TestManualBackend(unittest.TestCase):

    def test_collect_from_inbox(self):
        from backends.manual import ManualBackend, INBOX
        INBOX.mkdir(parents=True, exist_ok=True)
        probe = _rgba_fixture(INBOX, name="t_manual_probe.png")
        try:
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "out.png"
                meta = ManualBackend().generate(
                    "p", "n", [], out, "t_manual_probe", 0)
                self.assertTrue(out.is_file())
                self.assertEqual(meta["mode"], "manual")
                self.assertEqual(meta["inbox_source"], probe.name)
        finally:
            probe.unlink(missing_ok=True)

    def test_missing_inbox_raises(self):
        from backends.base import BackendError
        from backends.manual import ManualBackend
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(BackendError):
                ManualBackend().generate("p", "n", [], Path(td) / "x.png",
                                         "no_such_key_probe", 0)


if __name__ == "__main__":
    unittest.main()
