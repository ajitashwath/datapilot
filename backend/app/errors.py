class UserError(Exception):
    def __init__(self, message: str, code: str = "bad_request", status: int = 400, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.headers = headers or {}
