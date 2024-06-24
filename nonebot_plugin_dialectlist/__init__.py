from nonebot import require

require("nonebot_plugin_chatrecorder")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_userinfo")
require("nonebot_plugin_alconna")
require("nonebot_plugin_cesaa")

import re
import nonebot_plugin_saa as saa

from pyecharts.charts import Bar
from pyecharts import options as opts
from pyecharts.globals import ThemeType

from typing import Union, Optional, List
from datetime import datetime, timedelta
from arclet.alconna import ArparmaBehavior
from arclet.alconna.arparma import Arparma

from nonebot.log import logger
from nonebot.params import Arg, Depends
from nonebot.typing import T_State
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
)

from nonebot_plugin_chatrecorder import get_message_records
from nonebot_plugin_localstore import get_cache_file
from nonebot_plugin_htmlrender import html_to_pic
from nonebot_plugin_userinfo import get_user_info
from nonebot_plugin_session import Session, SessionIdType, extract_session

# from . import migrations #抄词云的部分代码，还不知道这有什么用
# from .function import *
from .config import Config, plugin_config
from .usage import __usage__
from .utils import (
    get_datetime_fromisoformat_with_timezone,
    get_datetime_now_with_timezone,
    got_rank,
    msg_counter,
    persist_id2user_id,
    parse_datetime
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

def wrapper(slot: Union[int, str], content: Optional[str]) -> str:
    if slot == "type" and content:
        return content
    return ""  # pragma: no cover

rank_cmd = on_alconna(
    Alconna(
        "B话榜",
        Args["type?", ["今日", "昨日", "本周", "上周", "本月", "上月", "年度", "历史"]][
            "time?", str,
            "group_id?", int
        ],
        behaviors=[SameTime()],
    ),
    aliases={"废话榜"},
    use_cmd_start=True,
)


rank_cmd.shortcut(
    r"(?P<type>今日|昨日|本周|上周|本月|上月|年度|历史)B话榜",
    {
        "prefix": True,
        "command": "B话榜 ",
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
    group_id: Optional[int] = None,
):

    dt = get_datetime_now_with_timezone()

    if not group_id:
        state["group_id"] = session.id2

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

    bar = Bar(init_opts=opts.InitOpts(theme=ThemeType.LIGHT))
    bar.add_xaxis(nicknames)
    bar.add_yaxis("B话数量", [i[1] for i in rank]) # type: ignore
    bar.render(str(get_cache_file("nonebot_plugin_dialectlist","cache.html")))
    with open(get_cache_file("nonebot_plugin_dialectlist","cache.html")) as f:
        a = f.read()
    image = await html_to_pic(a,device_scale_factor=3.2)

    await (saa.Text(string)+saa.Image(image)).finish(reply=True)
