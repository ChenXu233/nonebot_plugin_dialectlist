import re
import time
import asyncio
from typing import Tuple, Union
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo   # type: ignore

from nonebot import on_command, require
from nonebot.log import logger
from nonebot.params import Command, CommandArg, Arg, Depends
from nonebot.typing import T_State
from nonebot.matcher import Matcher
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Message


require("nonebot_plugin_chatrecorder")
from nonebot_plugin_chatrecorder import get_message_records
require("nonebot_plugin_guild_patch")
from nonebot_plugin_guild_patch import GuildMessageEvent

from .function import msg_counter, msg_list2msg
from .config import plugin_config

def parse_datetime(key: str):
    """解析数字，并将结果存入 state 中"""

    async def _key_parser(
        matcher: Matcher,
        state: T_State,
        input: Union[datetime, Message] = Arg(key)
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
    """从 iso8601 格式字符串中获取时间，并包含时区信息"""
    if plugin_config.timezone:
        return datetime.fromisoformat(date_string).astimezone(
            ZoneInfo(plugin_config.timezone)
        )
    else:
        return datetime.fromisoformat(date_string).astimezone()




rankings = on_command(
    '群话痨排行榜',
    aliases={
            "今日群话痨排行榜",
            "昨日群话痨排行榜",
            "本周群话痨排行榜",
            "本月群话痨排行榜",
            "年度群话痨排行榜",
            "历史群话痨排行榜",
        },
    priority=6,
    block=True
)

@rankings.handle()
async def _group_message(
    event:Union[GroupMessageEvent, GuildMessageEvent],
    state: T_State,commands: Tuple[str, ...] = Command(),
    args: Message = CommandArg()
    ):
    
    if isinstance(event, GroupMessageEvent):
        logger.debug('handle command from qq')
    elif isinstance(event, GuildMessageEvent):
        logger.debug('handle command from qqguild')
    
    dt = get_datetime_now_with_timezone()
    command = commands[0]
        
    if command == "群话痨排行榜":
        state["start"] = dt.replace(year=2000, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        state["stop"] = dt
    elif command == "今日群话痨排行榜":
        state["start"] = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        state["stop"] = dt
    elif command == "昨日群话痨排行榜":
        state["stop"] = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        state["start"] = state["stop"] - timedelta(days=1)
    elif command == "前日群话痨排行榜":
        state["stop"] = dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        state["start"] = state["stop"] - timedelta(days=1)
    elif command == "本周群话痨排行榜":
        state["start"] = dt.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=dt.weekday())
        state["stop"] = dt
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
                await rankings.finish("请输入正确的日期，不然我没法理解呢！")
    else:
        pass
    
@rankings.handle()
async def _private_message(
    event:PrivateMessageEvent,
    state: T_State,commands: Tuple[str, ...] = Command(),
    args: Message = CommandArg()
    ):
    # TODO:支持私聊的查询
    await rankings.finish('暂不支持私聊查询，今后可能会添加这一项功能')

@rankings.got(
    "start",
    prompt="请输入你要查询的起始日期（如 2022-01-01）",
    parameterless=[Depends(parse_datetime("start"))]
)
@rankings.got(
    "stop",
    prompt="请输入你要查询的结束日期（如 2022-02-22）",
    parameterless=[Depends(parse_datetime("stop"))]
)
async def handle_message(
    bot: Bot,
    event: GroupMessageEvent, #Union[GroupMessageEvent,GuildMessageEvent],
    stop: datetime = Arg(),
    start: datetime = Arg()
):
    
    st = time.time()
    
    #if isinstance(event,GroupMessageEvent):
    if plugin_config.dialectlist_excluded_self:
        bot_id:dict = await bot.call_api('get_login_info')
        plugin_config.dialectlist_excluded_people.append(bot_id['user_id'])
    print(event.self_id)
    msg_list = await get_message_records(
        bot_ids=[str(bot.self_id)],
        platforms=[str('qq')],
        group_ids=[str(event.group_id)],
        exclude_user_ids=plugin_config.dialectlist_excluded_people,
        time_start=start.astimezone(ZoneInfo("UTC")),
        time_stop=stop.astimezone(ZoneInfo("UTC"))
    )
        
    # elif isinstance(event, GuildMessageEvent):
    #     if plugin_config.dialectlist_excluded_self:
    #         bot_id = await bot.call_api('get_guild_service_profile')
    #     guild_ids:List[str] = [str(event.guild_id)]
    #     msg_list = await get_message_records(
    #         bot_ids=[str(bot.self_id)],
    #         platforms=['qqguild'],
    #         guild_ids=guild_ids,
    #         exclude_user_ids=plugin_config.dialectlist_excluded_people,
    #         time_start=start.astimezone(ZoneInfo("UTC")),
    #         time_stop=stop.astimezone(ZoneInfo("UTC"))
    #     )

        
    msg_dict = await msg_counter(msg_list=msg_list)
    # if isinstance(event,GroupMessageEvent):
    msg = await msg_list2msg(msg_list=msg_dict,gid=event.group_id,platform='qq',bot=bot,got_num=plugin_config.dialectlist_get_num)
    # elif isinstance(event, GuildMessageEvent):
    #     msg = await msg_list2msg(msg_list=msg_dict,gid=event.guild_id,platform='guild',bot=bot,got_num=plugin_config.dialectlist_get_num)
        
    await rankings.send(msg)
    await asyncio.sleep(1) #让图片先发出来
    if plugin_config.dialectlist_string_suffix_format:
        await rankings.finish(plugin_config.dialectlist_string_suffix_format.format(timecost=time.time()-st-1))
    
