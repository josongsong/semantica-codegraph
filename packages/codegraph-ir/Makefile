# Makefile for codegraph-ir
# Provides convenient commands for testing, building, and development

.PHONY: help test test-all test-slow test-unit test-integration test-e2e test-watch
.PHONY: bench coverage fmt lint clean doc install dev-deps

# Default target
.DEFAULT_GOAL := help

help: ## Show this help message
	@echo "codegraph-ir development commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Testing
test: ## Run all tests (excluding slow tests)
	cargo test --all-features --verbose

test-all: ## Run all tests including slow ones
	cargo test --all-features --verbose
	cargo test --all-features --verbose -- --ignored

test-slow: ## Run only slow tests
	cargo test --all-features --verbose -- --ignored

test-unit: ## Run only unit tests
	cargo test --lib --all-features --verbose

test-integration: ## Run only integration tests
	cargo test --test '*' --all-features --verbose

test-e2e: ## Run only end-to-end tests
	cargo test --test '*' --all-features --verbose -- e2e::

test-proptest: ## Run property-based tests with more cases
	PROPTEST_CASES=10000 cargo test --test proptest_parsing --verbose

test-watch: ## Run tests in watch mode
	cargo watch -c -x test

test-nocapture: ## Run tests with output
	cargo test --all-features -- --nocapture

# Benchmarking
bench: ## Run all benchmarks
	cargo bench --all-features

bench-parsing: ## Run parsing benchmarks only
	cargo bench --bench parsing_benchmarks

bench-pipeline: ## Run pipeline benchmarks only
	cargo bench --bench pipeline_benchmarks

bench-baseline: ## Save benchmark baseline
	cargo bench -- --save-baseline main

bench-compare: ## Compare against baseline
	cargo bench -- --baseline main

# Coverage
coverage: ## Generate test coverage report (HTML)
	cargo llvm-cov --workspace --all-features --html
	@echo "Coverage report generated at target/llvm-cov/html/index.html"

coverage-open: coverage ## Generate and open coverage report
	open target/llvm-cov/html/index.html

coverage-lcov: ## Generate coverage in LCOV format (for CI)
	cargo llvm-cov --workspace --all-features --lcov --output-path lcov.info

coverage-text: ## Show coverage summary in terminal
	cargo llvm-cov --workspace --all-features

# Code Quality
fmt: ## Format code
	cargo fmt --all

fmt-check: ## Check code formatting
	cargo fmt --all -- --check

lint: ## Run clippy lints
	cargo clippy --workspace --all-targets --all-features -- -D warnings

lint-fix: ## Apply clippy fixes
	cargo clippy --workspace --all-targets --all-features --fix

check: fmt-check lint test ## Run all checks (format, lint, test)

# Documentation
doc: ## Build documentation
	cargo doc --workspace --all-features --no-deps

doc-open: ## Build and open documentation
	cargo doc --workspace --all-features --no-deps --open

doc-test: ## Run documentation tests
	cargo test --workspace --doc

# Building
build: ## Build in debug mode
	cargo build --all-features

build-release: ## Build in release mode
	cargo build --all-features --release

build-python: ## Build Python bindings
	maturin develop --release

# Cleaning
clean: ## Clean build artifacts
	cargo clean
	rm -rf target/
	rm -f lcov.info

clean-coverage: ## Clean coverage data
	cargo llvm-cov clean

# Installation
install-dev-deps: ## Install development dependencies
	cargo install cargo-watch
	cargo install cargo-llvm-cov
	cargo install cargo-audit
	cargo install cargo-outdated
	cargo install maturin

install-tools: install-dev-deps ## Alias for install-dev-deps

# Development
dev: ## Start development mode (watch + test)
	cargo watch -c -x 'test --all-features'

dev-check: ## Watch mode for check + test
	cargo watch -c -x check -x 'test --all-features'

# CI Simulation
ci: fmt-check lint test-all coverage-lcov ## Run all CI checks locally
	@echo "✅ All CI checks passed!"

ci-fast: fmt-check lint test ## Run fast CI checks only
	@echo "✅ Fast CI checks passed!"

# Security
audit: ## Run security audit
	cargo audit

outdated: ## Check for outdated dependencies
	cargo outdated

# Utility
tree: ## Show dependency tree
	cargo tree

bloat: ## Analyze binary size
	cargo bloat --release

update: ## Update dependencies
	cargo update

# Python Tests
test-python: build-python ## Run Python integration tests
	cd tests/python && pytest -v

test-python-integration: build-python ## Run Python integration tests only
	cd tests/python && pytest integration/ -v

test-python-benchmark: build-python ## Run Python benchmark tests
	cd tests/python && pytest benchmarks/ -v -s

test-python-all: build-python ## Run all Python tests including slow ones
	cd tests/python && pytest -m "" -v

test-python-watch: ## Watch and run Python tests
	cd tests/python && pytest-watch

# Workspace
workspace-test: ## Test entire workspace
	cd ../.. && cargo test --workspace --all-features

workspace-build: ## Build entire workspace
	cd ../.. && cargo build --workspace --all-features

# Examples
example-pipeline: ## Run pipeline example
	cargo run --example simple_pipeline --features python

# Quick shortcuts
t: test ## Shortcut for test
b: build ## Shortcut for build
c: check ## Shortcut for check
f: fmt ## Shortcut for fmt
d: doc-open ## Shortcut for doc-open
w: test-watch ## Shortcut for test-watch
