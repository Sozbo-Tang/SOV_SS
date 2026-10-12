"""LocalKevEngine：Kev 决策模型的**进程内**推理引擎（不起 HTTP 服务）。

与 kev_client.KevClient 鸭子类型同接口（choose/ping）——KevPlayer 的
client 参数两者通用，换载体只换构造一行：

    from sovs.ai import KevPlayer, LocalKevEngine
    red = KevPlayer(0, LocalKevEngine("jaredpalmer/kev-0.5b"))   # 进程内
    blue = KevPlayer(1, KevClient("http://...:8011"))            # HTTP（可选）

实现路径（kev 仓库公开 API， predictors.py / checkpoint.py / device.py）：
  LocalPredictor(run, device, LoadOptions(dtype, merge, backend))
    → predictor(record) → {"probabilities": {qid: {选项: p}},
                           "latency_ms", "input_tokens", ...}
  record 形状与 HTTP 请求体同构：{"state": ..., "questions": {qid: {"type":
  "choice", "instructions": ..., "criteria": {...}}}}

平台兼容（用户要求 CUDA 与 Apple Silicon 双端）：
- device 缺省 kev.device.default_device()——cuda → mps → cpu 自动探测；
- backend 缺省 torch（Kev-0.5B 是 Qwen2.5 注意力底座，非 hybrid，MLX 路径
  本就拒绝注意力底座——torch/MPS 即其 Mac 正路，两平台同一条代码路径）；
- dtype 缺省 bf16（kev.serve 同款服务档：约 2~4.5x 提速，概率偏差 ≤0.01；
  决策可复现性锚在命令流日志而非模型，见 decision_log.py）。

依赖边界：torch/kev 仅在 __init__ **惰性导入**——本模块（及整个 sovs.ai）
在未装 torch 的环境仍可 import，KevPlayer 纯规则兜底不受影响。安装：
  git clone https://github.com/jaredpalmer/kev kev && pip install -e ./kev
（或 --kev-path 指仓库路径免安装直挂 sys.path；torch/transformers/peft
随 kev 依赖装入）。首跑按 run id 从 HuggingFace 拉权重并缓存；权重已
缓存而 Hub 不可达（断网/连接超时 Errno 60 类）时自动置 HF_HUB_OFFLINE=1
离线重试一次——缓存命中即可加载（见 _load_predictor/is_hub_unreachable）。
"""
from __future__ import annotations

import errno
import os
import sys

from sovs.ai.kev_client import KevChoiceAnswer, KevUnavailableError

DEFAULT_RUN = "jaredpalmer/kev-0.5b"

# ── Hub 不可达识别（离线回退用——见 LocalKevEngine._load）──

# 连接层 errno（darwin/linux 双端取并集；文件缺失类 Errno 2 不在其中）
_NET_ERRNOS = frozenset(
    getattr(errno, n) for n in ("ETIMEDOUT", "ECONNREFUSED", "EHOSTUNREACH",
                                "ENETUNREACH", "EHOSTDOWN", "ENETDOWN",
                                "ENETRESET") if hasattr(errno, n))
# 消息关键字（huggingface_hub/requests 各自包装网络错误，文本兜一路）
_NET_HINTS = ("timed out", "timeout", "connection", "unreachable",
              "name resolution", "temporarily unavailable")


def is_hub_unreachable(exc: BaseException) -> bool:
    """异常链上是否带网络不可达征（连接超时/拒绝/断网——Errno 60 类）。

    snapshot_download/requests/transformers 层层包装（raise ... from），逐帧
    走 __cause__/__context__ 链三路并集判：类型（TimeoutError/ConnectionError）、
    OSError 的 errno ∈ 网络集、消息关键字。缺文件/坏配置类不命中。
    """
    hop = 0
    while exc is not None and hop < 8:
        if isinstance(exc, (TimeoutError, ConnectionError)):
            return True
        if isinstance(exc, OSError) and exc.errno in _NET_ERRNOS:
            return True
        if any(h in str(exc).lower() for h in _NET_HINTS):
            return True
        exc = exc.__cause__ if exc.__cause__ is not None else exc.__context__
        hop += 1
    return False


class LocalKevEngine:
    """进程内 Kev 决策引擎（加载一次常驻；choose 每次一次前向，无生成）。"""

    def __init__(self, run: str = DEFAULT_RUN, *, device: str | None = None,
                 dtype: str | None = "bf16", backend: str | None = None,
                 kev_path: str | None = None):
        # 惰性导入：kev/torch 是可选重依赖（见模块 docstring 安装说明）
        try:
            import torch  # noqa: F401
            if kev_path:
                sys.path.insert(0, kev_path)
            from kev.checkpoint import LoadOptions
            from kev.device import default_device
            from kev.predictors import LocalPredictor
        except Exception as e:  # ImportError 或其依赖链任何缺口
            raise KevUnavailableError(
                f"kev/torch 未就绪（{e}）。安装：git clone "
                "https://github.com/jaredpalmer/kev kev && pip install -e ./kev"
                "（或构造时传 kev_path=仓库路径）") from e
        dtype_map = {"bf16": torch.bfloat16, "fp16": torch.float16,
                     "fp32": torch.float32, None: None}
        if dtype not in dtype_map:
            raise KevUnavailableError(f"dtype 仅支持 bf16/fp16/fp32/None: {dtype!r}")
        dev = device or default_device()
        opts = LoadOptions(dtype=dtype_map[dtype], merge=True, backend=backend)
        try:
            self._predictor = self._load_predictor(run, dev, opts, LocalPredictor)
        except Exception as e:
            raise KevUnavailableError(
                f"模型加载失败（run={run}, device={dev}）: {e}") from e
        self.run = run
        self.device = dev
        self.dtype = dtype
        self.backend = backend or "torch"
        # 最近一次调用的观测面（bench 读取：模型时延/输入 token 数）
        self.last: dict = {}

    # ── 加装：Hub 不可达时的离线回退（缓存命中即可加载，零网络代码）──

    @staticmethod
    def _load_predictor(run, dev, opts, local_predictor_cls):
        """LocalPredictor 装配；Hub 不可达（连接超时/拒绝类）→ 离线重试一次。

        checkpoint.resolve_run 经 snapshot_download 向 Hub 校验修订与 etag
        ——权重已在本地 HF 缓存而网络不可达时会整体连接超时（Errno 60）；
        置 HF_HUB_OFFLINE=1（TRANSFORMERS_OFFLINE 同步）后 hub 改走纯缓存
        解析，LoRA 检查点与 base 快照均可命中加载。首次下载（缓存为空）
        仍走在线路径不受影响；离线重试仍失败则抛（缺文件等非网络原因，
        异常带链上原始信息）。进程内该开关一经置位保持——后续加载同走
        缓存，与断网环境语义一致。
        """
        try:
            return local_predictor_cls(run, dev, opts)
        except Exception as e:
            if (os.environ.get("HF_HUB_OFFLINE") == "1"
                    or not is_hub_unreachable(e)):
                raise
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            return local_predictor_cls(run, dev, opts)

    # ── 与 KevClient 鸭子类型同接口 ──

    def choose(self, state, question_id: str, instructions,
               options: dict[str, object]) -> KevChoiceAnswer:
        if not 1 <= len(options) <= 255:
            raise KevUnavailableError(f"options 数越界: {len(options)}（须 1..255）")
        record = self._request(state, question_id, "choice", instructions,
                               {"type": "choice", "instructions": instructions,
                                "criteria": dict(options),
                                "label": next(iter(options)),  # 哑标签（评分面）
                                "src": "sovs-ai"})
        try:
            out = self._predictor(record)
        except Exception as e:   # ContextOverflow(ValueError)/内核缺失等
            raise KevUnavailableError(f"前向失败: {e}") from e
        probs = (out.get("probabilities") or {}).get(question_id) or {}
        if not probs:
            raise KevUnavailableError(f"回答缺失概率: {question_id!r}")
        # argmax（平值取 options 插入序首位——确定性；与 serve to_answers 同义）
        choice = max(options, key=lambda k: probs.get(k, 0.0))
        self.last = {"latency_ms": out.get("latency_ms", 0.0),
                     "input_tokens": out.get("input_tokens", 0)}
        k = len(options)
        conf = 1.0 if k == 1 else (probs.get(choice, 0.0) - 1.0 / k) / (1.0 - 1.0 / k)
        return KevChoiceAnswer(question_id=question_id, choice=choice,
                               confidence=max(0.0, conf),
                               probabilities=dict(probs))

    def ping(self) -> bool:
        """极小前向探活（加载已在 __init__ 完成，这里验推理通路）。"""
        record = self._request("health check", "ping", "noul", "ready?",
                               {"type": "noul", "instructions": "ready?",
                                "criteria": None, "label": False,
                                "src": "sovs-ai"})
        try:
            self._predictor(record)
            return True
        except Exception as e:
            raise KevUnavailableError(f"探活失败: {e}") from e

    @staticmethod
    def _request(state, qid: str, qtype: str, instructions, q: dict) -> dict:
        """LocalPredictor 的带标签请求格式（kev.data.materialize 口径）：
        state + {qid: {type/instructions/criteria/label/src}}——label/src 为
        评分面记账位，推理路径只需占位（choice=选项名哑值，noul=bool）。"""
        return {"state": state, "questions": {qid: q}}
