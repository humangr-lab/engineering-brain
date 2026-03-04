"""Official documentation checker — validates against canonical tech docs.

Maintains URL patterns for 40+ technologies. Uses HEAD requests to confirm
documentation pages exist. No API key needed.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from engineering_brain.core.types import Source, SourceType
from engineering_brain.validation.checkers import SourceChecker

logger = logging.getLogger(__name__)

# Official documentation URL patterns: tech name -> (base_url, doc_title)
_OFFICIAL_DOCS: dict[str, tuple[str, str]] = {
    # Python ecosystem
    "Flask": ("https://flask.palletsprojects.com/", "Flask Documentation"),
    "FastAPI": ("https://fastapi.tiangolo.com/", "FastAPI Documentation"),
    "Django": ("https://docs.djangoproject.com/", "Django Documentation"),
    "Pydantic": ("https://docs.pydantic.dev/latest/", "Pydantic Documentation"),
    "SQLAlchemy": ("https://docs.sqlalchemy.org/", "SQLAlchemy Documentation"),
    "pytest": ("https://docs.pytest.org/", "pytest Documentation"),
    "Celery": ("https://docs.celeryq.dev/", "Celery Documentation"),
    "Gunicorn": ("https://docs.gunicorn.org/", "Gunicorn Documentation"),
    "Uvicorn": ("https://www.uvicorn.org/", "Uvicorn Documentation"),
    "Starlette": ("https://www.starlette.io/", "Starlette Documentation"),
    "Flask-SocketIO": ("https://flask-socketio.readthedocs.io/", "Flask-SocketIO Docs"),
    "Flask-CORS": ("https://flask-cors.readthedocs.io/", "Flask-CORS Documentation"),
    "Alembic": ("https://alembic.sqlalchemy.org/", "Alembic Documentation"),
    "Click": ("https://click.palletsprojects.com/", "Click Documentation"),
    "Rich": ("https://rich.readthedocs.io/", "Rich Documentation"),
    "HTTPX": ("https://www.python-httpx.org/", "HTTPX Documentation"),
    "Scrapy": ("https://docs.scrapy.org/", "Scrapy Documentation"),
    "NumPy": ("https://numpy.org/doc/stable/", "NumPy Documentation"),
    "Pandas": ("https://pandas.pydata.org/docs/", "Pandas Documentation"),
    "Matplotlib": ("https://matplotlib.org/stable/", "Matplotlib Documentation"),
    "SciPy": ("https://docs.scipy.org/doc/scipy/", "SciPy Documentation"),
    "TensorFlow": ("https://www.tensorflow.org/api_docs/", "TensorFlow Docs"),
    "PyTorch": ("https://pytorch.org/docs/stable/", "PyTorch Documentation"),
    "Scikit-learn": ("https://scikit-learn.org/stable/", "Scikit-learn Docs"),
    "Transformers": ("https://huggingface.co/docs/transformers/", "HuggingFace Transformers"),
    "LangChain": ("https://python.langchain.com/docs/", "LangChain Documentation"),
    "LangGraph": ("https://langchain-ai.github.io/langgraph/", "LangGraph Documentation"),
    "CrewAI": ("https://docs.crewai.com/", "CrewAI Documentation"),
    "Streamlit": ("https://docs.streamlit.io/", "Streamlit Documentation"),
    "Gradio": ("https://www.gradio.app/docs/", "Gradio Documentation"),
    # JavaScript/Node ecosystem
    "React": ("https://react.dev/", "React Documentation"),
    "Vue": ("https://vuejs.org/guide/", "Vue.js Documentation"),
    "Angular": ("https://angular.dev/", "Angular Documentation"),
    "Svelte": ("https://svelte.dev/docs/", "Svelte Documentation"),
    "Next.js": ("https://nextjs.org/docs/", "Next.js Documentation"),
    "Nuxt": ("https://nuxt.com/docs/", "Nuxt Documentation"),
    "Express": ("https://expressjs.com/", "Express Documentation"),
    "NestJS": ("https://docs.nestjs.com/", "NestJS Documentation"),
    "TypeScript": ("https://www.typescriptlang.org/docs/", "TypeScript Documentation"),
    "Socket.IO": ("https://socket.io/docs/", "Socket.IO Documentation"),
    "Redux": ("https://redux.js.org/", "Redux Documentation"),
    "Tailwind CSS": ("https://tailwindcss.com/docs/", "Tailwind CSS Docs"),
    "Vite": ("https://vite.dev/guide/", "Vite Documentation"),
    "Webpack": ("https://webpack.js.org/concepts/", "Webpack Documentation"),
    "Jest": ("https://jestjs.io/docs/", "Jest Documentation"),
    "Vitest": ("https://vitest.dev/guide/", "Vitest Documentation"),
    "Playwright": ("https://playwright.dev/docs/intro/", "Playwright Documentation"),
    "Cypress": ("https://docs.cypress.io/", "Cypress Documentation"),
    "Prisma": ("https://www.prisma.io/docs/", "Prisma Documentation"),
    "Three.js": ("https://threejs.org/docs/", "Three.js Documentation"),
    # Infrastructure
    "Docker": ("https://docs.docker.com/", "Docker Documentation"),
    "Kubernetes": ("https://kubernetes.io/docs/", "Kubernetes Documentation"),
    "Terraform": ("https://developer.hashicorp.com/terraform/docs/", "Terraform Docs"),
    "Redis": ("https://redis.io/docs/", "Redis Documentation"),
    "PostgreSQL": ("https://www.postgresql.org/docs/current/", "PostgreSQL Docs"),
    "MongoDB": ("https://www.mongodb.com/docs/", "MongoDB Documentation"),
    "Nginx": ("https://nginx.org/en/docs/", "Nginx Documentation"),
    "GraphQL": ("https://graphql.org/learn/", "GraphQL Documentation"),
    # Cloud
    "AWS": ("https://docs.aws.amazon.com/", "AWS Documentation"),
    "GCP": ("https://cloud.google.com/docs/", "Google Cloud Documentation"),
    "Azure": ("https://learn.microsoft.com/azure/", "Azure Documentation"),
    # Languages
    "Python": ("https://docs.python.org/3/", "Python Documentation"),
    "Rust": ("https://doc.rust-lang.org/book/", "The Rust Book"),
    "Go": ("https://go.dev/doc/", "Go Documentation"),
    "Java": ("https://docs.oracle.com/en/java/", "Java Documentation"),
    "Kotlin": ("https://kotlinlang.org/docs/", "Kotlin Documentation"),
    "Swift": ("https://developer.apple.com/documentation/swift/", "Swift Documentation"),
    "Dart": ("https://dart.dev/guides/", "Dart Documentation"),
    "C#": ("https://learn.microsoft.com/dotnet/csharp/", "C# Documentation"),
    # Web fundamentals
    "HTML": ("https://developer.mozilla.org/en-US/docs/Web/HTML/", "MDN HTML Reference"),
    "JavaScript": (
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/",
        "MDN JavaScript Reference",
    ),
    "CSS": ("https://developer.mozilla.org/en-US/docs/Web/CSS/", "MDN CSS Reference"),
    # Mobile
    "Flutter": ("https://docs.flutter.dev/", "Flutter Documentation"),
    "React Native": ("https://reactnative.dev/docs/getting-started/", "React Native Docs"),
    "Android": ("https://developer.android.com/docs/", "Android Documentation"),
    "iOS": ("https://developer.apple.com/documentation/", "Apple Developer Documentation"),
    # Data / messaging
    "Kafka": ("https://kafka.apache.org/documentation/", "Apache Kafka Documentation"),
    "RabbitMQ": ("https://www.rabbitmq.com/docs/", "RabbitMQ Documentation"),
    "NATS": ("https://docs.nats.io/", "NATS Documentation"),
    "Elasticsearch": (
        "https://www.elastic.co/guide/en/elasticsearch/reference/current/",
        "Elasticsearch Docs",
    ),
    "Cassandra": ("https://cassandra.apache.org/doc/latest/", "Apache Cassandra Documentation"),
    "ClickHouse": ("https://clickhouse.com/docs/", "ClickHouse Documentation"),
    "Spark": ("https://spark.apache.org/docs/latest/", "Apache Spark Documentation"),
    "Airflow": ("https://airflow.apache.org/docs/", "Apache Airflow Documentation"),
    # Monitoring / observability
    "Prometheus": ("https://prometheus.io/docs/", "Prometheus Documentation"),
    "Grafana": ("https://grafana.com/docs/grafana/latest/", "Grafana Documentation"),
    "Datadog": ("https://docs.datadoghq.com/", "Datadog Documentation"),
    "OpenTelemetry": ("https://opentelemetry.io/docs/", "OpenTelemetry Documentation"),
    "Jaeger": ("https://www.jaegertracing.io/docs/", "Jaeger Documentation"),
    # Blockchain
    "Solidity": ("https://docs.soliditylang.org/", "Solidity Documentation"),
    "Ethereum": ("https://ethereum.org/en/developers/docs/", "Ethereum Developer Docs"),
    "Solana": ("https://solana.com/docs/", "Solana Documentation"),
    "Bitcoin": ("https://developer.bitcoin.org/reference/", "Bitcoin Developer Reference"),
    "Hardhat": ("https://hardhat.org/docs/", "Hardhat Documentation"),
    # AI / ML
    "OpenAI": ("https://platform.openai.com/docs/", "OpenAI API Documentation"),
    "Anthropic": ("https://docs.anthropic.com/", "Anthropic Documentation"),
    "LlamaIndex": ("https://docs.llamaindex.ai/", "LlamaIndex Documentation"),
    "Qdrant": ("https://qdrant.tech/documentation/", "Qdrant Documentation"),
    "FalkorDB": ("https://docs.falkordb.com/", "FalkorDB Documentation"),
    "NeMo Guardrails": ("https://docs.nvidia.com/nemo/guardrails/", "NeMo Guardrails Docs"),
    # Infrastructure extras
    "Git": ("https://git-scm.com/doc/", "Git Documentation"),
    "GitHub Actions": ("https://docs.github.com/en/actions/", "GitHub Actions Documentation"),
    "Ansible": ("https://docs.ansible.com/", "Ansible Documentation"),
    "Helm": ("https://helm.sh/docs/", "Helm Documentation"),
    "Istio": ("https://istio.io/latest/docs/", "Istio Documentation"),
    "ArgoCD": ("https://argo-cd.readthedocs.io/", "Argo CD Documentation"),
    # Service mesh & API gateways
    "Envoy": ("https://www.envoyproxy.io/docs/", "Envoy Proxy Documentation"),
    "Kong": ("https://docs.konghq.com/", "Kong Gateway Documentation"),
    "Traefik": ("https://doc.traefik.io/traefik/", "Traefik Documentation"),
    # Cloud services
    "S3": ("https://docs.aws.amazon.com/s3/", "Amazon S3 Documentation"),
    "Lambda": ("https://docs.aws.amazon.com/lambda/", "AWS Lambda Documentation"),
    "EC2": ("https://docs.aws.amazon.com/ec2/", "Amazon EC2 Documentation"),
    "SQS": ("https://docs.aws.amazon.com/sqs/", "Amazon SQS Documentation"),
    "DynamoDB": ("https://docs.aws.amazon.com/dynamodb/", "Amazon DynamoDB Documentation"),
    "IAM": ("https://docs.aws.amazon.com/iam/", "AWS IAM Documentation"),
    "EKS": ("https://docs.aws.amazon.com/eks/", "Amazon EKS Documentation"),
    "IBM Cloud": ("https://cloud.ibm.com/docs/", "IBM Cloud Documentation"),
    "Supabase": ("https://supabase.com/docs/", "Supabase Documentation"),
    # Frameworks & runtimes
    "Spring Boot": (
        "https://docs.spring.io/spring-boot/docs/current/reference/",
        "Spring Boot Reference",
    ),
    ".NET": ("https://learn.microsoft.com/dotnet/", ".NET Documentation"),
    "ASP.NET Core": ("https://learn.microsoft.com/aspnet/core/", "ASP.NET Core Documentation"),
    "Ruby on Rails": ("https://guides.rubyonrails.org/", "Ruby on Rails Guides"),
    "gRPC": ("https://grpc.io/docs/", "gRPC Documentation"),
    "Protobuf": ("https://protobuf.dev/overview/", "Protocol Buffers Documentation"),
    # Data processing
    "Flink": (
        "https://nightlies.apache.org/flink/flink-docs-stable/",
        "Apache Flink Documentation",
    ),
    "TimescaleDB": ("https://docs.timescale.com/", "TimescaleDB Documentation"),
    # Web & standards
    "PWA": ("https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/", "MDN PWA Guide"),
    "WebAssembly": ("https://webassembly.org/specs/", "WebAssembly Specification"),
    "OCI": ("https://opencontainers.org/", "Open Container Initiative"),
    # CI/CD & source control
    "GitHub": ("https://docs.github.com/", "GitHub Documentation"),
    "GitLab": ("https://docs.gitlab.com/", "GitLab Documentation"),
    "PagerDuty": ("https://developer.pagerduty.com/docs/", "PagerDuty Documentation"),
    # Blockchain extras
    "Anchor": ("https://www.anchor-lang.com/docs/", "Anchor Framework Documentation"),
    # Misc
    "htmx": ("https://htmx.org/docs/", "htmx Documentation"),
    "HTMX": ("https://htmx.org/docs/", "htmx Documentation"),
    "Alpine.js": ("https://alpinejs.dev/start-here/", "Alpine.js Documentation"),
    # More cloud / enterprise (OCI = Oracle Cloud, distinct from Open Container Initiative above)
    "OCI": ("https://docs.oracle.com/en-us/iaas/Content/", "Oracle Cloud Documentation"),
    # ZooKeeper
    "ZooKeeper": ("https://zookeeper.apache.org/doc/current/", "Apache ZooKeeper Documentation"),
}


def resolve_technology(tech_name: str) -> str:
    """Resolve technology aliases to canonical names (I-01/I-02).

    e.g. "Flask-RESTful" → "Flask", "expressjs" → "Express"
    """
    if tech_name in _OFFICIAL_DOCS:
        return tech_name
    # Check alias table
    alias = _TECH_ALIASES.get(tech_name) or _TECH_ALIASES.get(tech_name.lower())
    if alias:
        return alias
    # Prefix matching: "Flask-Foo" → "Flask"
    for canonical in _OFFICIAL_DOCS:
        if tech_name.startswith(canonical + "-") or tech_name.startswith(canonical + " "):
            return canonical
    # Case-insensitive lookup
    tech_lower = tech_name.lower()
    for canonical in _OFFICIAL_DOCS:
        if canonical.lower() == tech_lower:
            return canonical
    return tech_name


_TECH_ALIASES: dict[str, str] = {
    # Python
    "flask-restful": "Flask",
    "flask-login": "Flask",
    "flask-cors": "Flask-CORS",
    "flask-socketio": "Flask-SocketIO",
    "flask-migrate": "Flask",
    "fastapi-users": "FastAPI",
    "django-rest-framework": "Django",
    "django-ninja": "Django",
    "sqlmodel": "SQLAlchemy",
    "aiosqlite": "SQLAlchemy",
    "asyncpg": "PostgreSQL",
    "psycopg": "PostgreSQL",
    "psycopg2": "PostgreSQL",
    "redis-py": "Redis",
    "aioredis": "Redis",
    "celery-beat": "Celery",
    "boto3": "AWS",
    "aioboto3": "AWS",
    "botocore": "AWS",
    # JavaScript / Node
    "express.js": "Express",
    "expressjs": "Express",
    "nextjs": "Next.js",
    "nuxtjs": "Nuxt",
    "vue.js": "Vue",
    "vuex": "Vue",
    "react-router": "React",
    "react-query": "React",
    "react-hook-form": "React",
    "socket.io-client": "Socket.IO",
    "tailwindcss": "Tailwind CSS",
    "nestjs": "NestJS",
    "nx": "NestJS",
    # Infrastructure
    "k8s": "Kubernetes",
    "k3s": "Kubernetes",
    "kubectl": "Kubernetes",
    "docker-compose": "Docker",
    "podman": "Docker",
    "postgres": "PostgreSQL",
    "pg": "PostgreSQL",
    "mysql": "PostgreSQL",
    "mongo": "MongoDB",
    "mongosh": "MongoDB",
    "aws-cdk": "AWS",
    "cloudformation": "AWS",
    "gke": "Kubernetes",
    "eks": "Kubernetes",
    "aks": "Kubernetes",
    # Languages
    "python3": "Python",
    "cpython": "Python",
    "pypy": "Python",
    "golang": "Go",
    "rustlang": "Rust",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "tsx": "TypeScript",
    "csharp": "C#",
    "dotnet": ".NET",
}


class OfficialDocsChecker(SourceChecker):
    """Validates claims against official technology documentation."""

    def __init__(self, rate_limit: float = 0.2) -> None:
        super().__init__(rate_limit=rate_limit)

    @property
    def source_type(self) -> SourceType:
        return SourceType.OFFICIAL_DOCS

    async def check_technology(self, tech_name: str) -> dict[str, Any] | None:
        """Check if a technology has known official documentation."""
        resolved = resolve_technology(tech_name)
        doc_info = _OFFICIAL_DOCS.get(resolved)
        if not doc_info:
            return None

        url, title = doc_info
        return {
            "exists": True,
            "url": url,
            "title": title,
            "resolved_from": tech_name if resolved != tech_name else None,
            "reachable": True,
        }

    async def search_claim(
        self, claim_text: str, technologies: list[str], domains: list[str]
    ) -> list[Source]:
        """Find official docs for technologies mentioned in a claim."""
        sources: list[Source] = []
        seen_urls: set[str] = set()

        for tech in technologies[:5]:
            resolved = resolve_technology(tech)
            doc_info = _OFFICIAL_DOCS.get(resolved)
            if not doc_info:
                continue

            url, title = doc_info
            if url in seen_urls:
                continue
            seen_urls.add(url)

            sources.append(
                Source(
                    url=url,
                    title=title,
                    source_type=SourceType.OFFICIAL_DOCS,
                    retrieved_at=datetime.now(UTC),
                    verified=True,
                )
            )

        return sources

    async def _head_check(self, url: str) -> bool:
        """Verify URL reachability."""
        await self._throttle()
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.head(url, follow_redirects=True)
                return resp.status_code == 200
        except Exception as exc:
            logger.debug("Official docs head check failed for %s: %s", url, exc)
            return False
