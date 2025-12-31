"""
ML False Positive Filter

머신러닝 기반 False Positive 필터링
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

# Note: We intentionally avoid pickle due to security concerns (arbitrary code execution).
# Model serialization uses JSON for SimpleLogisticModel.
from trcr.ml.feature_extractor import FeatureExtractor, MatchFeatures
from trcr.ml.feedback_collector import FeedbackCollector, FeedbackType, UserFeedback


@dataclass
class FPPrediction:
    """FP 예측 결과"""

    is_likely_fp: bool
    fp_probability: float  # 0.0 ~ 1.0
    confidence: float  # 예측 신뢰도

    # 설명
    top_reasons: list[str] = field(default_factory=list)

    # 메타데이터
    model_version: str = ""
    elapsed_time: float = 0.0

    @property
    def should_filter(self) -> bool:
        """필터링해야 하는지 (높은 확률 + 높은 신뢰도)"""
        return self.fp_probability > 0.8 and self.confidence > 0.7


@dataclass
class FilterConfig:
    """필터 설정"""

    # 임계값
    fp_threshold: float = 0.5  # 이 이상이면 FP로 판단
    confidence_threshold: float = 0.6

    # 모델 설정
    model_path: str | None = None
    use_rule_based: bool = True  # 규칙 기반도 사용

    # 학습 설정
    min_samples_for_training: int = 10
    retrain_interval: int = 100  # N개 새 피드백마다 재학습


class MLModel(Protocol):
    """ML 모델 프로토콜"""

    def fit(self, X: list[list[float]], y: list[int]) -> None: ...
    def predict_proba(self, X: list[list[float]]) -> list[tuple[float, float]]: ...


class SimpleLogisticModel:
    """간단한 로지스틱 모델 (scikit-learn 없이)"""

    def __init__(self) -> None:
        self.weights: list[float] = []
        self.bias: float = 0.0
        self._is_fitted = False

    def fit(self, X: list[list[float]], y: list[int]) -> None:
        """학습"""
        if not X:
            return

        n_features = len(X[0])
        self.weights = [0.0] * n_features
        self.bias = 0.0

        # 간단한 경사하강법
        lr = 0.1
        n_epochs = 100

        for _ in range(n_epochs):
            for xi, yi in zip(X, y, strict=True):
                pred = self._sigmoid(self._dot(xi))
                error = yi - pred

                # 가중치 업데이트
                for j in range(n_features):
                    self.weights[j] += lr * error * xi[j]
                self.bias += lr * error

        self._is_fitted = True

    def predict_proba(self, X: list[list[float]]) -> list[tuple[float, float]]:
        """확률 예측"""
        if not self._is_fitted:
            # 기본값 (0.5, 0.5)
            return [(0.5, 0.5)] * len(X)

        probas = []
        for xi in X:
            p = self._sigmoid(self._dot(xi))
            probas.append((1 - p, p))  # (P(y=0), P(y=1))

        return probas

    def _dot(self, x: list[float]) -> float:
        """내적"""
        return sum(w * xi for w, xi in zip(self.weights, x, strict=True)) + self.bias

    @staticmethod
    def _sigmoid(z: float) -> float:
        """시그모이드"""
        import math

        try:
            return 1 / (1 + math.exp(-z))
        except OverflowError:
            return 0.0 if z < 0 else 1.0


class MLFPFilter:
    """ML False Positive 필터"""

    def __init__(
        self,
        config: FilterConfig | None = None,
        feedback_collector: FeedbackCollector | None = None,
    ) -> None:
        self.config = config or FilterConfig()
        self.feedback_collector = feedback_collector or FeedbackCollector()
        self.feature_extractor = FeatureExtractor(
            fp_history=self.feedback_collector.get_fp_rate_by_rule(),
            file_fp_history=self.feedback_collector.get_fp_rate_by_file(),
        )

        # 모델 초기화
        self._model: MLModel = SimpleLogisticModel()
        self._model_version = "v1.0-simple"
        self._samples_since_train = 0

        # 저장된 모델 로드
        if self.config.model_path:
            self._load_model()

    def predict(
        self,
        match: Any,
        code: str,
        file_path: str,
    ) -> FPPrediction:
        """
        FP 여부 예측

        Args:
            match: 취약점 매치 결과
            code: 소스 코드
            file_path: 파일 경로

        Returns:
            FPPrediction: 예측 결과
        """
        start_time = time.time()

        # 피처 추출
        features = self.feature_extractor.extract(match, code, file_path)

        # 규칙 기반 판단
        rule_based_fp, reasons = self._rule_based_check(features)

        # ML 예측
        X = [features.to_vector()]
        probas = self._model.predict_proba(X)
        ml_fp_prob = probas[0][1]  # P(FP)

        # 결합
        if self.config.use_rule_based:
            # 규칙 기반과 ML 결합
            final_prob = (ml_fp_prob + (1.0 if rule_based_fp else 0.0)) / 2.0
        else:
            final_prob = ml_fp_prob

        # 신뢰도 계산
        confidence = self._calculate_confidence(features, probas)

        return FPPrediction(
            is_likely_fp=final_prob > self.config.fp_threshold,
            fp_probability=final_prob,
            confidence=confidence,
            top_reasons=reasons,
            model_version=self._model_version,
            elapsed_time=time.time() - start_time,
        )

    def predict_batch(
        self,
        matches: list[tuple[Any, str, str]],
    ) -> list[FPPrediction]:
        """배치 예측"""
        return [self.predict(match, code, file_path) for match, code, file_path in matches]

    def train(
        self,
        feedbacks: list[UserFeedback] | None = None,
    ) -> dict[str, Any]:
        """
        모델 학습

        Args:
            feedbacks: 학습할 피드백 (None이면 collector에서 가져옴)

        Returns:
            dict: 학습 결과 통계
        """
        if feedbacks is None:
            feedbacks = self.feedback_collector.get_all()

        if len(feedbacks) < self.config.min_samples_for_training:
            return {
                "status": "skipped",
                "reason": f"Not enough samples ({len(feedbacks)} < {self.config.min_samples_for_training})",
            }

        # 피처 및 레이블 준비
        X: list[list[float]] = []
        y: list[int] = []

        for feedback in feedbacks:
            if feedback.feedback_type not in (
                FeedbackType.TRUE_POSITIVE,
                FeedbackType.FALSE_POSITIVE,
            ):
                continue

            # 피처 추출
            features = self.feature_extractor.extract_from_dict(
                match_data=feedback.match_data,
                code=feedback.code_snippet or "",
                file_path=feedback.file_path,
            )

            X.append(features.to_vector())
            y.append(1 if feedback.is_false_positive else 0)

        if len(X) < self.config.min_samples_for_training:
            return {
                "status": "skipped",
                "reason": f"Not enough labeled samples ({len(X)})",
            }

        # 학습
        self._model.fit(X, y)
        self._samples_since_train = 0

        # 모델 저장
        if self.config.model_path:
            self._save_model()

        return {
            "status": "trained",
            "samples": len(X),
            "fp_count": sum(y),
            "tp_count": len(y) - sum(y),
        }

    def add_feedback_and_maybe_train(
        self,
        rule_id: str,
        file_path: str,
        line: int,
        is_false_positive: bool,
        code_snippet: str = "",
    ) -> dict[str, Any]:
        """
        피드백 추가 및 필요시 재학습

        Returns:
            dict: 피드백 및 학습 결과
        """
        # 피드백 추가
        feedback_type = FeedbackType.FALSE_POSITIVE if is_false_positive else FeedbackType.TRUE_POSITIVE

        self.feedback_collector.add_feedback(
            rule_id=rule_id,
            file_path=file_path,
            line=line,
            feedback_type=feedback_type,
            code_snippet=code_snippet,
        )

        self._samples_since_train += 1

        # 재학습 체크
        train_result = None
        if self._samples_since_train >= self.config.retrain_interval:
            train_result = self.train()

        return {
            "feedback_added": True,
            "train_result": train_result,
        }

    def _rule_based_check(
        self,
        features: MatchFeatures,
    ) -> tuple[bool, list[str]]:
        """규칙 기반 FP 체크"""
        reasons: list[str] = []

        # 테스트 파일
        if features.in_test_file:
            reasons.append("In test file")

        # 새니타이저 있음
        if features.has_sanitizer_before:
            reasons.append("Sanitizer found before")

        # 가드 있음
        if features.has_guard_before:
            reasons.append("Guard condition before")

        # try 블록 내부
        if features.in_try_block:
            reasons.append("Inside try block")

        # 낮은 규칙 신뢰도
        if features.rule_confidence < 0.5:
            reasons.append("Low rule confidence")

        # 높은 규칙 FP율
        if features.rule_fp_rate > 0.5:
            reasons.append(f"High rule FP rate ({features.rule_fp_rate:.0%})")

        is_likely_fp = len(reasons) >= 2
        return is_likely_fp, reasons

    def _calculate_confidence(
        self,
        features: MatchFeatures,
        probas: list[tuple[float, float]],
    ) -> float:
        """예측 신뢰도 계산"""
        if not probas:
            return 0.5

        # 확률이 극단적일수록 신뢰도 높음
        prob = probas[0][1]
        distance_from_center = abs(prob - 0.5) * 2  # 0~1 범위

        # 피드백 수에 따른 조정
        feedback_count = self.feedback_collector.count()
        feedback_factor = min(feedback_count / 100, 1.0)

        confidence = distance_from_center * (0.5 + 0.5 * feedback_factor)

        return confidence

    def _save_model(self) -> None:
        """
        모델 저장 (JSON 형식)

        Note: pickle 대신 JSON을 사용하여 보안 취약점(임의 코드 실행) 방지.
        SimpleLogisticModel만 지원.
        """
        if self.config.model_path is None:
            return

        path = Path(self.config.model_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # SimpleLogisticModel 직렬화
        if isinstance(self._model, SimpleLogisticModel):
            model_data = {
                "type": "SimpleLogisticModel",
                "weights": self._model.weights,
                "bias": self._model.bias,
                "is_fitted": self._model._is_fitted,
            }
        else:
            # 다른 모델 타입은 지원하지 않음
            raise NotImplementedError(
                f"Model serialization not supported for {type(self._model).__name__}. "
                "Only SimpleLogisticModel is supported for security reasons."
            )

        with open(path, "w") as f:
            json.dump(
                {
                    "model": model_data,
                    "version": self._model_version,
                },
                f,
                indent=2,
            )

    def _load_model(self) -> None:
        """
        모델 로드 (JSON 형식)

        Note: pickle 대신 JSON을 사용하여 보안 취약점 방지.
        """
        if self.config.model_path is None:
            return

        path = Path(self.config.model_path)
        if not path.exists():
            return

        # 빈 파일 처리
        if path.stat().st_size == 0:
            return

        with open(path) as f:
            data = json.load(f)

        model_data = data.get("model", {})
        model_type = model_data.get("type")

        if model_type == "SimpleLogisticModel":
            model = SimpleLogisticModel()
            model.weights = model_data.get("weights", [])
            model.bias = model_data.get("bias", 0.0)
            model._is_fitted = model_data.get("is_fitted", False)
            self._model = model
        else:
            raise ValueError(f"Unknown model type: {model_type}. Only SimpleLogisticModel is supported.")

        self._model_version = data.get("version", "unknown")
