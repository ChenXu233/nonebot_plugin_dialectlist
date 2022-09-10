import json
from typing import Dict

from nonebot.log import logger
from nonebot.message import event_postprocessor
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import Message
from nonebot.adapters.onebot.v11.exception import ActionFailed

from nonebot_plugin_guild_patch import GuildMessageEvent

from .config import plugin_config


def update_json(updatedata:Dict):

    with open(plugin_config.dialectlist_json_path, 'w', encoding='utf-8') as f:
        json.dump(updatedata, f, ensure_ascii=False, indent=4)
        
def get_json()-> Dict[str,Dict]:
    
    if not plugin_config.dialectlist_json_path.exists():
        return {}

    with open(plugin_config.dialectlist_json_path, 'r', encoding='utf-8') as f:
        data:Dict = json.load(f)
    return data


@event_postprocessor
async def _pocesser(event:GuildMessageEvent):
    
    data = get_json()
    try:
        data[str(event.guild_id)][str(event.sender.nickname)] += 1
    except KeyError:
        data[str(event.guild_id)] = {str(event.sender.nickname):1}
    update_json(data)


async def get_guild_message_records(    
    guild_id:str,
    bot:Bot,
    got_num:int=10,
)->Message:
    data = get_json()
    ranking = []
    while len(ranking) < got_num:
        
        try:
            maxkey = max(data[guild_id], key=data[guild_id].get)  # type: ignore
        except ValueError:
            ranking.append(("null",0))
            continue
        ranking.append((maxkey,data[guild_id].pop(maxkey)))

    logger.debug('loaded list:\n{}'.format(ranking))
    out:str = ''
    for i in range(got_num):
        index = i+1
        nickname,chatdatanum = ranking[i]
        str_example = plugin_config.dialectlist_string_format.format(index=index,nickname=nickname,chatdatanum=chatdatanum)
        out = out + str_example
    
    return Message(out)
