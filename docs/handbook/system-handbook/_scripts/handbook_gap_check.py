"""
Handbook Gap Check

목표:
- 실제 코드 구조(src/contexts, src/agent, src/infra)에서 "스켈레톤"을 추출
- 핸드북 인덱스(_docs/HANDBOOK.md, _docs/system-handbook/README.md, _docs/system-handbook/modules/README.md)와 비교
- 누락/불일치(gap)를 리포트

원칙:
- 외부 의존성 없음(표준 라이브러리만)
- 문서 자동 생성/수정은 하지 않음(검증/리포트만)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


def find_repo_root(start: Path) -> Path:
    """
    스크립트 위치가 어디든 동작하도록 repo root를 탐색한다.
    기준: <root>/src/contexts 가 존재하는 디렉토리.
    """
    p = start.resolve()
    for cand in [p] + list(p.parents):
        if (cand / "src" / "contexts").exists():
            return cand
    raise RuntimeError(f"Failed to locate repo root from: {start}")


REPO_ROOT = find_repo_root(Path(__file__).parent)


@dataclass(frozen=True)
class ModuleSkeleton:
    name: str
    kind: str  # context|agent|infra
    path: str
    has_di: bool
    has_ports: bool
    has_domain: bool
    has_application: bool
    has_infrastructure: bool
    has_adapters: bool
    has_usecase: bool
    has_cli: bool
    py_files: int
    subdirs: list[str]
    role_hints: list[str]


def kebab(s: str) -> str:
    return s.replace("_", "-")


def iter_py_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.py"):
        # ignore cache
        if "__pycache__" in p.parts:
            continue
        yield p


def count_lines(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
    except Exception:
        return 0


def sha256_text(path: Path) -> str:
    h = hashlib.sha256()
    # small+safe: read whole file (docs/scripts/src only)
    data = path.read_bytes()
    h.update(data)
    return h.hexdigest()


def iter_tracked_files(repo_root: Path) -> list[Path]:
    """
    '다음 AI가 빠르게 파악'하기 위한 최소 트래킹 범위.
    - 코드: src/contexts, src/agent, src/infra
    - 문서: _docs/system-handbook, _docs/modules, _docs/HANDBOOK.md
    - 스크립트: scripts/handbook_gap_check.py, _docs/system-handbook/_scripts/*
    """
    tracked: list[Path] = []
    candidates = [
        repo_root / "src" / "contexts",
        repo_root / "src" / "agent",
        repo_root / "src" / "infra",
        repo_root / "_docs" / "system-handbook",
        repo_root / "_docs" / "modules",
        repo_root / "_docs" / "HANDBOOK.md",
        repo_root / "scripts" / "handbook_gap_check.py",
        repo_root / "_docs" / "system-handbook" / "_scripts",
    ]
    for c in candidates:
        if not c.exists():
            continue
        if c.is_file():
            tracked.append(c)
        else:
            # docs and code only
            for p in c.rglob("*"):
                if p.is_dir():
                    continue
                if "__pycache__" in p.parts:
                    continue
                # ignore internal state snapshots (otherwise 매 실행마다 changed로 잡힘)
                if "_state" in p.parts and "system-handbook" in p.parts and "_scripts" in p.parts:
                    continue
                # ignore binary-ish large files by extension
                if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip"}:
                    continue
                tracked.append(p)
    # stable ordering
    uniq = sorted({p.resolve() for p in tracked})
    return uniq


def build_file_fingerprints(repo_root: Path) -> dict[str, dict]:
    """
    relative_path -> {sha256, lines}
    """
    fps: dict[str, dict] = {}
    for p in iter_tracked_files(repo_root):
        rel = str(p.relative_to(repo_root))
        fps[rel] = {
            "sha256": sha256_text(p),
            "lines": count_lines(p),
        }
    return fps


def load_state(state_path: Path) -> dict | None:
    if not state_path.exists():
        return None
    return json.loads(state_path.read_text(encoding="utf-8"))


def write_state(state_path: Path, payload: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def role_hints_for_context(ctx_path: Path) -> list[str]:
    """
    아주 가벼운 휴리스틱:
    - 파일/디렉토리 존재 여부로 역할 힌트만 뽑는다.
    """
    hints: list[str] = []
    parts = set(p.name for p in ctx_path.iterdir() if p.is_dir())

    def has_dir(name: str) -> bool:
        return (ctx_path / name).exists()

    # indexing-ish
    if has_dir("infrastructure") and (ctx_path / "infrastructure" / "stages").exists():
        hints.append("pipeline(stages)")
    if has_dir("infrastructure") and (ctx_path / "infrastructure" / "jobs").exists():
        hints.append("jobs")

    # code foundation-ish
    if has_dir("infrastructure") and (ctx_path / "infrastructure" / "ir").exists():
        hints.append("IR")
    if has_dir("infrastructure") and (ctx_path / "infrastructure" / "dfg").exists():
        hints.append("DFG/CFG")
    if has_dir("infrastructure") and (ctx_path / "infrastructure" / "graph").exists():
        hints.append("Graph")
    if has_dir("infrastructure") and (ctx_path / "infrastructure" / "chunk").exists():
        hints.append("Chunk")
    if has_dir("infrastructure") and (ctx_path / "infrastructure" / "type_inference").exists():
        hints.append("TypeInference")
    if has_dir("infrastructure") and (ctx_path / "infrastructure" / "query").exists():
        hints.append("QueryEngine")

    # retrieval-ish
    if has_dir("infrastructure") and (ctx_path / "infrastructure" / "fusion").exists():
        hints.append("fusion")
    if has_dir("infrastructure") and (ctx_path / "infrastructure" / "multi_index").exists():
        hints.append("multi_index client")

    # DDD-ish
    if "domain" in parts:
        hints.append("DDD(domain)")
    if "application" in parts:
        hints.append("DDD(application)")
    if "ports" in parts:
        hints.append("ports")

    return hints


def build_skeleton(name: str, kind: str, path: Path) -> ModuleSkeleton:
    subdirs = sorted([p.name for p in path.iterdir() if p.is_dir() and not p.name.startswith("__")])
    py_files = sum(1 for _ in iter_py_files(path))
    role_hints: list[str] = []

    if kind == "context":
        role_hints = role_hints_for_context(path)
    elif kind == "infra":
        role_hints = ["config", "storage", "observability", "jobs", "llm/vector"]
    elif kind == "agent":
        role_hints = ["orchestration", "tools", "adapters", "verification loop"]

    return ModuleSkeleton(
        name=name,
        kind=kind,
        path=str(path.relative_to(REPO_ROOT)),
        has_di=(path / "di.py").exists(),
        has_ports=(path / "ports").exists(),
        has_domain=(path / "domain").exists(),
        has_application=(path / "application").exists(),
        has_infrastructure=(path / "infrastructure").exists(),
        has_adapters=(path / "adapters").exists(),
        has_usecase=(path / "usecase").exists() or (path / "use_cases").exists(),
        has_cli=(path / "cli").exists(),
        py_files=py_files,
        subdirs=subdirs,
        role_hints=sorted(set(role_hints)),
    )


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_handbook_modules_from_system_handbook_readme(text: str) -> set[str]:
    # example: - `code_foundation`: `_docs/system-handbook/modules/code-foundation.md`
    return set(re.findall(r"`([a-z0-9_]+)`:\s*`_docs/system-handbook/modules/[^`]+\.md`", text))


def parse_handbook_modules_index_entries(text: str) -> set[str]:
    # We accept either:
    # - `foo.md` (...), or
    # - `foo.md` (foo_bar: ...)
    files = set(re.findall(r"-\s+`([a-z0-9\-]+)\.md`\s*\(", text))
    # also parse (context_name: ...)
    ctx_names = set(re.findall(r"\(([^)]+?):", text))
    return files | ctx_names


def expected_module_doc_file_for(name: str) -> str:
    """
    context -> system-handbook/modules/<kebab>.md
    예외: retrieval_search/query-dsl는 query-and-retrieval.md에 함께 수렴.
    """
    if name in {"retrieval_search", "query-dsl", "query_dsl"}:
        return "query-and-retrieval.md"
    if name == "agent_code_editing":
        return "agent-code-editing.md"
    if name == "llm_arbitration":
        return "llm-arbitration.md"
    if name == "replay_audit":
        return "replay-audit.md"
    if name == "shared_kernel":
        return "shared-kernel.md"
    return f"{kebab(name)}.md"


def extract_backticked_repo_paths(md_text: str) -> list[str]:
    """
    모듈 문서에서 backtick으로 감싼 경로 중 repo-relative로 보이는 것만 추출.
    예: `src/contexts/foo/...`
    """
    paths = re.findall(r"`(src/[^`]+?)`", md_text)
    # normalize: strip trailing punctuation
    cleaned: list[str] = []
    for p in paths:
        p = p.strip()
        p = p.rstrip(".,);:")
        cleaned.append(p)
    # unique stable
    seen = set()
    out = []
    for p in cleaned:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def recommend_entry_files(module_root: Path, max_files: int = 8) -> list[str]:
    """
    다음 AI가 빠르게 파고들 수 있도록 "진입점 후보"를 얕은 휴리스틱으로 추천.
    우선순위:
    - di.py
    - ports/, application/, domain/, infrastructure/ 하위의 작은 entry 파일들
    - 그래도 없으면 LOC 기준 상위 파일
    """
    repo_root = REPO_ROOT
    picks: list[Path] = []

    def add_if_exists(p: Path) -> None:
        if p.exists() and p.is_file() and p not in picks:
            picks.append(p)

    add_if_exists(module_root / "di.py")
    for sub in ["ports", "application", "domain", "infrastructure", "adapters", "cli"]:
        base = module_root / sub
        if not base.exists():
            continue
        for name in ["__init__.py", "main.py", "api.py", "router.py"]:
            add_if_exists(base / name)

    # keyword-based candidates (cap)
    keywords = ["pipeline", "builder", "index", "query", "search", "graph", "chunk", "stage", "runner", "service"]
    for p in iter_py_files(module_root):
        low = p.name.lower()
        if any(k in low for k in keywords):
            add_if_exists(p)
        if len(picks) >= max_files:
            break

    if len(picks) < max_files:
        # fallback: largest LOC files
        all_py = list(iter_py_files(module_root))
        all_py.sort(key=lambda x: count_lines(x), reverse=True)
        for p in all_py:
            add_if_exists(p)
            if len(picks) >= max_files:
                break

    rels = []
    for p in picks[:max_files]:
        try:
            rels.append(str(p.relative_to(repo_root)))
        except Exception:
            rels.append(str(p))
    return rels


def extract_backticked_docs_paths(md_text: str) -> list[str]:
    """
    backtick으로 감싼 `_docs/...` 경로 추출
    """
    paths = re.findall(r"`(_docs/[^`]+?)`", md_text)
    cleaned: list[str] = []
    for p in paths:
        p = p.strip()
        p = p.split("#", 1)[0]  # drop anchor
        p = p.rstrip(".,);:")
        cleaned.append(p)
    seen = set()
    out: list[str] = []
    for p in cleaned:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def extract_markdown_links(md_text: str) -> list[str]:
    """
    markdown 링크 target만 추출: [text](target)
    - http(s), mailto는 제외
    - anchor(#...)만 있는 링크는 제외
    """
    targets = re.findall(r"\[[^\]]+\]\(([^)]+)\)", md_text)
    out: list[str] = []
    for t in targets:
        t = t.strip()
        if not t or t.startswith("#"):
            continue
        if t.startswith("http://") or t.startswith("https://") or t.startswith("mailto:"):
            continue
        # remove anchor
        t = t.split("#", 1)[0]
        t = t.strip()
        if t:
            out.append(t)
    # unique stable
    seen = set()
    uniq: list[str] = []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def validate_doc_links(md_path: Path, repo_root: Path) -> list[str]:
    """
    md 파일 내 링크가 실제 파일로 존재하는지 확인.
    - backticked `_docs/...`는 repo_root 기준
    - markdown 링크는 md_path 기준 상대경로로 resolve
    """
    try:
        text = load_text(md_path)
    except Exception:
        return [f"unreadable: {md_path}"]

    missing: list[str] = []
    # backticked docs paths
    for p in extract_backticked_docs_paths(text):
        if not (repo_root / p).exists():
            missing.append(f"{md_path.relative_to(repo_root)} :: `{p}`")

    # regular markdown links
    for t in extract_markdown_links(text):
        # treat absolute-like repo relative
        if t.startswith("_docs/") or t.startswith("src/") or t.startswith("scripts/") or t.startswith("tests/"):
            target = repo_root / t
        else:
            target = (md_path.parent / t).resolve()
        if not target.exists():
            missing.append(f"{md_path.relative_to(repo_root)} :: ({t})")

    return missing


def module_doc_min_contract_violations(md_text: str) -> list[str]:
    """
    living doc 최소 계약(너무 빡세지 않게):
    - `src/...` 경로가 1개 이상
    - 섹션 헤더(## 또는 ###)가 최소 2개 이상
    """
    problems: list[str] = []
    src_paths = extract_backticked_repo_paths(md_text)
    if not src_paths:
        problems.append("no `src/...` path")

    headers = re.findall(r"^#{2,3}\s+.+$", md_text, flags=re.MULTILINE)
    if len(headers) < 2:
        problems.append("too_few_sections(<2 '##/###')")

    return problems


def iter_test_files(tests_root: Path) -> Iterable[Path]:
    for p in tests_root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        yield p


def has_tests_for_module(tests_root: Path, module_name: str) -> bool:
    """
    아주 가벼운 휴리스틱:
    - tests 경로에 module_name 또는 kebab(module_name)이 포함되면 "커버됨"으로 본다.
    """
    # fast path: contexts/<name>
    ctx_dir = tests_root / "unit" / "contexts" / module_name
    if ctx_dir.exists():
        for _ in ctx_dir.rglob("test_*.py"):
            return True

    needle1 = module_name.lower()
    needle2 = kebab(module_name).lower()
    tokens = [t for t in re.split(r"[_\-]+", needle1) if t]

    # some aliases
    aliases = set()
    if module_name == "agent_code_editing":
        aliases.update(["code_editing", "code-editing", "edit"])
    if module_name == "llm_arbitration":
        aliases.update(["arbitration", "llm"])
    if module_name == "replay_audit":
        aliases.update(["replay", "audit"])
    if module_name == "shared_kernel":
        aliases.update(["shared", "kernel"])

    for p in iter_test_files(tests_root):
        s = str(p).lower()
        if needle1 in s or needle2 in s:
            return True
        if aliases and any(a in s for a in aliases):
            return True
        if tokens and sum(1 for t in tokens if t in s) >= min(2, len(tokens)):
            return True
    return False


def extract_public_api_signatures(module_root: Path, max_files: int = 20) -> list[str]:
    """
    다음 AI용 힌트: Protocol/ABC/dataclass 및 주요 클래스/함수 시그니처를 정적으로 뽑는다.
    (파서/AST 없이 regex)
    """
    candidates: list[Path] = []
    # prioritize ports/domain + di.py
    for p in [module_root / "di.py", module_root / "__init__.py"]:
        if p.exists():
            candidates.append(p)
    for sub in ["ports", "domain", "application", "infrastructure"]:
        base = module_root / sub
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            candidates.append(p)
    # dedup + cap
    seen = set()
    uniq: list[Path] = []
    for p in candidates:
        if p not in seen and p.is_file():
            seen.add(p)
            uniq.append(p)
        if len(uniq) >= max_files:
            break

    sigs: list[str] = []
    class_pat = re.compile(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\s*(\([^)]*\))?\s*:", re.MULTILINE)
    def_pat = re.compile(r"^def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", re.MULTILINE)
    for p in uniq:
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        # limit scanning to first ~400 lines for perf
        lines = txt.splitlines()[:400]
        head = "\n".join(lines)
        for m in class_pat.finditer(head):
            name = m.group(1)
            bases = m.group(2) or ""
            # keep only "public-ish" (not _Private)
            if name.startswith("_"):
                continue
            sigs.append(f"class {name}{bases}:")
        for m in def_pat.finditer(head):
            name = m.group(1)
            if name.startswith("_"):
                continue
            # prefer factory / builder / parse-ish
            if any(k in name.lower() for k in ["build", "create", "parse", "load", "dump", "query", "search", "index"]):
                sigs.append(f"def {name}(...)")
        if len(sigs) >= 30:
            break
    # unique stable
    seen2 = set()
    out: list[str] = []
    for s in sigs:
        if s not in seen2:
            seen2.add(s)
            out.append(s)
    return out[:30]


def scan_living_doc_violations(md_files: list[Path], repo_root: Path) -> list[str]:
    """
    living doc 위반(역사 문서 참조) 탐지: RFC/ADR token
    """
    pat = re.compile(r"\b(RFC-\d+|ADR-\d+)\b")
    out: list[str] = []
    for p in md_files:
        try:
            txt = load_text(p)
        except Exception:
            continue
        m = pat.search(txt)
        if m:
            out.append(f"{p.relative_to(repo_root)} :: {m.group(0)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(prog="handbook_gap_check.py")
    ap.add_argument("--json", dest="json_path", default=None, help="JSON report path (optional)")
    ap.add_argument("--fail-on-gap", action="store_true", help="If gaps exist, exit with code 1")
    ap.add_argument("--print-skeleton", action="store_true", help="Print skeleton summary")
    ap.add_argument("--strict", action="store_true", help="Enable all checks in strict mode (treat as gaps)")
    ap.add_argument(
        "--state",
        dest="state_path",
        default=str(REPO_ROOT / "_docs" / "system-handbook" / "_scripts" / "_state" / "handbook_gap_state.json"),
        help="State file path for change tracking",
    )
    ap.add_argument("--no-write-state", action="store_true", help="Do not write state file")
    ap.add_argument("--show-changes", action="store_true", help="Show change hints vs previous state")
    ap.add_argument(
        "--emit-ai-hints",
        dest="ai_hints_path",
        default=None,
        help="Write AI hint pack JSON (module entrypoints, doc-path validation, deltas)",
    )
    ap.add_argument(
        "--strict-doc-paths",
        action="store_true",
        help="Treat missing `src/...` paths mentioned in module docs as gaps",
    )
    ap.add_argument("--check-doc-links", action="store_true", help="Check markdown links/backticked _docs paths exist")
    ap.add_argument(
        "--enforce-doc-contract", action="store_true", help="Check module doc minimal contract (sections/src paths)"
    )
    ap.add_argument("--check-tests", action="store_true", help="Check module has some tests under /tests (heuristic)")
    ap.add_argument(
        "--tests-exempt",
        default="agent,shared_kernel",
        help="Comma-separated module names exempt from test check (default: agent,shared_kernel)",
    )
    ap.add_argument("--extract-api", action="store_true", help="Extract public API signatures into AI hints")
    ap.add_argument("--forbid-historical-tags", action="store_true", help="Detect RFC/ADR tokens in handbook docs")
    args = ap.parse_args()

    tests_exempt = {s.strip() for s in (args.tests_exempt or "").split(",") if s.strip()}

    # ===== actual modules =====
    ctx_root = REPO_ROOT / "src" / "contexts"
    agent_root = REPO_ROOT / "src" / "agent"
    infra_root = REPO_ROOT / "src" / "infra"

    actual_contexts = sorted([p.name for p in ctx_root.iterdir() if p.is_dir() and not p.name.startswith("__")])

    # explicit "modules" not under contexts
    actual_special = {
        "agent": agent_root.exists(),
        "infra": infra_root.exists(),
    }

    skeletons: list[ModuleSkeleton] = []
    for c in actual_contexts:
        skeletons.append(build_skeleton(c, "context", ctx_root / c))
    if actual_special["agent"]:
        skeletons.append(build_skeleton("agent", "agent", agent_root))
    if actual_special["infra"]:
        skeletons.append(build_skeleton("infra", "infra", infra_root))

    # ===== docs =====
    system_handbook_readme = load_text(REPO_ROOT / "_docs" / "system-handbook" / "README.md")
    system_handbook_modules_idx = load_text(REPO_ROOT / "_docs" / "system-handbook" / "modules" / "README.md")

    listed_in_home = parse_handbook_modules_from_system_handbook_readme(system_handbook_readme)
    listed_in_modules_index = parse_handbook_modules_index_entries(system_handbook_modules_idx)

    module_docs_dir = REPO_ROOT / "_docs" / "system-handbook" / "modules"
    module_doc_files = {p.name for p in module_docs_dir.glob("*.md") if p.name != "README.md"}

    # ===== gap checks =====
    gaps: dict[str, list[str]] = {
        "missing_in_system_handbook_readme": [],
        "missing_module_doc_file": [],
        "missing_in_modules_index": [],
        "missing_doc_src_paths": [],
        "missing_doc_links": [],
        "doc_contract_violations": [],
        "missing_tests": [],
        "living_doc_violations": [],
    }

    for c in actual_contexts:
        if c not in listed_in_home:
            gaps["missing_in_system_handbook_readme"].append(c)

        expected_file = expected_module_doc_file_for(c)
        if expected_file not in module_doc_files:
            gaps["missing_module_doc_file"].append(f"{c} -> {expected_file}")
        else:
            # validate src/... paths referenced in module doc
            md_path = module_docs_dir / expected_file
            md_text = load_text(md_path)
            doc_paths = extract_backticked_repo_paths(md_text)
            missing = [p for p in doc_paths if not (REPO_ROOT / p).exists()]
            for m in missing:
                gaps["missing_doc_src_paths"].append(f"{c} :: {expected_file} :: {m}")
            # doc contract (optional / strict)
            if args.strict or args.enforce_doc_contract:
                probs = module_doc_min_contract_violations(md_text)
                for prob in probs:
                    gaps["doc_contract_violations"].append(f"{c} :: {expected_file} :: {prob}")

        # modules index file list can include kebab file stems or explicit ctx_name markers
        if kebab(c) not in listed_in_modules_index and c not in listed_in_modules_index:
            # allow retrieval_search to be represented indirectly by query-and-retrieval.md
            if c in {"retrieval_search"} and "query-and-retrieval" in listed_in_modules_index:
                pass
            else:
                gaps["missing_in_modules_index"].append(c)

        # tests (optional / strict)
        if args.strict or args.check_tests:
            tests_root = REPO_ROOT / "tests"
            if c in tests_exempt:
                pass
            elif tests_root.exists() and not has_tests_for_module(tests_root, c):
                gaps["missing_tests"].append(c)

    # agent/infra coverage checks (not contexts)
    for special in ["agent", "infra"]:
        if actual_special[special] and special not in listed_in_home:
            gaps["missing_in_system_handbook_readme"].append(special)

        expected_file = expected_module_doc_file_for(special)
        if actual_special[special] and expected_file not in module_doc_files:
            gaps["missing_module_doc_file"].append(f"{special} -> {expected_file}")
        elif actual_special[special] and expected_file in module_doc_files:
            md_path = module_docs_dir / expected_file
            md_text = load_text(md_path)
            doc_paths = extract_backticked_repo_paths(md_text)
            missing = [p for p in doc_paths if not (REPO_ROOT / p).exists()]
            for m in missing:
                gaps["missing_doc_src_paths"].append(f"{special} :: {expected_file} :: {m}")
            if args.strict or args.enforce_doc_contract:
                probs = module_doc_min_contract_violations(md_text)
                for prob in probs:
                    gaps["doc_contract_violations"].append(f"{special} :: {expected_file} :: {prob}")

        if (args.strict or args.check_tests) and actual_special[special]:
            tests_root = REPO_ROOT / "tests"
            if special in tests_exempt:
                pass
            elif tests_root.exists() and not has_tests_for_module(tests_root, special):
                gaps["missing_tests"].append(special)

    # ===== output =====
    # doc links integrity (optional / strict)
    if args.strict or args.check_doc_links:
        md_files: list[Path] = []
        md_files.append(REPO_ROOT / "_docs" / "HANDBOOK.md")
        md_files.append(REPO_ROOT / "_docs" / "system-handbook" / "README.md")
        md_files.append(REPO_ROOT / "_docs" / "system-handbook" / "modules" / "README.md")
        for p in (REPO_ROOT / "_docs" / "system-handbook").rglob("*.md"):
            if "__pycache__" in p.parts:
                continue
            md_files.append(p)
        # validate
        seen = set()
        for p in md_files:
            if not p.exists() or p in seen:
                continue
            seen.add(p)
            gaps["missing_doc_links"].extend(validate_doc_links(p, REPO_ROOT))

    # living doc violations (optional / strict)
    if args.strict or args.forbid_historical_tags:
        md_files = list((REPO_ROOT / "_docs" / "system-handbook").rglob("*.md"))
        gaps["living_doc_violations"].extend(scan_living_doc_violations(md_files, REPO_ROOT))

    report = {
        "repo_root": str(REPO_ROOT),
        "actual_contexts": actual_contexts,
        "actual_special": actual_special,
        "docs": {
            "system_handbook_readme_modules": sorted(listed_in_home),
            "system_handbook_modules_index_entries": sorted(listed_in_modules_index),
            "system_handbook_module_doc_files": sorted(module_doc_files),
        },
        "skeletons": [asdict(s) for s in sorted(skeletons, key=lambda x: (x.kind, x.name))],
        "gaps": gaps,
    }

    # ===== LOC + change tracking =====
    def py_loc_under(root: Path) -> int:
        return sum(count_lines(p) for p in iter_py_files(root))

    loc_by_module: dict[str, int] = {}
    for c in actual_contexts:
        loc_by_module[c] = py_loc_under(ctx_root / c)
    if actual_special["agent"]:
        loc_by_module["agent"] = py_loc_under(agent_root)
    if actual_special["infra"]:
        loc_by_module["infra"] = py_loc_under(infra_root)

    report["loc"] = {
        "python_loc_by_module": dict(sorted(loc_by_module.items())),
        "python_loc_total": int(sum(loc_by_module.values())),
    }

    state_path = Path(args.state_path)
    prev_state = None if args.no_write_state else load_state(state_path)
    prev_loc = {}
    prev_fps = {}
    if isinstance(prev_state, dict):
        prev_loc = ((prev_state.get("loc") or {}).get("python_loc_by_module") or {}) if prev_state else {}
        prev_fps = (prev_state.get("file_fingerprints") or {}) if prev_state else {}

    fps = build_file_fingerprints(REPO_ROOT)

    # deltas (module LOC)
    module_loc_deltas: dict[str, dict] = {}
    if prev_loc:
        for name, now in loc_by_module.items():
            prev = int(prev_loc.get(name, 0))
            if int(now) != prev:
                module_loc_deltas[name] = {"prev": prev, "now": int(now), "delta": int(now) - prev}

    # changed files (hash)
    changed_files: list[dict[str, str]] = []
    if prev_fps:
        for rel, meta in fps.items():
            prev = prev_fps.get(rel)
            if not prev:
                changed_files.append({"path": rel, "change": "added"})
            else:
                if prev.get("sha256") != meta.get("sha256"):
                    changed_files.append({"path": rel, "change": "modified"})
        for rel in prev_fps.keys():
            if rel not in fps:
                changed_files.append({"path": rel, "change": "deleted"})

    # lightweight hints (for next AI runs)
    report["changes"] = {
        "has_prev_state": bool(prev_state),
        "module_loc_deltas": module_loc_deltas,
        "changed_files_total": len(changed_files),
        "changed_files_top": changed_files[:30],
    }

    # ===== AI hint pack =====
    ai_hints = {
        "intent": "static alignment + hints for next AI iteration",
        "modules": [],
    }
    # build per-module hints
    for s in sorted(skeletons, key=lambda x: (x.kind, x.name)):
        root = REPO_ROOT / s.path
        expected_doc = expected_module_doc_file_for(s.name)
        doc_file = (module_docs_dir / expected_doc) if (module_docs_dir / expected_doc).exists() else None
        doc_paths = []
        missing_doc_paths = []
        if doc_file:
            txt = load_text(doc_file)
            doc_paths = extract_backticked_repo_paths(txt)
            missing_doc_paths = [p for p in doc_paths if not (REPO_ROOT / p).exists()]
        public_api = []
        if args.strict or args.extract_api:
            public_api = extract_public_api_signatures(root, max_files=20)

        ai_hints["modules"].append(
            {
                "name": s.name,
                "kind": s.kind,
                "root": s.path,
                "role_hints": s.role_hints,
                "python_loc": int(loc_by_module.get(s.name, 0)),
                "recommended_entry_files": recommend_entry_files(root, max_files=8),
                "public_api_signatures_top": public_api,
                "expected_doc": str((module_docs_dir / expected_doc).relative_to(REPO_ROOT)),
                "doc_src_paths": doc_paths[:80],
                "doc_src_paths_missing": missing_doc_paths[:80],
                "has_tests_heuristic": (REPO_ROOT / "tests").exists()
                and has_tests_for_module(REPO_ROOT / "tests", s.name),
            }
        )

    report["ai_hints"] = ai_hints

    # strict mode: doc-path missing counts as gap for fail-on-gap
    if args.strict_doc_paths:
        pass  # gaps already populated; strictness handled by fail-on-gap

    if not args.no_write_state:
        state_payload = dict(report)
        state_payload["file_fingerprints"] = fps  # full for diffing next run
        write_state(state_path, state_payload)

    if args.print_skeleton:
        for s in sorted(skeletons, key=lambda x: (x.kind, x.name)):
            print(f"- {s.kind}:{s.name} py={s.py_files} dirs={','.join(s.subdirs[:8])}")

    # human summary
    has_gap = any(v for v in gaps.values())
    print("handbook_gap_check:")
    print(f"  contexts={len(actual_contexts)} agent={actual_special['agent']} infra={actual_special['infra']}")
    for k, v in gaps.items():
        print(f"  {k}={len(v)}")
    if has_gap:
        for k, v in gaps.items():
            if v:
                for item in v:
                    print(f"    - {k}: {item}")

    if args.show_changes:
        print("handbook_change_hint:")
        print(f"  python_loc_total={report['loc']['python_loc_total']}")
        if report["changes"]["has_prev_state"]:
            print(f"  changed_files_total={report['changes']['changed_files_total']}")
            deltas = report["changes"]["module_loc_deltas"]
            if deltas:
                items = sorted(deltas.items(), key=lambda kv: abs(kv[1]["delta"]), reverse=True)[:12]
                print("  module_loc_deltas_top:")
                for name, d in items:
                    print(f"    - {name}: {d['prev']} -> {d['now']} (delta {d['delta']})")
            top = report["changes"]["changed_files_top"]
            if top:
                print("  changed_files_top:")
                for item in top[:15]:
                    print(f"    - {item['change']}: {item['path']}")
        else:
            if args.no_write_state:
                print("  (no previous state) no-write-state enabled (comparison disabled)")
            else:
                print("  (no previous state) baseline state written for next run")

    if args.json_path:
        out = Path(args.json_path)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.ai_hints_path:
        out = Path(args.ai_hints_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report["ai_hints"], ensure_ascii=False, indent=2), encoding="utf-8")

    if args.fail_on_gap and has_gap:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
