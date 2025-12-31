#!/usr/bin/env python3
"""
TRCR 룰 기반 실제 분석 테스트

현재 등록된 TRCR 룰(CodeQL 포함)로 취약한 코드를 분석합니다.
"""
import sys
from pathlib import Path

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent / "packages"))

from codegraph_ir import TrcrAdapter


def main():
    print("=" * 70)
    print("🔍 TRCR Security Analysis Test")
    print("=" * 70)
    print()
    
    # Test files
    test_files = [
        "test_samples/vulnerable_code/sql_injection.py",
        "test_samples/vulnerable_code/command_injection.py",
        "test_samples/vulnerable_code/path_traversal.py",
    ]
    
    # Initialize TRCR
    print("📦 Loading TRCR rules...")
    trcr = TrcrAdapter(
        rules_dir="packages/codegraph-trcr/rules/atoms"
    )
    print(f"✅ Loaded {trcr.rule_count()} rules")
    print()
    
    # Analyze each file
    total_findings = 0
    
    for test_file in test_files:
        if not Path(test_file).exists():
            print(f"⚠️  Skipping {test_file} (not found)")
            continue
            
        print(f"🔎 Analyzing: {test_file}")
        print("-" * 70)
        
        # Read source
        source_code = Path(test_file).read_text()
        
        # Run analysis
        findings = trcr.analyze(
            file_path=test_file,
            source_code=source_code,
            language="python"
        )
        
        if findings:
            for finding in findings:
                total_findings += 1
                print(f"  🚨 [{finding['severity'].upper()}] {finding['rule_id']}")
                print(f"     {finding['cwe']} - {finding['message']}")
                print(f"     Line {finding['line']}: {finding['code_snippet']}")
                print()
        else:
            print("  ✅ No vulnerabilities found")
            print()
    
    # Summary
    print("=" * 70)
    print("📊 Analysis Summary")
    print("=" * 70)
    print(f"  Files analyzed:       {len(test_files)}")
    print(f"  Total findings:       {total_findings}")
    print(f"  Rules used:           {trcr.rule_count()}")
    print()
    
    if total_findings > 0:
        print("🎯 TRCR successfully detected vulnerabilities!")
    else:
        print("⚠️  No vulnerabilities detected (check rule configuration)")
    print()


if __name__ == "__main__":
    main()
