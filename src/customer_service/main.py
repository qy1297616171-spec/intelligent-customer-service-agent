from contextlib import asynccontextmanager
import logging
from time import perf_counter
from uuid import uuid4

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from fastapi.staticfiles import StaticFiles

from customer_service.ai_platform.cache import (
    InMemoryAnswerCache,
    RedisAnswerCache,
    ResilientAnswerCache,
)
from customer_service.ai_platform.factory import build_answer_generator
from customer_service.ai_platform.embeddings import build_embedding_provider
from customer_service.ai_platform.orchestrator import AnswerOrchestrator
from customer_service.ai_platform.rerank import build_reranker
from customer_service.ai_platform.safety import RuleBasedSafetyPolicy
from customer_service.bootstrap.config import Settings, get_settings
from customer_service.bootstrap.modules import ModuleDefinition, ModuleRegistry
from customer_service.modules.conversation.router import build_router as conversation_router
from customer_service.modules.commerce.router import build_router as commerce_router
from customer_service.modules.commerce.service import (
    CommerceFactResolver,
    build_commerce_store,
)
from customer_service.modules.knowledge.router import build_router as knowledge_router
from customer_service.modules.handoff.router import build_router as handoff_router
from customer_service.infrastructure.database import Database
from customer_service.modules.conversation.service import SqlConversationStore
from customer_service.modules.handoff.service import SqlHandoffStore
from customer_service.modules.knowledge.service import SqlKnowledgeStore
from customer_service.modules.analytics.router import build_router as analytics_router
from customer_service.modules.customer.router import build_router as customer_router
from customer_service.modules.customer.service import SqlCustomerStore
from customer_service.modules.audit.router import build_router as audit_router
from customer_service.modules.audit.service import AuditStore
from customer_service.modules.auth.router import build_router as auth_router
from customer_service.modules.auth.service import AuthService
from customer_service.infrastructure.redis import RateLimiter, create_redis_client
from customer_service.infrastructure.pgvector_store import PgVectorStore
from customer_service.infrastructure.observability import (
    HTTP_DURATION,
    HTTP_REQUESTS,
    configure_logging,
)


def create_app(settings_override: Settings | None = None) -> FastAPI:
    settings = settings_override or get_settings()
    configure_logging(settings.log_level)
    access_logger = logging.getLogger("customer_service.access")
    database = Database(settings.database_url)
    database.create_schema()
    embedding_provider = build_embedding_provider(settings)
    vector_provider = settings.vector_store_provider.strip().lower()
    if vector_provider not in {"auto", "json", "pgvector"}:
        raise ValueError("VECTOR_STORE_PROVIDER must be auto, json or pgvector")
    use_pgvector = vector_provider == "pgvector" or (
        vector_provider == "auto" and database.engine.dialect.name == "postgresql"
    )
    vector_index = (
        PgVectorStore(database, settings.pgvector_dimensions) if use_pgvector else None
    )
    knowledge_store = SqlKnowledgeStore(
        database,
        embedding_provider,
        settings.retrieval_vector_weight,
        settings.retrieval_keyword_weight,
        vector_index,
    )
    knowledge_store.backfill_embeddings()
    commerce_store = build_commerce_store(settings)
    conversation_store = SqlConversationStore(database)
    handoff_store = SqlHandoffStore(database)
    customer_store = SqlCustomerStore(database)
    customer_store.ensure_demo_customers()
    audit_store = AuditStore(database)
    auth_service = AuthService(database, settings)
    auth_service.ensure_bootstrap_admin()
    redis_client = create_redis_client(settings.redis_url) if settings.redis_enabled else None
    local_cache = InMemoryAnswerCache(settings.ai_cache_ttl_seconds)
    answer_cache = (
        ResilientAnswerCache(
            RedisAnswerCache(redis_client, settings.ai_cache_ttl_seconds), local_cache
        )
        if redis_client is not None
        else local_cache
    )
    rate_limiter = RateLimiter(redis_client)
    orchestrator = AnswerOrchestrator(
        retriever=knowledge_store,
        generator=build_answer_generator(settings),
        cache=answer_cache,
        min_evidence_score=settings.ai_min_evidence_score,
        business_resolver=CommerceFactResolver(commerce_store),
        reranker=build_reranker(settings),
        candidate_limit=settings.rerank_candidate_limit,
        evidence_limit=settings.rerank_top_n,
        safety_policy=RuleBasedSafetyPolicy(),
    )

    registry = ModuleRegistry(settings)
    registry.register(
        ModuleDefinition(
            name="auth",
            version="0.1.0",
            enabled=lambda config: config.feature_auth,
            router=auth_router(auth_service, audit_store, settings),
        )
    )
    registry.register(
        ModuleDefinition(
            name="audit",
            version="0.1.0",
            enabled=lambda config: config.feature_audit,
            router=audit_router(audit_store),
            dependencies=("auth",),
        )
    )
    registry.register(
        ModuleDefinition(
            name="customer",
            version="0.1.0",
            enabled=lambda config: config.feature_customer,
            router=customer_router(customer_store),
        )
    )
    registry.register(
        ModuleDefinition(
            name="commerce",
            version="0.1.0",
            enabled=lambda config: config.feature_commerce,
            router=commerce_router(commerce_store),
        )
    )
    registry.register(
        ModuleDefinition(
            name="knowledge",
            version="0.1.0",
            enabled=lambda config: config.feature_knowledge,
            router=knowledge_router(knowledge_store, answer_cache),
        )
    )
    registry.register(
        ModuleDefinition(
            name="conversation",
            version="0.1.0",
            enabled=lambda config: config.feature_conversation,
            router=conversation_router(orchestrator, conversation_store),
            dependencies=("knowledge", "commerce"),
        )
    )
    registry.register(
        ModuleDefinition(
            name="handoff",
            version="0.1.0",
            enabled=lambda config: config.feature_handoff,
            router=handoff_router(handoff_store, conversation_store),
            dependencies=("conversation",),
        )
    )
    registry.register(
        ModuleDefinition(
            name="analytics",
            version="0.1.0",
            enabled=lambda config: config.feature_analytics,
            router=analytics_router(conversation_store, handoff_store, knowledge_store),
            dependencies=("conversation", "handoff", "knowledge"),
        )
    )
    enabled_modules = registry.enabled_modules()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield

    async def authorize_request(request: Request) -> None:
        if not settings.auth_enabled:
            return
        path = request.url.path
        if path.startswith(("/static", "/docs", "/openapi.json")) or path in {
            "/", "/login", "/health", "/metrics", "/api/v1/auth/login"
        }:
            return
        token = request.cookies.get("access_token")
        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            token = authorization.removeprefix("Bearer ")
        identity = auth_service.decode_token(token)
        if identity is None:
            raise HTTPException(status_code=401, detail="请先登录")
        request.state.identity = identity
        tenant_id = request.query_params.get("tenant_id")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and "application/json" in request.headers.get("content-type", ""):
            try:
                payload = await request.json()
                tenant_id = payload.get("tenant_id", tenant_id) if isinstance(payload, dict) else tenant_id
            except ValueError:
                pass
        if tenant_id and tenant_id != identity.tenant_id:
            raise HTTPException(status_code=403, detail="禁止访问其他企业数据")
        if path.startswith("/api/v1/audit-logs") and identity.role not in {"owner", "admin"}:
            raise HTTPException(status_code=403, detail="需要管理员权限")
        if path.startswith("/api/v1/auth/users") and identity.role not in {"owner", "admin"}:
            raise HTTPException(status_code=403, detail="需要管理员权限")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if path.startswith(("/api/v1/knowledge", "/api/v1/customers")):
                allowed = {"owner", "admin", "editor"}
            else:
                allowed = {"owner", "admin", "editor", "agent"}
            if identity.role not in allowed:
                raise HTTPException(status_code=403, detail="当前角色没有写入权限")

    async def enforce_rate_limit(request: Request) -> None:
        if not settings.rate_limit_enabled or not request.url.path.startswith("/api/"):
            return
        identity = getattr(request.state, "identity", None)
        subject = identity.user_id if identity else (request.client.host if request.client else "unknown")
        is_login = request.url.path == "/api/v1/auth/login"
        limit = settings.login_rate_limit_per_minute if is_login else settings.rate_limit_requests_per_minute
        allowed, remaining = rate_limiter.allow(f"{subject}:{request.url.path}", limit)
        request.state.rate_limit_remaining = remaining
        if not allowed:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后重试")

    app = FastAPI(
        title="企业智能客服系统",
        description="基于企业知识库、证据引用和低置信度拒答的智能客服接口",
        version="0.1.0",
        lifespan=lifespan,
        dependencies=[Depends(authorize_request), Depends(enforce_rate_limit)],
    )
    web_dir = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=web_dir), name="static")
    for module in enabled_modules:
        app.include_router(module.router)

    @app.middleware("http")
    async def observe_requests(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        started = perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration = perf_counter() - started
            route = request.scope.get("route")
            route_path = getattr(route, "path", request.url.path)
            HTTP_REQUESTS.labels(request.method, route_path, str(status)).inc()
            HTTP_DURATION.labels(request.method, route_path).observe(duration)
            access_logger.info(
                "http_request",
                extra={
                    "request_id": request_id, "method": request.method,
                    "path": request.url.path, "status": status,
                    "duration_ms": round(duration * 1000, 2),
                },
            )

    @app.middleware("http")
    async def audit_mutations(request: Request, call_next):
        response = await call_next(request)
        identity = getattr(request.state, "identity", None)
        if identity and request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path != "/api/v1/auth/login":
            audit_store.add(
                identity.tenant_id, identity.user_id,
                f"http.{request.method.lower()}", request.url.path,
                "success" if response.status_code < 400 else "failed",
                request.client.host if request.client else "unknown",
            )
        return response

    @app.get("/", include_in_schema=False)
    def home(request: Request):
        if settings.auth_enabled and auth_service.decode_token(request.cookies.get("access_token")) is None:
            return RedirectResponse("/login", status_code=302)
        return FileResponse(web_dir / "index.html")

    @app.get("/login", include_in_schema=False)
    def login_page() -> FileResponse:
        return FileResponse(web_dir / "login.html")

    @app.get("/health", tags=["operations"])
    def health() -> dict[str, str]:
        database_status = "ok" if database.is_healthy() else "error"
        if redis_client is None:
            redis_status = "disabled"
        else:
            try:
                redis_status = "ok" if redis_client.ping() else "error"
            except Exception:
                redis_status = "fallback"
        return {
            "status": "ok" if database_status == "ok" else "degraded",
            "environment": settings.app_env,
            "database": database_status,
            "redis": redis_status,
        }

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/modules", tags=["operations"])
    def modules() -> list[dict[str, str]]:
        return [
            {"name": module.name, "version": module.version}
            for module in enabled_modules
        ]

    @app.get("/model-status", tags=["operations"])
    def model_status() -> dict[str, str | bool]:
        is_real_model = settings.ai_model_provider.lower() != "mock"
        return {
            "provider": settings.ai_model_provider,
            "model": settings.ai_model_name if is_real_model else "grounded-mock",
            "configured": is_real_model and bool(settings.ai_model_api_key),
            "fallback_enabled": settings.ai_model_fallback_enabled,
            "embedding_provider": settings.embedding_provider,
            "embedding_model": settings.embedding_model,
            "rerank_provider": settings.rerank_provider,
            "rerank_model": settings.rerank_model,
            "oms_provider": settings.oms_provider,
        }

    return app


app = create_app()
