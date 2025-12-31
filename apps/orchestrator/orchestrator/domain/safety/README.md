# Safety Module - Enterprise Security Layer

## 📋 Overview

Enterprise-grade security module for code generation agents. Provides:
- **Secret Detection & Scrubbing**: Prevents API keys, tokens, passwords from leaking
- **License Compliance**: Blocks GPL/AGPL, allows MIT/Apache
- **Dangerous Action Gating**: Requires approval for risky operations (rm -rf, DROP DATABASE, etc.)

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Domain Layer                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  SafetyOrchestrator (Business Logic)                │   │
│  │  - Depends ONLY on Ports (DIP)                      │   │
│  │  - Validates: Secrets, Licenses, Actions            │   │
│  │  - Orchestrates: Multi-stage pipeline               │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↓ depends on
┌─────────────────────────────────────────────────────────────┐
│                     Port Layer (Protocols)                   │
│  ┌──────────────────┐ ┌──────────────────┐ ┌─────────────┐ │
│  │SecretScannerPort │ │LicenseCheckerPort│ │ActionGatePort│ │
│  │@runtime_checkable│ │@runtime_checkable│ │@runtime...  │ │
│  └──────────────────┘ └──────────────────┘ └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            ↑ implements
┌─────────────────────────────────────────────────────────────┐
│                  Adapter Layer (Implementations)            │
│  ┌────────────────────┐ ┌──────────────────────────┐       │
│  │SecretScrubber      │ │LicenseComplianceChecker  │       │
│  │Adapter             │ │Adapter                   │       │
│  │- Regex patterns    │ │- SPDX matching           │       │
│  │- Entropy detection │ │- Policy enforcement      │       │
│  └────────────────────┘ └──────────────────────────┘       │
│  ┌────────────────────────────────────────────────────┐    │
│  │DangerousActionGateAdapter                          │    │
│  │- RiskClassifier (CRITICAL/HIGH/MEDIUM/LOW)         │    │
│  │- Approval workflow (Pending/Approved/Rejected)     │    │
│  │- Whitelist/Blacklist                               │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Basic Usage (via Container)

```python
from src.container import Container

container = Container()
safety = container.safety_orchestrator

# Validate content
result = safety.validate_content("AWS_KEY=AKIAIOSFODNN7EXAMPLE")
if not result.passed:
    print(f"Security issue: {result.message}")
```

### 2. Pipeline Validation

```python
from src.agent.domain.safety import ValidationContext, ActionType

ctx = ValidationContext(
    content="import requests",
    dependencies={"requests": "Apache License 2.0"},
    action_type=ActionType.FILE_WRITE,
    file_path="api.py",
)

results = safety.validate_pipeline(ctx)
if safety.is_safe(results):
    print("✅ All security checks passed!")
```

### 3. Manual Adapter Injection (Advanced)

```python
from src.agent.domain.safety import SafetyOrchestrator, SafetyConfig
from src.agent.adapters.safety import (
    SecretScrubberAdapter,
    LicenseComplianceCheckerAdapter,
    DangerousActionGateAdapter,
)

# Create custom orchestrator
orchestrator = SafetyOrchestrator(
    config=SafetyConfig(
        enable_secret_scanning=True,
        enable_license_checking=True,
        enable_action_gating=True,
        auto_scrub=True,
        strict_mode=False,
    ),
    secret_scanner=SecretScrubberAdapter(),
    license_checker=LicenseComplianceCheckerAdapter(),
    action_gate=DangerousActionGateAdapter(),
)
```

## 🔌 Integration with Orchestrators

### Step 1: Add to Orchestrator Constructor

```python
class V8AgentOrchestrator:
    def __init__(
        self,
        # ... existing params
        safety: SafetyOrchestrator,  # Add this
    ):
        self.safety = safety
```

### Step 2: Validate Before Generation

```python
async def generate_code(self, prompt: str):
    # 1. Scrub secrets from prompt
    result = self.safety.validate_content(prompt, auto_scrub=True)
    clean_prompt = result.scrubbed_content or prompt

    # 2. Generate code
    code = await self.llm.generate(clean_prompt)

    # 3. Validate generated code
    validation = self.safety.validate_content(code, auto_scrub=False)
    if not validation.passed:
        raise SecurityError(f"Generated code failed security check: {validation.message}")

    return code
```

### Step 3: Validate Actions

```python
async def write_file(self, path: str, content: str):
    # Check if action is allowed
    result = self.safety.validate_action(
        ActionType.FILE_WRITE,
        target=path,
        description=f"Write {len(content)} bytes to {path}",
    )

    if not result.passed:
        if result.message == "Awaiting approval":
            # Handle approval workflow
            await self.request_human_approval(path)
        else:
            raise PermissionError(f"Action blocked: {result.message}")

    # Safe to proceed
    await self.filesystem.write(path, content)
```

## 🧪 Testing

```bash
# Run all safety tests
pytest tests/agent/adapters/safety/ tests/agent/domain/safety/ -v

# Run specific test
pytest tests/agent/adapters/safety/test_action_gate.py::TestRiskClassifier -v

# Check coverage
pytest tests/agent/domain/safety/ --cov=src/agent/domain/safety --cov-report=html
```

## 📊 Security Levels

### Secret Detection
- **AWS Keys**: `AKIA[0-9A-Z]{16}`
- **GitHub Tokens**: `ghp_[a-zA-Z0-9]{36}`
- **JWT**: `eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.`
- **Private Keys**: `-----BEGIN .* PRIVATE KEY-----`
- **Generic API Keys**: High entropy detection

### License Compliance
- **Allowed**: MIT, Apache 2.0, BSD, ISC
- **Blocked**: GPL v2/v3, AGPL, SSPL
- **Requires Review**: MPL, EPL, CDDL

### Risk Classification
- **CRITICAL**: `rm -rf /`, `DROP DATABASE`, `dd if=`, `mkfs`
- **HIGH**: `sudo`, `chmod 777`, Delete `.py/.js/.ts`
- **MEDIUM**: Write to `.py/.js/.ts`
- **LOW**: Write to `.txt/.md/.log`

## 🔧 Configuration

```python
from src.agent.domain.safety import SafetyConfig, ScrubberConfig, LicensePolicy, GateConfig

config = SafetyConfig(
    enable_secret_scanning=True,
    enable_license_checking=True,
    enable_action_gating=True,
    auto_scrub=True,           # Auto-fix detected secrets
    strict_mode=False,         # Stop pipeline on first failure
)

scrubber_config = ScrubberConfig(
    detect_entropy=True,       # Use Shannon entropy
    entropy_threshold=4.5,     # Bits per character
    whitelist=["EXAMPLE_KEY"], # Allowed patterns
)

gate_config = GateConfig(
    auto_approve_low_risk=True,    # Auto-approve LOW risk
    auto_approve_medium_risk=False, # Require approval for MEDIUM+
    enable_audit=True,              # Log all actions
)
```

## 🎯 Best Practices

1. **Always validate before generation**
   ```python
   # ✅ Good
   clean_prompt = safety.validate_content(prompt, auto_scrub=True).scrubbed_content
   code = generate(clean_prompt)

   # ❌ Bad
   code = generate(prompt)  # May leak secrets!
   ```

2. **Validate generated code**
   ```python
   # ✅ Good
   code = generate(prompt)
   if not safety.validate_content(code).passed:
       raise SecurityError()

   # ❌ Bad
   code = generate(prompt)
   save(code)  # No validation!
   ```

3. **Use pipeline for comprehensive checks**
   ```python
   # ✅ Good
   ctx = ValidationContext(content=code, dependencies=deps, action_type=action)
   results = safety.validate_pipeline(ctx)
   if not safety.is_safe(results):
       handle_failure(results)

   # ❌ Bad
   safety.validate_content(code)  # Only checks secrets
   ```

## 📈 Metrics

```python
# Get validation metrics
metrics = safety.get_metrics()
print(f"Total validations: {metrics['total_validations']}")
print(f"Secrets detected: {metrics['secrets_detected']}")
print(f"License violations: {metrics['license_violations']}")
print(f"Actions blocked: {metrics['actions_blocked']}")

# Reset metrics
safety.reset_metrics()
```

## 🐛 Troubleshooting

### Issue: Circular Import Error
**Solution**: Already fixed with `TYPE_CHECKING` in ports

### Issue: Port Protocol Not Recognized
**Solution**: Ensure `@runtime_checkable` decorator is present

### Issue: Too Many False Positives
**Solution**: Add to whitelist
```python
scrubber.add_to_whitelist("EXAMPLE_KEY")
gate.config.file_write_whitelist.append(r"\.log$")
```

## 📚 References

- [SOLID Principles](https://en.wikipedia.org/wiki/SOLID)
- [Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/)
- [SPDX License List](https://spdx.org/licenses/)

---

**Version**: 2.0.0
**Last Updated**: 2025-12-13
**Status**: ✅ Production-Ready
