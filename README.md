# Harmony Auth

Discord OAuth2 Implicit Grant thingy for FastAPI.

Tokens are cached in Redis with the user's information & guilds (if enabled)

Yes. I know this is a mess. :)

## Server Usage

```python
from harmony_auth import HarmonyAuth
from fastapi import FastAPI, Depends

auth = HarmonyAuth()
app = FastAPI()


@app.get('/secure')
async def secure_route(user=Depends(auth)):
    return user

```

## Client Usage
1. [Request an implicit grant access token from Discord](https://discord.com/developers/docs/topics/oauth2#implicit-grant)
2. Pass received `access_token` to any endpoint with the Harmony Auth dependency to login and access resources.

```sh
curl -X GET --location "http://127.0.0.1:8000/secure" \
    -H "Accept: application/json" \
    -H "Authorization: Bearer {{access_token}}"
```

### Reload User Data
If you need to reload the user's data in the cache (if they joined a guild, for example), call `get_user(token, force_fetch=True)`

Example:
```python
@app.get("/refresh")
async def refresh_user_data(token: str = Depends(auth.token)):
    user = await auth.get_user(token, force_fetch=True)
    ...
```
This will update the cache and return the user.

### Log Out / Revoke token
Use `revoke_token(token)` to remove user data from the cache. This removes all the cached user information.

If you specify a `client_id` and `client_secret`, _Harmony Auth_ will request that Discord revokes the token.

### Q: How do I log in?
A: You don't need to log in. Just provide a valid access token.

## Rate limit protections
I personally don't want to handle this, so I am using [twilight-http-proxy](https://github.com/twilight-rs/http-proxy).

TODO: Create fork to add OAuth2 routes to twilight http proxy.
