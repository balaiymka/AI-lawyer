"""Модели эмбеддингов и реранкера (локально, без внешних API).

* BAAI/bge-m3 — один проход даёт dense-вектор (CLS, 1024) и sparse-веса токенов
  (лексический канал: relu(linear(hidden)) по токенам — как в оригинальной реализации BGE-M3).
* BAAI/bge-reranker-v2-m3 — cross-encoder, оценивает пару (запрос, фрагмент).

Обе модели мультиязычные и понимают казахский. Загружаются лениво и кэшируются в процессе.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings


@dataclass
class Encoded:
    dense: list[float]
    sparse: dict[int, float]  # token_id → вес


def _device():
    import torch

    pref = get_settings().ml_device
    if pref != "auto":
        return torch.device(pref)
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _dtype(device):
    """fp16 на GPU: модели вдвое легче (на Mac с 8 ГБ fp32-модели уходили в своп) и быстрее; на CPU — fp32."""
    import torch

    pref = get_settings().ml_dtype
    if pref != "auto":
        return getattr(torch, pref)
    return torch.float16 if device.type in ("mps", "cuda") else torch.float32


class BGEM3:
    def __init__(self, model_name: str) -> None:
        import torch
        from huggingface_hub import hf_hub_download
        from transformers import AutoModel, AutoTokenizer

        self.torch = torch
        self.device = _device()
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.dtype = _dtype(self.device)
        self.model = AutoModel.from_pretrained(model_name, torch_dtype=self.dtype).to(self.device).eval()
        self.sparse_linear = torch.nn.Linear(self.model.config.hidden_size, 1)
        state = torch.load(hf_hub_download(model_name, "sparse_linear.pt"), map_location="cpu")
        self.sparse_linear.load_state_dict(state)
        self.sparse_linear.to(self.device, dtype=self.dtype).eval()
        t = self.tokenizer
        self.skip_ids = {t.cls_token_id, t.eos_token_id, t.pad_token_id, t.unk_token_id}

    def encode(self, texts: list[str], max_length: int = 1024, batch_size: int = 8) -> list[Encoded]:
        torch = self.torch
        out: list[Encoded] = []
        with torch.inference_mode():
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                enc = self.tokenizer(batch, padding=True, truncation=True, max_length=max_length,
                                     return_tensors="pt").to(self.device)
                hidden = self.model(**enc).last_hidden_state
                dense = torch.nn.functional.normalize(hidden[:, 0], dim=-1).float().cpu()
                weights = torch.relu(self.sparse_linear(hidden)).squeeze(-1).float().cpu()
                ids = enc["input_ids"].cpu()
                for row in range(len(batch)):
                    sparse: dict[int, float] = {}
                    for tid, w in zip(ids[row].tolist(), weights[row].tolist()):
                        if tid in self.skip_ids or w <= 0:
                            continue
                        if w > sparse.get(tid, 0.0):
                            sparse[tid] = w
                    out.append(Encoded(dense=dense[row].tolist(), sparse=sparse))
        return out


class Reranker:
    def __init__(self, model_name: str) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.device = _device()
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_name, torch_dtype=_dtype(self.device)).to(self.device).eval()

    def score(self, query: str, passages: list[str], max_length: int = 1024, batch_size: int = 8) -> list[float]:
        torch = self.torch
        scores: list[float] = []
        with torch.inference_mode():
            for i in range(0, len(passages), batch_size):
                pairs = [[query, p] for p in passages[i : i + batch_size]]
                enc = self.tokenizer(pairs, padding=True, truncation=True, max_length=max_length,
                                     return_tensors="pt").to(self.device)
                logits = self.model(**enc).logits.view(-1).float()
                scores.extend(torch.sigmoid(logits).cpu().tolist())
        return scores


@lru_cache
def get_embedder() -> BGEM3:
    return BGEM3(get_settings().embed_model)


@lru_cache
def get_reranker() -> Reranker:
    return Reranker(get_settings().rerank_model)
