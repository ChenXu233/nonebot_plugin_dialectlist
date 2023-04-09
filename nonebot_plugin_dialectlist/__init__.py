import re
import time
from typing import Tuple, Union
from datetime import datetime, timedelta

from nonebot import on_command, require
from nonebot.log import logger
from nonebot.params import Command, CommandArg, Arg, Depends
from nonebot.typing import T_State
from nonebot.matcher import Matcher
from nonebot.adapters.onebot import V11Bot, V12Bot, V11Event, V12Event, V11Message, V12Message  # type: ignore

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

require("nonebot_plugin_chatrecorder")
from nonebot_plugin_chatrecorder import get_message_records

from .function import *
from .config import plugin_config


ranks = on_command(
    "群话痨排行榜",
    aliases={
        "今日群话痨排行榜",
        "昨日群话痨排行榜",
        "本周群话痨排行榜",
        "上周群话痨排行榜",
        "本月群话痨排行榜",
        "年度群话痨排行榜",
        "历史群话痨排行榜",
    },
    priority=6,
    block=True,
)


@ranks.handle()
async def _group_message(
    matcher: Matcher,
    event: Union[
        V11Event.GroupMessageEvent,
        V12Event.GroupMessageEvent,
        V12Event.ChannelMessageEvent,
    ],
    state: T_State,
    commands: Tuple[str, ...] = Command(),
    args: Union[V11Message, V11Message] = CommandArg(),
):
    if isinstance(event, V11Event.GroupMessageEvent):
        logger.debug("handle command from onebotV11 adapter(qq)")
    elif isinstance(event, V12Event.GroupMessageEvent):
        logger.debug("handle command from onebotV12 adapter")

    dt = get_datetime_now_with_timezone()
    command = commands[0]

    if command == "群话痨排行榜":
        state["start"] = dt.replace(
            year=2000, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        state["stop"] = dt
    elif command == "今日群话痨排行榜":
        state["start"] = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        state["stop"] = dt
    elif command == "昨日群话痨排行榜":
        state["stop"] = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        state["start"] = state["stop"] - timedelta(days=1)
    elif command == "前日群话痨排行榜":
        state["stop"] = dt.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=1)
        state["start"] = state["stop"] - timedelta(days=1)
    elif command == "本周群话痨排行榜":
        state["start"] = dt.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=dt.weekday())
        state["stop"] = dt
    elif command == "上周群话痨排行榜":
        state["start"] = dt.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=dt.weekday() + 7)
        state["stop"] = dt.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=dt.weekday())
    elif command == "本月群话痨排行榜":
        state["start"] = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        state["stop"] = dt
    elif command == "年度群话痨排行榜":
        state["start"] = dt.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        state["stop"] = dt
    elif command == "历史群话痨排行榜":
        plaintext = args.extract_plain_text().strip()
        match = re.match(r"^(.+?)(?:~(.+))?$", plaintext)
        if match:
            start = match.group(1)
            stop = match.group(2)
            try:
                state["start"] = get_datetime_fromisoformat_with_timezone(start)
                if stop:
                    state["stop"] = get_datetime_fromisoformat_with_timezone(stop)
                else:
                    # 如果没有指定结束日期，则认为是指查询这一天的数据
                    state["start"] = state["start"].replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    state["stop"] = state["start"] + timedelta(days=1)
            except ValueError:
                await matcher.finish("请输入正确的日期，不然我没法理解呢！")
    else:
        pass


@ranks.handle()
async def _private_message(
    matcher: Matcher,
    event: Union[V11Event.GroupMessageEvent, V12Event.GroupMessageEvent],
    state: T_State,
    commands: Tuple[str, ...] = Command(),
    args: Union[V11Message, V12Message] = CommandArg(),
):
    # TODO:支持私聊的查询
    await matcher.finish("暂不支持私聊查询，今后可能会添加这一项功能")


@ranks.got(
    "start",
    prompt="请输入你要查询的起始日期（如 2022-01-01）",
    parameterless=[Depends(parse_datetime("start"))],
)
@ranks.got(
    "stop",
    prompt="请输入你要查询的结束日期（如 2022-02-22）",
    parameterless=[Depends(parse_datetime("stop"))],
)
async def handle_message(
    matcher: Matcher,
    bot: Union[V11Bot, V12Bot],
    event: Union[
        V11Event.GroupMessageEvent,
        V12Event.GroupMessageEvent,
        V12Event.ChannelMessageEvent,
    ],
    stop: datetime = Arg(),
    start: datetime = Arg(),
):
    st = time.time()

    if plugin_config.dialectlist_excluded_self:
        bot_id = await bot.call_api("get_login_info")
        plugin_config.dialectlist_excluded_people.append(bot_id["user_id"])
    msg_list = await get_message_records(
        bot_ids=[str(bot.self_id)],
        platforms=[str(bot.platform)],
        group_ids=[str(event.group_id)]
        if isinstance(event, (V11Event.GroupMessageEvent, V12Event.GroupMessageEvent))
        else None,
        guild_ids=[str(event.guild_id)]
        if isinstance(event, V12Event.ChannelMessageEvent)
        else None,
        exclude_user_ids=plugin_config.dialectlist_excluded_people,
        time_start=start.astimezone(ZoneInfo("UTC")),
        time_stop=stop.astimezone(ZoneInfo("UTC")),
    )

    if isinstance(event, V11Event.GroupMessageEvent):
        processer = V11GroupMsgProcesser(bot=bot, gid=str(event.group_id), msg_list=msg_list)  # type: ignore
    elif isinstance(event, V12Event.GroupMessageEvent):
        processer = V12GroupMsgProcesser(bot=bot, gid=str(event.group_id), msg_list=msg_list)  # type: ignore
    elif isinstance(event, V12Event.ChannelMessageEvent):
        pass
    else:
        raise NotImplementedError("没支持呢(())")

    msg = await processer.get_send_msg()  # type: ignore
    await matcher.send(msg)
