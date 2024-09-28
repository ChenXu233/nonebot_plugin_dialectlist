import os
import httpx
import asyncio
import unicodedata

from typing import Dict, List
from sqlalchemy import or_, select
from sqlalchemy.sql import ColumnElement

from nonebot.log import logger
from nonebot.params import Depends
from nonebot.compat import model_dump
from nonebot.matcher import Matcher
from nonebot.adapters import Bot, Event

from nonebot_plugin_orm import get_session
from nonebot_plugin_session import Session, SessionLevel, extract_session
from nonebot_plugin_userinfo import get_user_info, UserInfo
from nonebot_plugin_userinfo.exception import NetworkError
from nonebot_plugin_localstore import get_cache_dir
from nonebot_plugin_htmlrender import template_to_pic
from nonebot_plugin_session_orm import SessionModel
from nonebot_plugin_chatrecorder import MessageRecord


from .model import UserRankInfo
from .config import plugin_config

cache_path = get_cache_dir("nonebot_plugin_dialectlist")


async def ensure_group(matcher: Matcher, session: Session = Depends(extract_session)):
    """确保在群组中使用"""
    if session.level not in [SessionLevel.LEVEL2, SessionLevel.LEVEL3]:
        await matcher.finish("请在群组中使用！")


async def persist_id2user_id(ids: List) -> List[str]:
    user_ids = []
    async with get_session() as db_session:
        for i in ids:
            user_id = (await db_session.scalar(select(SessionModel).where(or_(*[SessionModel.id == i])))).id1  # type: ignore
            user_ids.append(user_id)
    return user_ids


async def user_id2persist_id(ids: List[str]) -> List[int]:
    whereclause: List[ColumnElement[bool]] = []
    whereclause.append(or_(*[SessionModel.id1 == id for id in ids]))
    statement = (
        select(SessionModel).where(*whereclause)
        # .join(SessionModel, SessionModel.id == MessageRecord.session_persist_id)
    )
    async with get_session() as db_session:
        records = (await db_session.scalars(statement)).all()
    return [i.id for i in records]


async def group_id2persist_id(ids: List[str]) -> List[int]:
    persist_ids = []
    async with get_session() as db_session:
        for i in ids:
            persist_id = (await db_session.scalar(select(SessionModel).where(or_(*[SessionModel.id2 == i])))).id  # type: ignore
            persist_ids.append(persist_id)
    return persist_ids


async def persist_id2group_id(ids: List[str]) -> List[str]:
    whereclause: List[ColumnElement[bool]] = []
    whereclause.append(or_(*[SessionModel.id == id for id in ids]))
    statement = (
        select(SessionModel).where(*whereclause)
        # .join(SessionModel, SessionModel.id == MessageRecord.session_persist_id)
    )
    async with get_session() as db_session:
        records = (await db_session.scalars(statement)).all()
    return [i.id2 for i in records]


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


def got_rank(msg_dict: Dict[str, int]) -> List:
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


def remove_control_characters(string: str) -> str:
    """### 将字符串中的控制符去除

    Args:
        string (str): 需要去除的字符串

    Returns:
        (str): 经过处理的字符串
    """
    return "".join(ch for ch in string if unicodedata.category(ch)[0] != "C")


async def get_rank_image(rank: List[UserRankInfo]) -> bytes:
    for i in rank:
        if i.user_avatar:
            try:
                user_avatar = i.user_avatar_bytes
            except NotImplementedError:
                user_avatar = open(
                    os.path.dirname(os.path.abspath(__file__))
                    + "/template/avatar/default.jpg",
                    "rb",
                ).read()
            # if not os.path.exists(cache_path / str(i.user_id)):
            with open(cache_path / (str(i.user_id) + ".jpg"), "wb") as f:
                f.write(user_avatar)

    if plugin_config.template_path[:2] == "./":
        path = (
            os.path.dirname(os.path.abspath(__file__)) + plugin_config.template_path[1:]
        )
    else:
        path = plugin_config.template_path

    path_dir, filename = os.path.split(path)
    logger.debug(
        os.path.dirname(os.path.abspath(__file__)) + plugin_config.template_path[1:]
    )
    return await template_to_pic(
        path_dir,
        filename,
        {
            "users": rank,
            "cache_path": cache_path,
            "file_path": os.path.dirname(os.path.abspath(__file__)),
        },
        pages={"viewport": {"width": 1000, "height": 10}},
    )


def _get_user_nickname(user_info: UserInfo) -> str:
    user_nickname = (
        user_info.user_displayname
        if user_info.user_displayname
        else user_info.user_name if user_info.user_name else user_info.user_id
    )
    return user_nickname


async def _get_user_default_avatar() -> bytes:
    img = open(
        os.path.dirname(os.path.abspath(__file__)) + "/template/avatar/default.jpg",
        "rb",
    ).read()
    return img

async def _get_user_avatar(user: UserInfo, client: httpx.AsyncClient) -> bytes:
    if not user.user_avatar:
        return await _get_user_default_avatar()
    url = user.user_avatar.get_url()
    for i in range(3):
        try:
            resp = await client.get(url, timeout=10)
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            logger.warning(f"Error downloading {url}, retry {i}/3: {e}")
            await asyncio.sleep(3)
    raise NetworkError(f"{url} 下载失败！")

def get_default_user_info() -> UserInfo:
    user_info = UserInfo(
        user_id="114514",
        user_name="鬼知道这谁，bot获取不了",
    )
    return user_info

async def get_user_infos(
    bot: Bot, event: Event, rank: List, use_cache: bool = True
) -> List[UserRankInfo]:

    user_ids = [i[0] for i in rank]
    pool = [get_user_info(bot, event, id, use_cache) for id in user_ids]
    user_infos = await asyncio.gather(*pool)
    
    async with httpx.AsyncClient() as client:
        pool = []
        for i in user_infos:
            if not i:
                pool.append(_get_user_default_avatar())
                continue
            if i.user_avatar:
                pool.append(_get_user_avatar(i, client))
        user_avatars = await asyncio.gather(*pool)

    for i in user_avatars:
        if not i:
            user_avatars[user_avatars.index(i)] = await _get_user_default_avatar()

    total = sum([i[1] for i in rank])
    rank2 = []
    for i in range(len(rank)):

        user_info = user_infos[i]
        if not user_info:
            user_info = get_default_user_info()

        user = UserRankInfo(
            **model_dump(user_info),
            user_bnum=rank[i][1],
            user_proportion=round(rank[i][1] / total * 100, 2),
            user_index=i + 1,
            user_nickname=_get_user_nickname(user_info),
            user_avatar_bytes=user_avatars[i],
        )
        user.user_gender = (
            "♂"
            if user.user_gender == "male"
            else "♀" if user.user_gender == "female" else ""
        )
        rank2.append(user)

    return rank2
