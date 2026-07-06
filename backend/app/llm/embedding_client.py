import hashlib
import math
from functools import cached_property
from typing import Any

from openai import OpenAI

from app.core.config import settings


class EmbeddingClient:
    """Embedding wrapper for DashScope, local sentence-transformers, or mock vectors."""

    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=settings.dashscope_api_key or "mock-key",
            base_url=settings.dashscope_base_url,
            timeout=settings.bailian_timeout_seconds,
            max_retries=0,
        )

    def embed_text(self, text: str) -> list[float] | None:
        clean_text = " ".join((text or "").split())
        if not clean_text or not settings.enable_vector_memory:
            return None

        provider = settings.embedding_provider.lower()
        if provider == "mock" or settings.use_mock_llm:
            return self._mock_embedding(clean_text)
        if provider == "local":
            return self._fit_dimension(self._local_embedding(clean_text))
        return self._fit_dimension(self._dashscope_embedding(clean_text))

    def _dashscope_embedding(self, text: str) -> list[float]:
        try:
            response = self.client.embeddings.create(
                model=settings.bailian_embedding_model,
                input=text[:6000],
                dimensions=settings.embedding_dimension,
            )
        except TypeError:
            response = self.client.embeddings.create(
                model=settings.bailian_embedding_model,
                input=text[:6000],
            )
        return list(response.data[0].embedding)

    def _local_embedding(self, text: str) -> list[float]:
        embedding = self.local_model.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [float(value) for value in embedding.tolist()]

    def status(self) -> dict[str, str]:
        provider = settings.embedding_provider.lower()
        model = settings.local_embedding_model if provider == "local" else settings.bailian_embedding_model
        status = {
            "provider": settings.embedding_provider,
            "model": model,
            "configured_device": settings.local_embedding_device if provider == "local" else "",
            "runtime_device": self.local_runtime_device if provider == "local" else "",
        }
        loaded_model = self.__dict__.get("local_model")
        if loaded_model is not None:
            status["runtime_device"] = str(getattr(loaded_model, "device", status["runtime_device"]))
        return status

    @cached_property
    def local_model(self) -> Any:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=local requires sentence-transformers. "
                "Install it with: uv sync --extra local-embedding"
            ) from exc

        kwargs: dict[str, Any] = {"device": self.local_runtime_device}
        if settings.local_embedding_cache_dir:
            kwargs["cache_folder"] = settings.local_embedding_cache_dir
        return SentenceTransformer(settings.local_embedding_model, **kwargs)

    @cached_property
    def local_runtime_device(self) -> str:
        configured_device = (settings.local_embedding_device or "auto").strip().lower()
        if configured_device != "auto":
            return configured_device
        try:
            import torch
        except ImportError:
            return "cpu"
        return "cuda" if torch.cuda.is_available() else "cpu"

    @staticmethod
    def _mock_embedding(text: str) -> list[float]:
        values: list[float] = []
        seed = text.encode("utf-8")
        counter = 0
        while len(values) < settings.embedding_dimension:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            for byte in digest:
                values.append((byte / 127.5) - 1.0)
                if len(values) >= settings.embedding_dimension:
                    break
            counter += 1
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]

    @staticmethod
    def _fit_dimension(embedding: list[float]) -> list[float]:
        if len(embedding) == settings.embedding_dimension:
            return embedding
        if len(embedding) > settings.embedding_dimension:
            return embedding[: settings.embedding_dimension]
        return embedding + [0.0] * (settings.embedding_dimension - len(embedding))


bailian_embedding_client = EmbeddingClient()
