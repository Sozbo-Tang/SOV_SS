"""IMG-GEN 续跑/OpenAI 兼容后端测试（全部离线：出网点 monkeypatch、后端用
Fake 替身；manifest 批目录全部指到 tempfile 沙箱，不写真实 out/img_gen）。

覆盖：queue 变体优先顺序 / resume 跳过与 adopt / --max-new 预算闸 /
BackendFatal(402) exit 2 与续跑 / openai payload 构造与打码 / b64↔url 双响应 /
edits 404 降级 / 429 退避 / manifest 原子写与 KeyboardInterrupt / --fresh 守卫。
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "img_gen"))

import gen as gen_mod               # noqa: E402
import manifest as manifest_mod     # noqa: E402
import refs as refs_mod             # noqa: E402

from PIL import Image, ImageDraw

from backends.base import Backend, BackendError, BackendFatal  # noqa: E402


def _sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _unit_png_bytes(size=(1024, 1024)) -> bytes:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((154, 154, 870, 870),
                                fill=(120, 118, 110, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _write_unit_png(path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_unit_png_bytes())


def _entry(key: str, kind="units", priority="P0") -> dict:
    return {"key": key, "kind": kind, "priority": priority, "category": 0,
            "name": key, "prompt_notes": "note %s" % key}


def _args(batch, **kw):
    base = dict(batch=batch, backend="fake", variants=1, order_file=None,
                only=None, start_after=None, fresh=False, yes=False,
                force=False, retry_failed=False, max_new=0, max_fail=5,
                stop_on_error=False, stop_on_fatal=True, interval=0)
    base.update(kw)
    return types.SimpleNamespace(**base)


class FakeBackend(Backend):
    """按脚本演出的假后端：outcomes 依次弹出（None=成功落图）。"""

    name = "fake"

    def __init__(self, outcomes=None):
        self.calls = 0
        self.outcomes = list(outcomes or [])

    def generate(self, prompt, negative, refs, out_path, key, variant,
                 size=None, chroma=False):
        self.calls += 1
        out = self.outcomes.pop(0) if self.outcomes else None
        if out == "fatal":
            raise BackendFatal("模拟 402 余额/配额不足")
        if out == "ki":
            raise KeyboardInterrupt
        if isinstance(out, Exception):
            raise out
        _write_unit_png(out_path)
        return {"variant": variant, "mode": "fake"}


class Sandbox:
    """manifest 批目录＋后端注入全部圈进 tmp（退出即还原）。"""

    def __init__(self, batch: str, backend: Backend):
        import backends
        self.batch = batch
        self.backend = backend
        self.tmp = Path(tempfile.mkdtemp(prefix="imggen_t_"))
        self._backends = backends
        self._old_root = manifest_mod.OUT_ROOT
        self._old_get = backends.get_backend

    def __enter__(self):
        manifest_mod.OUT_ROOT = self.tmp
        self._backends.get_backend = lambda name: self.backend
        return self

    def __exit__(self, *exc):
        manifest_mod.OUT_ROOT = self._old_root
        self._backends.get_backend = self._old_get
        return False

    def run(self, entries, **kw):
        return gen_mod.cmd_run(_args(self.batch, **kw), entries)

    def bdir(self) -> Path:
        return self.tmp / self.batch

    def mf(self) -> dict:
        return manifest_mod.load(self.batch)


class TestQueueOrder(unittest.TestCase):

    def test_variant_major_and_tiers(self):
        entries = [_entry("u_p0a"), _entry("u_p1a", priority="P1"),
                   _entry("a_p0", "air"), _entry("g_p0", "bg"),
                   _entry("u_p0b")]
        q = gen_mod.build_queue(entries, "t_synth", 2)
        keys = [(j["key"], j["variant"]) for j in q["jobs"]]
        self.assertEqual(len(keys), 10)
        v0 = [k for k, v in keys if v == 0]
        v1 = [k for k, v in keys if v == 1]
        want = ["u_p0a", "u_p0b", "a_p0", "g_p0", "u_p1a"]  # P0 units→air→bg→P1
        self.assertEqual(v0, want)
        self.assertEqual(v1, want)
        self.assertEqual(keys.index((v1[0], 1)), 5)     # v0 全覆盖后才 v1
        self.assertEqual(q["order"], "variant_major")

    def test_batch01_25_jobs_and_cli_queue(self):
        import catalog as catalog_mod
        units, bgs = catalog_mod.load_catalogs()
        q = gen_mod.build_queue(units + bgs, "batch_01", 1)
        kinds = [j["kind"] for j in q["jobs"]]
        self.assertEqual(kinds, ["units"] * 10 + ["air"] * 10 + ["bg"] * 5)
        # CLI --queue 落盘（沙箱内，批名用 batch_01 才走 demo 卡组筛选）
        with Sandbox("batch_01", FakeBackend()) as sb:
            rc = gen_mod.cmd_queue(units + bgs, "batch_01", 1, None)
            self.assertEqual(rc, 0)
            on_disk = json.loads((sb.bdir() / "queue.json")
                                 .read_text(encoding="utf-8"))
            self.assertEqual(len(on_disk["jobs"]), 25)


class TestResume(unittest.TestCase):

    def test_skip_validated_generated_and_adopt(self):
        entries = [_entry("j%d" % i) for i in range(1, 6)]
        fake = FakeBackend()
        with Sandbox("t_resume", fake) as sb:
            jobs = {}
            for key, status in (("j1#v0", "validated"), ("j2#v0", "generated"),
                                ("j3#v0", "rejected")):
                p = sb.bdir() / "units" / ("%s.v0.png" % key.split("#")[0])
                _write_unit_png(p)
                jobs[key] = {"key": key, "key_base": key.split("#")[0],
                             "variant": 0, "kind": "units",
                             "output": "units/%s.v0.png" % key.split("#")[0],
                             "status": status, "backend": "fake",
                             "sha256": _sha(p), "error": None}
            _write_unit_png(sb.bdir() / "units" / "j4.v0.png")  # 无记录产物
            manifest_mod.save("t_resume", {"batch": "t_resume", "jobs": jobs})
            rc = sb.run(entries)
            self.assertEqual(rc, 0)
            self.assertEqual(fake.calls, 1, "只应生成 j5")
            mf = sb.mf()
            self.assertEqual(mf["jobs"]["j1#v0"]["status"], "validated")
            self.assertEqual(mf["jobs"]["j2#v0"]["status"], "generated")
            self.assertEqual(mf["jobs"]["j4#v0"]["status"], "generated")  # adopt
            self.assertEqual(mf["jobs"]["j4#v0"].get("meta"),
                             "adopt existing（盘上产物收编）")
            self.assertTrue(_sha(sb.bdir() / "units" / "j4.v0.png")
                            == mf["jobs"]["j4#v0"]["sha256"])   # adopt 校验 sha
            self.assertEqual(mf["jobs"]["j5#v0"]["status"], "validated")

    def test_retry_failed_regenerates_rejected(self):
        entries = [_entry("r1")]
        fake = FakeBackend()
        with Sandbox("t_retry", fake) as sb:
            p = sb.bdir() / "units" / "r1.v0.png"
            _write_unit_png(p)
            seed = {"batch": "t_retry", "jobs": {
                "r1#v0": {"key": "r1#v0", "key_base": "r1", "variant": 0,
                          "kind": "units", "output": "units/r1.v0.png",
                          "status": "rejected", "backend": "fake",
                          "sha256": _sha(p), "error": "x"}}}
            manifest_mod.save("t_retry", seed)
            self.assertEqual(sb.run(entries, retry_failed=True), 0)
            self.assertEqual(fake.calls, 1)
            manifest_mod.save("t_retry", seed)          # 默认（无旗标）重置回
            fake2 = FakeBackend()
            sb.backend = fake2
            self.assertEqual(sb.run(entries), 0)
            self.assertEqual(fake2.calls, 0, "rejected 默认跳过")


class TestMaxNew(unittest.TestCase):

    def test_two_then_stop_then_continue(self):
        entries = [_entry("m%d" % i) for i in range(1, 6)]
        fake = FakeBackend()
        with Sandbox("t_maxnew", fake) as sb:
            rc = sb.run(entries, max_new=2)
            self.assertEqual(rc, 0)
            self.assertEqual(fake.calls, 2)
            mf = sb.mf()
            self.assertEqual([mf["jobs"]["m%d#v0" % i]["status"]
                              for i in (1, 2)],
                             ["validated", "validated"])
            self.assertNotIn("m3#v0", mf["jobs"])       # 未跑=无记录
            fake2 = FakeBackend()
            sb.backend = fake2
            rc = sb.run(entries)                         # 同命令续跑
            self.assertEqual(rc, 0)
            self.assertEqual(fake2.calls, 3)             # 跳过前 2 补完 3


class TestFatal(unittest.TestCase):

    def test_402_blocks_and_resume(self):
        entries = [_entry("f%d" % i) for i in range(1, 6)]
        fake = FakeBackend(outcomes=[None, None, "fatal"])
        with Sandbox("t_fatal", fake) as sb:
            rc = sb.run(entries)
            self.assertEqual(rc, 2)
            mf = sb.mf()
            self.assertEqual(mf["jobs"]["f1#v0"]["status"], "validated")
            self.assertEqual(mf["jobs"]["f2#v0"]["status"], "validated")
            self.assertEqual(mf["jobs"]["f3#v0"]["status"], "pending")
            self.assertIn("402", mf["jobs"]["f3#v0"]["blocked_reason"])
            fake2 = FakeBackend()                        # 充值后同命令续
            sb.backend = fake2
            rc = sb.run(entries)
            self.assertEqual(rc, 0)
            self.assertEqual(fake2.calls, 3)             # 从第 3 张继续
            mf = sb.mf()
            self.assertTrue(all(mf["jobs"]["f%d#v0" % i]["status"] ==
                                "validated" for i in range(1, 6)))


class TestOpenAIRequest(unittest.TestCase):

    ENV = {"OPENAI_IMAGE_BASE": "https://api.example.com/v1",
           "OPENAI_IMAGE_KEY": "sk-TESTKEY-DO-NOT-LEAK",
           "OPENAI_IMAGE_MODEL": "img-model-x"}

    def setUp(self):
        from backends import openai_compat       # 包路径（相对导入须包上下文）
        self.oc = openai_compat
        for k, v in self.ENV.items():
            os.environ[k] = v

    def tearDown(self):
        for k in self.ENV:
            os.environ.pop(k, None)

    def cfg(self):
        return self.oc.env_config()

    def test_generations_request(self):
        req = self.oc.build_request(self.cfg(), "generations", "a tank",
                                    "text, blur", None, "1024x1024")
        self.assertEqual(req["url"],
                         "https://api.example.com/v1/images/generations")
        self.assertEqual(req["headers"]["Authorization"],
                         "Bearer sk-TESTKEY-DO-NOT-LEAK")
        body = json.loads(req["body"].decode("utf-8"))
        self.assertEqual(body["model"], "img-model-x")
        self.assertEqual(body["n"], 1)
        self.assertEqual(body["size"], "1024x1024")
        self.assertEqual(body["response_format"], "b64_json")
        self.assertIn("a tank", body["prompt"])
        self.assertIn("Avoid: text, blur", body["prompt"])   # 负面词折进

    def test_size_star_normalized_to_x(self):
        cfg = self.oc.env_config()
        req = self.oc.build_request(cfg, "generations", "p", "n", None,
                                    size="1024*1024")
        body = json.loads(req["body"].decode())
        self.assertEqual(body["size"], "1024x1024")
        req2 = self.oc.build_request(cfg, "generations", "p", "n", None,
                                     size="2560*1280")
        self.assertEqual(json.loads(req2["body"].decode())["size"],
                         "2560x1280")

    def test_edits_request_multipart(self):
        with tempfile.TemporaryDirectory() as td:
            ref = Path(td) / "r1.jpg"
            ref.write_bytes(b"\xff\xd8\xff fakejpeg")
            req = self.oc.build_request(self.cfg(), "edits", "p", "n", [ref],
                                        "1024x1024")
            self.assertEqual(req["url"],
                             "https://api.example.com/v1/images/edits")
            self.assertIn("multipart/form-data; boundary=",
                          req["headers"]["Content-Type"])
            self.assertEqual(req["form"]["images"], ["r1.jpg"])
            blob = req["body"]
            self.assertIn(b'name="image"; filename="r1.jpg"', blob)
            self.assertIn(b"\xff\xd8\xff fakejpeg", blob)
            self.assertIn(b'name="response_format"\r\n\r\nb64_json', blob)

    def test_payload_preview_masks_key(self):
        pv = self.oc.payload_preview(self.cfg(), "generations", "p", "n",
                                     None, "1024x1024", "k", 0)
        self.assertEqual(pv["headers"]["Authorization"], "Bearer ***")
        self.assertNotIn("sk-TESTKEY", json.dumps(pv))

    def test_parse_image_variants(self):
        b64 = base64.b64encode(b"\x89PNGfake").decode()
        self.assertEqual(
            self.oc._parse_image(
                json.dumps({"data": [{"b64_json": b64}]}).encode()),
            ("b64", b"\x89PNGfake"))
        self.assertEqual(
            self.oc._parse_image(
                json.dumps({"images": [{"url": "https://x/y.png"}]}).encode()),
            ("url", "https://x/y.png"))
        self.assertEqual(
            self.oc._parse_image(
                json.dumps({"url": "https://top/l.png"}).encode()),
            ("url", "https://top/l.png"))

    def _patch_fetch(self, script):
        calls = []

        def fake_fetch_full(url, data=None, headers=None, timeout=60,
                            allow_http=False):
            calls.append({"url": url, "data": data, "headers": headers})
            return script.pop(0)

        orig = refs_mod.fetch_full
        refs_mod.fetch_full = fake_fetch_full
        self.addCleanup(setattr, refs_mod, "fetch_full", orig)
        return calls

    def test_generate_b64_response_writes_file(self):
        png = _unit_png_bytes()
        body = json.dumps({"data": [{"b64_json":
                                     base64.b64encode(png).decode()}]}
                          ).encode()
        calls = self._patch_fetch([(200, body, {})])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "units" / "k.v0.png"
            meta = self.oc.OpenAICompatBackend().generate(
                "p", "n", [], out, "k", 0)
            self.assertEqual(meta["image_source"], "b64_json")
            self.assertEqual(out.read_bytes(), png)
            self.assertEqual(list(Path(td).rglob("*.part")), [])  # 无残留
            self.assertTrue(calls[0]["headers"]["Authorization"]
                            .startswith("Bearer "))
            self.assertEqual(calls[0]["url"],
                             "https://api.example.com/v1/images/generations")

    def test_generate_url_response_downloads(self):
        png = _unit_png_bytes()
        post = json.dumps({"data": [{"url":
                                     "https://cdn.example.com/img.png"}]}
                          ).encode()
        calls = self._patch_fetch([(200, post, {}), (200, png, {})])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "k.png"
            meta = self.oc.OpenAICompatBackend().generate(
                "p", "n", [], out, "k", 0)
            self.assertEqual(meta["image_source"], "url")
            self.assertEqual(out.read_bytes(), png)
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[1]["url"],
                             "https://cdn.example.com/img.png")

    def test_edits_404_degrades_to_generations(self):
        png = _unit_png_bytes()
        ok = json.dumps({"data": [{"b64_json":
                                   base64.b64encode(png).decode()}]}
                        ).encode()
        calls = self._patch_fetch([(404, b"not found", {}), (200, ok, {})])
        with tempfile.TemporaryDirectory() as td:
            ref = Path(td) / "r.png"
            ref.write_bytes(png)
            meta = self.oc.OpenAICompatBackend().generate(
                "p", "n", [ref], Path(td) / "k.png", "k", 0)
            self.assertIn("edits→generations", meta["degrade"])
            self.assertEqual(meta["mode"], "generations")
            self.assertEqual(calls[0]["url"],
                             "https://api.example.com/v1/images/edits")
            self.assertEqual(calls[1]["url"],
                             "https://api.example.com/v1/images/generations")

    def test_edits_transport_error_degrades_to_generations(self):
        png = _unit_png_bytes()
        ok = json.dumps({"data": [{"b64_json":
                                   base64.b64encode(png).decode()}]}
                        ).encode()
        calls = []

        def fake_fetch_full(url, data=None, headers=None, timeout=60,
                            allow_http=False):
            calls.append(url)
            if "images/edits" in url:
                raise urllib.error.URLError(OSError(32, "Broken pipe"))
            return (200, ok, {})

        orig = refs_mod.fetch_full
        refs_mod.fetch_full = fake_fetch_full
        self.addCleanup(setattr, refs_mod, "fetch_full", orig)
        with tempfile.TemporaryDirectory() as td:
            ref = Path(td) / "r.png"
            ref.write_bytes(png)
            meta = self.oc.OpenAICompatBackend().generate(
                "p", "n", [ref], Path(td) / "k.png", "k", 0)
            self.assertIn("传输失败", meta["degrade"])
            self.assertEqual(meta["mode"], "generations")
            self.assertEqual(calls[0],
                             "https://api.example.com/v1/images/edits")
            self.assertEqual(calls[1],
                             "https://api.example.com/v1/images/generations")

    def test_402_raises_fatal(self):
        self._patch_fetch([(402, b"insufficient balance", {})])
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(BackendFatal):
                self.oc.OpenAICompatBackend().generate(
                    "p", "n", [], Path(td) / "k.png", "k", 0)

    def test_429_retries_then_succeeds(self):
        png = _unit_png_bytes()
        ok = json.dumps({"data": [{"b64_json":
                                   base64.b64encode(png).decode()}]}
                        ).encode()
        self._patch_fetch([(429, b"rate", {}), (200, ok, {})])
        import time as _t
        orig_sleep = _t.sleep
        _t.sleep = lambda s: None                     # 免真实退避等待
        self.addCleanup(setattr, _t, "sleep", orig_sleep)
        with tempfile.TemporaryDirectory() as td:
            meta = self.oc.OpenAICompatBackend().generate(
                "p", "n", [], Path(td) / "k.png", "k", 0)
            self.assertEqual(meta["image_source"], "b64_json")

    def test_env_missing_raises(self):
        os.environ.pop("OPENAI_IMAGE_KEY", None)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(BackendError):
                self.oc.OpenAICompatBackend().generate(
                    "p", "n", [], Path(td) / "k.png", "k", 0)


class TestManifestAtomic(unittest.TestCase):

    def test_no_tmp_residue_and_ki_saved(self):
        entries = [_entry("a%d" % i) for i in range(1, 4)]
        fake = FakeBackend(outcomes=[None, "ki"])
        with Sandbox("t_ki", fake) as sb:
            rc = sb.run(entries)
            self.assertEqual(rc, 130)
            self.assertEqual(list(sb.bdir().glob("*.tmp")), [])
            mf = sb.mf()
            self.assertEqual(mf["jobs"]["a1#v0"]["status"], "validated")
            self.assertEqual(mf["jobs"]["a2#v0"]["status"], "pending")
            sb.backend = FakeBackend()
            rc = sb.run(entries)                        # 续跑补完
            self.assertEqual(rc, 0)
            mf = sb.mf()
            self.assertEqual(mf["jobs"]["a2#v0"]["status"], "validated")
            self.assertEqual(mf["jobs"]["a3#v0"]["status"], "validated")
            self.assertEqual(list(sb.bdir().glob("*.tmp")), [])

    def test_save_atomic_replaces(self):
        with Sandbox("t_atomic", FakeBackend()) as sb:
            manifest_mod.save("t_atomic", {"batch": "t_atomic", "jobs": {}})
            self.assertTrue((sb.bdir() / "manifest.json").is_file())
            self.assertEqual(list(sb.bdir().glob("*.tmp")), [])


class TestDryRunAndGuards(unittest.TestCase):

    def test_dry_run_openai_payloads_no_key(self):
        env = {"OPENAI_IMAGE_BASE": "https://api.example.com/v1",
               "OPENAI_IMAGE_KEY": "sk-SECRET-XYZ",
               "OPENAI_IMAGE_MODEL": "m"}
        for k, v in env.items():
            os.environ[k] = v
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in env])
        old_payloads = gen_mod.PAYLOADS_OUT
        old_root = manifest_mod.OUT_ROOT
        tmp = Path(tempfile.mkdtemp(prefix="imggen_dry_"))
        gen_mod.PAYLOADS_OUT = tmp / "payloads"
        manifest_mod.OUT_ROOT = tmp                     # queue 落沙箱
        self.addCleanup(setattr, gen_mod, "PAYLOADS_OUT", old_payloads)
        self.addCleanup(setattr, manifest_mod, "OUT_ROOT", old_root)
        entries = [_entry("d1"), _entry("d2", "air"), _entry("d3", "bg")]
        rc = gen_mod.cmd_dry_run_openai(entries, "t_dry", 1, None)
        self.assertEqual(rc, 0)
        files = sorted((tmp / "payloads").glob("*.json"))
        self.assertEqual(len(files), 3)
        for f in files:
            self.assertNotIn("sk-SECRET-XYZ", f.read_text(encoding="utf-8"))
        j1 = json.loads((tmp / "payloads" / "d1#v0.json").read_text())
        self.assertEqual(j1["headers"]["Authorization"], "Bearer ***")
        self.assertEqual(j1["backend"], "openai")

    def test_fresh_without_yes_rejected(self):
        self.assertEqual(gen_mod.main(["--run", "--fresh",
                                       "--batch", "t_no"]), 1)

    def test_start_after_unknown_key(self):
        with Sandbox("t_sa", FakeBackend()) as sb:
            self.assertEqual(
                sb.run([_entry("s1")], start_after="nope#v0"), 1)


if __name__ == "__main__":
    unittest.main()
