#!/usr/bin/env python3
"""Quick indexing script for codegraph"""

import asyncio
from pathlib import Path


async def quick_index():
    print("🚀 Starting quick indexing...")

    # Use simple file scanning and vector indexing
    from codegraph_shared.infra.config.settings import Settings
    from codegraph_shared.infra.storage.sqlite import SQLiteStore
    from codegraph_shared.infra.vector import create_qdrant_client

    settings = Settings()

    # Initialize stores
    db = SQLiteStore(connection_string="data/codegraph.db")
    await db.initialize()

    qdrant = await create_qdrant_client(mode="embedded", path="data/qdrant_storage")

    # Scan Python files
    repo_path = Path(".")
    py_files = list(repo_path.rglob("*.py"))

    # Filter out venv, __pycache__, etc
    py_files = [
        f for f in py_files if ".venv" not in str(f) and "__pycache__" not in str(f) and "benchmark" not in str(f)
    ]

    print(f"📁 Found {len(py_files)} Python files")

    # Simple indexing: read files and store in vector DB
    from codegraph_shared.infra.llm.local_llm import LocalLLMAdapter

    llm = LocalLLMAdapter(settings)

    indexed = 0
    for py_file in py_files[:100]:  # Limit to 100 files for quick test
        try:
            content = py_file.read_text()
            if len(content) > 100:  # Skip empty files
                # Generate embedding
                embedding = await llm.embed(content[:1000])  # First 1000 chars

                # Store in Qdrant
                await qdrant.upsert(
                    collection_name="chunks",
                    points=[
                        {
                            "id": str(indexed),
                            "vector": embedding,
                            "payload": {
                                "file_path": str(py_file),
                                "content": content[:500],
                            },
                        }
                    ],
                )
                indexed += 1
                if indexed % 10 == 0:
                    print(f"  ✓ Indexed {indexed} files...")
        except Exception as e:
            print(f"  ⚠ Error indexing {py_file}: {e}")

    print(f"\n✅ Indexing complete: {indexed} files indexed")


if __name__ == "__main__":
    asyncio.run(quick_index())
