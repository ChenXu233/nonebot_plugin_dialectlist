from datetime import datetime, time, tzinfo
from typing import Optional, Dict, List, Union
from zoneinfo import ZoneInfo
from sqlalchemy import or_, select
from sqlalchemy.sql import ColumnElement

from nonebot.log import logger
from nonebot.params import Arg, Depends
from nonebot.typing import T_State
from nonebot.matcher import Matcher
from nonebot.adapters import Message

from nonebot_plugin_orm import get_session
from nonebot_plugin_session import Session, SessionLevel, extract_session
from nonebot_plugin_session_orm import SessionModel
from nonebot_plugin_userinfo import EventUserInfo, UserInfo
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_chatrecorder import MessageRecord
from nonebot_plugin_alconna import AlconnaMatcher


from .config import plugin_config


def parse_datetime(key: str):
    """解析数字，并将结果存入 state 中"""

    async def _key_parser(
        matcher: AlconnaMatcher,
        state: T_State,
        input: Union[datetime, Message] = Arg(key),
    ):
        if isinstance(input, datetime):
            return

        plaintext = input.extract_plain_text()
        try:
            state[key] = get_datetime_fromisoformat_with_timezone(plaintext)
        except ValueError:
            await matcher.reject_arg(key, "请输入正确的日期，不然我没法理解呢！")

    return _key_parser


def get_datetime_now_with_timezone() -> datetime:
    """获取当前时间，并包含时区信息"""
    if plugin_config.timezone:
        return datetime.now(ZoneInfo(plugin_config.timezone))
    else:
        return datetime.now().astimezone()


def get_datetime_fromisoformat_with_timezone(date_string: str) -> datetime:
    """从 ISO-8601 格式字符串中获取时间，并包含时区信息"""
    if not plugin_config.timezone:
        return datetime.fromisoformat(date_string).astimezone()
    raw = datetime.fromisoformat(date_string)
    return (
        raw.astimezone(ZoneInfo(plugin_config.timezone))
        if raw.tzinfo
        else raw.replace(tzinfo=ZoneInfo(plugin_config.timezone))
    )


def time_astimezone(time: time, tz: Optional[tzinfo] = None) -> time:
    """将 time 对象转换为指定时区的 time 对象

    如果 tz 为 None，则转换为本地时区
    """
    local_time = datetime.combine(datetime.today(), time)
    return local_time.astimezone(tz).timetz()


def get_time_fromisoformat_with_timezone(time_string: str) -> time:
    """从 iso8601 格式字符串中获取时间，并包含时区信息"""
    if not plugin_config.timezone:
        return time_astimezone(time.fromisoformat(time_string))
    raw = time.fromisoformat(time_string)
    return (
        time_astimezone(raw, ZoneInfo(plugin_config.timezone))
        if raw.tzinfo
        else raw.replace(tzinfo=ZoneInfo(plugin_config.timezone))
    )


def get_time_with_scheduler_timezone(time: time) -> time:
    """获取转换到 APScheduler 时区的时间"""
    return time_astimezone(time, scheduler.timezone)


# 暂时不做考虑
# def admin_permission():
#     permission = SUPERUSER
#     with contextlib.suppress(ImportError):
#         from nonebot.adapters.onebot.v11.permission import GROUP_ADMIN, GROUP_OWNER

#         permission = permission | GROUP_ADMIN | GROUP_OWNER

#     return permission


async def ensure_group(matcher: Matcher, session: Session = Depends(extract_session)):
    """确保在群组中使用"""
    if session.level not in [SessionLevel.LEVEL2, SessionLevel.LEVEL3]:
        await matcher.finish("请在群组中使用！")


async def persist_id2user_id(ids: List) -> List[str]:
    whereclause: List[ColumnElement[bool]] = []
    whereclause.append(or_(*[SessionModel.id == id for id in ids]))
    statement = (
        select(SessionModel).where(*whereclause)
        # .join(SessionModel, SessionModel.id == MessageRecord.session_persist_id)
    )
    async with get_session() as db_session:
        records = (await db_session.scalars(statement)).all()
    return [i.id1 for i in records]


async def user_id2persist_id(id: str) -> int:
    whereclause: List[ColumnElement[bool]] = []
    whereclause.append(or_(*[SessionModel.id2 == id]))
    statement = (
        select(SessionModel).where(*whereclause)
        # .join(SessionModel, SessionModel.id == MessageRecord.session_persist_id)
    )
    async with get_session() as db_session:
        records = (await db_session.scalars(statement)).all()
    return records[0].id


def msg_counter(msg_list: List[MessageRecord]) -> Dict[str, int]:
    """### 计算每个人的消息量

    Args:
        msg_list (list[MessageRecord]): 需要处理的消息列表

    Returns:
        (dict[str,int]): 处理后的消息数量字典,键为用户,值为消息数量
    """

    lst: Dict[str, int] = {}
    msg_len = len(msg_list)
    logger.info("wow , there are {} msgs to count !!!".format(msg_len))

    for i in msg_list:
        try:
            lst[str(i.session_persist_id)] += 1
        except KeyError:
            lst[str(i.session_persist_id)] = 1

    logger.debug(f"finish counting, result is {lst}")

    return lst


def got_rank(msg_dict: Dict[str, int]) -> List[List[Union[str, int]]]:
    """### 获得排行榜

    Args:
        msg_dict (Dict[str,int]): 要处理的字典

    Returns:
        List[Tuple[str,int]]: 排行榜列表(已排序)
    """
    rank = []
    while len(rank) < plugin_config.get_num:
        try:
            max_key = max(msg_dict.items(), key=lambda x: x[1])
            rank.append(list(max_key))
            msg_dict.pop(max_key[0])
        except ValueError:
            logger.error(
                "群内拥有聊天记录的人数不足，无法获取到长度为{}的排行榜,已将长度变化为：{}".format(
                    plugin_config.get_num, len(rank)
                )
            )
            break  

    return rank

# def remove_control_characters(string: str) -> str:
#     """### 将字符串中的控制符去除

#     Args:
#         string (str): 需要去除的字符串

#     Returns:
#         (str): 经过处理的字符串
#     """
#     return "".join(ch for ch in string if unicodedata.category(ch)[0] != "C")


#     async def render_template_pic(self) -> bytes:
#         if plugin_config.dialectlist_visualization_type == "圆环图":
#             view = pygal.Pie(inner_radius=0.6, style=style)
#         elif plugin_config.dialectlist_visualization_type == "饼图":
#             view = pygal.Pie(style=style)
#         else:
#             view = pygal.Bar(style=style)

#         view.title = "消息可视化"
#         for i, j in zip(self.rank, await self.get_nickname_list()):  # type: ignore
#             view.add(str(j), int(i[1]))

#         png: bytes = view.render_to_png()  # type: ignore
#         self.img = png
#         return png