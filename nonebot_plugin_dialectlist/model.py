from typing import Union
from nonebot_plugin_orm import Model
from nonebot_plugin_userinfo import UserInfo


class UserRankInfo(UserInfo):
    user_bnum: int
    user_proportion: float
    user_nickname: str
    user_index: Union[int, str]
    user_avatar_bytes: bytes


class MsgData(Model):
    __table_args__ = {"extend_existing": True}
