"""
Data/ML Integration Mode

Handles data pipeline and machine learning integration tasks.

Features:
- Data pipeline analysis
- ML model integration
- Feature engineering suggestions
- Data validation
- Model deployment configuration
"""

import re
from typing import Any

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task

logger = get_logger(__name__)


@mode_registry.register(AgentMode.DATA_ML_INTEGRATION)
class DataMLIntegrationMode(BaseModeHandler):
    """
    Data/ML Integration mode for data and ML tasks.

    Flow:
    1. Analyze data pipeline
    2. Detect ML frameworks
    3. Validate data handling
    4. Check model integration
    5. Generate recommendations

    Transitions:
    - ml_ready → TEST (ready for testing)
    - ml_issues → IMPLEMENTATION (fixes needed)
    - data_quality → VERIFICATION (data validation needed)
    """

    def __init__(self, llm_client=None):
        """
        Initialize Data/ML Integration mode.

        Args:
            llm_client: Optional LLM client for intelligent analysis
        """
        super().__init__(AgentMode.DATA_ML_INTEGRATION)
        self.llm = llm_client

    async def enter(self, context: ModeContext) -> None:
        """Enter data/ML integration mode."""
        await super().enter(context)
        self.logger.info("🤖 Data/ML Integration mode: Analyzing ML pipelines")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute data/ML analysis.

        Args:
            task: ML task
            context: Shared mode context

        Returns:
            Result with ML analysis
        """
        self.logger.info(f"Analyzing ML integration: {task.query}")

        # 1. Detect ML frameworks
        frameworks = self._detect_frameworks(context.pending_changes)

        # 2. Analyze data pipeline
        pipeline_analysis = self._analyze_pipeline(context.pending_changes)

        # 3. Analyze model integration
        model_analysis = self._analyze_models(context.pending_changes)

        # 4. Check data validation
        data_validation = self._check_data_validation(context.pending_changes)

        # 5. Check ML best practices
        best_practices = self._check_best_practices(context.pending_changes, frameworks)

        # 6. Generate recommendations
        recommendations = await self._generate_recommendations(
            frameworks, pipeline_analysis, model_analysis, best_practices
        )

        # 7. Detect issues
        issues = self._consolidate_issues(pipeline_analysis, model_analysis, data_validation, best_practices)

        report = {
            "frameworks": frameworks,
            "pipeline": pipeline_analysis,
            "models": model_analysis,
            "data_validation": data_validation,
            "best_practices": best_practices,
            "recommendations": recommendations,
            "issues": issues,
        }

        # 8. Determine trigger
        trigger = self._determine_trigger(issues, data_validation)

        return self._create_result(
            data=report,
            trigger=trigger,
            explanation=f"Found {len(frameworks)} ML frameworks, "
            f"{len(issues)} issues, {len(recommendations)} recommendations",
        )

    def _detect_frameworks(self, pending_changes: list[dict]) -> list[dict]:
        """Detect ML frameworks used in code."""
        frameworks = []

        framework_patterns = {
            "tensorflow": [r"import tensorflow", r"from tensorflow", r"tf\."],
            "pytorch": [r"import torch", r"from torch", r"nn\.Module"],
            "scikit-learn": [r"from sklearn", r"import sklearn"],
            "pandas": [r"import pandas", r"pd\.DataFrame"],
            "numpy": [r"import numpy", r"np\.array"],
            "keras": [r"from keras", r"import keras"],
            "transformers": [r"from transformers", r"import transformers"],
            "xgboost": [r"import xgboost", r"from xgboost"],
            "lightgbm": [r"import lightgbm", r"from lightgbm"],
        }

        for change in pending_changes:
            content = change.get("content", "")

            for framework, patterns in framework_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, content):
                        if not any(f["name"] == framework for f in frameworks):
                            frameworks.append({"name": framework, "detected_in": change.get("file_path", "")})
                        break

        return frameworks

    def _analyze_pipeline(self, pending_changes: list[dict]) -> dict[str, Any]:
        """Analyze data pipeline structure."""
        analysis = {"stages": [], "data_sources": [], "transformations": [], "issues": []}

        pipeline_indicators = {
            "data_loading": [r"pd\.read_", r"load_data", r"fetch_data", r"\.csv", r"\.parquet"],
            "preprocessing": [r"preprocess", r"transform", r"normalize", r"standardize", r"encode"],
            "feature_engineering": [r"feature_", r"create_features", r"extract_features"],
            "training": [r"\.fit\(", r"\.train\(", r"model\.fit"],
            "evaluation": [r"\.score\(", r"evaluate", r"accuracy", r"precision", r"recall"],
            "prediction": [r"\.predict\(", r"inference", r"\.forward\("],
        }

        for change in pending_changes:
            content = change.get("content", "")

            for stage, patterns in pipeline_indicators.items():
                for pattern in patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        if stage not in analysis["stages"]:
                            analysis["stages"].append(stage)
                        break

        # Check for common issues
        for change in pending_changes:
            content = change.get("content", "")

            # Data leakage check
            if "fit_transform" in content and "test" in content.lower():
                analysis["issues"].append(
                    {
                        "type": "data_leakage",
                        "severity": "high",
                        "message": "Potential data leakage: fit_transform on test data",
                    }
                )

            # Missing data handling
            if "pd.read_" in content and "dropna" not in content and "fillna" not in content:
                analysis["issues"].append(
                    {
                        "type": "missing_data_handling",
                        "severity": "warning",
                        "message": "No explicit handling for missing data",
                    }
                )

        return analysis

    def _analyze_models(self, pending_changes: list[dict]) -> dict[str, Any]:
        """Analyze ML model integration."""
        analysis = {"models": [], "configurations": [], "issues": []}

        for change in pending_changes:
            content = change.get("content", "")
            file_path = change.get("file_path", "")

            # Detect model definitions
            model_patterns = [
                (r"class \w+\(nn\.Module\)", "pytorch_model"),
                (r"Sequential\(\[", "keras_sequential"),
                (r"RandomForest|GradientBoosting|XGB", "tree_model"),
                (r"LinearRegression|LogisticRegression", "linear_model"),
                (r"\.from_pretrained\(", "pretrained_model"),
            ]

            for pattern, model_type in model_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    analysis["models"].append(
                        {
                            "type": model_type,
                            "file": file_path,
                            "pattern": match[:50] if isinstance(match, str) else str(match)[:50],
                        }
                    )

            # Check for model saving/loading
            if "save_model" in content or "torch.save" in content or "joblib.dump" in content:
                analysis["configurations"].append({"type": "model_persistence", "file": file_path})

            # Check for issues
            if ".eval()" not in content and "model(" in content and "training" in content.lower():
                analysis["issues"].append(
                    {
                        "type": "missing_eval_mode",
                        "severity": "warning",
                        "message": "Model may not be in eval mode during inference",
                        "file": file_path,
                    }
                )

        return analysis

    def _check_data_validation(self, pending_changes: list[dict]) -> dict[str, Any]:
        """Check data validation practices."""
        validation = {"checks": [], "missing": [], "score": 100}

        validation_patterns = {
            "schema_validation": [r"pydantic", r"marshmallow", r"jsonschema", r"Schema"],
            "type_checking": [r"isinstance\(", r"assert.*type", r": int", r": float", r": str"],
            "range_validation": [r"assert.*>", r"assert.*<", r"\.between\("],
            "null_checking": [r"is None", r"is not None", r"isna\(\)", r"notna\(\)"],
        }

        for change in pending_changes:
            content = change.get("content", "")

            for check_type, patterns in validation_patterns.items():
                found = False
                for pattern in patterns:
                    if re.search(pattern, content):
                        validation["checks"].append({"type": check_type, "found": True})
                        found = True
                        break

                if not found and check_type not in [c["type"] for c in validation["checks"]]:
                    validation["missing"].append(check_type)

        # Calculate score
        validation["score"] = max(0, 100 - len(validation["missing"]) * 20)

        return validation

    def _check_best_practices(self, pending_changes: list[dict], frameworks: list[dict]) -> dict[str, Any]:
        """Check ML best practices."""
        practices = {"followed": [], "violations": []}

        for change in pending_changes:
            content = change.get("content", "")
            file_path = change.get("file_path", "")

            # Check for reproducibility
            if "random_state" in content or "seed" in content or "set_seed" in content:
                practices["followed"].append({"practice": "reproducibility", "file": file_path})
            elif "random" in content.lower() and "RandomForest" not in content:
                practices["violations"].append(
                    {
                        "practice": "reproducibility",
                        "message": "Random operations without seed",
                        "file": file_path,
                    }
                )

            # Check for train/test split
            if "train_test_split" in content or "cross_val" in content:
                practices["followed"].append({"practice": "proper_splitting", "file": file_path})

            # Check for model versioning
            if "mlflow" in content.lower() or "wandb" in content.lower() or "dvc" in content.lower():
                practices["followed"].append({"practice": "experiment_tracking", "file": file_path})

            # Check for hardcoded hyperparameters
            if re.search(r"learning_rate\s*=\s*\d", content) or re.search(r"lr\s*=\s*\d", content):
                practices["violations"].append(
                    {
                        "practice": "config_management",
                        "message": "Hardcoded hyperparameters",
                        "file": file_path,
                    }
                )

        return practices

    async def _generate_recommendations(
        self,
        frameworks: list[dict],
        pipeline: dict,
        models: dict,
        practices: dict,
    ) -> list[dict]:
        """Generate ML recommendations."""
        recommendations = []

        # Framework-specific recommendations
        framework_names = [f["name"] for f in frameworks]

        if "pytorch" in framework_names and "tensorboard" not in str(pipeline):
            recommendations.append(
                {
                    "type": "tooling",
                    "priority": "medium",
                    "recommendation": "Consider using TensorBoard for training visualization",
                }
            )

        # Pipeline recommendations
        if "feature_engineering" not in pipeline.get("stages", []):
            recommendations.append(
                {
                    "type": "pipeline",
                    "priority": "low",
                    "recommendation": "Consider adding explicit feature engineering stage",
                }
            )

        # Practice recommendations
        for violation in practices.get("violations", []):
            recommendations.append(
                {
                    "type": "best_practice",
                    "priority": "high",
                    "recommendation": f"Fix {violation['practice']}: {violation['message']}",
                }
            )

        # Data validation recommendations
        if pipeline.get("issues"):
            for issue in pipeline["issues"]:
                recommendations.append(
                    {
                        "type": "data_quality",
                        "priority": issue.get("severity", "medium"),
                        "recommendation": issue["message"],
                    }
                )

        return recommendations

    def _consolidate_issues(self, pipeline: dict, models: dict, validation: dict, practices: dict) -> list[dict]:
        """Consolidate all issues."""
        issues = []
        issues.extend(pipeline.get("issues", []))
        issues.extend(models.get("issues", []))
        issues.extend([{"type": v["practice"], "message": v["message"]} for v in practices.get("violations", [])])

        if validation.get("score", 100) < 60:
            issues.append(
                {
                    "type": "data_validation",
                    "severity": "high",
                    "message": f"Low data validation score: {validation['score']}/100",
                }
            )

        return issues

    def _determine_trigger(self, issues: list[dict], data_validation: dict) -> str:
        """Determine appropriate trigger based on analysis."""
        high_severity = any(i.get("severity") == "high" for i in issues)

        if data_validation.get("score", 100) < 60:
            return "data_quality"
        elif high_severity:
            return "ml_issues"
        else:
            return "ml_ready"

    async def exit(self, context: ModeContext) -> None:
        """Exit data/ML integration mode."""
        self.logger.info("Data/ML integration analysis complete")
        await super().exit(context)
