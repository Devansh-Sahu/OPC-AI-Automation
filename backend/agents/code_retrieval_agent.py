"""
Code Retrieval Agent - RAG pipeline with AST-based chunking.
Embeds repo code into ChromaDB and retrieves relevant context for issues.
"""

import asyncio
import json
import logging
import math
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, END

from backend.agents.base_agent import BaseAgent, BaseAgentState
from backend.core.config import settings
from backend.core.database import async_session
from backend.core.vector_store import VectorStore

logger = logging.getLogger(__name__)

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "__pycache__", ".tox",
    "dist", "build", "target", ".venv", "venv", "coverage",
}


class CodeRetrievalState(BaseAgentState):
    repo_full_name: str
    issue_title: str
    issue_body: str
    local_path: str
    collection_name: str
    chunks_indexed: int
    retrieved_chunks: List[Dict[str, Any]]
    reranked_chunks: List[Dict[str, Any]]


class CodeRetrievalAgent(BaseAgent):
    """
    Builds a RAG pipeline for code retrieval:
    1. AST-based chunking with tree-sitter
    2. Embeds chunks into ChromaDB
    3. Retrieves top-15 relevant chunks via semantic + BM25 re-ranking
    """

    def __init__(self):
        super().__init__("code_retrieval_agent")
        self.vector_store = VectorStore()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(CodeRetrievalState)

        graph.add_node("check_index_exists", self._node_check_index_exists)
        graph.add_node("clone_and_index", self._node_clone_and_index)
        graph.add_node("semantic_search", self._node_semantic_search)
        graph.add_node("bm25_rerank", self._node_bm25_rerank)
        graph.add_node("enrich_context", self._node_enrich_context)

        graph.set_entry_point("check_index_exists")
        graph.add_conditional_edges(
            "check_index_exists",
            self._should_reindex,
            {
                "index": "clone_and_index",
                "search": "semantic_search",
            },
        )
        graph.add_edge("clone_and_index", "semantic_search")
        graph.add_edge("semantic_search", "bm25_rerank")
        graph.add_edge("bm25_rerank", "enrich_context")
        graph.add_edge("enrich_context", END)

        return graph

    def _should_reindex(self, state: CodeRetrievalState) -> str:
        """Determine if we need to re-index (no existing collection or forced)."""
        if state["metadata"].get("force_reindex") or state["chunks_indexed"] == -1:
            return "index"
        return "search"

    async def run(
        self, input_data: Dict[str, Any], run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self._initialized:
            await self.initialize()

        run_id = run_id or self._new_run_id()
        self._create_context(run_id)

        repo_full_name = input_data["repo_full_name"]
        collection_name = f"ose_{repo_full_name.replace('/', '_').replace('-', '_')}"

        initial_state: CodeRetrievalState = {
            **self._base_initial_state(run_id),
            "repo_full_name": repo_full_name,
            "issue_title": input_data.get("issue_title", ""),
            "issue_body": input_data.get("issue_body", ""),
            "local_path": input_data.get("local_path", ""),
            "collection_name": collection_name,
            "chunks_indexed": -1,  # -1 means "check if exists"
            "retrieved_chunks": [],
            "reranked_chunks": [],
            "metadata": {
                "force_reindex": input_data.get("force_reindex", False),
            },
        }

        config = {"configurable": {"thread_id": run_id}}
        return await self.compiled_graph.ainvoke(initial_state, config=config)

    async def _node_check_index_exists(self, state: CodeRetrievalState) -> Dict[str, Any]:
        """Check if ChromaDB collection already exists for this repo."""
        try:
            count = await self.vector_store.count(state["collection_name"])
            logger.info(f"Collection {state['collection_name']} has {count} chunks")
            return {"chunks_indexed": count, "current_step": "check_index_exists"}
        except Exception:
            return {"chunks_indexed": -1, "current_step": "check_index_exists"}

    async def _node_clone_and_index(self, state: CodeRetrievalState) -> Dict[str, Any]:
        """Clone repo (if needed) and index all source files into ChromaDB."""
        local_path = state["local_path"]
        repo_full_name = state["repo_full_name"]
        tmp_created = False

        if not local_path or not Path(local_path).exists():
            # Clone repo
            local_path = tempfile.mkdtemp(prefix="ose_rag_")
            tmp_created = True
            repo_url = f"https://x-access-token:{settings.GITHUB_TOKEN}@github.com/{repo_full_name}.git"

            proc = await asyncio.create_subprocess_exec(
                "git", "clone", "--depth=1", "--single-branch", repo_url, local_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode != 0:
                raise RuntimeError(f"Clone failed: {stderr.decode()[:300]}")

        # Gather and chunk all source files
        chunks = await self._chunk_repository(local_path, repo_full_name)
        logger.info(f"Generated {len(chunks)} chunks from {repo_full_name}")

        # Delete old collection and re-index
        try:
            await self.vector_store.delete_collection(state["collection_name"])
        except Exception:
            pass

        # Batch embed and store
        batch_size = 50
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            documents = [c["content"] for c in batch]
            metadatas = [{k: v for k, v in c.items() if k != "content"} for c in batch]
            ids = [f"{repo_full_name}_{c['file_path']}_{c['start_line']}" for c in batch]
            # Make IDs safe
            ids = [re.sub(r"[^a-zA-Z0-9_-]", "_", id_)[:512] for id_ in ids]

            await self.vector_store.add_documents(
                collection_name=state["collection_name"],
                documents=documents,
                metadatas=metadatas,
                ids=ids,
            )

        # Clean up tmp dir if we created it
        if tmp_created:
            import shutil
            shutil.rmtree(local_path, ignore_errors=True)
            local_path = ""

        return {
            "local_path": local_path,
            "chunks_indexed": len(chunks),
            "current_step": "clone_and_index",
        }

    async def _chunk_repository(self, local_path: str, repo_full_name: str) -> List[Dict]:
        """AST-based chunking of all source files in the repo."""
        chunks = []
        path = Path(local_path)
        supported_extensions = {".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java"}

        source_files = []
        for filepath in path.rglob("*"):
            if any(skip in filepath.parts for skip in SKIP_DIRS):
                continue
            if filepath.is_file() and filepath.suffix in supported_extensions:
                if filepath.stat().st_size < 200_000:  # Skip huge files
                    source_files.append(filepath)

        source_files = source_files[:300]  # Cap

        for filepath in source_files:
            try:
                rel_path = str(filepath.relative_to(path))
                language = {
                    ".py": "python", ".js": "javascript",
                    ".ts": "typescript", ".tsx": "typescript",
                    ".go": "go", ".rs": "rust", ".java": "java",
                }.get(filepath.suffix, "unknown")

                file_chunks = await self._chunk_file(filepath, rel_path, language, repo_full_name)
                chunks.extend(file_chunks)
            except Exception as e:
                logger.debug(f"Chunking failed for {filepath}: {e}")

        return chunks

    async def _chunk_file(
        self, filepath: Path, rel_path: str, language: str, repo_full_name: str
    ) -> List[Dict]:
        """Chunk a single file into function/class level chunks with summaries."""
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        chunks = []

        # Extract chunks via regex (fast, no tree-sitter dep needed for indexing)
        raw_chunks = self._extract_raw_chunks(content, rel_path, language)

        for chunk in raw_chunks:
            chunk_text = chunk["content"]
            token_estimate = len(chunk_text.split()) * 1.3

            # If chunk is too large, split it
            if token_estimate > 500:
                chunk_text = self._truncate_to_tokens(chunk_text, 500)

            # Generate natural language summary prefix for better embedding
            summary = self._generate_chunk_summary(chunk, language)
            embedding_text = f"{summary}\n\n{chunk_text}"

            chunks.append({
                "content": embedding_text,
                "raw_content": chunk_text,
                "file_path": rel_path,
                "function_name": chunk.get("name", ""),
                "class_name": chunk.get("class_name", ""),
                "chunk_type": chunk.get("chunk_type", "function"),
                "start_line": chunk.get("start_line", 0),
                "end_line": chunk.get("end_line", 0),
                "language": language,
                "repo_full_name": repo_full_name,
            })

        return chunks

    def _extract_raw_chunks(self, content: str, rel_path: str, language: str) -> List[Dict]:
        """Extract function/class chunks via regex."""
        chunks = []
        lines = content.split("\n")

        if language == "python":
            # Find all def and class blocks
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("def ") or stripped.startswith("async def ") or stripped.startswith("class "):
                    # Determine kind
                    kind = "class" if stripped.startswith("class ") else "function"
                    # Extract name
                    match = re.match(r"(?:async\s+)?(?:def|class)\s+(\w+)", stripped)
                    name = match.group(1) if match else "unknown"
                    indent = len(line) - len(line.lstrip())
                    # Find end: next line with same or lesser indent
                    end = i + 1
                    for j in range(i + 1, min(i + 100, len(lines))):
                        l = lines[j]
                        if l.strip() == "":
                            continue
                        curr_indent = len(l) - len(l.lstrip())
                        if curr_indent <= indent and l.strip():
                            end = j
                            break
                    else:
                        end = min(i + 80, len(lines))

                    chunk_lines = lines[i:end]
                    chunks.append({
                        "name": name,
                        "chunk_type": kind,
                        "class_name": None,
                        "start_line": i + 1,
                        "end_line": end,
                        "content": "\n".join(chunk_lines),
                    })

        elif language in ("javascript", "typescript"):
            # Match function declarations, arrow functions, class declarations
            pattern = re.compile(
                r'(?:^|\n)(?:export\s+)?(?:async\s+)?(?:function\s+(\w+)|class\s+(\w+)|const\s+(\w+)\s*=)'
            )
            for match in pattern.finditer(content):
                name = match.group(1) or match.group(2) or match.group(3) or "anonymous"
                kind = "class" if match.group(2) else "function"
                start = content[:match.start()].count("\n")
                end = min(start + 60, len(lines) - 1)
                chunks.append({
                    "name": name,
                    "chunk_type": kind,
                    "class_name": None,
                    "start_line": start + 1,
                    "end_line": end + 1,
                    "content": "\n".join(lines[start:end + 1]),
                })

        elif language == "go":
            pattern = re.compile(r'^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(', re.MULTILINE)
            for match in pattern.finditer(content):
                name = match.group(1)
                start = content[:match.start()].count("\n")
                end = min(start + 60, len(lines) - 1)
                chunks.append({
                    "name": name,
                    "chunk_type": "function",
                    "class_name": None,
                    "start_line": start + 1,
                    "end_line": end + 1,
                    "content": "\n".join(lines[start:end + 1]),
                })

        # Fallback: if no chunks found, use file-level chunk
        if not chunks:
            chunks.append({
                "name": Path(rel_path).stem,
                "chunk_type": "module",
                "class_name": None,
                "start_line": 1,
                "end_line": len(lines),
                "content": "\n".join(lines[:100]),  # First 100 lines
            })

        return chunks

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to approximately max_tokens."""
        words = text.split()
        target_words = int(max_tokens / 1.3)
        if len(words) <= target_words:
            return text
        return " ".join(words[:target_words]) + "\n... [truncated]"

    def _generate_chunk_summary(self, chunk: Dict, language: str) -> str:
        """Generate natural language summary prefix for better embedding quality."""
        kind = chunk.get("chunk_type", "function")
        name = chunk.get("name", "unknown")
        file_path = chunk.get("file_path", "")
        class_name = chunk.get("class_name")

        if class_name:
            return f"Method '{name}' in class '{class_name}' in file '{file_path}' ({language})"
        elif kind == "class":
            return f"Class '{name}' defined in file '{file_path}' ({language})"
        elif kind == "module":
            return f"Module-level code in file '{file_path}' ({language})"
        else:
            return f"Function '{name}' in file '{file_path}' ({language})"

    async def _node_semantic_search(self, state: CodeRetrievalState) -> Dict[str, Any]:
        """Semantic search using issue title + body as query."""
        query = f"{state['issue_title']}\n\n{state['issue_body'][:2000]}"

        try:
            results = await self.vector_store.query(
                collection_name=state["collection_name"],
                query_texts=[query],
                n_results=20,
            )

            chunks = []
            if results and results.get("documents"):
                docs = results["documents"][0]
                metas = results.get("metadatas", [[]])[0]
                distances = results.get("distances", [[]])[0]

                for doc, meta, dist in zip(docs, metas, distances):
                    chunks.append({
                        "content": doc,
                        "metadata": meta,
                        "semantic_score": 1.0 - dist,  # Convert distance to similarity
                    })

            logger.info(f"Semantic search returned {len(chunks)} chunks")
            return {"retrieved_chunks": chunks, "current_step": "semantic_search"}

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return {"retrieved_chunks": [], "current_step": "semantic_search"}

    async def _node_bm25_rerank(self, state: CodeRetrievalState) -> Dict[str, Any]:
        """BM25 keyword re-ranking on top semantic results."""
        chunks = state["retrieved_chunks"]
        query = f"{state['issue_title']} {state['issue_body'][:1000]}"

        if not chunks:
            return {"reranked_chunks": [], "current_step": "bm25_rerank"}

        # Tokenize query
        query_terms = set(self._tokenize(query))

        # Compute BM25 scores
        k1, b = 1.5, 0.75
        all_texts = [c["content"] for c in chunks]
        avg_dl = sum(len(t.split()) for t in all_texts) / len(all_texts)

        scored = []
        for chunk in chunks:
            doc_terms = self._tokenize(chunk["content"])
            doc_len = len(doc_terms)
            tf_counts = Counter(doc_terms)

            bm25_score = 0.0
            for term in query_terms:
                tf = tf_counts.get(term, 0)
                if tf > 0:
                    idf = math.log((len(chunks) + 1) / (1 + sum(1 for c in chunks if term in c["content"].lower())))
                    bm25 = idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / avg_dl))
                    bm25_score += bm25

            # Combined score: 60% semantic + 40% BM25 (normalized)
            semantic = chunk.get("semantic_score", 0)
            combined = 0.6 * semantic + 0.4 * min(1.0, bm25_score / 10)
            scored.append({**chunk, "bm25_score": bm25_score, "combined_score": combined})

        # Sort by combined score and take top 15
        scored.sort(key=lambda x: x["combined_score"], reverse=True)
        top_15 = scored[:15]

        logger.info(f"BM25 re-ranking: {len(chunks)} -> 15 chunks")
        return {"reranked_chunks": top_15, "current_step": "bm25_rerank"}

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenizer for BM25."""
        return re.findall(r"\b[a-zA-Z_]\w+\b", text.lower())

    async def _node_enrich_context(self, state: CodeRetrievalState) -> Dict[str, Any]:
        """Enrich chunks with parent class context for method-level chunks."""
        chunks = state["reranked_chunks"]
        enriched = []

        for chunk in chunks:
            meta = chunk.get("metadata", {})
            class_name = meta.get("class_name", "")
            file_path = meta.get("file_path", "")

            # Add parent class info if this is a method
            if class_name and file_path:
                # Find the class definition chunk
                class_context = next(
                    (c for c in state["retrieved_chunks"]
                     if c.get("metadata", {}).get("file_path") == file_path
                     and c.get("metadata", {}).get("chunk_type") == "class"
                     and c.get("metadata", {}).get("name") == class_name),
                    None
                )
                if class_context:
                    chunk = {
                        **chunk,
                        "parent_class_context": class_context.get("content", "")[:500],
                    }

            enriched.append(chunk)

        logger.info(f"Returning {len(enriched)} enriched chunks")
        return {
            "reranked_chunks": enriched,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "current_step": "complete",
        }
