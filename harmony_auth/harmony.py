import pickle
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Optional, Any, Union

import httpx
from dateutil import parser as iso_parser
from fastapi import Security, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.security.api_key import APIKeyCookie
from redis import asyncio as aioredis
from starlette.status import HTTP_403_FORBIDDEN, HTTP_400_BAD_REQUEST

from .models import DiscordUser, PartialDiscordGuild, CurrentUserData

authorize_header = HTTPBearer(auto_error=False)
authorize_cookie = APIKeyCookie(name='token', auto_error=False)
_not_authenticated = HTTPException(
    status_code=HTTP_403_FORBIDDEN, detail="Not authenticated"
)


def _json_or_text(response: httpx.Response) -> Union[dict[Any, Any], str]:
    try:
        return response.json() or response.text
    except JSONDecodeError:
        return response.text


class HarmonyAuth:
    def __init__(
            self,
            redis_url: str = "redis://localhost",
            required_scopes: set = None,
            use_cookie: bool = False,
            use_header: bool = True,
            cookie_name: str = "access-token",
            retrieve_guilds: bool = True,
            api_url: str = "https://discord.com/api/v10",
            client_id: Optional[int] = None,
            client_secret: Optional[str] = None,
            verify_client_id=True
    ):
        """
        Discord OAuth2 Implicit Flow handler for FastAPI.

        :param redis_url: URL for redis cache
        :param required_scopes: *optional* scopes the token must have access to. Defaults to identify, guilds
        :param use_cookie: Allow token to be passed through cookie
        :param use_header: Allow token to be passed through Authorization header
        :param cookie_name: Name of cookie. Defaults to "token"
        :param retrieve_guilds: Whether to fetch list of user guilds upon login
        :param api_url: Base url to Discord's API. Useful if using twilight-http-proxy.
        :param client_id: Used for verifying token client id and token revocation
        :param client_secret: Used for token revocation
        :param verify_client_id: Whether to verify the token matches the client id. Requires client_id
        """
        if use_cookie is False and use_header is False:
            raise AttributeError(
                "use_cookie and use_header are both False one of them needs to be True"
            )
        self.use_cookie = use_cookie
        self.use_header = use_header
        self.cookie_name = cookie_name
        self.retrieve_guilds = retrieve_guilds
        self.client_id = client_id
        self.client_secret = client_secret
        self.verify_client_id = verify_client_id

        if not required_scopes:
            self.required_scopes = {'identify', 'guilds'}
        elif isinstance(required_scopes, set):
            self.required_scopes = required_scopes
        else:
            self.required_scopes = set(required_scopes)

        self.redis_client = aioredis.from_url(redis_url)
        self.session = httpx.AsyncClient(base_url=api_url)

    def _get_token(self,
                   header_token: Optional[HTTPAuthorizationCredentials],
                   cookie_token: Optional[str],
                   ) -> Optional[str]:
        """
        Returns token from header or cookie.
        Tries header first (if enabled)
        :raise HTTPException: if neither header nor cookie token supplied
        """
        if self.use_header:
            if not header_token and not self.use_cookie:
                raise _not_authenticated
            return header_token.credentials
        if self.use_cookie:
            if not cookie_token:
                raise _not_authenticated
            return cookie_token

    async def discord_request(self, url: str, token: str, method='GET', json: Optional[Any] = None,
                              headers: Optional[dict] = None, **kwargs) -> Union[dict[str, Any], str]:
        if headers is None:
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", }
        if 'Authorization' not in headers:
            headers['Authorization'] = f"Bearer {token}"
        if 'Accept' not in headers:
            headers["Accept"] = "application/json"

        try:
            response = await self.session.request(method=method, url=url, headers=headers, json=json, **kwargs)
            response.raise_for_status()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail="Discord unavailable") from exc
        except httpx.HTTPStatusError as exc:
            # Reraise as Starlette HTTP error
            raise HTTPException(
                status_code=exc.response.status_code, detail=_json_or_text(exc.response)
            ) from exc
        return _json_or_text(response)

    async def _store_user(self, token: str):
        # Verify token is valid & get user
        user_data = await self.discord_request("/oauth2/@me", token)
        # noinspection PyTypeChecker
        if self.verify_client_id and self.client_id and self.client_id != int(user_data['application']['id']):
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid client ID for token provided")
        scopes = user_data['scopes']

        # Ensure minimal scopes are met
        if not self.required_scopes.issubset(scopes):
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Invalid scopes. Please reauthorize with {self.required_scopes} scopes."
            )

        # Set proper expiry date
        expires = iso_parser.isoparse(user_data['expires'])
        expires = expires - datetime.now(timezone.utc)

        # Get current user
        # Discord's /oauth2/@me endpoint doesn't provide enough user info. Have to get current user
        user_response = await self.discord_request("/users/@me", token)
        user = DiscordUser.parse_obj(user_response)
        # Get guilds
        if self.retrieve_guilds:
            guilds_response = await self.discord_request("/users/@me/guilds", token)
            guilds = [PartialDiscordGuild.parse_obj(obj) for obj in guilds_response]
        else:
            guilds = []

        user_data = CurrentUserData(user=user, guilds=guilds)
        data_pickled = pickle.dumps(user_data)
        await self.redis_client.setex(token, time=expires, value=data_pickled)
        return user_data

    async def get_user(self, token: str, force_fetch=False) -> CurrentUserData:
        # Look up in cache first
        if force_fetch:
            return await self._store_user(token)

        cached_pickle = await self.redis_client.get(token)
        if cached_pickle:
            return pickle.loads(cached_pickle)
        else:
            return await self._store_user(token)

    async def revoke_token(self, token: str):
        # Remove token & data from cache
        await self.redis_client.delete(token)
        # Only revoke with discord if client id & secret are provided
        if self.client_id and self.client_secret:
            revoke_data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "token": token
            }
            await self.discord_request(url="/oauth2/token/revoke", method='POST',
                                       headers={"Content-Type": "application/x-www-form-urlencoded"},
                                       data=revoke_data, token=token)  # Don't actually need token for this request

    async def __call__(self,
                       request: Request,
                       header_token: HTTPAuthorizationCredentials = Security(authorize_header),
                       cookie_token: str = Security(authorize_cookie),
                       ) -> CurrentUserData:
        """FastAPI Dependency to require valid Discord User token"""
        token = self._get_token(header_token, cookie_token)

        return await self.get_user(token)

    async def token(self,
                    _: Request,
                    header_token: HTTPAuthorizationCredentials = Security(authorize_header),
                    cookie_token: str = Security(authorize_cookie)
                    ) -> str:
        """Get token"""
        return self._get_token(header_token, cookie_token)
