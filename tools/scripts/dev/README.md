# 개발 스크립트

매일 사용하는 핵심 스크립트

## 🚀 빠른 테스트

### test_fast.sh
```bash
./dev/test_fast.sh
```
Unit 테스트만 빠르게 실행 (일반)

### test_fast_only.sh
```bash
./dev/test_fast_only.sh
```
느린 테스트 전부 skip (초고속)

### test_quick.sh
```bash
./dev/test_quick.sh
```
Quick 검증용

## 📊 프로파일링

### profile_slow_tests.py
```bash
python dev/profile_slow_tests.py
```
느린 테스트를 자동으로 찾아서 리포트

## 🤖 Agent 테스트

### run_ai_agent_scenarios.py
```bash
python dev/run_ai_agent_scenarios.py
```
Agent 시나리오 테스트 (최근 작업용)
