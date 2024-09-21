from datetime import datetime
from typing import Union
from pydantic import BaseModel
from sqlalchemy import JSON, TEXT, String,Integer
from nonebot_plugin_orm import Model
from nonebot_plugin_userinfo import UserInfo
from sqlalchemy.orm import Mapped, mapped_column


class UserRankInfo(UserInfo):
    user_bnum: int
    user_proportion: float
    user_nickname: str
    user_index: Union[int, str]
    user_avatar_bytes: bytes


# class MsgCountDayData(BaseModel):
#     session_id: str
#     session_bnum: int

class MessageCountCache(Model):
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(primary_key=True)
    time: Mapped[datetime]
    session_id: Mapped[int] = mapped_column(Integer)
    session_bnum: Mapped[int] = mapped_column(Integer)
