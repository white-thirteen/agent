"""Errors translated by the HTTP boundary."""


class PublicError(RuntimeError):
    """Safe fixed messages for errors crossing the HTTP boundary."""

    code = "agent_not_ready"
    status_code = 503
    message = "Agent resources or execution entry point are not ready."

    def __init__(self, message: str | None = None):
        super().__init__(message or self.message)


class AgentNotReadyError(PublicError):
    """The execution graph or its prerequisite resources are unavailable."""


class SessionUnavailableError(PublicError):
    code = "session_unavailable"
    message = "Session storage is unavailable."


class DemoUserNotAllowedError(PublicError):
    code = "demo_user_not_allowed"
    status_code = 403
    message = "Demo user is not allowed."


class DemoIdentityDisabledError(PublicError):
    code = "demo_identity_disabled"
    message = "Demo identity is disabled in this environment."


class RuntimeRequestError(PublicError):
    """Finite runtime admission/query errors, with no SDK or State payload."""

    def __init__(self, code: str, *, status_url: str | None = None):
        messages = {
            "thread_busy": (409, "This session is already executing."),
            "task_blocked": (409, "This task is waiting at a protected boundary."),
            "explicit_new_task_required": (409, "Use new_task to start a new task after failure."),
            "request_id_conflict": (409, "Request ID was already used for different input."),
            "subscription_exists": (409, "A subscription already exists. Query its status."),
            "runtime_busy": (503, "Execution capacity is full."),
            "runtime_stopping": (503, "Runtime is stopping."),
            "run_not_found": (404, "Run was not found."),
            "execution_uncertain": (409, "Execution state requires reconciliation."),
            "state_unavailable": (503, "Task state is unavailable."),
            "event_replay_not_supported": (409, "Event replay is not supported. Query run status."),
        }
        self.code = code
        self.status_code, self.message = messages[code]
        self.status_url = status_url
        super().__init__()
