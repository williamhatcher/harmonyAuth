from fastapi import FastAPI, Depends

from harmony_auth import HarmonyAuth, CurrentUserData

app = FastAPI()

auth = HarmonyAuth()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/@me", response_model=CurrentUserData)
async def user_info(user=Depends(auth)):
    return user


@app.get("/logout")
async def logout(_=Depends(auth.revoke_token)):
    return


@app.get('/secure')
async def secure_route(user: CurrentUserData = Depends(auth)):
    return user


@app.get("/show-token")
async def show_token(token: str = Depends(auth.token)):
    return token


@app.get("/refresh")
async def refresh_user_data(token: str = Depends(auth.token)):
    await auth.get_user(token, force_fetch=True)
    return "done"
