import pygal
import unicodedata

from typing_extensions import Literal
from typing import List, Optional, Dict
from pygal.style import Style

from nonebot.log import logger
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import Message,MessageSegment
from nonebot.exception import ActionFailed

from nonebot_plugin_chatrecorder.model import MessageRecord

from .config import plugin_config
style=Style(font_family=plugin_config.dialectlist_font)


def remove_control_characters(string:str) -> str:
    """将字符串中的控制符去除

    Args:
        string (str): 需要去除的字符串

    Returns:
        (str): 经过处理的字符串
    """
    return "".join(ch for ch in string if unicodedata.category(ch)[0]!="C")


async def msg_counter(msg_list:List[MessageRecord])->Dict[str,int]:
    '''
        计算出话最多的几个人的id并返回
    '''

    lst:Dict[str,int] = {}
    msg_len = len(msg_list)
    logger.info('wow , there are {} msgs to count !!!'.format(msg_len))
    
    for i in msg_list:
        try:
            lst[i.user_id] += 1
        except KeyError:
            lst[i.user_id] = 1

    logger.debug(lst)
    
    return lst

async def msg_list2msg(
    msg_list:Dict[str,int],
    gid:int,
    got_num:int,
    platform:Optional[Literal['guild', 'qq']],
    bot:Bot
)->Message:
    
    ranking = []
    while len(ranking) < got_num:
        
        try:
            maxkey = max(msg_list, key=msg_list.get)  # type: ignore
        except ValueError:
            ranking.append(["null",0])
            continue

        logger.debug('searching member {} from group {}'.format(str(maxkey),str(gid)))
    
        try:
            if platform == 'qq':
                member_info = await bot.call_api(
                    "get_group_member_info",
                    group_id=int(gid),
                    user_id=int(maxkey),
                    no_cache=True
                )
                nickname:str = member_info['nickname']if not member_info['card'] else member_info['card']
            else:
                member_info = await bot.call_api(
                    "get_guild_member_profile",
                    guild_id=str(gid),
                    user_id=str(maxkey)
                )
                nickname:str = member_info['nickname']
            ranking.append([remove_control_characters(nickname).strip(),msg_list.pop(maxkey)])
        except ActionFailed as e:
            logger.warning(e)
            logger.warning('member {} is not exit in group {}'.format(str(maxkey),str(gid)))
            msg_list.pop(maxkey)


    logger.debug('loaded list:\n{}'.format(ranking))
    
    if plugin_config.dialectlist_visualization:
        if plugin_config.dialectlist_visualization_type == '圆环图':
            view = pygal.Pie(inner_radius=0.6,style=style)
        elif plugin_config.dialectlist_visualization_type == '饼图':
            view = pygal.Pie(style=style)
        else:
            view = pygal.Bar(style=style)
            
        view.title = '消息可视化'
        for i in ranking:
            view.add(str(i[0]),int(i[1]))
        try:
            png: bytes = view.render_to_png()   # type: ignore
            process_msg =  Message(MessageSegment.image(png))
        except OSError:
            logger.error('GTK+(GIMP Toolkit) is not installed, the svg can not be transformed to png')
            plugin_config.dialectlist_visualization = False
            process_msg =  Message('无法发送可视化图片，请检查是否安装GTK+，详细安装教程可见github\nhttps://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer \n若不想安装这个软件，再次使用这个指令不会显示这个提示')
    else:
        process_msg = ''
        
    out:str = ''
    for i in range(got_num):
        index = i+1
        nickname,chatdatanum = ranking[i]
        str_example = plugin_config.dialectlist_string_format.format(index=index,nickname=nickname,chatdatanum=chatdatanum)
        out = out + str_example
        
    logger.debug(out)
    
    return Message(out)+process_msg
