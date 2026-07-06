# Short Drama Memory Architecture

## Goals

The memory system keeps multi-episode creation coherent without blocking the main generation flow. It separates stable series knowledge, recent episode state, retrievable long-term memory, and asynchronous vector indexing.

## Layers

1. Working context
   - Runtime LangGraph state for the current job.
   - Carries user brief, agent trace, review findings, current outline, draft script, and optional human edits.

2. Series state
   - Project bible stored on the project row.
   - Includes logline, theme, main line, character roles, character desires, and writing rules.
   - Used as stable constraints for each episode.

3. Episodic memory
   - Compact summaries from saved versions.
   - Keeps recent episode title, summary, ending hook, and status changes.
   - The prompt packet uses the latest episodes directly so the next episode can pick up open beats.

4. Long-term chunk memory
   - Saved versions are decomposed into knowledge chunks:
     - episode_summary
     - open_thread
     - character_memory
     - scene_memory
   - Chunks are written immediately with `embedding_status = pending`.

5. Async vector indexing
   - `MemoryIndexer` owns a background queue.
   - Saving a project version enqueues chunk ids after the database commit.
   - The worker fills BGE-M3 embeddings and marks chunks as `indexed` or `failed`.
   - BGE-M3 uses 1024-dimensional vectors in this project. Recreate or migrate the pgvector column if you previously initialized the database with another dimension.
   - `LOCAL_EMBEDDING_DEVICE=auto` prefers CUDA for BGE-M3 when the PyTorch runtime can see an NVIDIA GPU, then falls back to CPU.
   - Script generation is not blocked by local embedding latency.

6. Hybrid retrieval
   - Vector recall reads only `indexed` chunks.
   - Keyword recall can still find newly saved text while embeddings are pending.
   - Results are fused with reciprocal rank fusion and injected into the world-builder and lead-writer context packets.

## Operational Flow

```text
save version
  -> write project/version rows
  -> split memory chunks
  -> commit pending chunks
  -> enqueue chunk ids
  -> background BGE-M3 embedding
  -> mark indexed/failed
  -> next generation uses hybrid retrieval
```

## Observability

The backend exposes:

- `GET /api/memory/indexer`
- `POST /api/memory/indexer/enqueue-pending`

The frontend shows queue size, pending/indexed/failed counts, provider/model, configured/runtime device, and the latest indexing error.
