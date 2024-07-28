from typing import Optional, Literal, List, Union
from pydantic import BaseModel
from nonebot_plugin_userinfo import get_user_info, UserInfo


class UserRankInfo(UserInfo):
    user_bnum: int
    user_proportion: float
    user_nickname: str
    user_index: Union[int, str]
    user_avatar_bytes: bytes
