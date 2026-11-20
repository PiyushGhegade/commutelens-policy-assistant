import asyncio
import logging
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.answers import render_answer
from app.auth import COMPANIES, Identity, admin, identity, issue
from app.config import Settings
from app.llm import FakeLLM, GeminiLLM, GroqLLM, ProviderError
from app.models import Answer, Citation, LLMAttempt, Policy, PolicyResponse, Question, StrictModel
from app.retrieval import retrieve
from app.store import PolicyConflict, PolicyStore, UnsafeDocument

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)


class Login(StrictModel):
    username: str
    password: str


def foreign_company(question: str, own: str) -> bool:
    words = set(re.findall(r"[a-z0-9]+", question.lower()))
    return any(slug != own and slug in words for slug in COMPANIES)


def create_app(settings: Settings | None = None, *, store=None, llm=None, fallback_llm=None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = store or PolicyStore(settings.data_dir, settings.embedding_model)
        await asyncio.to_thread(app.state.store.seed, ROOT / "policies")
        # Warm the embedding model before accepting requests. Cold downloads are startup work.
        await asyncio.to_thread(app.state.store.embed, ["commute policy"])
        app.state.fallback_llm = fallback_llm
        if llm is not None:
            app.state.llm = llm
        elif settings.llm_provider == "gemini":
            app.state.llm = GeminiLLM(settings)
            # One call by default. No automatic retries that consume extra quota.
        elif settings.llm_provider == "groq":
            app.state.llm = GroqLLM(settings)
        elif settings.llm_provider == "fake":
            app.state.llm = FakeLLM()
        else:
            raise ValueError("LLM_PROVIDER must be gemini, groq or fake")
        yield
        await app.state.llm.aclose()
        if app.state.fallback_llm is not None and app.state.fallback_llm is not app.state.llm:
            await app.state.fallback_llm.aclose()
        if store is None:
            app.state.store.close()

    app = FastAPI(title="Commute Policy Assistant", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    # Timed-out Chroma calls continue in a thread. Bound them to avoid unbounded buildup.
    retrieval_slots = threading.BoundedSemaphore(4)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Check the input fields. Questions accept only question and retrieval; company comes from your session."
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logger.error("Request failed: %s", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={
                "detail": "The service is temporarily unavailable. Try again or contact the transport desk."
            },
        )

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "provider": settings.llm_provider,
            "real_llm_configured": bool(settings.gemini_api_key)
            if settings.llm_provider == "gemini"
            else bool(settings.groq_api_key)
            if settings.llm_provider == "groq"
            else False,
            "embedding": settings.embedding_model,
            "demo_mode": settings.demo_mode,
            "model": app.state.llm.model_name,
            "answer_timeout_seconds": settings.answer_timeout,
        }

    @app.post("/auth/demo-token")
    async def login(body: Login):
        return {"access_token": issue(settings, body.username, body.password), "token_type": "bearer"}

    @app.get("/me")
    async def me(user: Identity = Depends(identity)):
        return {
            "subject": user.subject,
            "company": user.company,
            "company_name": COMPANIES[user.company],
            "role": user.role,
        }

    @app.get("/policy", response_model=Policy)
    async def active_policy(request: Request, user: Identity = Depends(identity)):
        snapshot = request.app.state.store.active(user.company)
        if not snapshot:
            raise HTTPException(404, "Your policy is unavailable. Contact the transport desk.")
        return snapshot.policy

    @app.post("/admin/policy")
    async def publish(body: Policy, request: Request, user: Identity = Depends(admin)):
        try:
            result = await asyncio.to_thread(request.app.state.store.ingest, user.company, body)
            return {"status": "active", "company": user.company, "version": result.policy.version}
        except PolicyConflict:
            raise HTTPException(409, "Publish a version greater than the active version.") from None
        except UnsafeDocument:
            raise HTTPException(
                422,
                "The document contains assistant-directed instructions. Remove them and retry; the active policy is unchanged.",
            ) from None
        except Exception:
            raise HTTPException(
                503, "Policy indexing failed. The active policy is unchanged. Try again."
            ) from None

    @app.post("/questions", response_model=Answer)
    async def ask(body: Question, request: Request, user: Identity = Depends(identity)):
        started = perf_counter()
        snapshot = None
        calls = 0
        retrieval_ms = 0.0
        retrieved_ids = []
        request_id = uuid4().hex
        attempts = []
        model = ""
        answer_style = "policy_excerpt" if settings.llm_provider == "fake" else "direct"
        verdict = None

        def finish(status, message, *, citations=None, reason=""):
            return Answer(
                status=status,
                answer=message,
                citations=citations or [],
                company=user.company,
                version=snapshot.policy.version if snapshot else None,
                llm_calls=calls,
                latency_ms=round((perf_counter() - started) * 1000, 2),
                retrieval_ms=round(retrieval_ms, 2),
                retrieved_ids=retrieved_ids,
                provider=settings.llm_provider,
                reason=reason,
                request_id=request_id,
                llm_model=model,
                llm_attempts=attempts,
                answer_style=answer_style,
                verdict=verdict,
            )

        def not_covered(reason):
            nonlocal verdict
            verdict = "not_covered"
            return finish(
                "not_covered",
                "I could not find a rule covering this question in your company's current policy. Please contact the transport desk.",
                reason=reason,
            )

        def bounded_retrieval():
            if not retrieval_slots.acquire(blocking=False):
                raise ProviderError("retrieval_busy")
            try:
                return retrieve(request.app.state.store, snapshot, body.question, body.retrieval)
            finally:
                retrieval_slots.release()

        try:
            async with asyncio.timeout(settings.answer_timeout):
                snapshot = request.app.state.store.active(user.company)
                if not snapshot:
                    return finish(
                        "try_again",
                        "Your policy is unavailable. Please contact the transport desk.",
                        reason="no_policy",
                    )
                if foreign_company(body.question, user.company):
                    return not_covered("outside_company")
                retrieval_started = perf_counter()
                try:
                    hits = await asyncio.wait_for(
                        asyncio.to_thread(bounded_retrieval), settings.retrieval_timeout
                    )
                except TimeoutError:
                    retrieval_ms = (perf_counter() - retrieval_started) * 1000
                    return finish(
                        "try_again",
                        "Policy search is taking too long. Please try again or contact the transport desk.",
                        reason="retrieval_timeout",
                    )
                finally:
                    retrieval_ms = (perf_counter() - retrieval_started) * 1000
                retrieved_ids = [h.section.id for h in hits]
                if not hits:
                    return not_covered("no_evidence")
                selectors = [request.app.state.llm]
                if request.app.state.fallback_llm is not None:
                    selectors.append(request.app.state.fallback_llm)
                allowed = {h.section.id: h.section for h in hits}
                for index, selector in enumerate(selectors):
                    remaining = settings.answer_timeout - (perf_counter() - started) - 0.04
                    if remaining <= 0:
                        raise ProviderError("llm_timeout")
                    budget = (
                        min(settings.first_llm_timeout, remaining)
                        if index == 0 and len(selectors) > 1
                        else remaining
                    )
                    model = selector.model_name
                    attempt_started = perf_counter()
                    calls += 1
                    try:
                        selection = PolicyResponse.model_validate(
                            await asyncio.wait_for(selector.respond(body.question, hits), budget)
                        )
                        if any(sid not in allowed for sid in selection.section_ids):
                            raise ProviderError("invalid_output")
                    except (TimeoutError, ProviderError) as exc:
                        error = ProviderError("llm_timeout") if isinstance(exc, TimeoutError) else exc
                        attempts.append(
                            LLMAttempt(
                                model=model,
                                status=str(error),
                                latency_ms=round((perf_counter() - attempt_started) * 1000, 2),
                                http_status=error.http_status,
                            )
                        )
                        # Never log keys, prompts, response bodies, or user questions.
                        logger.warning(
                            "LLM request failed request_id=%s model=%s reason=%s http_status=%s",
                            request_id,
                            model,
                            str(error),
                            error.http_status,
                        )
                        different_model = (
                            index + 1 < len(selectors) and selectors[index + 1].model_name != model
                        )
                        if index + 1 < len(selectors) and (
                            error.retryable or (str(error) == "model_unavailable" and different_model)
                        ):
                            continue
                        raise error
                    attempts.append(
                        LLMAttempt(
                            model=model,
                            status="ok",
                            latency_ms=round((perf_counter() - attempt_started) * 1000, 2),
                        )
                    )
                    break
                # No await between final version check and response assembly.
                if not request.app.state.store.is_current(snapshot):
                    return finish(
                        "try_again",
                        "Your policy changed while I was checking. Please ask again to use the latest version.",
                        reason="policy_changed",
                    )
                if selection.not_covered:
                    return not_covered("insufficient_evidence")
                verdict = selection.verdict
                selected = [allowed[sid] for sid in selection.section_ids]
                citations = [
                    Citation(
                        document=snapshot.policy.document,
                        version=snapshot.policy.version,
                        section_id=s.id,
                        section=s.title,
                        quote=s.text,
                    )
                    for s in selected
                ]
                return finish("answered", render_answer(selection), citations=citations)

        except TimeoutError:
            return finish(
                "try_again",
                "The answer is taking too long. Please try again or contact the transport desk.",
                reason="answer_timeout",
            )
        except ProviderError as exc:
            reason = str(exc)
            messages = {
                "missing_key": "The AI service is not configured. Please contact the transport desk.",
                "quota": "The AI service has reached its free-tier limit. Please try again later or contact the transport desk.",
                "llm_timeout": "The AI service did not respond in time. Please try again or contact the transport desk.",
                "llm_unavailable": "The AI service is temporarily unavailable. Please try again or contact the transport desk.",
                "network_error": "The AI service could not be reached. Please try again or contact the transport desk.",
                "auth_error": "The AI service rejected its credentials. Please contact the transport desk to check the configuration.",
                "model_unavailable": "The configured AI model is unavailable. Please contact the transport desk to check the configuration.",
                "invalid_request": "The AI service configuration needs attention. Please contact the transport desk.",
            }
            return finish(
                "try_again",
                messages.get(
                    reason,
                    "I could not verify an answer right now. Please try again or contact the transport desk.",
                ),
                reason=reason,
            )
        except Exception as exc:
            logger.warning("Answer validation failed request_id=%s error=%s", request_id, type(exc).__name__)
            return finish(
                "try_again",
                "I could not verify an answer right now. Please try again or contact the transport desk.",
                reason="verification_failed",
            )

    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.get("/", include_in_schema=False)
    async def home():
        return FileResponse(ROOT / "static" / "index.html")

    return app


app = create_app()
