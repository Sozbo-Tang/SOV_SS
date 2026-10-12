"""Kev 决策服务 HTTP 客户端（stdlib-only——urllib+json，零第三方依赖）。

协议（与 kev.serve / TypeSafe /v1/systemone 对齐，wire 格式照 kev/api.py
SystemOneRequest 字面）：
  POST /v1/systemone
  {"state": str|dict|list, "model": "kev-latest",
   "questions": {qid: {"type": "choice", "instructions": ...,
                       "criteria": {选项名: 描述|null}}}}
  → {"model": ..., "answers": {qid: {"type": "choice", "choice": 选项名,
                                     "confidence": f, "probabilities": {...}}},
     "usage": {...}, "latency_ms": ...}

认证：服务端设 KEV_API_KEY 时要求 Authorization: Bearer <key>；未设=开放
（本地缺省）。本客户端始终携带 key（若配置）——与 TypeSafe 客户端行为一致。

兼容性：仅 CPython 标准库；CUDA/MPS/MLX 差异全部由服务端承载，本模块
不 import torch——在无 GPU、无 torch 的环境同样可运行（指向远端服务即可）。

安全边界（SSRF 加固）：base_url 是**开发者配置**而非对局输入，且合法目标
常为本机/内网（kev.serve 缺省 127.0.0.1）——故不做私网/环回拦截，但收口
三件事：① 构造期协议白名单（仅 http/https）+ 端口范围 + 拒绝 URL userinfo；
② 禁自动重定向（防 3xx 跳转改变目标）；③ 请求体恒为 JSON、无表单/文件面。

合法性否决权在客户端侧兜一层：choice 返回值必须 ∈ criteria 选项名，否则
抛 KevUnavailableError（上层降级规则兜底）——不把非法决策放进命令流。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlsplit


class KevUnavailableError(Exception):
    """决策服务不可用/响应不合法（连接失败、超时、非 200、坏 JSON、非法选项）。

    上层（KevPlayer）捕获后降级到规则兜底，不中断对局。
    """


@dataclass(frozen=True)
class KevChoiceAnswer:
    """choice 问题的回答。probabilities 键=选项名（服务端 round 4 位）。"""
    question_id: str
    choice: str
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """3xx 一律拒绝——重定向可能把请求改道到非预期目标。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise KevUnavailableError(f"服务端重定向被拒绝: {code} → {newurl}")


class KevClient:
    """极薄客户端：一次 HTTP 往返 = 一次 system_one 决策（prefill-only，无生成）。

    base_url 形如 "http://127.0.0.1:8011"（尾斜杠 tolerated）；timeout_s 覆盖
    连接与读超时整体（urllib 单一 timeout 语义）。
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8011", *,
                 api_key: str | None = None, model: str = "kev-latest",
                 timeout_s: float = 30.0):
        parts = urlsplit(base_url if "://" in base_url else "http://" + base_url)
        if parts.scheme not in ("http", "https"):
            raise KevUnavailableError(
                f"base_url 协议仅限 http/https: {base_url!r}（得到 {parts.scheme!r}）")
        if not parts.hostname:
            raise KevUnavailableError(f"base_url 缺主机名: {base_url!r}")
        if parts.username is not None or parts.password is not None:
            raise KevUnavailableError(f"base_url 不接受 userinfo: {base_url!r}")
        if parts.port is not None and not 1 <= parts.port <= 65535:
            raise KevUnavailableError(f"base_url 端口越界: {base_url!r}")
        self.base_url = f"{parts.scheme}://{parts.netloc}"
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        # 独立 opener：挂 NoRedirect（默认 OpenerDirector 会装 HTTPRedirectHandler）
        self._opener = urllib.request.build_opener(_NoRedirectHandler())

    # ── 对外入口 ──

    def choose(self, state, question_id: str, instructions,
               options: dict[str, object]) -> KevChoiceAnswer:
        """单 choice 问题便捷入口。options={选项名: 描述(或 None)}，1..255 项。

        返回的 choice 保证 ∈ options 键（否则 KevUnavailableError）。
        """
        if not 1 <= len(options) <= 255:
            raise KevUnavailableError(f"options 数越界: {len(options)}（须 1..255）")
        questions = {question_id: {
            "type": "choice",
            "instructions": instructions,
            "criteria": dict(options),
        }}
        answers = self.system_one(state, questions)
        ans = answers.get(question_id)
        if not isinstance(ans, dict) or ans.get("type") != "choice":
            raise KevUnavailableError(f"回答缺失或类型不对: {question_id!r} → {ans!r}")
        choice = ans.get("choice")
        if choice not in options:
            raise KevUnavailableError(f"服务端返回非法选项 {choice!r}（不在 {list(options)}）")
        probs = ans.get("probabilities")
        return KevChoiceAnswer(
            question_id=question_id,
            choice=choice,
            confidence=float(ans.get("confidence", 0.0)),
            probabilities=dict(probs) if isinstance(probs, dict) else {},
        )

    def system_one(self, state, questions: dict) -> dict[str, object]:
        """原始 system_one 调用 → answers 映射（qid → 回答 dict）。

        任何网络/协议层失败统一抛 KevUnavailableError（不抛 urllib 原生异常，
        上层只需捕一种）。
        """
        payload = {"state": self._state_payload(state), "model": self.model,
                   "questions": questions}
        data = self._post_json("/v1/systemone", payload)
        answers = data.get("answers") if isinstance(data, dict) else None
        if not isinstance(answers, dict):
            raise KevUnavailableError(f"响应缺 answers 字段: {str(data)[:200]}")
        return answers

    def ping(self) -> bool:
        """健康探活：一个最小 noul 问题（服务端一次极短前向）。失败抛 KevUnavailableError。"""
        self.system_one(
            state="health check",
            questions={"ping": {"type": "noul", "instructions": "ready?",
                                "criteria": None}},
        )
        return True

    # ── 内部 ──

    @staticmethod
    def _state_payload(state) -> object:
        """state 必须可 JSON 序列化——错误信息指到调用方数据而非协议层。"""
        try:
            json.dumps(state, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            raise KevUnavailableError(f"state 不可 JSON 序列化: {e}") from e
        return state

    def _post_json(self, path: str, payload: dict) -> object:
        url = self.base_url + path
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with self._opener.open(req, timeout=self.timeout_s) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            detail = b""
            try:
                detail = e.read()[:300]
            except Exception:
                pass
            raise KevUnavailableError(f"HTTP {e.code} @ {url}: {detail!r}") from e
        except KevUnavailableError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise KevUnavailableError(f"连接失败 @ {url}: {e}") from e
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise KevUnavailableError(f"响应不是合法 JSON: {raw[:200]!r}") from e
