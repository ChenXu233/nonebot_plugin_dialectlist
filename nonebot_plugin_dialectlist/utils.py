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
            break

    return rank


# import abc
# import pygal
# import unicodedata
# import requests
# from datetime import datetime

# from typing import List, Dict, Union
# from pygal.style import Style

# from nonebot import require
# from nonebot.log import logger
# from nonebot.params import Arg
# from nonebot.typing import T_State
# from nonebot.matcher import Matcher
# from nonebot.adapters import Bot, Message
# from nonebot.adapters.onebot import V11Bot, V12Bot, V11Message, V12Message, V11MessageSegment, V12MessageSegment  # type: ignore
# from nonebot.exception import ActionFailed

# try:
#     from zoneinfo import ZoneInfo
# except ImportError:
#     from backports.zoneinfo import ZoneInfo  # type: ignore

# require("nonebot_plugin_chatrecorder")
# from nonebot_plugin_chatrecorder import get_message_records
# from nonebot_plugin_chatrecorder.model import MessageRecord

# from .config import plugin_config

# style = Style(font_family=plugin_config.dialectlist_font)


# def remove_control_characters(string: str) -> str:
#     """### 将字符串中的控制符去除

#     Args:
#         string (str): 需要去除的字符串

#     Returns:
#         (str): 经过处理的字符串
#     """
#     return "".join(ch for ch in string if unicodedata.category(ch)[0] != "C")


# def parse_datetime(key: str):
#     """解析数字，并将结果存入 state 中"""

#     async def _key_parser(
#         matcher: Matcher,
#         state: T_State,
#         input: Union[datetime, Union[V11Message, V12Message]] = Arg(key),
#     ):
#         if isinstance(input, datetime):
#             return

#         plaintext = input.extract_plain_text()
#         try:
#             state[key] = get_datetime_fromisoformat_with_timezone(plaintext)
#         except ValueError:
#             await matcher.reject_arg(key, "请输入正确的日期，不然我没法理解呢！")

#     return _key_parser


# def get_datetime_now_with_timezone() -> datetime:
#     """获取当前时间，并包含时区信息"""
#     if plugin_config.timezone:
#         return datetime.now(ZoneInfo(plugin_config.timezone))
#     else:
#         return datetime.now().astimezone()


# def get_datetime_fromisoformat_with_timezone(date_string: str) -> datetime:
#     """从 iso8601 格式字符串中获取时间，并包含时区信息"""
#     if plugin_config.timezone:
#         return datetime.fromisoformat(date_string).astimezone(
#             ZoneInfo(plugin_config.timezone)
#         )
#     else:
#         return datetime.fromisoformat(date_string).astimezone()


# def msg_counter(msg_list: List[MessageRecord]) -> Dict[str, int]:
#     """### 计算每个人的消息量

#     Args:
#         msg_list (list[MessageRecord]): 需要处理的消息列表

#     Returns:
#         (dict[str,int]): 处理后的消息数量字典,键为用户,值为消息数量
#     """

#     lst: Dict[str, int] = {}
#     msg_len = len(msg_list)
#     logger.info("wow , there are {} msgs to count !!!".format(msg_len))

#     for i in msg_list:
#         try:
#             lst[i.user_id] += 1
#         except KeyError:
#             lst[i.user_id] = 1

#     logger.debug(lst)

#     return lst


# def got_rank(msg_dict: Dict[str, int]) -> List[List[Union[str, int]]]:
#     """### 获得排行榜

#     Args:
#         msg_dict (Dict[str,int]): 要处理的字典

#     Returns:
#         List[Tuple[str,int]]: 排行榜列表(已排序)
#     """
#     rank = []
#     while len(rank) < plugin_config.dialectlist_get_num:
#         try:
#             max_key = max(msg_dict.items(), key=lambda x: x[1])
#             rank.append(list(max_key))
#             msg_dict.pop(max_key[0])
#         except ValueError:
#             rank.append(["null", 0])
#             continue

#     return rank


# class MsgProcesser(abc.ABC):
#     def __init__(self, bot: Bot, gid: str, msg_list: List[MessageRecord]) -> None:
#         if isinstance(bot, Bot):
#             self.bot = bot
#         else:
#             self.bot = None
#         self.gid = gid
#         self.rank = got_rank(msg_counter(msg_list))

#     @abc.abstractmethod
#     async def get_nickname_list(self) -> List:
#         """
#         ### 获得昵称
#         #### 抽象原因
#         要对onebot协议不同版本进行适配
#         """
#         raise NotImplementedError

#     @abc.abstractmethod
#     def get_head_portrait_urls(self) -> List:
#         raise NotImplementedError

#     @abc.abstractmethod
#     async def get_send_msg(self) -> Message:
#         raise NotImplementedError

#     async def get_msg(self) -> List[Union[str, bytes, None]]:
#         str_msg = await self.render_template_msg()
#         pic_msg = None
#         if plugin_config.dialectlist_visualization:
#             try:
#                 pic_msg = await self.render_template_pic()
#             except OSError:
#                 plugin_config.dialectlist_visualization = False
#                 str_msg += "\n\n无法发送可视化图片，请检查是否安装GTK+，详细安装教程可见github\nhttps://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer \n若不想安装这个软件，再次使用这个指令不会显示这个提示"
#         return [str_msg, pic_msg]

#     async def render_template_msg(self) -> str:
#         """渲染文字"""
#         string: str = ""
#         rank: List = self.rank
#         nicknames: List = await self.get_nickname_list()
#         for i in range(len(rank)):
#             index = i + 1
#             nickname, chatdatanum = nicknames[i], rank[i][1]
#             str_example = plugin_config.dialectlist_string_format.format(
#                 index=index, nickname=nickname, chatdatanum=chatdatanum
#             )
#             string += str_example

#         return string

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


# class V11GroupMsgProcesser(MsgProcesser):
#     def __init__(self, bot: V11Bot, gid: str, msg_list: List[MessageRecord]) -> None:
#         super().__init__(bot, gid, msg_list)
#         self.bot = bot

#     async def get_nickname_list(self) -> List:
#         nicknames = []
#         for i in range(len(self.rank)):
#             try:
#                 member_info = await self.bot.get_group_member_info(
#                     group_id=int(self.gid), user_id=int(self.rank[i][0]), no_cache=True
#                 )
#                 nickname=(
#                     member_info["nickname"]
#                     if not member_info["card"]
#                     else member_info["card"]
#                 )
#                 nicknames.append(remove_control_characters(nickname))
#             except (ActionFailed,ValueError) as e:
#                 nicknames.append("{}这家伙不在群里了".format(self.rank[i][0]))

#         return nicknames

#     def get_head_portrait_urls(self) -> List:
#         self.portrait_urls = [
#             "http://q2.qlogo.cn/headimg_dl?dst_uin={}&spec=640".format(i[0])
#             for i in self.rank
#         ]
#         return self.portrait_urls

#     async def get_send_msg(self) -> V11Message:
#         msgs: List = await self.get_msg()
#         msg = V11Message()
#         msg += V11MessageSegment.text(msgs[0])  # type: ignore
#         msg += V11MessageSegment.image(msgs[1])  # type: ignore
#         return msg


# class V12MsgProcesser(MsgProcesser):
#     def __init__(self, bot: V12Bot, gid: str, msg_list: List[MessageRecord]) -> None:
#         super().__init__(bot, gid, msg_list)
#         self.bot = bot

#     async def get_send_msg(self) -> V12Message:
#         msgs: List = await self.get_msg()
#         msg = V12Message()
#         msg += V12MessageSegment.text(msgs[0])  # type: ignore
#         msg += V12MessageSegment.image(msgs[1])  # type: ignore
#         return msg

#     def get_head_portrait_urls(self) -> List:
#         return super().get_head_portrait_urls()


# class V12GroupMsgProcesser(V12MsgProcesser):
#     def __init__(self, bot: V12Bot, gid: str, msg_list: List[MessageRecord]) -> None:
#         super().__init__(bot, gid, msg_list)

#     async def get_nickname_list(self) -> List:
#         nicknames = []
#         for i in range(len(self.rank)):
#             try:
#                 member_info = await self.bot.get_group_member_info(
#                     group_id=str(self.gid), user_id=str(self.rank[i][0]), no_cache=True
#                 )
#                 nickname=(
#                     member_info["user_displayname"]
#                     if member_info["user_displayname"]
#                     else member_info["user_name"]
#                 )
#                 nicknames.append(remove_control_characters(nickname))
#             except ActionFailed as e:
#                 nicknames.append("{}这家伙不在群里了".format(self.rank[i][0]))
#         return nicknames


# class V12GuildMsgProcesser(V12MsgProcesser):
#     def __init__(self, bot: V12Bot, gid: str, msg_list: List[MessageRecord]) -> None:
#         super().__init__(bot, gid, msg_list)

#     async def get_nickname_list(self) -> List:
#         nicknames = []
#         for i in range(len(self.rank)):
#             try:
#                 member_info = await self.bot.get_guild_member_info(
#                     guild_id=str(self.gid), user_id=str(self.rank[i][0]), no_cache=True
#                 )
#                 nickname=(
#                     member_info["user_displayname"]
#                     if member_info["user_displayname"]
#                     else member_info["user_name"]
#                 )
#                 nicknames.append(remove_control_characters(nickname))
#             except ActionFailed as e:
#                 nicknames.append("{}这家伙不在群里了".format(self.rank[i][0]))
#         return nicknames
