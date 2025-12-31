# 유지보수 스크립트

정기적인 최적화 및 검증

## 🔧 최적화

### optimize_test_fixtures.py
```bash
python maintenance/optimize_test_fixtures.py
```
테스트 파일의 LayeredIRBuilder 사용을 shared_ir_builder로 자동 변환

## 🔗 통합 체크

### integration_check.py
```bash
python maintenance/integration_check.py
```
통합 테스트 상태 체크

## 🛠️ 수정

### fix_test_irdoc.py
```bash
python maintenance/fix_test_irdoc.py
```
IRDocument 관련 테스트 수정

## 📚 인덱싱

### index_test_repo.py
```bash
python maintenance/index_test_repo.py
```
테스트 레포지토리 인덱싱
