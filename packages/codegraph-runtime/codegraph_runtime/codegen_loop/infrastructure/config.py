"""
Infrastructure Configuration

예산, 임계값 등 설정
"""

# 예산 (Budget)
BUDGETS = {
    "max_iterations": 10,
    "max_tokens_per_request": 4096,
    "total_token_budget": 50000,
}

# 임계값 (Thresholds)
THRESHOLDS = {
    "convergence": 0.95,
    "oscillation_similarity": 0.9,
    "test_pass_rate": 1.0,
}

# LLM 설정
LLM_CONFIG = {
    "model": "claude-3-5-sonnet-20241022",
    "temperature": 0.3,
    "max_tokens": 4096,
}

# Sandbox 설정
SANDBOX_CONFIG = {
    "timeout": 60,
    "memory_limit": "512m",
}
