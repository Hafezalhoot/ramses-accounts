"""Bound request bytes before JSON/multipart parsing and temporary-file writes."""
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

MAX_REQUEST_BYTES = 7 * 1024 * 1024  # One 6 MiB evidence file + multipart overhead.
TOO_LARGE = 'حجم الطلب أكبر من الحد المسموح؛ أرسل مرفقًا واحدًا لا يتجاوز 6 ميجابايت'


class RequestBodyLimitMiddleware:
    def __init__(self, app, max_bytes=MAX_REQUEST_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        lengths = [value for key, value in scope['headers'] if key.lower() == b'content-length']
        if lengths:
            if len(lengths) != 1 or not lengths[0].isdigit():
                return await JSONResponse({'detail':'طول الطلب غير صالح'}, status_code=400)(scope, receive, send)
            # Bound the decimal representation too; int() must not parse an
            # attacker-controlled, arbitrarily long sequence of digits.
            length = lengths[0].lstrip(b'0') or b'0'
            if len(length) > len(str(self.max_bytes)) or int(length) > self.max_bytes:
                return await JSONResponse({'detail':TOO_LARGE}, status_code=413)(scope, receive, send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                if received > self.max_bytes:
                    # FastAPI preserves HTTPException from body parsing;
                    # Starlette closes partial upload spools on stream failure.
                    raise HTTPException(status_code=413, detail=TOO_LARGE)
            return message

        await self.app(scope, limited_receive, send)
