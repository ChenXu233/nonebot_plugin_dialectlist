from typing import Union
from pydantic import BaseModel
from nonebot_plugin_orm import Model
from nonebot_plugin_userinfo import UserInfo


class UserRankInfo(UserInfo):
    user_bnum: int
    user_proportion: float
    user_nickname: str
    user_index: Union[int, str]
    user_avatar_bytes: bytes

class MsgCountDayData(BaseModel):
    user_id:str
# class MsgCountData(Model):
#     __tablename__ = 'dialectlist_msg_data'
