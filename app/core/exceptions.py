class LabelForgeError(Exception):
    """Base class for domain errors, mapped to HTTP responses at the API layer."""


class NotFoundError(LabelForgeError):
    pass


class ValidationError(LabelForgeError):
    pass


class ConflictError(LabelForgeError):
    pass
