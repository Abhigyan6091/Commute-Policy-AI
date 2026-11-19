import hashlib
import math
import re
import time
from collections import OrderedDict
from threading import Lock
import chromadb
from chromadb.config import Settings as ChromaSettings
from rank_bm25 import BM25Okapi
from app.schemas import Chunk
from app.security import suspicious

def tokens(text):
    return re.findall(r'[a-z0-9]+', text.lower())

def reciprocal_rank_fusion(dense_results, bm25_results, k=60, top_n=3):
    scores = {}
    for rank, chunk in enumerate(dense_results):
        cid = chunk['chunk_id'] if isinstance(chunk, dict) else chunk.chunk_id
        scores[cid] = scores.get(cid, 0) + 1 / (k + rank + 1)
    for rank, chunk in enumerate(bm25_results):
        cid = chunk['chunk_id'] if isinstance(chunk, dict) else chunk.chunk_id
        scores[cid] = scores.get(cid, 0) + 1 / (k + rank + 1)
    # merge all candidates
    all_chunks = {(c['chunk_id'] if isinstance(c, dict) else c.chunk_id): c for c in dense_results + bm25_results}
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [all_chunks[cid] for cid, _ in ranked[:top_n]]

class LocalEmbedder:
    def __init__(self, model, device):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model, device=device)
        self.lock = Lock()
        self.encode(['transport policy'])
    def encode(self, texts):
        with self.lock:
            return self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()

class FakeEmbedder:
    # Offline test double; deliberately not a semantic model.
    def encode(self, texts):
        result = []
        for text in texts:
            vector = [0.0] * 256
            for word in tokens(text):
                i = int.from_bytes(hashlib.sha256(word.encode()).digest()[:4], 'big') % 256
                vector[i] += 1
            norm = math.sqrt(sum(v*v for v in vector)) or 1
            result.append([v/norm for v in vector])
        return result

def scope(company, version):
    return {'$and': [{'company_id': {'$eq': company}}, {'policy_version': {'$eq': version}}]}

class VectorStore:
    def __init__(self, path, embedding_model):
        self.client = chromadb.PersistentClient(path=str(path), settings=ChromaSettings(anonymized_telemetry=False))
        # Model fingerprint prevents mixing incompatible embedding spaces after config changes.
        name = 'policy_' + hashlib.sha256(embedding_model.encode()).hexdigest()[:20]
        self.collection = self.client.get_or_create_collection(name, metadata={'hnsw:space': 'cosine'})
    def add(self, chunks, embeddings):
        if len(chunks) != len(embeddings):
            raise ValueError('Incomplete embedding batch')
        for offset in range(0, len(chunks), 100):
            batch = chunks[offset:offset+100]
            self.collection.add(ids=[c.chunk_id for c in batch],
                embeddings=embeddings[offset:offset+100], documents=[c.text for c in batch],
                metadatas=[{k: v for k, v in c.model_dump(exclude={'text'}).items() if v is not None} for c in batch])
    def verify(self, company, version, chunks):
        result = self.collection.get(where=scope(company, version), include=['metadatas', 'documents'])
        expected = {c.chunk_id: c for c in chunks}
        if set(result['ids']) != set(expected):
            raise ValueError('Incomplete vector insertion')
        for ident, meta, text in zip(result['ids'], result['metadatas'], result['documents']):
            c = Chunk.model_validate({**meta, 'text': text})
            if c != expected[ident] or hashlib.sha256(text.encode()).hexdigest() != c.content_hash:
                raise ValueError('Vector metadata or text mismatch')
    def delete(self, company, version):
        self.collection.delete(where=scope(company, version))
    def search(self, vector, company, version, count):
        result = self.collection.query(query_embeddings=[vector], where=scope(company, version),
            n_results=count, include=['metadatas', 'documents', 'distances'])
        return [(Chunk.model_validate({**m, 'text': t}), 1-float(d))
            for m, t, d in zip(result['metadatas'][0], result['documents'][0], result['distances'][0])]

class Retriever:
    def __init__(self, db, vectors, embedder, settings):
        self.db, self.vectors, self.embedder, self.settings = db, vectors, embedder, settings
        self.indexes, self.lock = OrderedDict(), Lock()
    def index(self, company, version):
        key = (company, version)
        with self.lock:
            if key not in self.indexes:
                chunks = self.db.chunks(company, version)
                if not chunks:
                    return [], None
                self.indexes[key] = (chunks, BM25Okapi([tokens(c.text) for c in chunks]))
                while len(self.indexes) > 24:
                    self.indexes.popitem(last=False)
            self.indexes.move_to_end(key)
            chunks_ref, index_ref = self.indexes[key]  # snapshot reference under lock
        return chunks_ref, index_ref
    def retrieve(self, company, version, question, mode=None):
        started = time.perf_counter()
        chunks, index = self.index(company, version)
        if not chunks:
            return [], {'embedding': 0.0, 'retrieval': 0.0}
        emb_start = time.perf_counter()
        vector = self.embedder.encode([question])[0]
        emb_ms = (time.perf_counter() - emb_start)*1000
        dense = self.vectors.search(vector, company, version, min(12, len(chunks)))
        authoritative = {c.chunk_id: c for c in chunks}
        def valid(c):
            if c.company_id != company or c.policy_version != version or authoritative.get(c.chunk_id) != c:
                raise ValueError('Retrieved evidence violates authoritative scope')
            return not suspicious(c.text) and not suspicious(c.section_title)
        dense = sorted([(c, score) for c, score in dense if valid(c)],
                       key=lambda pair: (-pair[1], pair[0].section_number, pair[0].content_hash))
        dense_candidates = [c for c, score in dense if score >= self.settings.relevance_threshold]
        
        retrieval_mode = mode or self.settings.retrieval_mode
        if retrieval_mode == 'hybrid' and index is not None:
            scores = index.get_scores(tokens(question))
            bm25_candidates = [chunks[i] for i in sorted(range(len(chunks)),
                key=lambda i: (-scores[i], chunks[i].section_number, chunks[i].content_hash))
                               if scores[i] > 0 and valid(chunks[i])][:min(3, len(chunks))]
            selected = reciprocal_rank_fusion(dense_candidates, bm25_candidates, k=60, top_n=3)
        else:
            selected = dense_candidates[:3]
        return selected, {'embedding': emb_ms, 'retrieval': (time.perf_counter()-started)*1000-emb_ms}
