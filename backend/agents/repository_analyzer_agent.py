"""
Repository Analyzer Agent - Deep static analysis of repositories.
Clones, parses AST, computes metrics, builds dependency graph.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict

from langgraph.graph import StateGraph, END

from backend.agents.base_agent import BaseAgent, BaseAgentState
from backend.core.config import settings
from backend.core.database import async_session

logger = logging.getLogger(__name__)

# File extension -> language mapping
EXTENSION_LANGUAGE_MAP = {
    ".py": "python", ".pyx": "python", ".pyi": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".c": "c",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".swift": "swift",
    ".scala": "scala",
    ".r": "r", ".R": "r",
}

# Dependency files -> framework detection
FRAMEWORK_INDICATORS = {
    "requirements.txt": {"django": "Django", "flask": "Flask", "fastapi": "FastAPI",
                         "tornado": "Tornado", "aiohttp": "aiohttp"},
    "package.json": {"react": "React", "vue": "Vue", "angular": "@angular",
                     "next": "Next.js", "express": "Express", "nestjs": "@nestjs",
                     "svelte": "Svelte", "nuxt": "Nuxt"},
    "Cargo.toml": {"actix-web": "Actix", "axum": "Axum", "rocket": "Rocket",
                   "warp": "Warp", "hyper": "Hyper"},
    "go.mod": {"gin-gonic": "Gin", "echo": "Echo", "fiber": "Fiber",
               "chi": "Chi", "gorilla/mux": "Gorilla Mux"},
    "pom.xml": {"spring-boot": "Spring Boot", "quarkus": "Quarkus",
                "micronaut": "Micronaut"},
    "build.gradle": {"spring-boot": "Spring Boot"},
}

TEST_FRAMEWORK_INDICATORS = {
    "pytest": ("pytest.ini", "pyproject.toml", "setup.cfg"),
    "unittest": ("test_*.py",),
    "jest": ("jest.config.js", "jest.config.ts"),
    "vitest": ("vitest.config.ts", "vitest.config.js"),
    "mocha": (".mocharc.js", ".mocharc.yml"),
    "go_test": ("_test.go",),
    "cargo_test": ("Cargo.toml",),
    "rspec": ("spec/", ".rspec"),
}


class RepositoryAnalyzerState(BaseAgentState):
    repo_full_name: str
    repo_url: str
    local_path: str
    language_distribution: Dict[str, int]
    primary_language: str
    frameworks: List[str]
    test_framework: str
    build_system: str
    file_tree: List[Dict[str, Any]]
    ast_chunks: List[Dict[str, Any]]
    metrics: Dict[str, Any]
    dependency_graph: Dict[str, List[str]]
    architecture_pattern: str
    hotspot_files: List[str]
    maintainer_responsiveness: float
    contribution_patterns: Dict[str, Any]
    analysis_result: Dict[str, Any]


class RepositoryAnalyzerAgent(BaseAgent):
    """
    Performs deep static analysis of a repository:
    shallow clone -> language/framework detection -> AST parsing ->
    metrics computation -> dependency graph -> hotspot detection.
    """

    def __init__(self):
        super().__init__("repository_analyzer_agent")

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(RepositoryAnalyzerState)

        graph.add_node("clone_repo", self._node_clone_repo)
        graph.add_node("detect_stack", self._node_detect_stack)
        graph.add_node("build_file_tree", self._node_build_file_tree)
        graph.add_node("parse_ast", self._node_parse_ast)
        graph.add_node("compute_metrics", self._node_compute_metrics)
        graph.add_node("build_dependency_graph", self._node_build_dependency_graph)
        graph.add_node("detect_architecture", self._node_detect_architecture)
        graph.add_node("analyze_git_history", self._node_analyze_git_history)
        graph.add_node("assemble_result", self._node_assemble_result)
        graph.add_node("save_to_db", self._node_save_to_db)
        graph.add_node("cleanup", self._node_cleanup)

        graph.set_entry_point("clone_repo")
        graph.add_edge("clone_repo", "detect_stack")
        graph.add_edge("detect_stack", "build_file_tree")
        graph.add_edge("build_file_tree", "parse_ast")
        graph.add_edge("parse_ast", "compute_metrics")
        graph.add_edge("compute_metrics", "build_dependency_graph")
        graph.add_edge("build_dependency_graph", "detect_architecture")
        graph.add_edge("detect_architecture", "analyze_git_history")
        graph.add_edge("analyze_git_history", "assemble_result")
        graph.add_edge("assemble_result", "save_to_db")
        graph.add_edge("save_to_db", "cleanup")
        graph.add_edge("cleanup", END)

        return graph

    async def run(
        self, input_data: Dict[str, Any], run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self._initialized:
            await self.initialize()

        run_id = run_id or self._new_run_id()
        self._create_context(run_id)

        repo_full_name = input_data["repo_full_name"]
        repo_url = input_data.get("repo_url", f"https://github.com/{repo_full_name}.git")

        initial_state: RepositoryAnalyzerState = {
            **self._base_initial_state(run_id),
            "repo_full_name": repo_full_name,
            "repo_url": repo_url,
            "local_path": "",
            "language_distribution": {},
            "primary_language": "",
            "frameworks": [],
            "test_framework": "",
            "build_system": "",
            "file_tree": [],
            "ast_chunks": [],
            "metrics": {},
            "dependency_graph": {},
            "architecture_pattern": "unknown",
            "hotspot_files": [],
            "maintainer_responsiveness": 0.5,
            "contribution_patterns": {},
            "analysis_result": {},
        }

        config = {"configurable": {"thread_id": run_id}}
        return await self.compiled_graph.ainvoke(initial_state, config=config)

    async def _node_clone_repo(self, state: RepositoryAnalyzerState) -> Dict[str, Any]:
        """Shallow clone repository to temp dir."""
        tmp_dir = tempfile.mkdtemp(prefix="ose_repo_")
        repo_url = state["repo_url"]

        # Add token auth for private repos
        if settings.GITHUB_TOKEN:
            repo_url = repo_url.replace(
                "https://github.com",
                f"https://x-access-token:{settings.GITHUB_TOKEN}@github.com"
            )

        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "clone", "--depth=1", "--single-branch",
                repo_url, tmp_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            if proc.returncode != 0:
                raise RuntimeError(f"git clone failed: {stderr.decode()[:500]}")

            logger.info(f"Cloned {state['repo_full_name']} to {tmp_dir}")
            return {"local_path": tmp_dir, "current_step": "clone_repo"}

        except asyncio.TimeoutError:
            raise RuntimeError(f"Clone timed out for {state['repo_full_name']}")

    async def _node_detect_stack(self, state: RepositoryAnalyzerState) -> Dict[str, Any]:
        """Detect primary language, frameworks, test framework, build system."""
        local_path = Path(state["local_path"])

        # Language distribution from file extensions
        lang_counts: Dict[str, int] = defaultdict(int)
        for filepath in local_path.rglob("*"):
            if filepath.is_file():
                ext = filepath.suffix.lower()
                lang = EXTENSION_LANGUAGE_MAP.get(ext)
                if lang:
                    lang_counts[lang] += 1

        primary_language = max(lang_counts, key=lang_counts.get) if lang_counts else "unknown"

        # Framework detection from dependency files
        frameworks = []
        for dep_file, indicators in FRAMEWORK_INDICATORS.items():
            dep_path = local_path / dep_file
            if dep_path.exists():
                try:
                    content = dep_path.read_text(encoding="utf-8", errors="ignore").lower()
                    for keyword, framework_name in indicators.items():
                        if keyword.lower() in content:
                            frameworks.append(framework_name)
                except Exception:
                    pass

        # Test framework detection
        test_framework = "unknown"
        test_priority = [
            ("pytest", ["pytest.ini", "pyproject.toml", "setup.cfg"], "pytest"),
            ("jest", ["jest.config.js", "jest.config.ts", "package.json"], "jest"),
            ("vitest", ["vitest.config.ts", "vitest.config.js"], "vitest"),
            ("mocha", [".mocharc.js", ".mocharc.yml", ".mocharc.yaml"], "mocha"),
        ]

        for _, files, name in test_priority:
            for f in files:
                if (local_path / f).exists():
                    content = ""
                    try:
                        content = (local_path / f).read_text(encoding="utf-8", errors="ignore").lower()
                    except Exception:
                        pass
                    if name in content or (local_path / f).name in ["pytest.ini"]:
                        test_framework = name
                        break
            if test_framework != "unknown":
                break

        # Check Go test
        if list(local_path.rglob("*_test.go")):
            test_framework = "go_test"

        # Check cargo test
        if (local_path / "Cargo.toml").exists():
            test_framework = "cargo_test"

        # Build system detection
        build_system = "unknown"
        build_indicators = [
            ("Makefile", "make"), ("CMakeLists.txt", "cmake"),
            ("build.gradle", "gradle"), ("pom.xml", "maven"),
            ("package.json", "npm"),  # Will refine below
            ("Cargo.toml", "cargo"), ("go.mod", "go_build"),
            ("setup.py", "setuptools"), ("pyproject.toml", "pyproject"),
        ]

        for filename, build_name in build_indicators:
            if (local_path / filename).exists():
                build_system = build_name
                break

        # Refine npm vs yarn vs pnpm
        if build_system == "npm":
            if (local_path / "yarn.lock").exists():
                build_system = "yarn"
            elif (local_path / "pnpm-lock.yaml").exists():
                build_system = "pnpm"

        return {
            "language_distribution": dict(lang_counts),
            "primary_language": primary_language,
            "frameworks": list(set(frameworks)),
            "test_framework": test_framework,
            "build_system": build_system,
            "current_step": "detect_stack",
        }

    async def _node_build_file_tree(self, state: RepositoryAnalyzerState) -> Dict[str, Any]:
        """Build a structured file tree (excluding vendor/node_modules/etc)."""
        local_path = Path(state["local_path"])
        SKIP_DIRS = {
            ".git", "node_modules", "vendor", "__pycache__", ".tox",
            "dist", "build", "target", ".venv", "venv", ".env",
            "coverage", ".pytest_cache", ".mypy_cache",
        }

        file_tree = []
        for filepath in local_path.rglob("*"):
            # Skip excluded dirs
            if any(skip in filepath.parts for skip in SKIP_DIRS):
                continue
            if not filepath.is_file():
                continue

            rel_path = str(filepath.relative_to(local_path))
            try:
                size = filepath.stat().st_size
                file_tree.append({
                    "path": rel_path,
                    "size_bytes": size,
                    "extension": filepath.suffix.lower(),
                    "language": EXTENSION_LANGUAGE_MAP.get(filepath.suffix.lower(), ""),
                })
            except Exception:
                pass

        logger.info(f"File tree: {len(file_tree)} files")
        return {"file_tree": file_tree, "current_step": "build_file_tree"}

    async def _node_parse_ast(self, state: RepositoryAnalyzerState) -> Dict[str, Any]:
        """Parse AST for all supported source files using tree-sitter."""
        local_path = Path(state["local_path"])
        primary_lang = state["primary_language"]
        all_chunks = []

        # Get source files to parse (limit to primary language)
        source_files = [
            f for f in state["file_tree"]
            if f["language"] == primary_lang and f["size_bytes"] < 500_000
        ][:200]  # Cap at 200 files

        for file_info in source_files:
            filepath = local_path / file_info["path"]
            try:
                chunks = await self._parse_file_ast(filepath, primary_lang, file_info["path"])
                all_chunks.extend(chunks)
            except Exception as e:
                logger.debug(f"AST parse failed for {file_info['path']}: {e}")

        logger.info(f"Parsed {len(all_chunks)} AST chunks from {len(source_files)} files")
        return {"ast_chunks": all_chunks, "current_step": "parse_ast"}

    async def _parse_file_ast(self, filepath: Path, language: str, rel_path: str) -> List[Dict]:
        """Parse a single file into AST chunks using tree-sitter or regex fallback."""
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        chunks = []

        try:
            import tree_sitter_python as tspython
            import tree_sitter_javascript as tsjavascript
            from tree_sitter import Language, Parser

            lang_map = {
                "python": (tspython, "python"),
                "javascript": (tsjavascript, "javascript"),
            }

            if language in lang_map:
                ts_module, lang_name = lang_map[language]
                lang_obj = Language(ts_module.language())
                parser = Parser(lang_obj)
                tree = parser.parse(content.encode("utf-8"))
                chunks = self._extract_tree_sitter_chunks(tree, content, rel_path, language)
            else:
                chunks = self._regex_extract_chunks(content, rel_path, language)
        except ImportError:
            # Fallback to regex-based extraction
            chunks = self._regex_extract_chunks(content, rel_path, language)

        return chunks

    def _extract_tree_sitter_chunks(self, tree, content: str, rel_path: str, language: str) -> List[Dict]:
        """Extract function/class chunks from tree-sitter AST."""
        chunks = []
        lines = content.split("\n")

        def visit_node(node, parent_class=None):
            if node.type in ("function_definition", "function_declaration", "method_definition",
                              "arrow_function", "class_definition", "class_declaration"):
                start_line = node.start_point[0]
                end_line = node.end_point[0]
                chunk_text = "\n".join(lines[start_line:end_line + 1])

                # Extract name
                name = "anonymous"
                for child in node.children:
                    if child.type in ("identifier", "name"):
                        name = child.text.decode("utf-8") if isinstance(child.text, bytes) else str(child.text)
                        break

                chunk_type = "class" if "class" in node.type else "function"

                chunks.append({
                    "file_path": rel_path,
                    "chunk_type": chunk_type,
                    "name": name,
                    "class_name": parent_class,
                    "start_line": start_line + 1,
                    "end_line": end_line + 1,
                    "content": chunk_text[:3000],  # Limit chunk size
                    "language": language,
                    "token_count_estimate": len(chunk_text.split()) * 1.3,
                })

                # Visit children for nested classes/methods
                new_parent = name if chunk_type == "class" else parent_class
                for child in node.children:
                    visit_node(child, new_parent)
            else:
                for child in node.children:
                    visit_node(child, parent_class)

        visit_node(tree.root_node)
        return chunks

    def _regex_extract_chunks(self, content: str, rel_path: str, language: str) -> List[Dict]:
        """Fallback regex-based chunk extraction."""
        chunks = []
        lines = content.split("\n")

        if language == "python":
            # Match function and class definitions
            pattern = re.compile(r'^(class|def)\s+(\w+)', re.MULTILINE)
            for match in pattern.finditer(content):
                kind = "class" if match.group(1) == "class" else "function"
                name = match.group(2)
                start_line = content[:match.start()].count("\n")
                # Estimate end line (next top-level def/class or EOF)
                end_line = min(start_line + 50, len(lines) - 1)
                chunk_text = "\n".join(lines[start_line:end_line + 1])
                chunks.append({
                    "file_path": rel_path,
                    "chunk_type": kind,
                    "name": name,
                    "class_name": None,
                    "start_line": start_line + 1,
                    "end_line": end_line + 1,
                    "content": chunk_text[:3000],
                    "language": language,
                    "token_count_estimate": len(chunk_text.split()) * 1.3,
                })

        elif language in ("javascript", "typescript"):
            pattern = re.compile(
                r'(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s*)?\(|class\s+(\w+))',
                re.MULTILINE
            )
            for match in pattern.finditer(content):
                name = match.group(1) or match.group(2) or match.group(3) or "anonymous"
                kind = "class" if match.group(3) else "function"
                start_line = content[:match.start()].count("\n")
                end_line = min(start_line + 40, len(lines) - 1)
                chunk_text = "\n".join(lines[start_line:end_line + 1])
                chunks.append({
                    "file_path": rel_path,
                    "chunk_type": kind,
                    "name": name,
                    "class_name": None,
                    "start_line": start_line + 1,
                    "end_line": end_line + 1,
                    "content": chunk_text[:3000],
                    "language": language,
                    "token_count_estimate": len(chunk_text.split()) * 1.3,
                })

        return chunks

    async def _node_compute_metrics(self, state: RepositoryAnalyzerState) -> Dict[str, Any]:
        """Compute cyclomatic complexity and other code metrics."""
        chunks = state["ast_chunks"]
        file_tree = state["file_tree"]

        total_functions = sum(1 for c in chunks if c["chunk_type"] == "function")
        total_classes = sum(1 for c in chunks if c["chunk_type"] == "class")
        total_files = len(file_tree)
        total_source_files = sum(1 for f in file_tree if f["language"] != "")

        # Estimate cyclomatic complexity via branch keyword counting
        def estimate_complexity(chunk: Dict) -> int:
            content = chunk.get("content", "")
            keywords = ["if ", "elif ", "else:", "for ", "while ", "except ",
                        "case ", "&&", "||", "?"]
            count = sum(content.count(kw) for kw in keywords)
            return max(1, count + 1)  # McCabe formula: branches + 1

        complexities = [estimate_complexity(c) for c in chunks]
        avg_complexity = sum(complexities) / len(complexities) if complexities else 1.0
        high_complexity_funcs = sum(1 for c in complexities if c > 10)

        # File size statistics
        file_sizes = [f["size_bytes"] for f in file_tree]
        avg_file_size = sum(file_sizes) / len(file_sizes) if file_sizes else 0

        metrics = {
            "total_files": total_files,
            "total_source_files": total_source_files,
            "total_functions": total_functions,
            "total_classes": total_classes,
            "total_ast_chunks": len(chunks),
            "avg_cyclomatic_complexity": round(avg_complexity, 2),
            "high_complexity_function_count": high_complexity_funcs,
            "avg_file_size_bytes": round(avg_file_size, 0),
            "largest_file_bytes": max(file_sizes) if file_sizes else 0,
        }

        logger.info(f"Metrics: {metrics}")
        return {"metrics": metrics, "current_step": "compute_metrics"}

    async def _node_build_dependency_graph(self, state: RepositoryAnalyzerState) -> Dict[str, Any]:
        """Build import/dependency graph for source files."""
        local_path = Path(state["local_path"])
        primary_lang = state["primary_language"]
        dep_graph: Dict[str, List[str]] = {}

        source_files = [
            f for f in state["file_tree"]
            if f["language"] == primary_lang
        ][:100]

        for file_info in source_files:
            filepath = local_path / file_info["path"]
            try:
                content = filepath.read_text(encoding="utf-8", errors="ignore")
                imports = self._extract_imports(content, primary_lang)
                dep_graph[file_info["path"]] = imports
            except Exception:
                pass

        return {"dependency_graph": dep_graph, "current_step": "build_dependency_graph"}

    def _extract_imports(self, content: str, language: str) -> List[str]:
        """Extract import statements from source code."""
        imports = []
        if language == "python":
            pattern = re.compile(r'^(?:import|from)\s+([\w.]+)', re.MULTILINE)
            imports = [m.group(1) for m in pattern.finditer(content)]
        elif language in ("javascript", "typescript"):
            pattern = re.compile(r'(?:import|require)\s*\(?["\']([^"\']+)["\']', re.MULTILINE)
            imports = [m.group(1) for m in pattern.finditer(content)]
        elif language == "go":
            pattern = re.compile(r'"([^"]+)"', re.MULTILINE)
            in_import = False
            for line in content.split("\n"):
                if "import (" in line:
                    in_import = True
                elif in_import and ")" in line:
                    in_import = False
                elif in_import:
                    m = pattern.search(line)
                    if m:
                        imports.append(m.group(1))
        return imports[:50]  # Cap

    async def _node_detect_architecture(self, state: RepositoryAnalyzerState) -> Dict[str, Any]:
        """Detect architectural pattern from file structure and imports."""
        file_tree = state["file_tree"]
        paths = [f["path"] for f in file_tree]
        paths_lower = [p.lower() for p in paths]

        pattern = "monolith"

        # Check for microservices indicators
        if any("service" in p or "svc" in p for p in paths_lower):
            if len([p for p in paths_lower if "service" in p]) > 3:
                pattern = "microservices"

        # Check for MVC
        mvc_dirs = {"models", "views", "controllers", "templates"}
        found_mvc = sum(1 for d in mvc_dirs if any(d in p for p in paths_lower))
        if found_mvc >= 3:
            pattern = "mvc"

        # Check for event-driven
        if any(kw in " ".join(paths_lower) for kw in ["event", "handler", "subscriber", "publisher", "queue"]):
            pattern = "event-driven"

        # Check for plugin-based
        if any(kw in " ".join(paths_lower) for kw in ["plugin", "extension", "addon", "middleware"]):
            pattern = "plugin-based"

        # Check for layered (clean/hexagonal)
        if any(d in " ".join(paths_lower) for d in ["domain", "usecase", "infrastructure", "adapter", "port"]):
            pattern = "clean-architecture"

        return {"architecture_pattern": pattern, "current_step": "detect_architecture"}

    async def _node_analyze_git_history(self, state: RepositoryAnalyzerState) -> Dict[str, Any]:
        """Analyze git log for hotspot files and contribution patterns."""
        local_path = state["local_path"]
        hotspot_files = []
        maintainer_responsiveness = 0.5
        contribution_patterns = {}

        try:
            # Get file change frequency
            result = subprocess.run(
                ["git", "log", "--format=", "--name-only", "--since=90.days.ago"],
                cwd=local_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                file_changes: Dict[str, int] = defaultdict(int)
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        file_changes[line.strip()] += 1
                hotspot_files = sorted(file_changes, key=file_changes.get, reverse=True)[:10]

            # Get PR merge stats for responsiveness
            pr_result = subprocess.run(
                ["git", "log", "--format=%ci", "--merges", "--since=90.days.ago"],
                cwd=local_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if pr_result.returncode == 0:
                merge_count = len([l for l in pr_result.stdout.strip().split("\n") if l.strip()])
                # Normalize: >20 merges in 90 days = highly responsive
                maintainer_responsiveness = min(1.0, merge_count / 20)

            # Get commit author distribution
            author_result = subprocess.run(
                ["git", "shortlog", "-sn", "--since=90.days.ago"],
                cwd=local_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if author_result.returncode == 0:
                contributors = []
                for line in author_result.stdout.strip().split("\n")[:10]:
                    parts = line.strip().split("\t")
                    if len(parts) == 2:
                        contributors.append({"name": parts[1], "commits": int(parts[0].strip())})
                contribution_patterns["top_contributors"] = contributors
                contribution_patterns["contributor_count"] = len(contributors)

        except Exception as e:
            logger.warning(f"Git history analysis failed: {e}")

        return {
            "hotspot_files": hotspot_files,
            "maintainer_responsiveness": maintainer_responsiveness,
            "contribution_patterns": contribution_patterns,
            "current_step": "analyze_git_history",
        }

    async def _node_assemble_result(self, state: RepositoryAnalyzerState) -> Dict[str, Any]:
        """Assemble final analysis JSON."""
        result = {
            "repo_full_name": state["repo_full_name"],
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "primary_language": state["primary_language"],
            "language_distribution": state["language_distribution"],
            "frameworks": state["frameworks"],
            "test_framework": state["test_framework"],
            "build_system": state["build_system"],
            "architecture_pattern": state["architecture_pattern"],
            "metrics": state["metrics"],
            "hotspot_files": state["hotspot_files"],
            "maintainer_responsiveness": state["maintainer_responsiveness"],
            "contribution_patterns": state["contribution_patterns"],
            "dependency_graph_summary": {
                "total_modules": len(state["dependency_graph"]),
                "most_imported": self._find_most_imported(state["dependency_graph"]),
            },
            "ast_summary": {
                "total_chunks": len(state["ast_chunks"]),
                "languages": list(set(c["language"] for c in state["ast_chunks"])),
            },
        }

        return {"analysis_result": result, "current_step": "assemble_result"}

    def _find_most_imported(self, dep_graph: Dict[str, List[str]]) -> List[str]:
        """Find modules that are most commonly imported."""
        import_counts: Dict[str, int] = defaultdict(int)
        for imports in dep_graph.values():
            for imp in imports:
                import_counts[imp] += 1
        return sorted(import_counts, key=import_counts.get, reverse=True)[:10]

    async def _node_save_to_db(self, state: RepositoryAnalyzerState) -> Dict[str, Any]:
        """Save analysis result to repository_knowledge table."""
        try:
            async with async_session() as session:
                from backend.models.repository import RepositoryKnowledge
                from sqlalchemy import select

                result = await session.execute(
                    select(RepositoryKnowledge).where(
                        RepositoryKnowledge.repo_full_name == state["repo_full_name"]
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    existing.analysis_data = state["analysis_result"]
                    existing.ast_chunks = state["ast_chunks"][:500]  # Store top 500 chunks
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    knowledge = RepositoryKnowledge(
                        repo_full_name=state["repo_full_name"],
                        primary_language=state["primary_language"],
                        frameworks=state["frameworks"],
                        test_framework=state["test_framework"],
                        build_system=state["build_system"],
                        architecture_pattern=state["architecture_pattern"],
                        analysis_data=state["analysis_result"],
                        ast_chunks=state["ast_chunks"][:500],
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    session.add(knowledge)

                await session.commit()
                logger.info(f"Saved analysis for {state['repo_full_name']} to DB")
        except Exception as e:
            logger.warning(f"Failed to save to DB: {e}")

        return {"current_step": "save_to_db"}

    async def _node_cleanup(self, state: RepositoryAnalyzerState) -> Dict[str, Any]:
        """Clean up temp directory."""
        import shutil
        local_path = state["local_path"]
        if local_path and os.path.exists(local_path):
            try:
                shutil.rmtree(local_path, ignore_errors=True)
                logger.info(f"Cleaned up {local_path}")
            except Exception as e:
                logger.warning(f"Cleanup failed: {e}")
        return {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "current_step": "complete",
        }
