import re
import time
from typing import Dict, List, Tuple, Union
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
from nonebot.adapters.onebot.v11 import GroupMessageEvent,Message
from nonebot.adapters.onebot.v11.exception import ActionFailed



require("nonebot_plugin_datastore")
require("nonebot_plugin_chatrecorder")
from .record4dialectlist import get_message_records
from .config import plugin_config

async def msg_got_counter(
    gid:int,
    bot:Bot,
    start_time=None,
    stop_time=None,
    got_num:int=10
)->Message:
    '''
        计算出结果并返回可以直接发送的字符串
    '''
    st = time.time()
    gids:List[str] = [str(gid)]
    bot_id = await bot.call_api('get_login_info')
    bot_id = [str(bot_id['user_id'])]
    
    logger.debug('loading msg form group {}'.format(gid))
    
    gnl = await bot.call_api('get_group_member_list',group_id=int(gid))

    logger.debug('group {} have number {}'.format(gid,len(gnl)))

    msg = await get_message_records(
        group_ids=gids,
        exclude_user_ids=bot_id,
        message_type='group',
        time_start=start_time,
        time_stop=stop_time
    )

    lst:Dict[str,int] = {}
    for i in msg:
        try:
            lst[i.user_id] +=1
        except KeyError:
            lst[i.user_id] =1

    logger.debug(lst)
    logger.debug('group number num is '+str(len(lst)))

    ranking = []
    while len(ranking) < got_num:
        try:
            maxkey = max(lst, key=lst.get)  # type: ignore
        except ValueError:
            ranking.append(None)
            continue

        logger.debug('searching number {} form group {}'.format(str(maxkey),str(gid)))
        try:
            
            t = await bot.call_api(
                "get_group_member_info",
                group_id=int(gid),
                user_id=int(maxkey),
                no_cache=True
            )
            
            nickname:str = t['nickname']if not t['card'] else t['card']
            ranking.append([nickname.strip(),lst.pop(maxkey)])
            
        except ActionFailed as e:
            
            logger.warning(e)
            logger.warning('number {} not exit in group {}'.format(str(maxkey),str(gid)))
            lst.pop(maxkey)

    logger.debug('loaded list:\n{}'.format(ranking))
    
    
    out:str = ''
    for i in range(got_num):
        str_example = '第{}名：\n{}条消息\n'.format(i+1,str(ranking[i])[1:-1])
        out = out + str_example
    out = out + '\n\n你们的职业是水群吗？————MYX\n计算花费时间:{}秒'.format(time.time()-st)
    
    return Message(out)


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
async def _a(event:GroupMessageEvent,state: T_State,commands: Tuple[str, ...] = Command(),args: Message = CommandArg()):
    
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
    event: GroupMessageEvent,
    start: datetime = Arg(),
    stop: datetime = Arg()
):

    # 将时间转换到 UTC 时区
    msg = await msg_got_counter(
        gid=event.group_id,
        bot=bot,
        start_time=start.astimezone(ZoneInfo("UTC")),
        stop_time=stop.astimezone(ZoneInfo("UTC"))
        )
    await rankings.finish(msg)



