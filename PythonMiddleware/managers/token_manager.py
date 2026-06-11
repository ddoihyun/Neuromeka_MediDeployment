import grpc
import time

import common as Common


class TokenManager(metaclass=Common.SingletonMeta):
    def __init__(self, config_client) -> None:
        super().__init__()
        self._config_client = config_client
        self.token_cache = None

    def check_token_cache(self, token):
        token_pass = False
        if self.token_cache is not None:
            if self.token_cache[1] > time.time():
                token_pass = (self.token_cache[0] == token)
            else:
                self.token_cache = None
        return token_pass

    def update_token_cache(self, token=None):
        token_pass = False
        if token is None:
            if self.token_cache is not None:
                token = self.token_cache[0]
            else:
                return token_pass
        res = self._config_client.VerifyToken(token=token)
        if res is not None:
            token_pass = int(res['code']) == 0
            if token_pass:
                self.token_cache = (token, time.time()+5)  # cache time 5 sec
        else:
            self.token_cache = None
        return token_pass

    @classmethod
    def check(cls, func):
        def wrapper(self, request, context):
            try:
                metadata = dict(context.invocation_metadata())
                auth_header = metadata.get('authorization')
                if auth_header and auth_header.startswith("Bearer "):
                    token = auth_header.split("Bearer ")[1]
                    token_pass = cls().check_token_cache(token)
                    if not token_pass:
                        token_pass = cls().update_token_cache(token)
                    if token_pass:
                        res = func(self, request, context)
                        return res
                    else:
                        cls().token_cache = None
                        context.set_code(grpc.StatusCode.UNAVAILABLE)
                return None
            except:
                return None
        return wrapper
