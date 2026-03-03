"""PyPI + npm package registry checker.

Validates that referenced technologies exist as real packages.
No API key needed. No real rate limits (CDN-backed).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from engineering_brain.core.types import Source, SourceType
from engineering_brain.validation.checkers import SourceChecker

logger = logging.getLogger(__name__)

# Map brain technology names → PyPI package names
_PYPI_MAP: dict[str, str] = {
    "Flask": "flask", "FastAPI": "fastapi", "Django": "django",
    "Pydantic": "pydantic", "SQLAlchemy": "sqlalchemy", "pytest": "pytest",
    "Gunicorn": "gunicorn", "Celery": "celery", "Airflow": "apache-airflow",
    "Alembic": "alembic", "Jinja2": "jinja2", "CrewAI": "crewai",
    "LangChain": "langchain", "Pandas": "pandas", "NumPy": "numpy",
    "Redis": "redis", "Requests": "requests", "HTTPX": "httpx",
    "Flask-SocketIO": "flask-socketio", "Flask-CORS": "flask-cors",
    "CORS": "flask-cors", "Uvicorn": "uvicorn", "Starlette": "starlette",
    "Click": "click", "Rich": "rich", "Typer": "typer",
    "Boto3": "boto3", "Scrapy": "scrapy", "BeautifulSoup": "beautifulsoup4",
    "Pillow": "pillow", "Matplotlib": "matplotlib", "SciPy": "scipy",
    "TensorFlow": "tensorflow", "PyTorch": "torch", "Scikit-learn": "scikit-learn",
    "Transformers": "transformers", "LangGraph": "langgraph",
    "Qdrant": "qdrant-client", "FalkorDB": "falkordb",
    "Neo4j": "neo4j", "MongoDB": "pymongo", "PostgreSQL": "psycopg2",
    "MySQL": "mysqlclient", "SQLite": "sqlite3",
    "Pydantic v2": "pydantic", "Python": "", "Cython": "cython",
    "Poetry": "poetry", "Black": "black", "Ruff": "ruff",
    "MyPy": "mypy", "Sphinx": "sphinx", "MkDocs": "mkdocs",
    "SocketIO": "python-socketio",
    "NeMo Guardrails": "nemoguardrails", "LlamaIndex": "llama-index",
    "DSPy": "dspy-ai", "Instructor": "instructor",
    "Streamlit": "streamlit", "Gradio": "gradio",
    # Data / messaging
    "Kafka": "confluent-kafka", "confluent-kafka": "confluent-kafka",
    "Elasticsearch": "elasticsearch", "Cassandra": "cassandra-driver",
    "ClickHouse": "clickhouse-connect", "Spark": "pyspark", "PySpark": "pyspark",
    "RabbitMQ": "pika", "NATS": "nats-py",
    # Monitoring
    "Prometheus": "prometheus-client", "Datadog": "datadog",
    "OpenTelemetry": "opentelemetry-api", "Jaeger": "jaeger-client",
    # AI / ML
    "OpenAI": "openai", "Anthropic": "anthropic",
    "Langfuse": "langfuse", "LiteLLM": "litellm",
    # Blockchain
    "Solidity": "", "Hardhat": "",
    # Service mesh & gateways
    "gRPC": "grpcio", "Protobuf": "protobuf",
    # Data
    "Flink": "apache-flink", "TimescaleDB": "timescaledb",
    "DynamoDB": "boto3",
    # Frameworks
    "Spring Boot": "", ".NET": "", "ASP.NET Core": "",
    "Ruby on Rails": "",
    # Other
    "Ansible": "ansible", "Terraform": "",
    "Supabase": "supabase", "structlog": "structlog",
}

# Map brain technology names → npm package names
_NPM_MAP: dict[str, str] = {
    "React": "react", "Vue": "vue", "Angular": "@angular/core",
    "Svelte": "svelte", "Next.js": "next", "Nuxt": "nuxt",
    "Express": "express", "Remix": "remix", "Astro": "astro",
    "TypeScript": "typescript", "Webpack": "webpack", "Vite": "vite",
    "Tailwind CSS": "tailwindcss", "Socket.IO": "socket.io",
    "Redux": "redux", "Zustand": "zustand", "Jotai": "jotai",
    "React Query": "@tanstack/react-query", "SWR": "swr",
    "Playwright": "playwright", "Cypress": "cypress", "Jest": "jest",
    "Vitest": "vitest", "ESLint": "eslint", "Prettier": "prettier",
    "Node.js": "node", "Deno": "deno", "Bun": "bun",
    "Three.js": "three", "D3": "d3", "Chart.js": "chart.js",
    "HTMX": "htmx.org", "Alpine.js": "alpinejs",
    "NestJS": "@nestjs/core", "Fastify": "fastify",
    "Prisma": "prisma", "Drizzle": "drizzle-orm",
    "tRPC": "@trpc/server", "GraphQL": "graphql",
    "Apollo": "@apollo/client", "Axios": "axios",
    "React Native": "react-native", "Expo": "expo",
    "Electron": "electron", "Tauri": "@tauri-apps/api",
    "Storybook": "storybook",
    # Mobile
    "React Native": "react-native", "Expo": "expo",
    # Build tools
    "Turbopack": "turbo",
}


class PackageRegistryChecker(SourceChecker):
    """Checks PyPI and npm for package existence and metadata."""

    @property
    def source_type(self) -> SourceType:
        return SourceType.PACKAGE_REGISTRY

    async def check_technology(self, tech_name: str) -> dict[str, Any] | None:
        """Check if technology exists on PyPI or npm."""
        # Try PyPI first
        pypi_pkg = _PYPI_MAP.get(tech_name)
        if pypi_pkg:
            result = await self._check_pypi(pypi_pkg)
            if result:
                result["tech_name"] = tech_name
                return result

        # Try npm
        npm_pkg = _NPM_MAP.get(tech_name)
        if npm_pkg:
            result = await self._check_npm(npm_pkg)
            if result:
                result["tech_name"] = tech_name
                return result

        # Not in our maps — could be a platform (AWS, Kubernetes, etc.)
        return None

    async def _check_pypi(self, package: str) -> dict[str, Any] | None:
        """Query PyPI JSON API."""
        if not package:
            return None
        await self._throttle()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"https://pypi.org/pypi/{package}/json")
                if resp.status_code == 404:
                    return {"exists": False, "registry": "pypi", "package": package}
                data = resp.json()
                info = data.get("info", {})
                return {
                    "exists": True,
                    "registry": "pypi",
                    "package": package,
                    "version": info.get("version", ""),
                    "summary": (info.get("summary") or "")[:200],
                    "home_page": info.get("home_page") or info.get("project_url") or "",
                    "is_deprecated": _is_pypi_deprecated(info),
                    "license": (info.get("license") or "")[:50],
                }
        except Exception as e:
            logger.debug("PyPI check failed for %s: %s", package, e)
            return None

    async def _check_npm(self, package: str) -> dict[str, Any] | None:
        """Query npm registry API."""
        if not package:
            return None
        await self._throttle()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"https://registry.npmjs.org/{package}")
                if resp.status_code == 404:
                    return {"exists": False, "registry": "npm", "package": package}
                data = resp.json()
                latest = data.get("dist-tags", {}).get("latest", "")
                return {
                    "exists": True,
                    "registry": "npm",
                    "package": package,
                    "version": latest,
                    "summary": (data.get("description") or "")[:200],
                    "home_page": data.get("homepage") or "",
                    "is_deprecated": bool(data.get("deprecated")),
                    "license": (data.get("license") or "")[:50] if isinstance(data.get("license"), str) else "",
                }
        except Exception as e:
            logger.debug("npm check failed for %s: %s", package, e)
            return None

    async def search_claim(self, claim_text: str, technologies: list[str], domains: list[str]) -> list[Source]:
        """Verify technologies exist on PyPI/npm. Returns Source for each found package."""
        sources: list[Source] = []

        for tech in technologies[:5]:
            pypi_pkg = _PYPI_MAP.get(tech)
            if pypi_pkg:
                result = await self._check_pypi(pypi_pkg)
                if result and result.get("exists"):
                    sources.append(Source(
                        url=f"https://pypi.org/project/{pypi_pkg}/",
                        title=f"PyPI: {pypi_pkg} v{result.get('version', '?')}",
                        source_type=SourceType.PACKAGE_REGISTRY,
                        retrieved_at=datetime.now(timezone.utc),
                        verified=True,
                    ))
                continue

            npm_pkg = _NPM_MAP.get(tech)
            if npm_pkg:
                result = await self._check_npm(npm_pkg)
                if result and result.get("exists"):
                    sources.append(Source(
                        url=f"https://www.npmjs.com/package/{npm_pkg}",
                        title=f"npm: {npm_pkg} v{result.get('version', '?')}",
                        source_type=SourceType.PACKAGE_REGISTRY,
                        retrieved_at=datetime.now(timezone.utc),
                        verified=True,
                    ))

        return sources


def _is_pypi_deprecated(info: dict) -> bool:
    """Heuristic: check if a PyPI package is deprecated."""
    classifiers = info.get("classifiers") or []
    for c in classifiers:
        if "inactive" in c.lower() or "deprecated" in c.lower():
            return True
    summary = (info.get("summary") or "").lower()
    return "deprecated" in summary or "no longer maintained" in summary
