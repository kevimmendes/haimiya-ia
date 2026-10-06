#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import hashlib
from typing import List, Dict, Any, Optional

try:
    import chromadb
except Exception:
    chromadb = None


class VectorMemory:
    def __init__(self, persist_dir: str = "Arcana/Memoria/chroma"):
        self.persist_dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)
        self.client = None
        self.collection = None
        self.available = False
        self._init_client()

    def _init_client(self):
        if chromadb is None:
            return
        try:
            self.client = chromadb.PersistentClient(path=self.persist_dir)
            try:
                self.collection = self.client.get_or_create_collection(
                    name="haimiya_memory",
                    metadata={"hnsw:space": "cosine"}
                )
            except Exception:
                self.collection = self.client.get_or_create_collection(name="haimiya_memory")
            self.available = True
        except Exception as e:
            print(f"[VECTOR] Erro ao iniciar ChromaDB: {e}")

    def add_text(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        if not self.available or not self.collection or not text:
            return False
        try:
            doc_id = hashlib.sha256((text + json.dumps(metadata or {}, ensure_ascii=False)).encode("utf-8")).hexdigest()[:32]
            self.collection.add(documents=[text], metadatas=[metadata or {"source": "unknown"}], ids=[doc_id])
            return True
        except Exception as e:
            print(f"[VECTOR] Erro ao adicionar: {e}")
            return False

    def search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        if not self.available or not self.collection or not query:
            return []
        try:
            results = self.collection.query(query_texts=[query], n_results=min(n_results, 10))
            out = []
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            dists = results.get("distances", [[]])[0]
            for i, d in enumerate(docs):
                out.append({
                    "text": d,
                    "metadata": metas[i] if i < len(metas) else {},
                    "distance": dists[i] if i < len(dists) else 1.0
                })
            return out
        except Exception as e:
            print(f"[VECTOR] Erro na busca: {e}")
            return []


def get_vector_memory() -> VectorMemory:
    return VectorMemory()
