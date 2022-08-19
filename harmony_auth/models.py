from typing import Optional

from pydantic import BaseModel

MISSING = Optional[str]


class DiscordUser(BaseModel):
    id: str
    username: str
    discriminator: str
    avatar: MISSING
    bot: Optional[bool]
    system: Optional[bool]
    mfa_enabled: Optional[bool]
    banner: MISSING
    accent_color: Optional[int]
    locale: MISSING
    verified: Optional[bool]
    email: MISSING
    flags: Optional[int]
    premium_type: Optional[int]
    public_flags: Optional[int]

    class Config:
        schema_extra = {
            'example':
                {
                    "id": "80351110224678912",
                    "username": "Nelly",
                    "discriminator": "1337",
                    "avatar": "8342729096ea3675442027381ff50dfe",
                    "bot": False,
                    "system": False,
                    "mfa_enabled": True,
                    "banner": "06c16474723fe537c283b8efa61a30c8",
                    "accent_color": 16711680,
                    "locale": "en-US",
                    "verified": True,
                    "email": "nelly@discord.com",
                    "flags": 64,
                    "premium_type": 1,
                    "public_flags": 64
                }
        }


class PartialDiscordGuild(BaseModel):
    id: str
    name: str
    icon: MISSING
    owner: bool
    permissions: str
    features: list[str]

    class Config:
        schema_extra = {
            'example':
                {
                    "id": "80351110224678912",
                    "name": "1337 Krew",
                    "icon": "8342729096ea3675442027381ff50dfe",
                    "owner": True,
                    "permissions": "36953089",
                    "features": ["COMMUNITY", "NEWS"]
                }
        }


class CurrentUserData(BaseModel):
    user: DiscordUser
    guilds: list[PartialDiscordGuild]
