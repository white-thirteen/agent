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
