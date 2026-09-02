"""Worker wiring: turns configuration into a running LiveKit session.

Everything that touches the agent framework's *lifecycle* lives here. The
awkward parts are deliberate:

* ``session.start`` accepts room options under different keyword names across
  1.x releases, so the supported one is discovered by inspecting the signature
  rather than assumed.
* The HTTP client and memory store are closed from a shutdown callback, because
  a worker that leaks a connection pool per room dies slowly in production.
"""

from __future__ import annotations

import inspect
from collections.abc import Collection
from typing import Any

from . import compat, providers
from .agent import ToolDeps, build_agent
from .config import Settings, load_settings
from .errors import NinaError
from .logging_setup import configure_logging, get_logger
from .persona import build_greeting, build_instructions

logger = get_logger("runtime")


def _load_dotenv() -> None:
    """Load a local ``.env`` if python-dotenv is available.

    Optional on purpose: in a container the environment is already populated and
    there is no file to read.
    """
    try:
        from dotenv import load_dotenv  # noqa: PLC0415
    except ImportError:
        return
    load_dotenv()


def _room_kwargs(session: Any, noise_filter: Any | None) -> dict[str, Any]:
    """Build the room-options keyword for whichever ``session.start`` we have.

    Returns an empty dict when no noise filter is configured or when the
    installed version exposes neither known keyword, since noise cancellation is
    an enhancement rather than a requirement.
    """
    if noise_filter is None:
        return {}

    agents = compat.load_agents()
    try:
        params: Collection[str] = inspect.signature(session.start).parameters
    except (TypeError, ValueError):  # pragma: no cover - defensive
        params = ()

    if "room_input_options" in params:
        room_input_options = getattr(agents, "RoomInputOptions", None)
        if room_input_options is not None:
            return {"room_input_options": room_input_options(noise_cancellation=noise_filter)}

    if "room_options" in params:
        room_io = getattr(agents, "room_io", None)
        if room_io is not None:
            return {
                "room_options": room_io.RoomOptions(
                    audio_input=room_io.AudioInputOptions(noise_cancellation=noise_filter)
                )
            }

    logger.warning("this livekit-agents build exposes no room options; skipping noise filter")
    return {}


def _attach_metrics(session: Any, ctx: Any) -> None:
    """Log per-turn metrics and a usage summary, when the build supports it."""
    agents = compat.load_agents()
    metrics = getattr(agents, "metrics", None)
    if metrics is None:
        return

    @session.on("metrics_collected")
    def _on_metrics(event: Any) -> None:
        try:
            metrics.log_metrics(event.metrics)
        except Exception:  # pragma: no cover - telemetry must never break a call
            logger.debug("could not log metrics", exc_info=True)

    async def _log_usage() -> None:
        usage = getattr(session, "usage", None)
        if usage is not None:
            logger.info("session usage", extra={"usage": str(usage)})

    add_shutdown = getattr(ctx, "add_shutdown_callback", None)
    if callable(add_shutdown):
        add_shutdown(_log_usage)


async def entrypoint(ctx: Any, settings: Settings | None = None) -> None:
    """Run one NINA session for one room.

    Args:
        ctx: The LiveKit ``JobContext`` for this job.
        settings: Injectable configuration; loaded from the environment when
            omitted.
    """
    agents = compat.load_agents()
    settings = settings or load_settings()

    room_name = getattr(getattr(ctx, "room", None), "name", "<unknown>")
    log_fields = getattr(ctx, "log_context_fields", None)
    if isinstance(log_fields, dict):
        log_fields["room"] = room_name
    logger.info(
        "session starting",
        extra={"room": room_name, "stack": providers.describe(settings)},
    )

    deps = ToolDeps.from_settings(settings)

    add_shutdown = getattr(ctx, "add_shutdown_callback", None)
    if callable(add_shutdown):
        add_shutdown(deps.aclose)

    # The realtime provider needs the system prompt at construction time; the
    # pipeline provider ignores it and takes it from the agent instead.
    session_kwargs = providers.build_session_kwargs(
        settings, build_instructions(settings.persona, tools=settings.tools)
    )
    session = agents.AgentSession(**session_kwargs)
    _attach_metrics(session, ctx)

    noise_filter = compat.load_noise_cancellation(settings.noise_cancellation)
    if settings.noise_cancellation != "none" and noise_filter is None:
        logger.warning(
            "noise cancellation requested but unavailable; continuing without it",
            extra={"mode": settings.noise_cancellation},
        )

    try:
        await session.start(
            room=ctx.room,
            agent=build_agent(deps),
            **_room_kwargs(session, noise_filter),
        )

        if settings.persona.greet_on_start:
            await session.generate_reply(instructions=build_greeting(settings.persona))
    except Exception:
        # Close eagerly: on a failed start the shutdown callback may never fire.
        await deps.aclose()
        raise

    logger.info("session started", extra={"room": room_name})


def build_worker_options(settings: Settings) -> Any:
    """Build ``WorkerOptions`` bound to our entrypoint."""
    agents = compat.load_agents()

    async def _entrypoint(ctx: Any) -> None:
        await entrypoint(ctx, settings)

    return agents.WorkerOptions(entrypoint_fnc=_entrypoint)


def run() -> None:
    """Process entrypoint: load config, configure logging, hand off to the CLI.

    LiveKit's own CLI owns ``sys.argv`` from here (``dev``, ``start``,
    ``console``, ``download-files``), which is why this function takes no
    arguments.
    """
    _load_dotenv()
    settings = load_settings()
    configure_logging(settings.log_level, settings.log_format)
    logger.info(
        "starting NINA",
        extra={"stack": providers.describe(settings), "tools": ", ".join(settings.tools) or "none"},
    )

    agents = compat.load_agents()
    worker_options = build_worker_options(settings)
    if not hasattr(agents, "cli"):  # pragma: no cover - defensive
        raise NinaError("livekit.agents has no cli module")
    agents.cli.run_app(worker_options)
