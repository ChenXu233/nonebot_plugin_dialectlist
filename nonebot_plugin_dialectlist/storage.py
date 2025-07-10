import json
import os
from datetime import datetime

from nonebot import get_driver
from nonebot.adapters import Bot, Event
from nonebot.log import logger
from nonebot.message import event_postprocessor
from nonebot.params import Depends
from nonebot_plugin_chatrecorder import get_message_records
from nonebot_plugin_chatrecorder.utils import remove_timezone
from nonebot_plugin_uninfo import Session, get_session
from nonebot_plugin_uninfo.orm import SessionModel,get_session_persist_id
from nonebot_plugin_localstore import get_data_file
from nonebot_plugin_orm import get_session
from sqlalchemy import delete, or_, select

from .config import plugin_config
from .model import MessageCountCache


async def get_cache(time_start: datetime, time_stop: datetime, group_id: str):
    async with get_session() as db_session:
        where = [or_(SessionModel.id2 == group_id)]
        statement = select(SessionModel).where(*where)

        sessions = (await db_session.scalars(statement)).all()

        where = [
            or_(*[MessageCountCache.session_id == session.id for session in sessions])
        ]
        statement = select(MessageCountCache).where(*where)
        where.append(or_(MessageCountCache.time >= remove_timezone(time_start)))
        where.append(or_(MessageCountCache.time <= remove_timezone(time_stop)))
        statement = select(MessageCountCache).where(*where)

        user_caches = (await db_session.scalars(statement)).all()
        raw_rank = {}
        for i in user_caches:
            raw_rank[i.session_id] = raw_rank.get(i.session_id, 0) + i.session_bnum
        return raw_rank


async def build_cache():
    async with get_session() as db_session:
        await db_session.execute(delete(MessageCountCache))
        await db_session.commit()
    logger.info("先前可能存在的缓存已清空")
    messages = await get_message_records(types=["message"])
    async with get_session() as db_session:
        for msg in messages:
            msg_session_id = msg.session_persist_id

            where = [or_(MessageCountCache.session_id == msg_session_id)]
            where.append(
                or_(
                    MessageCountCache.time
                    == remove_timezone(
                        msg.time.replace(hour=1, minute=0, second=0, microsecond=0)
                    )
                )
            )
            statement = select(MessageCountCache).where(*where)

            user_cache = (await db_session.scalars(statement)).all()

            if user_cache:
                user_cache[0].session_bnum += 1
            else:
                user_cache = MessageCountCache(
                    session_id=msg.session_persist_id,
                    time=remove_timezone(
                        msg.time.replace(hour=1, minute=0, second=0, microsecond=0)
                    ),
                    session_bnum=1,
                )
                db_session.add(user_cache)
            await db_session.commit()

    logger.info("缓存构建完成")


driver = get_driver()


@driver.on_startup
async def _():
    if not plugin_config.counting_cache:
        return
    f_name = get_data_file("nonebot-plugin-dialectlist", "is-pre-cached.json")
    if not os.path.exists(f_name):
        with open(f_name, "w", encoding="utf-8") as f:
            s = json.dumps({"is-pre-cached": False}, ensure_ascii=False, indent=4)
            f.write(s)

    with open(f_name, "r", encoding="utf-8") as f:
        if json.load(f)["is-pre-cached"]:
            return
    logger.info("未检查到缓存，开始构建缓存")
    with open(f_name, "w", encoding="utf-8") as f:
        await build_cache()
        json.dump({"is-pre-cached": True}, f, ensure_ascii=False, indent=4)


@event_postprocessor
async def _(bot: Bot, event: Event, session: Session = Depends(extract_session)):
    if not plugin_config.counting_cache:
        return
    if not session.id2:
        return
    if event.get_type() != "message":
        return
    now = datetime.now()
    now = now.replace(hour=1, minute=0, second=0, microsecond=0)

    async with get_session() as db_session:
        session_id = await get_session_persist_id(session)
        logger.debug("session_id:" + str(session_id))
        where = [or_(MessageCountCache.session_id == session_id)]
        where.append(or_(MessageCountCache.time == remove_timezone(now)))
        statement = select(MessageCountCache).where(*where)
        user_cache = (await db_session.scalars(statement)).first()
        if user_cache:
            user_cache.session_bnum += 1
        else:
            user_cache = MessageCountCache(
                session_id=session_id,
                time=remove_timezone(now),
                session_bnum=1,
            )
            db_session.add(user_cache)
        await db_session.commit()
    logger.debug("已计入缓存")


# TODO: 修复缓存储存