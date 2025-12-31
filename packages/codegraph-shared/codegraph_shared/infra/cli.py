"""
Infrastructure CLI for debugging.

Usage:
    python -m src.infra.cli health
    python -m src.infra.cli stats
    python -m src.infra.cli test-circuit-breaker
"""

import asyncio

import typer

app = typer.Typer(help="Infrastructure debugging CLI")


@app.command()
def health():
    """Check all infrastructure health."""

    async def _check():
        from codegraph_shared.infra.config.settings import Settings
        from codegraph_shared.infra.storage.postgres_enhanced import EnhancedPostgresStore

        settings = Settings()

        typer.echo("🏥 Infrastructure Health Check")
        typer.echo("=" * 60)

        # PostgreSQL
        try:
            store = EnhancedPostgresStore(
                settings.database_url,
                enable_circuit_breaker=True,
            )

            is_healthy, details = await store.health_check()

            status_emoji = "✅" if is_healthy else "❌"
            typer.echo(f"\n{status_emoji} PostgreSQL: {details['status'].upper()}")
            typer.echo(f"   Latency: {details.get('latency_ms', 'N/A'):.2f}ms")
            typer.echo(f"   Pool: {details.get('pool_free', 0)}/{details.get('pool_size', 0)} free")
            typer.echo(f"   Error rate: {details.get('error_rate', 0):.2%}")

            if details.get("circuit_breaker"):
                cb = details["circuit_breaker"]
                typer.echo(f"   Circuit: {cb['state'].upper()} ({cb['failure_count']} failures)")

            await store.close()

        except Exception as e:
            typer.echo(f"❌ PostgreSQL: ERROR - {e}", err=True)

        typer.echo("\n" + "=" * 60)

    asyncio.run(_check())


@app.command()
def stats():
    """Show infrastructure statistics."""
    from codegraph_shared.common.observability import get_metrics_collector

    collector = get_metrics_collector()
    metrics = collector.get_all_metrics()

    typer.echo("\n📊 Infrastructure Metrics")
    typer.echo("=" * 60)

    # Counters
    typer.echo("\n🔢 Counters:")
    for name, value in sorted(metrics["counters"].items()):
        typer.echo(f"   {name}: {value:,.0f}")

    # Gauges
    typer.echo("\n📏 Gauges:")
    for name, value in sorted(metrics["gauges"].items()):
        typer.echo(f"   {name}: {value:.2f}")

    # Histograms (P50, P95, P99)
    typer.echo("\n📈 Histograms:")
    for name in sorted(metrics["histograms"].keys()):
        stats_data = collector.get_histogram_stats(name)
        typer.echo(f"   {name}:")
        typer.echo(f"      P50: {stats_data['p50']:.2f}")
        typer.echo(f"      P95: {stats_data['p95']:.2f}")
        typer.echo(f"      P99: {stats_data['p99']:.2f}")

    typer.echo("\n" + "=" * 60)


@app.command()
def test_circuit_breaker(
    failures: int = typer.Option(5, help="Number of failures to trigger"),
):
    """Test circuit breaker behavior."""

    async def _test():
        from codegraph_shared.infra.resilience import CircuitBreaker, CircuitBreakerConfig

        typer.echo(f"\n⚡ Testing Circuit Breaker (trigger after {failures} failures)")
        typer.echo("=" * 60)

        breaker = CircuitBreaker(
            "test",
            CircuitBreakerConfig(
                failure_threshold=failures,
                timeout=5.0,
            ),
            debug=True,
        )

        # Fail N times
        for i in range(failures + 3):
            try:
                async with breaker:
                    if i < failures:
                        raise RuntimeError(f"Simulated failure {i + 1}")
                    else:
                        typer.echo(f"   ✅ Attempt {i + 1}: Success")
            except Exception as e:
                typer.echo(f"   ❌ Attempt {i + 1}: {type(e).__name__}")

            await asyncio.sleep(0.1)

        # Print final stats
        typer.echo()
        breaker.print_stats()

    asyncio.run(_test())


if __name__ == "__main__":
    app()
