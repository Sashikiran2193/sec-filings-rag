"""Embed 10-K chunks and load them into a local Chroma vector store.

Usage: python embed_10k.py

Reads data/chunks/chunks.jsonl, embeds each chunk with
BAAI/bge-small-en-v1.5 in batches, and stores vectors, text and metadata in
the "sec_10k" collection under chroma/. The collection is rebuilt on every
run, so it always matches the current chunks file.

Filings say "we", not the company's name, so each chunk is embedded with a
header naming the company, year and section (see embed_text). The stored
text is the chunk alone.
"""

import json
import os
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # harmless on Windows

import chromadb
from fastembed import TextEmbedding

import keyword_index
from chunk_10k import tokenizer

CHUNKS_FILE = Path("data/chunks/chunks.jsonl")
CHROMA_DIR = Path("chroma")
COLLECTION = "sec_10k"

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
EMBED_DIM = 384
MODEL_MAX_TOKENS = 512
BATCH_SIZE = 64
# bge models expect this prefix on search queries (not on the stored chunks).
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def load_chunks() -> list[dict]:
    with CHUNKS_FILE.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def embed_text(chunk: dict) -> str:
    """What gets embedded: "Tesla, Inc. | FY2025 10-K | Item 1A Risk Factors" + the chunk."""
    header = f"{chunk['company']} | FY{chunk['year']} 10-K | {chunk['section']} {chunk['section_title']}"
    return f"{header}\n{chunk['text']}"


def check_lengths(texts: list[str]) -> int:
    """Fail early if anything would be cut off by the model's input limit; return the longest."""
    lengths = [len(e.ids) for e in tokenizer().encode_batch(texts)]  # includes special tokens
    too_long = sum(n > MODEL_MAX_TOKENS for n in lengths)
    if too_long:
        raise ValueError(f"{too_long} chunks exceed {MODEL_MAX_TOKENS} tokens; re-run chunk_10k.py")
    return max(lengths)


def embed_all(model: TextEmbedding, texts: list[str], progress: bool = True) -> list[list[float]]:
    vectors = []
    start = time.time()
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        vectors += [v.tolist() for v in model.embed(batch, batch_size=BATCH_SIZE)]
        if progress:
            done = i + len(batch)
            print(f"\rEmbedded {done}/{len(texts)} chunks ({time.time() - start:.0f}s)", end="")
    if progress:
        print()
    return vectors


def get_collection(client: chromadb.ClientAPI, reset: bool = False):
    if reset and COLLECTION in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION)
    return client.get_or_create_collection(
        COLLECTION,
        embedding_function=None,  # vectors are supplied by this script
        configuration={"hnsw": {"space": "cosine"}},
        metadata={"embedding_model": EMBED_MODEL, "dimension": EMBED_DIM},
    )


def filing_filter(ticker: str, year: str) -> dict:
    return {"$and": [{"ticker": ticker}, {"year": year}]}


def is_loaded(collection, ticker: str, year: str) -> bool:
    return bool(collection.get(where=filing_filter(ticker, year), limit=1)["ids"])


def replace_filing(collection, model: TextEmbedding, ticker: str, year: str, chunks: list[dict]) -> None:
    """Embed one filing's chunks and swap them in for any already stored."""
    texts = [embed_text(c) for c in chunks]
    check_lengths(texts)
    vectors = embed_all(model, texts, progress=False)
    collection.delete(where=filing_filter(ticker, year))
    store(collection, chunks, vectors)
    keyword_index.replace_filing(ticker, year, chunks)


def store(collection, chunks: list[dict], vectors: list[list[float]]) -> None:
    for i in range(0, len(chunks), BATCH_SIZE * 8):
        batch = chunks[i : i + BATCH_SIZE * 8]
        collection.add(
            ids=[c["id"] for c in batch],
            embeddings=vectors[i : i + len(batch)],
            documents=[c["text"] for c in batch],
            metadatas=[{k: v for k, v in c.items() if k not in ("id", "text")} for c in batch],
        )


def main() -> None:
    chunks = load_chunks()
    texts = [embed_text(c) for c in chunks]
    print(f"Longest input: {check_lengths(texts)} tokens (limit {MODEL_MAX_TOKENS})")
    model = TextEmbedding(EMBED_MODEL)
    vectors = embed_all(model, texts)
    assert len(vectors[0]) == EMBED_DIM, f"expected {EMBED_DIM} dims, got {len(vectors[0])}"

    collection = get_collection(chromadb.PersistentClient(path=str(CHROMA_DIR)), reset=True)
    store(collection, chunks, vectors)
    print(f"Stored {collection.count()} chunks in {CHROMA_DIR}/ (collection '{COLLECTION}')")
    keyword_index.rebuild(chunks)
    print(f"Rebuilt keyword index {keyword_index.DB_FILE}")


if __name__ == "__main__":
    main()
