from nonebot import require

require("nonebot_plugin_chatrecorder")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_userinfo")
require("nonebot_plugin_alconna")
require("nonebot_plugin_cesaa")

import re
import os
import cn2an
import time as t
import nonebot_plugin_saa as saa

from typing import Union, Optional, List
from datetime import datetime, timedelta
from arclet.alconna import ArparmaBehavior
from arclet.alconna.arparma import Arparma

from nonebot.log import logger
from nonebot.typing import T_State
from nonebot.compat import model_dump
from nonebot.params import Arg, Depends
from nonebot.adapters import Bot, Event
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot_plugin_alconna import (
    Args,
    Option,
    Alconna,
    on_alconna,
)

from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_userinfo import get_user_info
from nonebot_plugin_chatrecorder import get_message_records
from nonebot_plugin_session import Session, SessionIdType, extract_session

# from . import migrations #抄词云的部分代码，还不知道这有什么用
# from .function import *
from .config import Config, plugin_config
from .usage import __usage__
from .time import (
    get_datetime_fromisoformat_with_timezone,
    get_datetime_now_with_timezone,
    parse_datetime,
)
from .model import UserRankInfo
from .utils import (
    got_rank,
    msg_counter,
    get_rank_image,
    persist_id2user_id,
    # get_user_info2,
)

__plugin_meta__ = PluginMetadata(
    name="B话排行榜",
    description="调查群U的B话数量，以一定的顺序排序后排序出来。",
    usage=__usage__,
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


def wrapper(slot: Union[int, str], content: Optional[str], context) -> str:
    if slot == "type" and content:
        return content
    return ""  # pragma: no cover


rank_cmd = on_alconna(
    Alconna(
        "B话榜",
        Args["type?", ["今日", "昨日", "本周", "上周", "本月", "上月", "年度", "历史"]][
            "time?",
            str,
        ],
        Option("-g|--group_id", Args["group_id?", str]),
        behaviors=[SameTime()],
    ),
    aliases={"废话榜"},
    use_cmd_start=True,
    block=True,
)


rank_cmd.shortcut(
    r"(?P<type>今日|昨日|本周|上周|本月|上月|年度|历史)B话榜",
    {
        "prefix": True,
        "command": "B话榜",
        "wrapper": wrapper,
        "args": ["{type}"],
    },
)
rank_cmd.shortcut(
    r"(?P<type>今日|昨日|本周|上周|本月|上月|年度|历史)废话榜",
    {
        "prefix": True,
        "command": "废话榜",
        "wrapper": wrapper,
        "args": ["{type}"],
    },
)


# 这段函数完全抄的词云
@rank_cmd.handle()
async def _group_message(
    state: T_State,
    session: Session = Depends(extract_session),
    type: Optional[str] = None,
    time: Optional[str] = None,
    group_id: Optional[str] = None,
):
    t1 = t.time()
    state["t1"] = t1
    dt = get_datetime_now_with_timezone()

    if not group_id:
        group_id = session.id2
        logger.debug(f"session id2: {group_id}")
    if group_id:
        state["group_id"] = group_id

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
                    
    logger.debug(f"命令解析花费时间:{t.time() - t1}")


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
@rank_cmd.got("group_id", prompt="请输入你要查询的群号。")
async def handle_rank(
    state: T_State,
    bot: Bot,
    event: Event,
    session: Session = Depends(extract_session),
    start: datetime = Arg(),
    stop: datetime = Arg(),
):
    t1 = t.time()
    if id := state["group_id"]:
        id = str(id)
        logger.debug(f"group_id: {id}")
    else:
        id = session.id2
        logger.debug(f"group_id: {id}")

    if not id:
        await saa.Text("没有指定群哦").finish()

    logger.debug(f"所属群聊解析花费时间:{t.time() - t1}")
    t1 = t.time()

    messages = await get_message_records(
        id2s=[id],
        id_type=SessionIdType.GROUP,
        include_bot_id=False,
        include_bot_type=False,
        types=["message"],  # 排除机器人自己发的消息
        time_start=start,
        time_stop=stop,
        exclude_id1s=plugin_config.excluded_people,
    )
    
    logger.debug(f"获取群聊消息花费时间:{t.time() - t1}")
    t1 = t.time()
    
    if not messages:
        await saa.Text("明明这个时间段都没有人说话怎么会有话痨榜呢？").finish()

    rank = got_rank(msg_counter(messages))
    logger.debug(f"群聊消息计数花费时间:{t.time() - t1}")
    t1 = t.time()
    logger.debug(rank)
    rank2: List[UserRankInfo] = []
    ids = await persist_id2user_id([int(i[0]) for i in rank])
    for i in range(len(rank)):
        rank[i][0] = str(ids[i])
        logger.debug(rank[i])

    total = sum([i[1] for i in rank])
    index = 1
    for i in rank:
        if user_info := await get_user_info(bot, event, user_id=str(i[0])):
            logger.debug(user_info)
            user_nickname = (
                user_info.user_displayname
                if user_info.user_displayname
                else user_info.user_name if user_info.user_name else user_info.user_id
            )
            user_avatar = (
                await user_info.user_avatar.get_image()
                if user_info.user_avatar
                else open(
                    os.path.dirname(os.path.abspath(__file__))
                    + "/template/avatar/default.jpg",
                    "rb",
                ).read()
            )
            user = UserRankInfo(
                **model_dump(user_info),
                user_bnum=i[1],
                user_proportion=round(i[1] / total * 100, 2),
                user_index=cn2an.an2cn(index),
                user_nickname=user_nickname,
                user_avatar_bytes=user_avatar,
            )
            user.user_gender = (
                "她"
                if user_info.user_gender == "female"
                else "他" if user_info.user_gender == "male" else "ta"
            )
            rank2.append(user)
            index += 1

    string: str = ""
    for i in rank2:
        logger.debug(i.user_name)
    for i in range(len(rank2)):
        str_example = plugin_config.string_format.format(
            index=rank2[i].user_index,
            nickname=rank2[i].user_nickname,
            chatdatanum=rank2[i].user_bnum,
        )
        string += str_example

    msg = saa.Text(string)
    logger.debug(f"群聊消息渲染文字花费时间:{t.time() - t1}")
    t1 = t.time()

    if plugin_config.visualization:
        image = await get_rank_image(rank2)
        msg += saa.Image(image)

    if plugin_config.suffix:
        timecost = t.time() - state["t1"]
        suffix = saa.Text(plugin_config.string_suffix.format(timecost=timecost))
        msg += suffix

    logger.debug(f"群聊消息渲染图片花费时间:{t.time() - t1}")

    await msg.finish(reply=True)


# @scheduler.scheduled_job(
#     "dialectlist", day="*/2", id="xxx", args=[1], kwargs={"arg2": 2}
# )
# async def __():
#     pass
