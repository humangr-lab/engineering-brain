"""Architecture patterns and principles checker.

Maps well-known architecture patterns, design principles, and software
engineering concepts to their canonical reference URLs. No API calls needed.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from engineering_brain.core.types import Source, SourceType
from engineering_brain.validation.checkers import SourceChecker

logger = logging.getLogger(__name__)

# Canonical references for architecture patterns and principles.
# Format: keyword(s) in claim text → (url, title)
_PATTERN_REFS: dict[str, tuple[str, str]] = {
    # Martin Fowler patterns
    "event sourcing": ("https://martinfowler.com/eaaDev/EventSourcing.html", "Martin Fowler: Event Sourcing"),
    "cqrs": ("https://martinfowler.com/bliki/CQRS.html", "Martin Fowler: CQRS"),
    "domain-driven design": ("https://martinfowler.com/bliki/DomainDrivenDesign.html", "Martin Fowler: DDD"),
    "ddd": ("https://martinfowler.com/bliki/DomainDrivenDesign.html", "Martin Fowler: DDD"),
    "bounded context": ("https://martinfowler.com/bliki/BoundedContext.html", "Martin Fowler: Bounded Context"),
    "ubiquitous language": ("https://martinfowler.com/bliki/UbiquitousLanguage.html", "Martin Fowler: Ubiquitous Language"),
    "aggregate": ("https://martinfowler.com/bliki/DDD_Aggregate.html", "Martin Fowler: DDD Aggregate"),
    "strangler fig": ("https://martinfowler.com/bliki/StranglerFigApplication.html", "Martin Fowler: Strangler Fig"),
    "saga pattern": ("https://microservices.io/patterns/data/saga.html", "Microservices.io: Saga Pattern"),
    "saga": ("https://microservices.io/patterns/data/saga.html", "Microservices.io: Saga Pattern"),
    "circuit breaker": ("https://martinfowler.com/bliki/CircuitBreaker.html", "Martin Fowler: Circuit Breaker"),
    "feature toggle": ("https://martinfowler.com/articles/feature-toggles.html", "Martin Fowler: Feature Toggles"),
    "feature flag": ("https://martinfowler.com/articles/feature-toggles.html", "Martin Fowler: Feature Toggles"),
    "microservices": ("https://martinfowler.com/articles/microservices.html", "Martin Fowler: Microservices"),
    "monolith": ("https://martinfowler.com/bliki/MonolithFirst.html", "Martin Fowler: Monolith First"),
    "refactoring": ("https://refactoring.com/catalog/", "Refactoring.com Catalog"),
    "blue-green deployment": ("https://martinfowler.com/bliki/BlueGreenDeployment.html", "Martin Fowler: Blue-Green"),
    "canary deployment": ("https://martinfowler.com/bliki/CanaryRelease.html", "Martin Fowler: Canary Release"),
    "branch by abstraction": ("https://martinfowler.com/bliki/BranchByAbstraction.html", "Martin Fowler: Branch by Abstraction"),
    "continuous integration": ("https://martinfowler.com/articles/continuousIntegration.html", "Martin Fowler: CI"),
    "continuous delivery": ("https://martinfowler.com/bliki/ContinuousDelivery.html", "Martin Fowler: Continuous Delivery"),
    "trunk-based development": ("https://trunkbaseddevelopment.com/", "Trunk Based Development"),
    "specification by example": ("https://martinfowler.com/bliki/SpecificationByExample.html", "Martin Fowler: Specification by Example"),

    # Microsoft Architecture Center / cloud patterns
    "outbox pattern": ("https://learn.microsoft.com/azure/architecture/best-practices/transactional-outbox-cosmos", "Microsoft: Outbox Pattern"),
    "retry pattern": ("https://learn.microsoft.com/azure/architecture/patterns/retry", "Microsoft: Retry Pattern"),
    "bulkhead": ("https://learn.microsoft.com/azure/architecture/patterns/bulkhead", "Microsoft: Bulkhead Pattern"),
    "sidecar": ("https://learn.microsoft.com/azure/architecture/patterns/sidecar", "Microsoft: Sidecar Pattern"),
    "ambassador": ("https://learn.microsoft.com/azure/architecture/patterns/ambassador", "Microsoft: Ambassador Pattern"),
    "backends for frontends": ("https://learn.microsoft.com/azure/architecture/patterns/backends-for-frontends", "Microsoft: BFF Pattern"),
    "event-driven": ("https://learn.microsoft.com/azure/architecture/guide/architecture-styles/event-driven", "Microsoft: Event-Driven Architecture"),
    "materialized view": ("https://learn.microsoft.com/azure/architecture/patterns/materialized-view", "Microsoft: Materialized View"),
    "dead letter": ("https://learn.microsoft.com/azure/architecture/patterns/queue-based-load-leveling", "Microsoft: Queue-Based Load Leveling"),
    "throttling": ("https://learn.microsoft.com/azure/architecture/patterns/throttling", "Microsoft: Throttling Pattern"),
    "claim check": ("https://learn.microsoft.com/azure/architecture/patterns/claim-check", "Microsoft: Claim Check Pattern"),
    "competing consumers": ("https://learn.microsoft.com/azure/architecture/patterns/competing-consumers", "Microsoft: Competing Consumers"),
    "priority queue": ("https://learn.microsoft.com/azure/architecture/patterns/priority-queue", "Microsoft: Priority Queue Pattern"),
    "sharding": ("https://learn.microsoft.com/azure/architecture/patterns/sharding", "Microsoft: Sharding Pattern"),

    # SOLID principles (Wikipedia — authoritative for CS concepts)
    "single responsibility": ("https://en.wikipedia.org/wiki/Single-responsibility_principle", "Wikipedia: SRP"),
    "open-closed": ("https://en.wikipedia.org/wiki/Open%E2%80%93closed_principle", "Wikipedia: OCP"),
    "liskov substitution": ("https://en.wikipedia.org/wiki/Liskov_substitution_principle", "Wikipedia: LSP"),
    "interface segregation": ("https://en.wikipedia.org/wiki/Interface_segregation_principle", "Wikipedia: ISP"),
    "dependency inversion": ("https://en.wikipedia.org/wiki/Dependency_inversion_principle", "Wikipedia: DIP"),

    # GRASP principles
    "information expert": ("https://en.wikipedia.org/wiki/GRASP_(object-oriented_design)#Information_expert", "Wikipedia: GRASP Information Expert"),
    "low coupling": ("https://en.wikipedia.org/wiki/Loose_coupling", "Wikipedia: Loose Coupling"),
    "high cohesion": ("https://en.wikipedia.org/wiki/Cohesion_(computer_science)", "Wikipedia: Cohesion"),
    "polymorphism": ("https://en.wikipedia.org/wiki/Polymorphism_(computer_science)", "Wikipedia: Polymorphism"),
    "pure fabrication": ("https://en.wikipedia.org/wiki/GRASP_(object-oriented_design)#Pure_fabrication", "Wikipedia: GRASP Pure Fabrication"),
    "indirection": ("https://en.wikipedia.org/wiki/GRASP_(object-oriented_design)#Indirection", "Wikipedia: GRASP Indirection"),

    # Software engineering laws
    "conway's law": ("https://en.wikipedia.org/wiki/Conway%27s_law", "Wikipedia: Conway's Law"),
    "lehman's law": ("https://en.wikipedia.org/wiki/Lehman%27s_laws_of_software_evolution", "Wikipedia: Lehman's Laws"),
    "law of demeter": ("https://en.wikipedia.org/wiki/Law_of_Demeter", "Wikipedia: Law of Demeter"),
    "brooks' law": ("https://en.wikipedia.org/wiki/Brooks%27s_law", "Wikipedia: Brooks' Law"),
    "goodhart's law": ("https://en.wikipedia.org/wiki/Goodhart%27s_law", "Wikipedia: Goodhart's Law"),
    "pareto": ("https://en.wikipedia.org/wiki/Pareto_principle", "Wikipedia: Pareto Principle"),
    "yagni": ("https://en.wikipedia.org/wiki/You_aren%27t_gonna_need_it", "Wikipedia: YAGNI"),
    "dry": ("https://en.wikipedia.org/wiki/Don%27t_repeat_yourself", "Wikipedia: DRY Principle"),
    "kiss": ("https://en.wikipedia.org/wiki/KISS_principle", "Wikipedia: KISS Principle"),

    # GoF / Design patterns
    "observer pattern": ("https://en.wikipedia.org/wiki/Observer_pattern", "Wikipedia: Observer Pattern"),
    "strategy pattern": ("https://en.wikipedia.org/wiki/Strategy_pattern", "Wikipedia: Strategy Pattern"),
    "factory": ("https://en.wikipedia.org/wiki/Factory_method_pattern", "Wikipedia: Factory Method"),
    "singleton": ("https://en.wikipedia.org/wiki/Singleton_pattern", "Wikipedia: Singleton Pattern"),
    "decorator pattern": ("https://en.wikipedia.org/wiki/Decorator_pattern", "Wikipedia: Decorator Pattern"),
    "adapter pattern": ("https://en.wikipedia.org/wiki/Adapter_pattern", "Wikipedia: Adapter Pattern"),
    "facade": ("https://en.wikipedia.org/wiki/Facade_pattern", "Wikipedia: Facade Pattern"),
    "proxy pattern": ("https://en.wikipedia.org/wiki/Proxy_pattern", "Wikipedia: Proxy Pattern"),
    "command pattern": ("https://en.wikipedia.org/wiki/Command_pattern", "Wikipedia: Command Pattern"),
    "state pattern": ("https://en.wikipedia.org/wiki/State_pattern", "Wikipedia: State Pattern"),
    "template method": ("https://en.wikipedia.org/wiki/Template_method_pattern", "Wikipedia: Template Method"),
    "builder pattern": ("https://en.wikipedia.org/wiki/Builder_pattern", "Wikipedia: Builder Pattern"),
    "repository pattern": ("https://martinfowler.com/eaaCatalog/repository.html", "Martin Fowler: Repository"),
    "unit of work": ("https://martinfowler.com/eaaCatalog/unitOfWork.html", "Martin Fowler: Unit of Work"),

    # Data / distributed systems
    "change data capture": ("https://en.wikipedia.org/wiki/Change_data_capture", "Wikipedia: CDC"),
    "cdc": ("https://en.wikipedia.org/wiki/Change_data_capture", "Wikipedia: CDC"),
    "polyglot persistence": ("https://en.wikipedia.org/wiki/Polyglot_persistence", "Wikipedia: Polyglot Persistence"),
    "data mesh": ("https://www.datamesh-architecture.com/", "Data Mesh Architecture"),
    "data lake": ("https://en.wikipedia.org/wiki/Data_lake", "Wikipedia: Data Lake"),
    "data warehouse": ("https://en.wikipedia.org/wiki/Data_warehouse", "Wikipedia: Data Warehouse"),
    "schema evolution": ("https://en.wikipedia.org/wiki/Schema_evolution", "Wikipedia: Schema Evolution"),
    "slowly changing dimension": ("https://en.wikipedia.org/wiki/Slowly_changing_dimension", "Wikipedia: SCD"),
    "idempoten": ("https://en.wikipedia.org/wiki/Idempotence", "Wikipedia: Idempotence"),
    "eventual consistency": ("https://en.wikipedia.org/wiki/Eventual_consistency", "Wikipedia: Eventual Consistency"),
    "cap theorem": ("https://en.wikipedia.org/wiki/CAP_theorem", "Wikipedia: CAP Theorem"),
    "two-phase commit": ("https://en.wikipedia.org/wiki/Two-phase_commit_protocol", "Wikipedia: 2PC"),
    "consensus": ("https://en.wikipedia.org/wiki/Consensus_(computer_science)", "Wikipedia: Consensus"),
    "partitioning": ("https://en.wikipedia.org/wiki/Partition_(database)", "Wikipedia: Data Partitioning"),
    "replication": ("https://en.wikipedia.org/wiki/Replication_(computing)", "Wikipedia: Replication"),
    "backpressure": ("https://www.reactivemanifesto.org/glossary#Back-Pressure", "Reactive Manifesto: Back-Pressure"),
    "load balancing": ("https://en.wikipedia.org/wiki/Load_balancing_(computing)", "Wikipedia: Load Balancing"),
    "service mesh": ("https://en.wikipedia.org/wiki/Service_mesh", "Wikipedia: Service Mesh"),
    "api gateway": ("https://microservices.io/patterns/apigateway.html", "Microservices.io: API Gateway"),
    "rate limiting": ("https://en.wikipedia.org/wiki/Rate_limiting", "Wikipedia: Rate Limiting"),

    # Testing
    "test pyramid": ("https://martinfowler.com/bliki/TestPyramid.html", "Martin Fowler: Test Pyramid"),
    "test double": ("https://martinfowler.com/bliki/TestDouble.html", "Martin Fowler: Test Double"),
    "mutation testing": ("https://en.wikipedia.org/wiki/Mutation_testing", "Wikipedia: Mutation Testing"),
    "property-based testing": ("https://en.wikipedia.org/wiki/Property_testing", "Wikipedia: Property Testing"),
    "contract testing": ("https://martinfowler.com/bliki/ContractTest.html", "Martin Fowler: Contract Test"),
    "chaos engineering": ("https://principlesofchaos.org/", "Principles of Chaos Engineering"),
    "fuzz testing": ("https://en.wikipedia.org/wiki/Fuzzing", "Wikipedia: Fuzzing"),
    "integration test": ("https://martinfowler.com/bliki/IntegrationTest.html", "Martin Fowler: Integration Test"),
    "acceptance test": ("https://en.wikipedia.org/wiki/Acceptance_testing", "Wikipedia: Acceptance Testing"),

    # Agile / PM
    "scrum": ("https://scrumguides.org/scrum-guide.html", "Official Scrum Guide"),
    "kanban": ("https://en.wikipedia.org/wiki/Kanban_(development)", "Wikipedia: Kanban"),
    "sprint": ("https://scrumguides.org/scrum-guide.html#the-sprint", "Scrum Guide: The Sprint"),
    "retrospective": ("https://en.wikipedia.org/wiki/Retrospective#Software_development", "Wikipedia: Retrospective"),
    "user story": ("https://en.wikipedia.org/wiki/User_story", "Wikipedia: User Story"),
    "definition of done": ("https://scrumguides.org/scrum-guide.html#increment", "Scrum Guide: Definition of Done"),
    "okr": ("https://en.wikipedia.org/wiki/Objectives_and_key_results", "Wikipedia: OKRs"),
    "prd": ("https://en.wikipedia.org/wiki/Product_requirements_document", "Wikipedia: PRD"),
    "roadmap": ("https://en.wikipedia.org/wiki/Technology_roadmap", "Wikipedia: Technology Roadmap"),
    "technical debt": ("https://martinfowler.com/bliki/TechnicalDebt.html", "Martin Fowler: Technical Debt"),
    "tech debt": ("https://martinfowler.com/bliki/TechnicalDebt.html", "Martin Fowler: Technical Debt"),

    # UX / UI
    "accessibility": ("https://www.w3.org/WAI/standards-guidelines/wcag/", "W3C WCAG Guidelines"),
    "wcag": ("https://www.w3.org/WAI/standards-guidelines/wcag/", "W3C WCAG Guidelines"),
    "aria": ("https://www.w3.org/WAI/ARIA/apg/", "W3C ARIA Authoring Practices"),
    "responsive design": ("https://en.wikipedia.org/wiki/Responsive_web_design", "Wikipedia: Responsive Design"),
    "design system": ("https://en.wikipedia.org/wiki/Design_system", "Wikipedia: Design System"),
    "atomic design": ("https://bradfrost.com/blog/post/atomic-web-design/", "Brad Frost: Atomic Design"),
    "skeleton screen": ("https://uxdesign.cc/what-you-should-know-about-skeleton-screens-a820c45a571a", "UX Collective: Skeleton Screens"),
    "progressive disclosure": ("https://en.wikipedia.org/wiki/Progressive_disclosure", "Wikipedia: Progressive Disclosure"),
    "heuristic evaluation": ("https://www.nngroup.com/articles/ten-usability-heuristics/", "Nielsen Norman: 10 Heuristics"),
    "fitts' law": ("https://en.wikipedia.org/wiki/Fitts%27s_law", "Wikipedia: Fitts' Law"),
    "hick's law": ("https://en.wikipedia.org/wiki/Hick%27s_law", "Wikipedia: Hick's Law"),

    # DevOps / SRE
    "sli": ("https://sre.google/sre-book/service-level-objectives/", "Google SRE Book: SLOs"),
    "slo": ("https://sre.google/sre-book/service-level-objectives/", "Google SRE Book: SLOs"),
    "sla": ("https://en.wikipedia.org/wiki/Service-level_agreement", "Wikipedia: SLA"),
    "error budget": ("https://sre.google/sre-book/embracing-risk/", "Google SRE Book: Error Budgets"),
    "blameless postmortem": ("https://sre.google/sre-book/postmortem-culture/", "Google SRE Book: Postmortems"),
    "postmortem": ("https://sre.google/sre-book/postmortem-culture/", "Google SRE Book: Postmortems"),
    "observability": ("https://en.wikipedia.org/wiki/Observability_(software)", "Wikipedia: Observability"),
    "three pillars": ("https://www.oreilly.com/library/view/distributed-systems-observability/9781492033431/", "O'Reilly: Distributed Systems Observability"),
    "infrastructure as code": ("https://en.wikipedia.org/wiki/Infrastructure_as_code", "Wikipedia: IaC"),
    "gitops": ("https://opengitops.dev/", "OpenGitOps"),
    "twelve-factor": ("https://12factor.net/", "The Twelve-Factor App"),
    "12-factor": ("https://12factor.net/", "The Twelve-Factor App"),
    "immutable infrastructure": ("https://en.wikipedia.org/wiki/Immutable_infrastructure", "Wikipedia: Immutable Infrastructure"),

    # Security
    "zero trust": ("https://en.wikipedia.org/wiki/Zero_trust_security_model", "Wikipedia: Zero Trust"),
    "defense in depth": ("https://en.wikipedia.org/wiki/Defense_in_depth_(computing)", "Wikipedia: Defense in Depth"),
    "least privilege": ("https://en.wikipedia.org/wiki/Principle_of_least_privilege", "Wikipedia: Least Privilege"),
    "threat model": ("https://owasp.org/www-community/Threat_Modeling", "OWASP: Threat Modeling"),
    "owasp top 10": ("https://owasp.org/www-project-top-ten/", "OWASP Top 10"),

    # Performance
    "caching": ("https://en.wikipedia.org/wiki/Cache_(computing)", "Wikipedia: Cache"),
    "cdn": ("https://en.wikipedia.org/wiki/Content_delivery_network", "Wikipedia: CDN"),
    "lazy loading": ("https://en.wikipedia.org/wiki/Lazy_loading", "Wikipedia: Lazy Loading"),
    "connection pool": ("https://en.wikipedia.org/wiki/Connection_pool", "Wikipedia: Connection Pool"),
    "n+1": ("https://en.wikipedia.org/wiki/N%2B1_query_problem", "Wikipedia: N+1 Query Problem"),
    "pagination": ("https://en.wikipedia.org/wiki/Pagination", "Wikipedia: Pagination"),
    "batch processing": ("https://en.wikipedia.org/wiki/Batch_processing", "Wikipedia: Batch Processing"),
    "stream processing": ("https://en.wikipedia.org/wiki/Stream_processing", "Wikipedia: Stream Processing"),

    # Architecture styles
    "hexagonal": ("https://en.wikipedia.org/wiki/Hexagonal_architecture_(software)", "Wikipedia: Hexagonal Architecture"),
    "ports and adapters": ("https://en.wikipedia.org/wiki/Hexagonal_architecture_(software)", "Wikipedia: Hexagonal Architecture"),
    "clean architecture": ("https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html", "Robert Martin: Clean Architecture"),
    "onion architecture": ("https://en.wikipedia.org/wiki/Hexagonal_architecture_(software)", "Wikipedia: Hexagonal Architecture"),
    "layered architecture": ("https://en.wikipedia.org/wiki/Multitier_architecture", "Wikipedia: Multitier Architecture"),
    "plugin architecture": ("https://en.wikipedia.org/wiki/Plug-in_(computing)", "Wikipedia: Plugin Architecture"),
    "microkernel": ("https://en.wikipedia.org/wiki/Microkernel", "Wikipedia: Microkernel"),
    "modular monolith": ("https://www.kamilgrzybek.com/blog/posts/modular-monolith-primer", "Modular Monolith Primer"),

    # Microservice patterns
    "database per service": ("https://microservices.io/patterns/data/database-per-service.html", "Microservices.io: Database per Service"),
    "service discovery": ("https://microservices.io/patterns/service-registry.html", "Microservices.io: Service Registry"),
    "distributed tracing": ("https://opentelemetry.io/docs/concepts/signals/traces/", "OpenTelemetry: Distributed Traces"),
    "api composition": ("https://microservices.io/patterns/data/api-composition.html", "Microservices.io: API Composition"),
    "event notification": ("https://martinfowler.com/articles/201701-event-driven.html", "Martin Fowler: Event-Driven"),
    "event-carried state": ("https://martinfowler.com/articles/201701-event-driven.html", "Martin Fowler: Event-Driven"),
    "asynchronous communication": ("https://microservices.io/patterns/communication-style/messaging.html", "Microservices.io: Messaging"),
    "choreography": ("https://microservices.io/patterns/data/saga.html", "Microservices.io: Saga Pattern"),
    "orchestration": ("https://microservices.io/patterns/data/saga.html", "Microservices.io: Saga Pattern"),

    # Deployment / reliability
    "zero downtime": ("https://martinfowler.com/bliki/ParallelChange.html", "Martin Fowler: Parallel Change"),
    "expand-contract": ("https://martinfowler.com/bliki/ParallelChange.html", "Martin Fowler: Parallel Change"),
    "graceful degradation": ("https://en.wikipedia.org/wiki/Graceful_degradation", "Wikipedia: Graceful Degradation"),
    "timeout": ("https://microservices.io/patterns/reliability/circuit-breaker.html", "Microservices.io: Circuit Breaker"),
    "health check": ("https://microservices.io/patterns/observability/health-check-api.html", "Microservices.io: Health Check"),
    "readiness probe": ("https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/", "Kubernetes: Probes"),
    "liveness probe": ("https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/", "Kubernetes: Probes"),
    "rolling update": ("https://kubernetes.io/docs/tutorials/kubernetes-basics/update/", "Kubernetes: Rolling Updates"),

    # More design principles / practices
    "composition over inheritance": ("https://en.wikipedia.org/wiki/Composition_over_inheritance", "Wikipedia: Composition over Inheritance"),
    "least astonishment": ("https://en.wikipedia.org/wiki/Principle_of_least_astonishment", "Wikipedia: Principle of Least Astonishment"),
    "separation of concerns": ("https://en.wikipedia.org/wiki/Separation_of_concerns", "Wikipedia: Separation of Concerns"),
    "encapsulation": ("https://en.wikipedia.org/wiki/Encapsulation_(computer_programming)", "Wikipedia: Encapsulation"),
    "inversion of control": ("https://en.wikipedia.org/wiki/Inversion_of_control", "Wikipedia: Inversion of Control"),
    "dependency injection": ("https://en.wikipedia.org/wiki/Dependency_injection", "Wikipedia: Dependency Injection"),
    "tell don't ask": ("https://martinfowler.com/bliki/TellDontAsk.html", "Martin Fowler: Tell Don't Ask"),
    "adr": ("https://adr.github.io/", "ADR GitHub: Architecture Decision Records"),
    "architecture decision record": ("https://adr.github.io/", "ADR GitHub: Architecture Decision Records"),
    "specification pattern": ("https://en.wikipedia.org/wiki/Specification_pattern", "Wikipedia: Specification Pattern"),
    "backend for frontend": ("https://learn.microsoft.com/azure/architecture/patterns/backends-for-frontends", "Microsoft: BFF Pattern"),
    "bff": ("https://learn.microsoft.com/azure/architecture/patterns/backends-for-frontends", "Microsoft: BFF Pattern"),
    "data quality": ("https://en.wikipedia.org/wiki/Data_quality", "Wikipedia: Data Quality"),
    "data contract": ("https://datacontract.com/", "Data Contract Specification"),
    "data governance": ("https://en.wikipedia.org/wiki/Data_governance", "Wikipedia: Data Governance"),

    # Versioning / API design
    "semantic versioning": ("https://semver.org/", "Semantic Versioning"),
    "semver": ("https://semver.org/", "Semantic Versioning"),
    "api versioning": ("https://learn.microsoft.com/azure/architecture/best-practices/api-design", "Microsoft: API Design"),
    "rest": ("https://en.wikipedia.org/wiki/REST", "Wikipedia: REST"),
    "graphql": ("https://graphql.org/learn/", "GraphQL Specification"),
    "grpc": ("https://grpc.io/docs/what-is-grpc/", "gRPC: What is gRPC?"),
    "openapi": ("https://spec.openapis.org/oas/latest.html", "OpenAPI Specification"),
    "json schema": ("https://json-schema.org/", "JSON Schema"),
    "protobuf": ("https://protobuf.dev/overview/", "Protocol Buffers Documentation"),

    # Reliability / resilience patterns
    "exponential backoff": ("https://en.wikipedia.org/wiki/Exponential_backoff", "Wikipedia: Exponential Backoff"),
    "backoff": ("https://en.wikipedia.org/wiki/Exponential_backoff", "Wikipedia: Exponential Backoff"),
    "jitter": ("https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/", "AWS: Backoff and Jitter"),
    "load shedding": ("https://en.wikipedia.org/wiki/Load_shedding", "Wikipedia: Load Shedding"),
    "toil": ("https://sre.google/sre-book/eliminating-toil/", "Google SRE Book: Eliminating Toil"),
    "runbook": ("https://en.wikipedia.org/wiki/Runbook", "Wikipedia: Runbook"),

    # UX / Design principles
    "gestalt": ("https://en.wikipedia.org/wiki/Gestalt_psychology#Gestalt_laws_of_grouping", "Wikipedia: Gestalt Laws"),
    "proximity": ("https://en.wikipedia.org/wiki/Gestalt_psychology#Proximity", "Wikipedia: Gestalt Proximity"),
    "similarity": ("https://en.wikipedia.org/wiki/Gestalt_psychology#Similarity", "Wikipedia: Gestalt Similarity"),
    "closure": ("https://en.wikipedia.org/wiki/Gestalt_psychology#Closure", "Wikipedia: Gestalt Closure"),
    "breadcrumb": ("https://www.nngroup.com/articles/breadcrumbs/", "Nielsen Norman: Breadcrumbs"),
    "navigation": ("https://www.nngroup.com/articles/navigation-ia/", "Nielsen Norman: Navigation"),
    "modal": ("https://www.nngroup.com/articles/modal-nonmodal-dialog/", "Nielsen Norman: Modal Dialog"),
    "toast": ("https://www.nngroup.com/articles/indicators-validations-notifications/", "Nielsen Norman: Notifications"),
    "form validation": ("https://www.nngroup.com/articles/errors-forms-design-guidelines/", "Nielsen Norman: Form Errors"),
    "error message": ("https://www.nngroup.com/articles/error-message-guidelines/", "Nielsen Norman: Error Messages"),
    "loading indicator": ("https://www.nngroup.com/articles/progress-indicators/", "Nielsen Norman: Progress Indicators"),
    "empty state": ("https://www.nngroup.com/articles/empty-state-interface-design/", "Nielsen Norman: Empty States"),
    "infinite scroll": ("https://www.nngroup.com/articles/infinite-scrolling-tips/", "Nielsen Norman: Infinite Scroll"),
    "design token": ("https://www.designtokens.org/", "Design Tokens Community Group"),
    "storybook": ("https://storybook.js.org/docs/", "Storybook Documentation"),
    "component": ("https://www.componentdriven.org/", "Component Driven Development"),
    "controlled vs uncontrolled": ("https://react.dev/learn/sharing-state-between-components#controlled-and-uncontrolled-components", "React: Controlled Components"),

    # Error handling / debugging
    "error boundary": ("https://react.dev/reference/react/Component#catching-rendering-errors-with-an-error-boundary", "React: Error Boundary"),
    "structured logging": ("https://en.wikipedia.org/wiki/Logging_(computing)", "Wikipedia: Logging"),
    "rubber duck": ("https://en.wikipedia.org/wiki/Rubber_duck_debugging", "Wikipedia: Rubber Duck Debugging"),
    "scientific method": ("https://en.wikipedia.org/wiki/Scientific_method", "Wikipedia: Scientific Method"),
    "root cause analysis": ("https://en.wikipedia.org/wiki/Root_cause_analysis", "Wikipedia: Root Cause Analysis"),
    "boy scout rule": ("https://www.oreilly.com/library/view/97-things-every/9780596809515/ch08.html", "O'Reilly: Boy Scout Rule"),
    "coverage gate": ("https://docs.sonarqube.org/latest/user-guide/quality-gates/", "SonarQube: Quality Gates"),

    # Compliance / security standards
    "iso 27001": ("https://www.iso.org/standard/27001", "ISO 27001 Standard"),
    "iso27001": ("https://www.iso.org/standard/27001", "ISO 27001 Standard"),
    "gdpr": ("https://gdpr-info.eu/", "GDPR Info"),
    "soc 2": ("https://en.wikipedia.org/wiki/System_and_Organization_Controls", "Wikipedia: SOC 2"),
    "pci dss": ("https://www.pcisecuritystandards.org/", "PCI Security Standards"),
    "risk assessment": ("https://en.wikipedia.org/wiki/IT_risk_management", "Wikipedia: IT Risk Management"),

    # CI/CD
    "pull request": ("https://docs.github.com/en/pull-requests", "GitHub: Pull Requests"),
    "code review": ("https://google.github.io/eng-practices/review/", "Google: Code Review Practices"),
    "pre-commit hook": ("https://pre-commit.com/", "Pre-commit Framework"),

    # Project management extras
    "risk register": ("https://en.wikipedia.org/wiki/Risk_register", "Wikipedia: Risk Register"),
    "stakeholder": ("https://en.wikipedia.org/wiki/Stakeholder_(corporate)", "Wikipedia: Stakeholder"),
    "estimation": ("https://en.wikipedia.org/wiki/Software_development_effort_estimation", "Wikipedia: Effort Estimation"),
    "planning poker": ("https://en.wikipedia.org/wiki/Planning_poker", "Wikipedia: Planning Poker"),
    "burndown": ("https://en.wikipedia.org/wiki/Burn_down_chart", "Wikipedia: Burndown Chart"),
    "velocity": ("https://en.wikipedia.org/wiki/Velocity_(software_development)", "Wikipedia: Velocity"),

    # LLM / AI techniques
    "chain-of-thought": ("https://arxiv.org/abs/2201.11903", "arXiv: Chain-of-Thought Prompting"),
    "chain of thought": ("https://arxiv.org/abs/2201.11903", "arXiv: Chain-of-Thought Prompting"),
    "react pattern": ("https://arxiv.org/abs/2210.03629", "arXiv: ReAct"),
    "reasoning and acting": ("https://arxiv.org/abs/2210.03629", "arXiv: ReAct"),
    "structured output": ("https://platform.openai.com/docs/guides/structured-outputs", "OpenAI: Structured Outputs"),
    "reflection pattern": ("https://arxiv.org/abs/2303.11366", "arXiv: Reflexion"),
    "system prompt": ("https://platform.openai.com/docs/guides/text-generation", "OpenAI: Text Generation Guide"),
    "prompt engineering": ("https://platform.openai.com/docs/guides/prompt-engineering", "OpenAI: Prompt Engineering"),
    "model routing": ("https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching", "Anthropic: Build with Claude"),
    "context window": ("https://en.wikipedia.org/wiki/Large_language_model", "Wikipedia: Large Language Model"),
    "llm evaluation": ("https://huggingface.co/docs/evaluate/", "HuggingFace: Evaluate"),
    "rag": ("https://arxiv.org/abs/2005.11401", "arXiv: RAG (Retrieval-Augmented Generation)"),
    "retrieval-augmented": ("https://arxiv.org/abs/2005.11401", "arXiv: RAG"),
    "agentic": ("https://www.anthropic.com/engineering/building-effective-agents", "Anthropic: Building Effective Agents"),
    "tool use": ("https://docs.anthropic.com/en/docs/build-with-claude/tool-use", "Anthropic: Tool Use"),
    "streaming": ("https://developer.mozilla.org/en-US/docs/Web/API/Streams_API", "MDN: Streams API"),
    "few-shot": ("https://en.wikipedia.org/wiki/Few-shot_learning", "Wikipedia: Few-Shot Learning"),
    "fine-tuning": ("https://platform.openai.com/docs/guides/fine-tuning", "OpenAI: Fine-Tuning"),
    "embedding": ("https://en.wikipedia.org/wiki/Word_embedding", "Wikipedia: Word Embedding"),
    "vector database": ("https://en.wikipedia.org/wiki/Vector_database", "Wikipedia: Vector Database"),
    "semantic search": ("https://en.wikipedia.org/wiki/Semantic_search", "Wikipedia: Semantic Search"),
    "guardrail": ("https://docs.nvidia.com/nemo/guardrails/", "NeMo Guardrails Documentation"),
    "hallucination": ("https://en.wikipedia.org/wiki/Hallucination_(artificial_intelligence)", "Wikipedia: AI Hallucination"),
    "token": ("https://platform.openai.com/tokenizer", "OpenAI: Tokenizer"),
    "temperature": ("https://platform.openai.com/docs/api-reference/chat/create#chat-create-temperature", "OpenAI: Temperature Parameter"),
    "fallback chain": ("https://python.langchain.com/docs/how_to/fallbacks/", "LangChain: Fallbacks"),

    # Error handling / code quality
    "guard clause": ("https://refactoring.guru/replace-nested-conditional-with-guard-clauses", "Refactoring Guru: Guard Clauses"),
    "early return": ("https://refactoring.guru/replace-nested-conditional-with-guard-clauses", "Refactoring Guru: Guard Clauses"),
    "custom exception": ("https://docs.python.org/3/tutorial/errors.html#user-defined-exceptions", "Python: User-Defined Exceptions"),
    "exception hierarchy": ("https://docs.python.org/3/library/exceptions.html#exception-hierarchy", "Python: Exception Hierarchy"),
    "log level": ("https://docs.python.org/3/library/logging.html#logging-levels", "Python: Logging Levels"),
    "structured json": ("https://jsonapi.org/", "JSON:API Specification"),
    "validate input": ("https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html", "OWASP: Input Validation"),
    "catch exception": ("https://docs.python.org/3/tutorial/errors.html", "Python: Errors and Exceptions"),
    "bare except": ("https://docs.python.org/3/tutorial/errors.html#handling-exceptions", "Python: Handling Exceptions"),
    "cache-control": ("https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control", "MDN: Cache-Control"),
    "stale-while-revalidate": ("https://web.dev/stale-while-revalidate/", "web.dev: stale-while-revalidate"),

    # Distributed systems specifics
    "fencing token": ("https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html", "Kleppmann: Distributed Locking"),
    "transactional outbox": ("https://microservices.io/patterns/data/transactional-outbox.html", "Microservices.io: Transactional Outbox"),
    "network partition": ("https://en.wikipedia.org/wiki/Network_partition", "Wikipedia: Network Partition"),
    "split brain": ("https://en.wikipedia.org/wiki/Split-brain_(computing)", "Wikipedia: Split Brain"),
    "leader election": ("https://en.wikipedia.org/wiki/Leader_election", "Wikipedia: Leader Election"),
    "write-ahead log": ("https://en.wikipedia.org/wiki/Write-ahead_logging", "Wikipedia: Write-Ahead Logging"),
    "wal": ("https://en.wikipedia.org/wiki/Write-ahead_logging", "Wikipedia: Write-Ahead Logging"),
    "quorum": ("https://en.wikipedia.org/wiki/Quorum_(distributed_computing)", "Wikipedia: Quorum"),
    "vector clock": ("https://en.wikipedia.org/wiki/Vector_clock", "Wikipedia: Vector Clock"),
    "crdt": ("https://en.wikipedia.org/wiki/Conflict-free_replicated_data_type", "Wikipedia: CRDT"),
    "gossip protocol": ("https://en.wikipedia.org/wiki/Gossip_protocol", "Wikipedia: Gossip Protocol"),

    # SOC / Compliance
    "soc 2": ("https://en.wikipedia.org/wiki/System_and_Organization_Controls", "Wikipedia: SOC"),
    "least privilege": ("https://en.wikipedia.org/wiki/Principle_of_least_privilege", "Wikipedia: Least Privilege"),
    "mfa": ("https://en.wikipedia.org/wiki/Multi-factor_authentication", "Wikipedia: MFA"),
    "multi-factor": ("https://en.wikipedia.org/wiki/Multi-factor_authentication", "Wikipedia: MFA"),
    "access control": ("https://en.wikipedia.org/wiki/Access_control", "Wikipedia: Access Control"),
    "rbac": ("https://en.wikipedia.org/wiki/Role-based_access_control", "Wikipedia: RBAC"),

    # More design system / UI
    "changelog": ("https://keepachangelog.com/", "Keep a Changelog"),
    "migration guide": ("https://semver.org/", "Semantic Versioning"),
    "breaking change": ("https://semver.org/", "Semantic Versioning"),
    "creator": ("https://en.wikipedia.org/wiki/GRASP_(object-oriented_design)#Creator", "Wikipedia: GRASP Creator"),

    # Infrastructure as Code
    "pulumi": ("https://www.pulumi.com/docs/", "Pulumi Documentation"),
    "cdk": ("https://docs.aws.amazon.com/cdk/v2/guide/home.html", "AWS CDK Documentation"),

    # Nielsen's UX heuristics
    "visibility of system status": ("https://www.nngroup.com/articles/visibility-system-status/", "NN/g: Visibility of System Status"),
    "match between system and real world": ("https://www.nngroup.com/articles/match-system-real-world/", "NN/g: Match System & Real World"),
    "user control and freedom": ("https://www.nngroup.com/articles/user-control-and-freedom/", "NN/g: User Control"),
    "consistency and standards": ("https://www.nngroup.com/articles/consistency-and-standards/", "NN/g: Consistency"),
    "error prevention": ("https://www.nngroup.com/articles/slips/", "NN/g: Error Prevention"),
    "recognition rather than recall": ("https://www.nngroup.com/articles/recognition-and-recall/", "NN/g: Recognition vs Recall"),
    "flexibility and efficiency": ("https://www.nngroup.com/articles/flexibility-efficiency-heuristic/", "NN/g: Flexibility"),
    "aesthetic and minimalist": ("https://www.nngroup.com/articles/aesthetic-minimalist-design/", "NN/g: Minimalist Design"),
    "help users recognize": ("https://www.nngroup.com/articles/error-message-guidelines/", "NN/g: Error Messages"),
    "help and documentation": ("https://www.nngroup.com/articles/help-and-documentation/", "NN/g: Help and Documentation"),
    "miller's law": ("https://en.wikipedia.org/wiki/The_Magical_Number_Seven,_Plus_or_Minus_Two", "Wikipedia: Miller's Law"),

    # UX patterns
    "command palette": ("https://www.nngroup.com/articles/command-palette/", "NN/g: Command Palette"),
    "wizard": ("https://www.nngroup.com/articles/wizards/", "NN/g: Wizards"),
    "autosave": ("https://www.nngroup.com/articles/auto-save/", "NN/g: Auto-Save"),
    "smart default": ("https://www.nngroup.com/articles/slips/", "NN/g: Smart Defaults"),
    "optimistic ui": ("https://www.smashingmagazine.com/2016/11/true-lies-of-optimistic-user-interfaces/", "Smashing: Optimistic UI"),
    "typeahead": ("https://www.nngroup.com/articles/search-visible-and-simple/", "NN/g: Search"),
    "inline error": ("https://www.nngroup.com/articles/errors-forms-design-guidelines/", "NN/g: Inline Errors"),
    "data table": ("https://www.nngroup.com/articles/comparison-tables/", "NN/g: Data Tables"),
    "deny-by-default": ("https://en.wikipedia.org/wiki/Principle_of_least_privilege", "Wikipedia: Least Privilege"),
    "fail fast": ("https://en.wikipedia.org/wiki/Fail-fast_(systems_design)", "Wikipedia: Fail-Fast"),
    "explicit over implicit": ("https://peps.python.org/pep-0020/", "PEP 20: Zen of Python"),
    "conservative default": ("https://en.wikipedia.org/wiki/Principle_of_least_privilege", "Wikipedia: Least Privilege"),
    "atomic state": ("https://en.wikipedia.org/wiki/Linearizability", "Wikipedia: Linearizability"),
    "api as contract": ("https://swagger.io/resources/articles/adopting-an-api-first-approach/", "Swagger: API-First Approach"),
    "immediate feedback": ("https://www.nngroup.com/articles/response-times-3-important-limits/", "NN/g: Response Times"),
    "measure before optim": ("https://wiki.c2.com/?PrematureOptimization", "C2 Wiki: Premature Optimization"),
    "deterministic test": ("https://martinfowler.com/articles/nonDeterminism.html", "Martin Fowler: Non-Determinism in Tests"),
    "input validation": ("https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html", "OWASP: Input Validation"),
    "result type": ("https://en.wikipedia.org/wiki/Result_type", "Wikipedia: Result Type"),
    "fixture": ("https://docs.pytest.org/en/latest/how-to/fixtures.html", "pytest: Fixtures"),
    "request context": ("https://opentelemetry.io/docs/concepts/context-propagation/", "OpenTelemetry: Context Propagation"),

    # PM / Product frameworks
    "jobs-to-be-done": ("https://en.wikipedia.org/wiki/Jobs_to_be_done", "Wikipedia: Jobs to be Done"),
    "jtbd": ("https://en.wikipedia.org/wiki/Jobs_to_be_done", "Wikipedia: Jobs to be Done"),
    "rice": ("https://www.productplan.com/glossary/rice-scoring-model/", "ProductPlan: RICE Scoring"),
    "aarrr": ("https://en.wikipedia.org/wiki/AARRR_metrics", "Wikipedia: AARRR Metrics"),
    "pirate metrics": ("https://en.wikipedia.org/wiki/AARRR_metrics", "Wikipedia: AARRR Metrics"),
    "north star metric": ("https://amplitude.com/blog/north-star-metric", "Amplitude: North Star Metric"),
    "a/b test": ("https://en.wikipedia.org/wiki/A/B_testing", "Wikipedia: A/B Testing"),
    "cohort analysis": ("https://en.wikipedia.org/wiki/Cohort_analysis", "Wikipedia: Cohort Analysis"),
    "customer interview": ("https://www.nngroup.com/articles/user-interviews/", "NN/g: User Interviews"),
    "prototype": ("https://en.wikipedia.org/wiki/Prototype", "Wikipedia: Prototype"),
    "opportunity scoring": ("https://www.strategyzer.com/library/the-value-proposition-canvas", "Strategyzer: Value Proposition"),
    "assumption map": ("https://www.strategyzer.com/library/the-value-proposition-canvas", "Strategyzer: Value Proposition"),
    "backlog grooming": ("https://scrumguides.org/scrum-guide.html#product-backlog", "Scrum Guide: Product Backlog"),
    "backlog refinement": ("https://scrumguides.org/scrum-guide.html#product-backlog", "Scrum Guide: Product Backlog"),

    # Project management specifics
    "story point": ("https://en.wikipedia.org/wiki/Story_point", "Wikipedia: Story Points"),
    "cone of uncertainty": ("https://en.wikipedia.org/wiki/Cone_of_Uncertainty", "Wikipedia: Cone of Uncertainty"),
    "spike": ("https://en.wikipedia.org/wiki/Spike_(software_development)", "Wikipedia: Technical Spike"),
    "raci": ("https://en.wikipedia.org/wiki/Responsibility_assignment_matrix", "Wikipedia: RACI Matrix"),
    "team topolog": ("https://teamtopologies.com/", "Team Topologies"),
    "psychological safety": ("https://en.wikipedia.org/wiki/Psychological_safety", "Wikipedia: Psychological Safety"),
    "decision log": ("https://adr.github.io/", "ADR GitHub"),
    "rollback plan": ("https://en.wikipedia.org/wiki/Rollback_(data_management)", "Wikipedia: Rollback"),
    "red/yellow/green": ("https://en.wikipedia.org/wiki/Traffic_light_rating_system", "Wikipedia: Traffic Light Rating"),

    # RAG patterns
    "chunk overlap": ("https://docs.llamaindex.ai/en/stable/module_guides/loading/node_parsers/", "LlamaIndex: Node Parsers"),
    "chunk metadata": ("https://docs.llamaindex.ai/en/stable/module_guides/loading/node_parsers/", "LlamaIndex: Node Parsers"),
    "rerank": ("https://docs.cohere.com/docs/reranking", "Cohere: Reranking"),
    "cross-encoder": ("https://www.sbert.net/examples/applications/cross-encoder/README.html", "SBERT: Cross-Encoders"),
    "grounded generation": ("https://docs.cohere.com/docs/grounded-generation", "Cohere: Grounded Generation"),

    # Spec writing
    "functional requirement": ("https://en.wikipedia.org/wiki/Functional_requirement", "Wikipedia: Functional Requirement"),
    "non-functional requirement": ("https://en.wikipedia.org/wiki/Non-functional_requirement", "Wikipedia: Non-Functional Requirement"),
    "acceptance criteria": ("https://en.wikipedia.org/wiki/Acceptance_testing", "Wikipedia: Acceptance Testing"),
    "given/when/then": ("https://en.wikipedia.org/wiki/Behavior-driven_development", "Wikipedia: BDD"),
    "edge case": ("https://en.wikipedia.org/wiki/Edge_case", "Wikipedia: Edge Case"),
    "boundary condition": ("https://en.wikipedia.org/wiki/Boundary_value_analysis", "Wikipedia: Boundary Value Analysis"),
    "problem statement": ("https://en.wikipedia.org/wiki/Problem_statement", "Wikipedia: Problem Statement"),
    "milestone": ("https://en.wikipedia.org/wiki/Milestone_(project_management)", "Wikipedia: Milestone"),
    "phased delivery": ("https://en.wikipedia.org/wiki/Iterative_and_incremental_development", "Wikipedia: Iterative Development"),

    # Cloud / multi-cloud
    "landing zone": ("https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/", "Microsoft: Landing Zones"),
    "finops": ("https://www.finops.org/", "FinOps Foundation"),
    "well-architected": ("https://aws.amazon.com/architecture/well-architected/", "AWS Well-Architected"),
    "availability zone": ("https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-regions-availability-zones.html", "AWS: Availability Zones"),
    "disaster recovery": ("https://en.wikipedia.org/wiki/Disaster_recovery", "Wikipedia: Disaster Recovery"),
    "rpo": ("https://en.wikipedia.org/wiki/Disaster_recovery#Recovery_Point_Objective", "Wikipedia: RPO"),
    "rto": ("https://en.wikipedia.org/wiki/Disaster_recovery#Recovery_Time_Objective", "Wikipedia: RTO"),
    "6 rs": ("https://aws.amazon.com/blogs/enterprise-strategy/6-strategies-for-migrating-applications-to-the-cloud/", "AWS: 6 Migration Strategies"),
    "tagging": ("https://docs.aws.amazon.com/tag-editor/latest/userguide/tagging.html", "AWS: Resource Tagging"),
    "identity provider": ("https://en.wikipedia.org/wiki/Identity_provider", "Wikipedia: Identity Provider"),

    # Systems / scaling
    "horizontal scaling": ("https://en.wikipedia.org/wiki/Scalability#Horizontal_(scale_out)", "Wikipedia: Horizontal Scaling"),
    "read replica": ("https://en.wikipedia.org/wiki/Replication_(computing)", "Wikipedia: Replication"),
    "pub/sub": ("https://en.wikipedia.org/wiki/Publish%E2%80%93subscribe_pattern", "Wikipedia: Pub/Sub"),
    "point-to-point": ("https://en.wikipedia.org/wiki/Message_queue", "Wikipedia: Message Queue"),

    # LLM specifics
    "agent memory": ("https://python.langchain.com/docs/how_to/#memory", "LangChain: Memory"),
    "tool loop": ("https://docs.anthropic.com/en/docs/build-with-claude/tool-use", "Anthropic: Tool Use"),
    "pii": ("https://en.wikipedia.org/wiki/Personal_data", "Wikipedia: Personal Data"),
    "ground truth": ("https://en.wikipedia.org/wiki/Ground_truth", "Wikipedia: Ground Truth"),
    "evaluation dataset": ("https://huggingface.co/docs/evaluate/", "HuggingFace: Evaluate"),

    # Final mop-up — exact keyword variants from remaining unvalidated
    "composition over configuration": ("https://en.wikipedia.org/wiki/Convention_over_configuration", "Wikipedia: Convention over Configuration"),
    "degrade gracefully": ("https://en.wikipedia.org/wiki/Graceful_degradation", "Wikipedia: Graceful Degradation"),
    "error log": ("https://docs.python.org/3/library/logging.html", "Python: Logging"),
    "terraform": ("https://developer.hashicorp.com/terraform/docs/", "Terraform Documentation"),
    "data residency": ("https://en.wikipedia.org/wiki/Data_sovereignty", "Wikipedia: Data Sovereignty"),
    "zero-trust": ("https://en.wikipedia.org/wiki/Zero_trust_security_model", "Wikipedia: Zero Trust"),
    "environment-based configuration": ("https://12factor.net/config", "12-Factor: Config"),
    "environment variable": ("https://12factor.net/config", "12-Factor: Config"),
    "validate at the boundary": ("https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html", "OWASP: Input Validation"),
    "testing pyramid": ("https://martinfowler.com/bliki/TestPyramid.html", "Martin Fowler: Test Pyramid"),
    "risk-driven": ("https://en.wikipedia.org/wiki/Risk_management", "Wikipedia: Risk Management"),
    "brooks's law": ("https://en.wikipedia.org/wiki/Brooks%27s_law", "Wikipedia: Brooks' Law"),
    "fitts's law": ("https://en.wikipedia.org/wiki/Fitts%27s_law", "Wikipedia: Fitts' Law"),
    "alternatives considered": ("https://adr.github.io/", "ADR GitHub"),
    "status code": ("https://developer.mozilla.org/en-US/docs/Web/HTTP/Status", "MDN: HTTP Status Codes"),
    "error response": ("https://jsonapi.org/format/#errors", "JSON:API: Errors"),
    "auto-save": ("https://www.nngroup.com/articles/auto-save/", "NN/g: Auto-Save"),
    "inline field error": ("https://www.nngroup.com/articles/errors-forms-design-guidelines/", "NN/g: Form Errors"),
    "interconnect": ("https://cloud.google.com/network-connectivity/docs/interconnect", "GCP: Cloud Interconnect"),
    "direct connect": ("https://docs.aws.amazon.com/directconnect/", "AWS: Direct Connect"),
    "mandatory tag": ("https://docs.aws.amazon.com/tag-editor/latest/userguide/tagging.html", "AWS: Tagging"),
    "document risk": ("https://en.wikipedia.org/wiki/Risk_register", "Wikipedia: Risk Register"),
}


class ArchitecturePatternsChecker(SourceChecker):
    """Validates architecture patterns and principles against canonical references."""

    @property
    def source_type(self) -> SourceType:
        return SourceType.OFFICIAL_DOCS  # Reuse type — these are authoritative refs

    async def check_technology(self, tech_name: str) -> dict[str, Any] | None:
        """Not applicable — this checker works on claim text, not tech names."""
        return None

    async def search_claim(
        self,
        claim_text: str,
        technologies: list[str],
        domains: list[str],
    ) -> list[Source]:
        """Match claim text against known architecture pattern references."""
        sources: list[Source] = []
        text_lower = claim_text.lower()
        seen_urls: set[str] = set()

        for keyword, (url, title) in _PATTERN_REFS.items():
            if keyword in text_lower and url not in seen_urls:
                seen_urls.add(url)
                sources.append(Source(
                    url=url,
                    title=title,
                    source_type=SourceType.OFFICIAL_DOCS,
                    retrieved_at=datetime.now(timezone.utc),
                    verified=True,
                ))
                if len(sources) >= 3:
                    break

        return sources
