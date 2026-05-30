"""
Embeddings service for Pellier

Generates vector embeddings using Cohere Embed English v3 via Amazon Bedrock.
Provides embedding generation for search queries and documents with
asymmetric input types for improved retrieval quality.
"""

import logging
import math
import time
from typing import List

import boto3
import json
from botocore.exceptions import ClientError

from config import settings

logger = logging.getLogger(__name__)


_TOTAL_EMBEDDING_COST = 0.0
_EMBEDDING_COST_PER_CALL = 0.00001  # ~$0.01 per 1K Cohere Embed English v3 calls


def get_cache_stats() -> dict:
    """Return embedding cost statistics for the Context & Cost dashboard."""
    from services.cache import get_cache
    cache = get_cache()
    stats = cache.stats() if cache else {"hits": 0, "misses": 0, "hit_rate": 0.0, "total_requests": 0}
    stats["total_embedding_cost_usd"] = round(_TOTAL_EMBEDDING_COST, 6)
    return stats


class EmbeddingService:
    """
    Service for generating text embeddings using Cohere Embed English v3 via Bedrock.

    Cohere Embed English v3 generates 1024-dimensional vectors with asymmetric
    input types (search_query vs search_document) for improved retrieval.
    """

    def __init__(self):
        """Initialize embeddings service with Bedrock client."""
        self.bedrock_runtime = boto3.client(
            service_name="bedrock-runtime",
            region_name=settings.AWS_REGION
        )
        self.model_id = settings.BEDROCK_EMBEDDING_MODEL
        self.embedding_dimension = 1024

        # Retry event tracking for frontend indicators
        self._retry_callbacks = []
        logger.debug(f"Initialized embeddings service: {self.model_id}")

    def on_retry(self, callback):
        """Register a callback for retry events: callback(attempt, max_attempts)"""
        self._retry_callbacks.append(callback)

    def _notify_retry(self, attempt: int, max_attempts: int = 3):
        for cb in self._retry_callbacks:
            try:
                cb(attempt, max_attempts)
            except Exception:
                pass

    @staticmethod
    def _normalize_embedding(vec: List[float]) -> List[float]:
        """L2-normalize embedding vector for stable cosine behavior."""
        norm = math.sqrt(sum(v * v for v in vec))
        if norm <= 0:
            return vec
        return [v / norm for v in vec]

    def _call_bedrock_embedding(self, request_body: dict) -> dict:
        """
        Call Bedrock embedding API with retry logic.
        """
        max_attempts = 3
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                response = self.bedrock_runtime.invoke_model(
                    modelId=self.model_id,
                    contentType="application/json",
                    accept="*/*",
                    body=json.dumps(request_body)
                )
                return json.loads(response['body'].read())
            except ClientError as e:
                last_error = e
                error_code = e.response['Error']['Code']
                if error_code in ('ThrottlingException', 'ServiceUnavailableException', 'ModelTimeoutException'):
                    if attempt < max_attempts:
                        self._notify_retry(attempt, max_attempts)
                        wait_time = min(0.5 * (2 ** (attempt - 1)), 5)
                        logger.warning(f"Bedrock API retry {attempt}/{max_attempts}, waiting {wait_time}s: {error_code}")
                        time.sleep(wait_time)
                        continue
                raise
            except Exception as e:
                last_error = e
                if attempt < max_attempts:
                    self._notify_retry(attempt, max_attempts)
                    time.sleep(0.5 * attempt)
                    continue
                raise
        raise last_error  # type: ignore

    def generate_embedding(
        self,
        text: str,
        input_type: str = "search_query",
        normalize: bool = True,
    ) -> List[float]:
        """
        Generate embedding vector for a single text string.

        Args:
            text: Input text to embed
            input_type: Cohere input type - "search_query" for queries,
                       "search_document" for documents being indexed
            normalize: Whether to normalize the embedding vector

        Returns:
            List of floats representing the embedding vector (1024 dimensions)

        Raises:
            ValueError: If text is empty or invalid
            ClientError: If Bedrock API call fails
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # Truncate if too long
        max_length = 8192  # characters
        text = text[:max_length].strip()

        global _TOTAL_EMBEDDING_COST

        from services.cache import get_cache
        cache = get_cache()

        # Cache key includes input_type since query vs document produce different vectors
        cache_key = f"{input_type}:{text}"

        # Check cache first
        if cache:
            cached = cache.get("emb", cache_key)
            if cached is not None:
                logger.debug("Embedding cache hit")
                return cached

        try:
            # Prepare request body for Cohere Embed English v3.
            # v3 does NOT accept an output_dimension parameter — it returns a
            # fixed 1024-dim vector natively. (Embed v4 used output_dimension;
            # passing it to v3 raises a ValidationException.)
            request_body = {
                "texts": [text],
                "input_type": input_type,
                "embedding_types": ["float"],
            }

            # Call Bedrock API with retry logic
            response_body = self._call_bedrock_embedding(request_body)

            # Extract embedding vector (Cohere format)
            embeddings_data = response_body.get("embeddings", {})
            float_embeddings = embeddings_data.get("float", [])

            if not float_embeddings or len(float_embeddings) == 0:
                raise ValueError("No embeddings returned from Cohere Embed English v3")

            embedding = float_embeddings[0]

            if not embedding or len(embedding) != self.embedding_dimension:
                raise ValueError(
                    f"Invalid embedding dimension: expected {self.embedding_dimension}, "
                    f"got {len(embedding)}"
                )

            if normalize:
                embedding = self._normalize_embedding(embedding)

            _TOTAL_EMBEDDING_COST += _EMBEDDING_COST_PER_CALL

            # Store in cache (1 hour TTL for embeddings)
            if cache:
                cache.set("emb", cache_key, embedding, ttl=3600)

            return embedding

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"Bedrock API error ({error_code}): {error_message}")
            raise
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise

    def generate_embeddings_batch(
        self,
        texts: List[str],
        input_type: str = "search_document",
        normalize: bool = True,
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of input texts
            input_type: Cohere input type (defaults to "search_document" for batch indexing)
            normalize: Whether to normalize embedding vectors

        Returns:
            List of embedding vectors, one per input text
        """
        if not texts:
            return []

        embeddings = []
        errors = []

        for i, text in enumerate(texts):
            try:
                embedding = self.generate_embedding(text, input_type=input_type, normalize=normalize)
                embeddings.append(embedding)
            except Exception as e:
                logger.error(f"Error embedding text {i}: {e}")
                errors.append((i, str(e)))
                # Append zero vector as placeholder
                embeddings.append([0.0] * self.embedding_dimension)

        if errors:
            logger.warning(
                f"Failed to generate {len(errors)} embeddings out of {len(texts)}"
            )

        return embeddings

    def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a search query.

        Uses input_type="search_query" for Cohere's asymmetric retrieval optimization.

        Args:
            query: Search query text

        Returns:
            Embedding vector for the query
        """
        query = query.strip()

        if not query:
            raise ValueError("Query cannot be empty")

        return self.generate_embedding(query, input_type="search_query", normalize=True)

    def embed_document(self, document: str) -> List[float]:
        """
        Generate embedding for a document.

        Uses input_type="search_document" for Cohere's asymmetric retrieval optimization.

        Args:
            document: Document text to embed

        Returns:
            Embedding vector for the document
        """
        document = document.strip()

        if not document:
            raise ValueError("Document cannot be empty")

        return self.generate_embedding(document, input_type="search_document", normalize=True)

    def get_embedding_dimension(self) -> int:
        """Get the dimension of embedding vectors."""
        return self.embedding_dimension

    def get_model_id(self) -> str:
        """Get the Bedrock model ID being used."""
        return self.model_id

    def health_check(self) -> dict:
        """
        Check if embeddings service is healthy.

        Performs a test embedding generation to verify Bedrock connectivity.
        """
        try:
            test_text = "test"
            embedding = self.generate_embedding(test_text, input_type="search_query")

            return {
                "status": "healthy",
                "model_id": self.model_id,
                "embedding_dimension": len(embedding),
                "region": settings.AWS_REGION
            }

        except Exception as e:
            logger.error(f"Embeddings health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "model_id": self.model_id
            }
