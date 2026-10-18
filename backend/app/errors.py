class AppError(Exception):
    def __init__(self, code, message, status=400, retryable=False, **extra):
        self.code, self.message, self.status, self.retryable, self.extra = code, message, status, retryable, extra

    def payload(self, request_id=None):
        return dict(code=self.code, message=self.message, retryable=self.retryable, request_id=request_id, **self.extra)
