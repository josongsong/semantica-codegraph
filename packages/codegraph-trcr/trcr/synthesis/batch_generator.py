"""
Batch Generator CLI

대량의 규칙을 자동 생성하는 CLI 도구
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from trcr.synthesis.llm_synthesizer import (
    LLMRuleSynthesizer,
    SynthesisConfig,
    SynthesisResult,
)
from trcr.synthesis.prompt_templates import Language, VulnerabilityCategory


def create_parser() -> argparse.ArgumentParser:
    """CLI 파서 생성"""
    parser = argparse.ArgumentParser(
        description="LLM 기반 Taint 분석 규칙 대량 생성",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # Python SQL Injection 규칙 10개 생성
  python -m trcr.synthesis.batch_generator --language python --category sql_injection --count 10

  # JavaScript 모든 카테고리 규칙 생성
  python -m trcr.synthesis.batch_generator --language javascript --all-categories --count 5

  # CVE 기반 규칙 생성
  python -m trcr.synthesis.batch_generator --cve 2021-44228 --description "Log4j RCE" --language java
""",
    )

    # 기본 옵션
    parser.add_argument(
        "--language",
        "-l",
        choices=[l.value for l in Language],
        required=True,
        help="대상 언어",
    )

    parser.add_argument(
        "--category",
        "-c",
        choices=[c.value for c in VulnerabilityCategory],
        help="취약점 카테고리",
    )

    parser.add_argument(
        "--all-categories",
        action="store_true",
        help="모든 카테고리 생성",
    )

    parser.add_argument(
        "--count",
        "-n",
        type=int,
        default=10,
        help="카테고리당 생성할 규칙 수 (기본: 10)",
    )

    # CVE 옵션
    parser.add_argument(
        "--cve",
        help="CVE ID (예: 2021-44228)",
    )

    parser.add_argument(
        "--description",
        help="CVE 설명",
    )

    parser.add_argument(
        "--software",
        help="영향받는 소프트웨어",
    )

    # 출력 옵션
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="출력 파일 경로 (YAML)",
    )

    parser.add_argument(
        "--format",
        "-f",
        choices=["yaml", "json"],
        default="yaml",
        help="출력 형식 (기본: yaml)",
    )

    parser.add_argument(
        "--append",
        action="store_true",
        help="기존 파일에 추가",
    )

    # LLM 옵션
    parser.add_argument(
        "--model",
        "-m",
        default="gpt-4o-mini",
        help="LLM 모델 (기본: gpt-4o-mini)",
    )

    parser.add_argument(
        "--temperature",
        "-t",
        type=float,
        default=0.7,
        help="Temperature (기본: 0.7)",
    )

    parser.add_argument(
        "--api-key",
        help="OpenAI API 키 (또는 OPENAI_API_KEY 환경변수)",
    )

    parser.add_argument(
        "--ollama",
        action="store_true",
        help="Ollama 로컬 모델 사용",
    )

    # 기타 옵션
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="상세 출력",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 생성 없이 프롬프트만 확인",
    )

    return parser


def format_rules_yaml(results: list[SynthesisResult]) -> str:
    """결과를 YAML 형식으로 포맷"""
    all_rules: list[dict[str, Any]] = []

    for result in results:
        for rule in result.rules:
            rule_dict = {
                "id": rule.id,
                "tags": rule.tags,
                "severity": rule.severity,
                "match": [],
            }

            for clause in rule.match:
                clause_dict: dict[str, Any] = {}
                if clause.call:
                    clause_dict["call"] = clause.call
                if clause.type:
                    clause_dict["type"] = clause.type
                if clause.read:
                    clause_dict["read"] = clause.read
                if clause.args:
                    clause_dict["args"] = {
                        idx: {
                            k: v
                            for k, v in {
                                "tainted": c.tainted,
                                "regex": c.regex,
                                "constant": c.constant,
                            }.items()
                            if v is not None
                        }
                        for idx, c in clause.args.items()
                    }
                rule_dict["match"].append(clause_dict)

            if rule.effect:
                effect_dict: dict[str, Any] = {"kind": rule.effect.kind}
                if rule.effect.confidence is not None:
                    effect_dict["confidence"] = rule.effect.confidence
                if rule.effect.propagate_from:
                    effect_dict["from"] = rule.effect.propagate_from
                if rule.effect.propagate_to:
                    effect_dict["to"] = rule.effect.propagate_to
                rule_dict["effect"] = effect_dict

            all_rules.append(rule_dict)

    return yaml.dump(all_rules, allow_unicode=True, sort_keys=False)


def format_rules_json(results: list[SynthesisResult]) -> str:
    """결과를 JSON 형식으로 포맷"""
    all_rules: list[dict[str, Any]] = []

    for result in results:
        for rule in result.rules:
            rule_dict = {
                "id": rule.id,
                "tags": rule.tags,
                "severity": rule.severity,
                "match": [
                    {
                        k: v
                        for k, v in {
                            "call": c.call,
                            "type": c.type,
                            "read": c.read,
                            "args": {
                                str(idx): {
                                    "tainted": ac.tainted,
                                    "regex": ac.regex,
                                }
                                for idx, ac in (c.args or {}).items()
                            }
                            if c.args
                            else None,
                        }.items()
                        if v
                    }
                    for c in rule.match
                ],
            }

            if rule.effect:
                rule_dict["effect"] = {
                    "kind": rule.effect.kind,
                    "confidence": rule.effect.confidence,
                }

            all_rules.append(rule_dict)

    return json.dumps(all_rules, indent=2, ensure_ascii=False)


def print_summary(results: list[SynthesisResult], verbose: bool = False) -> None:
    """결과 요약 출력"""
    total_rules = sum(len(r.rules) for r in results)
    total_time = sum(r.elapsed_time for r in results)
    total_tokens = sum(r.tokens_used for r in results)

    print("\n" + "=" * 60)
    print("생성 결과 요약")
    print("=" * 60)
    print(f"총 규칙 수: {total_rules}")
    print(f"총 소요 시간: {total_time:.2f}초")
    print(f"총 토큰 사용: {total_tokens:,}")

    if verbose:
        print("\n카테고리별 상세:")
        for result in results:
            status = "✓" if result.success else "✗"
            quality = f"{result.quality_score:.1%}" if result.quality_score else "N/A"
            print(f"  {status} {result.category}: {len(result.rules)}개, 품질 {quality}, {result.elapsed_time:.2f}초")

            if result.validation and result.validation.warnings:
                for warning in result.validation.warnings[:3]:
                    print(f"    ⚠ {warning.message}")

    print("=" * 60)


def main(argv: list[str] | None = None) -> int:
    """메인 진입점"""
    parser = create_parser()
    args = parser.parse_args(argv)

    # 검증
    if not args.category and not args.all_categories and not args.cve:
        parser.error("--category, --all-categories, 또는 --cve 중 하나 필요")

    if args.cve and not args.description:
        parser.error("--cve 사용 시 --description 필요")

    # 설정 생성
    config = SynthesisConfig(
        model=args.model,
        temperature=args.temperature,
        api_key=args.api_key,
        api_base="http://localhost:11434" if args.ollama else None,
    )

    # 합성기 생성
    synthesizer = LLMRuleSynthesizer(config=config)

    # Dry run
    if args.dry_run:
        print("Dry run 모드 - 프롬프트만 출력")
        from trcr.synthesis.prompt_templates import PromptLibrary

        if args.cve:
            system, user = PromptLibrary.get_cve_prompt(
                cve_id=args.cve,
                cve_description=args.description,
                affected_software=args.software or "Unknown",
                language=args.language,
            )
        else:
            category = args.category or "sql_injection"
            system, user = PromptLibrary.get_prompt(
                category=category,
                language=args.language,
                count=args.count,
            )

        print("\n[System Prompt]")
        print(system[:500] + "..." if len(system) > 500 else system)
        print("\n[User Prompt]")
        print(user)
        return 0

    # 생성 실행
    results: list[SynthesisResult] = []

    if args.cve:
        # CVE 기반 생성
        print(f"CVE-{args.cve} 규칙 생성 중...")
        result = synthesizer.generate_from_cve(
            cve_id=args.cve,
            cve_description=args.description,
            affected_software=args.software or "Unknown",
            language=args.language,
        )
        results.append(result)

    elif args.all_categories:
        # 모든 카테고리
        categories = [c.value for c in VulnerabilityCategory]
        print(f"{len(categories)}개 카테고리에 대해 규칙 생성 중...")

        for i, category in enumerate(categories, 1):
            print(f"  [{i}/{len(categories)}] {category}...")
            result = synthesizer.generate_atoms(
                language=args.language,
                category=category,
                count=args.count,
            )
            results.append(result)

            if args.verbose:
                status = "✓" if result.success else "✗"
                print(f"    {status} {len(result.rules)}개 생성")

    else:
        # 단일 카테고리
        print(f"{args.category} 규칙 생성 중...")
        result = synthesizer.generate_atoms(
            language=args.language,
            category=args.category,
            count=args.count,
        )
        results.append(result)

    # 결과 출력
    print_summary(results, verbose=args.verbose)

    # 파일 저장
    if args.output:
        if args.format == "yaml":
            content = format_rules_yaml(results)
        else:
            content = format_rules_json(results)

        mode = "a" if args.append else "w"
        with open(args.output, mode) as f:
            if args.append:
                f.write("\n# Generated at " + datetime.now().isoformat() + "\n")
            f.write(content)

        print(f"\n저장됨: {args.output}")
    else:
        # stdout 출력
        if args.format == "yaml":
            print("\n생성된 규칙:")
            print(format_rules_yaml(results))
        else:
            print(format_rules_json(results))

    # 성공 여부
    total_rules = sum(len(r.rules) for r in results)
    return 0 if total_rules > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
