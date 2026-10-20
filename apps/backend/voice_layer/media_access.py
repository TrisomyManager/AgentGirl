"""Durable ownership of generated voice assets; no host dependency."""

import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from sqlalchemy import Column, String, select

from shared_runtime.database import AsyncSessionLocal, Base


class VoiceAssetORM(Base):
    __tablename__ = "voice_assets"
    filename = Column(String(255), primary_key=True)
    user_id = Column(String(128), nullable=False, index=True)


async def register_voice_asset(url: str, user_id: str | None):
    if not user_id:
        return
    path = urlsplit(url).path
    if not path.startswith("/static/voice/"):
        return
    name = PurePosixPath(path).name
    if not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,254}", name):
        raise ValueError("Invalid voice asset name")
    async with AsyncSessionLocal() as session:
        if session.bind.dialect.name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
        else:
            from sqlalchemy.dialects.postgresql import insert
        await session.execute(insert(VoiceAssetORM).values(filename=name, user_id=user_id).on_conflict_do_nothing())
        owner = await session.scalar(select(VoiceAssetORM.user_id).where(VoiceAssetORM.filename == name))
        if owner != user_id:
            raise PermissionError("Voice asset has a different owner")
        await session.commit()


async def owns_voice_asset(filename: str, user_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", filename):
        return False
    async with AsyncSessionLocal() as session:
        owner = await session.scalar(select(VoiceAssetORM.user_id).where(VoiceAssetORM.filename == filename))
    return owner == user_id


def delete_voice_files(filenames):
    """Only remove an owned basename inside the configured voice output folder."""
    from voice_layer.audio_utils import get_voice_temp_directory

    root = get_voice_temp_directory().resolve()
    for filename in filenames:
        if not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,254}", filename):
            raise ValueError("Invalid voice asset name")
        target = root / filename
        if target.is_symlink() or target.resolve().parent != root:
            raise ValueError("Voice asset escaped output directory")
        target.unlink(missing_ok=True)
