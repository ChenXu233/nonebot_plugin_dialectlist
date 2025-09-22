import asyncio
import os
import re
import unicodedata
from typing import Dict, List, Optional, Any

import httpx
from sqlalchemy import select, func

from nonebot.adapters import Bot, Event
from nonebot.compat import model_dump
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot_plugin_chatrecorder import MessageRecord
from nonebot_plugin_htmlrender import template_to_pic
from nonebot_plugin_localstore import get_cache_dir
from nonebot_plugin_orm import get_session
from nonebot_plugin_userinfo import UserInfo, get_user_info
from nonebot_plugin_uninfo import Session
from nonebot_plugin_uninfo.model import SceneType
from nonebot_plugin_uninfo.orm import SessionModel, UserModel
from nonebot_plugin_uninfo import get_session as extract_session
from nonebot_plugin_userinfo.exception import NetworkError
from nonebot_plugin_chatrecorder.record import filter_statement


from .config import plugin_config
from .schema import UserRankInfo

cache_path = get_cache_dir('nonebot_plugin_dialectlist')


async def ensure_group(
	matcher: Matcher, session: Session = Depends(extract_session)
):
	"""确保在群组中使用"""
	if session.scene.type not in [SceneType.GROUP, SceneType.GUILD]:
		await matcher.finish('请在群组中使用！')


async def persist_id2user_id(ids: List) -> List[str]:
	user_ids = []
	if not ids:
		return user_ids

	async with get_session() as db_session:
		statement = (
			select(UserModel.user_id)
			.join(SessionModel, UserModel.id == SessionModel.user_persist_id)
			.where(SessionModel.id.in_(ids))
		)
		result = await db_session.scalars(statement)
		user_ids = result.all()

	return list(user_ids)


def got_rank(msg_dict: Dict[int, int]) -> List[List[Any]]:
	"""### 获得排行榜

	Args:
	    msg_dict (Dict[int,int]): 要处理的字典

	Returns:
	    List[Tuple[int,int]]: 排行榜列表(已排序)
	"""
	rank = []
	while len(rank) < plugin_config.get_num:
		try:
			max_key = max(msg_dict.items(), key=lambda x: x[1])
			rank.append(list(max_key))
			msg_dict.pop(max_key[0])
		except ValueError:
			logger.error(
				'群内拥有聊天记录的人数不足，无法获取到长度为{}的排行榜,已将长度变化为：{}'.format(
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
	return ''.join(ch for ch in string if unicodedata.category(ch)[0] != 'C')


async def get_rank_image(rank: List[UserRankInfo]) -> bytes:
	for i in rank:
		if i.user_avatar:
			try:
				user_avatar = i.user_avatar_bytes
			except NotImplementedError:
				user_avatar = open(
					os.path.dirname(os.path.abspath(__file__))
					+ '/template/avatar/default.jpg',
					'rb',
				).read()
			# if not os.path.exists(cache_path / str(i.user_id)):
			with open(cache_path / (str(i.user_id) + '.jpg'), 'wb') as f:
				f.write(user_avatar)

	if plugin_config.template_path[:2] == './':
		path = (
			os.path.dirname(os.path.abspath(__file__))
			+ plugin_config.template_path[1:]
		)
	else:
		path = plugin_config.template_path

	path_dir, filename = os.path.split(path)
	logger.debug(
		os.path.dirname(os.path.abspath(__file__))
		+ plugin_config.template_path[1:]
	)
	return await template_to_pic(
		path_dir,
		filename,
		{
			'users': rank,
			'cache_path': cache_path,
			'file_path': os.path.dirname(os.path.abspath(__file__)),
		},
		pages={'viewport': {'width': 1000, 'height': 10}},
	)


def _get_user_nickname(user_info: UserInfo) -> str:
	user_nickname = (
		user_info.user_displayname
		if user_info.user_displayname
		else user_info.user_name
		if user_info.user_name
		else user_info.user_id
	)
	return user_nickname


async def _get_user_default_avatar() -> bytes:
	img = open(
		os.path.dirname(os.path.abspath(__file__))
		+ '/template/avatar/default.jpg',
		'rb',
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
			logger.warning(f'Error downloading {url}, retry {i}/3: {e}')
			await asyncio.sleep(3)
	raise NetworkError(f'{url} 下载失败！')


def get_default_user_info() -> UserInfo:
	user_info = UserInfo(
		user_id='114514',
		user_name='鬼知道这谁，bot获取不了',
	)
	return user_info


async def get_user_infos(
	bot: Bot,
	event: Event,
	rank: List,
	use_cache: bool = plugin_config.use_user_info_cache,
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
			user_avatars[
				user_avatars.index(i)
			] = await _get_user_default_avatar()

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
		print(user.user_gender)
		if user.user_gender == 'male':
			user.user_gender = '♂'
		elif user.user_gender == 'female':
			user.user_gender = '♀'
		else:
			user.user_gender = '🤔'
		rank2.append(user)

	return rank2


async def get_user_message_counts(
	keyword: Optional[str] = None, **kwargs
) -> Dict[int, int]:
	"""获取每个用户的消息数量（直接在数据库层面统计）

	参数:
	  * ``keyword``: 可选，关键词，只统计包含该关键词的消息
	  * ``**kwargs``: 筛选参数，具体查看 `filter_statement` 中的定义

	返回值:
	  * ``Dict[str, int]``: 键为user_persist_id，值为该用户的消息数量
	"""
	whereclause = filter_statement(**kwargs)

	# 如果提供了关键词，添加关键词过滤条件
	if keyword:
		# 构造LIKE条件，类似于msg_counter函数中的正则匹配
		# 根据数据库类型不同，可能需要调整LIKE的语法
		keyword_condition = MessageRecord.plain_text.ilike(f'%{keyword}%')
		whereclause.append(keyword_condition)

	# 使用SQL的GROUP BY和COUNT进行分组统计
	statement = (
		select(
			SessionModel.user_persist_id,
			func.count(MessageRecord.id).label('message_count'),
		)
		.select_from(MessageRecord)
		.join(SessionModel, SessionModel.id == MessageRecord.session_persist_id)
		.where(*whereclause)
		.group_by(SessionModel.user_persist_id)
	)

	async with get_session() as db_session:
		result = await db_session.execute(statement)
		# 转换为字典格式返回
		return {user_id: count for user_id, count in result.all()}
