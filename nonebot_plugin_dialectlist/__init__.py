from nonebot import require

require("nonebot_plugin_chatrecorder")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_userinfo")
require("nonebot_plugin_alconna")
require("nonebot_plugin_cesaa")

import re
import os
import time

import nonebot_plugin_saa as saa

from typing import Tuple, Union, Optional, List
from datetime import datetime, timedelta
from arclet.alconna import ArparmaBehavior
from arclet.alconna.arparma import Arparma

from nonebot import on_command, get_driver
from nonebot.log import logger
from nonebot.params import Command, CommandArg, Arg, Depends
from nonebot.typing import T_State
from nonebot.matcher import Matcher
from nonebot import get_driver
from nonebot.adapters import Bot, Event, Message
from nonebot.params import Arg, Depends
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot.typing import T_State
from nonebot_plugin_alconna import (
    Alconna,
    AlconnaMatch,
    AlconnaMatcher,
    AlconnaQuery,
    Args,
    Match,
    Option,
    Query,
    image_fetch,
    on_alconna,
    store_true,
)

from nonebot_plugin_chatrecorder import get_message_records
from nonebot_plugin_userinfo import EventUserInfo, UserInfo, get_user_info
from nonebot_plugin_session import Session, SessionIdType, extract_session
from nonebot_plugin_cesaa import get_messages_plain_text


# from . import migrations #抄词云的部分代码，还不知道这有什么用
# from .function import *
from .config import Config, plugin_config
from .utils import (
    get_datetime_fromisoformat_with_timezone,
    get_datetime_now_with_timezone,
    got_rank,
    msg_counter,
    persist_id2user_id,
)

with open(os.path.dirname(__file__) + "/usage.md") as f:
    usage = f.read()

__plugin_meta__ = PluginMetadata(
    name="B话排行榜",
    description="调查群U的B话数量，以一定的顺序排序后排序出来。",
    usage=usage,
    homepage="https://github.com/ChenXu233/nonebot_plugin_dialectlist",
    type="application",
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_chatrecorder", "nonebot_plugin_saa", "nonebot_plugin_alconna"
    ),
    config=Config,
    # extra={"orm_version_location": migrations},
)


# 抄的词云，不过真的很适合B话榜。
class SameTime(ArparmaBehavior):
    def operate(self, interface: Arparma):
        type = interface.query("type")
        time = interface.query("time")
        if type is None and time:
            interface.behave_fail()


rank_cmd = on_alconna(
    Alconna(
        "B话榜",
        Args["type?", ["今日", "昨日", "本周", "上周", "本月", "上月", "年度", "历史"]][
            "time?", str
        ],
        behaviors=[SameTime()],
    ),
    use_cmd_start=True,
)


def wrapper(slot: Union[int, str], content: Optional[str]) -> str:
    if slot == "type" and content:
        return content
    return ""  # pragma: no cover


rank_cmd.shortcut(
    r"(?P<type>今日|昨日|本周|上周|本月|上月|年度|历史)B话榜",
    {
        "prefix": True,
        "command": "B话榜 ",
        "wrapper": wrapper,
        "args": ["{type}"],
    },
)


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


# TODO 处理函数更新
# 参考词云


# 这段函数完全抄的词云
@rank_cmd.handle()
async def _group_message(
    state: T_State,
    type: Optional[str] = None,
    time: Optional[str] = None,
):

    dt = get_datetime_now_with_timezone()

    if not type:
        await rank_cmd.finish(__plugin_meta__.usage)

    dt = get_datetime_now_with_timezone()

    if type == "今日":
        state["start"] = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        state["stop"] = dt
    elif type == "昨日":
        state["stop"] = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        state["start"] = state["stop"] - timedelta(days=1)
    elif type == "本周":
        state["start"] = dt.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=dt.weekday())
        state["stop"] = dt
    elif type == "上周":
        state["stop"] = dt.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=dt.weekday())
        state["start"] = state["stop"] - timedelta(days=7)
    elif type == "本月":
        state["start"] = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        state["stop"] = dt
    elif type == "上月":
        state["stop"] = dt.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(microseconds=1)
        state["start"] = state["stop"].replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
    elif type == "年度":
        state["start"] = dt.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        state["stop"] = dt
    elif type == "历史":
        if time:
            plaintext = time
            if match := re.match(r"^(.+?)(?:~(.+))?$", plaintext):
                start = match[1]
                stop = match[2]
                try:
                    state["start"] = get_datetime_fromisoformat_with_timezone(start)
                    if stop:
                        state["stop"] = get_datetime_fromisoformat_with_timezone(stop)
                    else:
                        # 如果没有指定结束日期，则认为是所给日期的当天的词云
                        state["start"] = state["start"].replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                        state["stop"] = state["start"] + timedelta(days=1)
                except ValueError:
                    await rank_cmd.finish("请输入正确的日期，不然我没法理解呢！")


@rank_cmd.got(
    "start",
    prompt="请输入你要查询的起始日期（如 2022-01-01）",
    parameterless=[Depends(parse_datetime("start"))],
)
@rank_cmd.got(
    "stop",
    prompt="请输入你要查询的结束日期（如 2022-02-22）",
    parameterless=[Depends(parse_datetime("stop"))],
)
async def handle_rank(
    bot: Bot,
    event: Event,
    session: Session = Depends(extract_session),
    start: datetime = Arg(),
    stop: datetime = Arg(),
):
    """生成词云"""
    messages = await get_message_records(
        session=session,
        id_type=SessionIdType.GROUP,
        include_bot_id=False,
        include_bot_type=False,
        types=["message"],  # 排除机器人自己发的消息
        time_start=start,
        time_stop=stop,
        exclude_id1s=plugin_config.excluded_people,
    )

    rank = got_rank(msg_counter(messages))
    ids = await persist_id2user_id([int(i[0]) for i in rank])
    for i in range(len(rank)):
        rank[i][0] = str(ids[i])

    string: str = ""
    nicknames: List = []
    for i in rank:
        if user_info := await get_user_info(bot, event, user_id=str(i[0])):
            (
                nicknames.append(user_info.user_displayname)
                if user_info.user_displayname
                else (
                    nicknames.append(user_info.user_name)
                    if user_info.user_name
                    else nicknames.append(user_info.user_id)
                )
            )
        else:
            nicknames.append(None)
    logger.debug(nicknames)
    for i in range(len(rank)):
        index = i + 1
        nickname, chatdatanum = nicknames[i], rank[i][1]
        str_example = plugin_config.string_format.format(
            index=index, nickname=nickname, chatdatanum=chatdatanum
        )
        string += str_example

    await saa.Text(string).finish(reply=True)
