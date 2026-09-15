class ApiError(Exception):
    """Raised by module handlers to produce a {code, msg} error response."""

    def __init__(self, msg: str, code: int = 1):
        self.msg = msg
        self.code = code
        super().__init__(msg)
