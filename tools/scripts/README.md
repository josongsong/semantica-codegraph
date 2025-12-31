# Scripts Organization

체계적인 스크립트 관리 구조

## 📁 구조

\`\`\`
scripts/
├── dev/              # 개발 중 자주 사용하는 스크립트
│   ├── test_fast.sh        # 빠른 unit 테스트
│   ├── test_fast_only.sh   # 느린 테스트 전부 skip
│   └── profile_slow_tests.py  # 느린 테스트 프로파일링
│
├── benchmark/        # 성능 벤치마크
│   ├── benchmark_ir_builder.py
│   ├── benchmark_type_inference.py
│   └── benchmark_current_search.py
│
└── maintenance/      # 유지보수/최적화
    ├── optimize_test_fixtures.py
    └── integration_check.py
\`\`\`

## 🎯 사용법

### 개발 중 빠른 테스트
\`\`\`bash
./scripts/dev/test_fast.sh
\`\`\`

### 느린 테스트 찾기
\`\`\`bash
python scripts/dev/profile_slow_tests.py
\`\`\`

### 벤치마크 실행
\`\`\`bash
python scripts/benchmark/benchmark_ir_builder.py
\`\`\`

## 📋 원칙

1. **dev/**: 매일 사용하는 스크립트만
2. **benchmark/**: 성능 측정 전용
3. **maintenance/**: 정기 유지보수 작업

