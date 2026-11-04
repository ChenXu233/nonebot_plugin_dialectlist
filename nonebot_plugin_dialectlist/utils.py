import asyncio
import base64
import inspect
import os
from typing import Any, Dict, List, Optional

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select

from nonebot.adapters import Bot, Event
from nonebot.compat import model_dump
from nonebot.log import logger
from nonebot_plugin_chatrecorder import MessageRecord
from nonebot_plugin_chatrecorder.record import filter_statement
from nonebot_plugin_orm import get_session
from nonebot_plugin_uninfo.orm import (
	BotModel,
	SceneModel,
	SessionModel,
	UserModel,
)
from nonebot_plugin_userinfo import UserInfo, get_user_info
from nonebot_plugin_userinfo.exception import NetworkError


try:  # htmlrender >= 0.8：render_template 需要模板目录在本地白名单内，
	# 这里改用 render_html：模板由我们自己渲染成字符串，资源全部内联，
	# 因此不需要用户额外配置任何本地路径。
	from nonebot_plugin_htmlrender import render_html
	from nonebot_plugin_htmlrender import render_template
except ImportError:  # pragma: no cover - 0.6 / 0.7
	render_html = None  # type: ignore[assignment]
	render_template = None  # type: ignore[assignment]

try:  # htmlrender < 0.8
	from nonebot_plugin_htmlrender import template_to_pic
except ImportError:  # pragma: no cover - 0.8 起已被移除
	template_to_pic = None  # type: ignore[assignment]

from .config import plugin_config
from .schema import UserRankInfo

# 0.8 的 render_template 用 variables/width/height，0.7 的签名仍是 request/**kwargs
_NEW_RENDER_API = (
	render_template is not None
	and 'variables' in inspect.signature(render_template).parameters
)
_VIEWPORT = {'viewport': {'width': 1000, 'height': 10}}
_PLUGIN_TEMPLATE_DIR = os.path.dirname(os.path.abspath(__file__)) + '/template'
_inline_css_cache: Dict[str, str] = {}


def _build_inline_css(css_path: str) -> str:
	"""读取样式表并把字体内联成 data URI，模板不再依赖本地文件"""
	if css_path in _inline_css_cache:
		return _inline_css_cache[css_path]

	with open(css_path, encoding='utf-8') as f:
		css = f.read()

	font_path = os.path.join(
		os.path.dirname(os.path.dirname(css_path)),
		'res',
		'HarmonyOS_Sans_SC.woff2',
	)
	if os.path.exists(font_path):
		with open(font_path, 'rb') as f:
			font = base64.b64encode(f.read()).decode('ascii')
		css = css.replace(
			'../res/HarmonyOS_Sans_SC.woff2', f'data:font/woff2;base64,{font}'
		)

	_inline_css_cache[css_path] = css
	return css


def _resolve_template_file() -> str:
	template_path = plugin_config.template_path
	if template_path[:2] == './':
		return os.path.dirname(os.path.abspath(__file__)) + template_path[1:]
	return template_path


async def _render_template_to_pic(
	template_dir: str, template_name: str, context: Dict[str, Any]
) -> bytes:
	"""渲染模板，兼容 htmlrender 0.6 / 0.7 与 0.8+ 两套接口"""
	if _NEW_RENDER_API:
		try:
			environment = Environment(
				loader=FileSystemLoader(template_dir),
				autoescape=select_autoescape(['html', 'htm', 'xml', 'j2']),
			)
			html = environment.get_template(template_name).render(**context)
			image = await render_html(  # type: ignore[misc]
				html,
				width=1000,
				height=None,
				device_pixel_ratio=2,
			)
		except Exception as exc:
			if type(exc).__name__ == 'CapabilityUnavailable':
				raise RuntimeError(
					'htmlrender 0.8+ 必须显式指定渲染后端，请在 .env 中添加：\n'
					'  RENDER__PROVIDER=playwright\n'
					'首次渲染会自动安装 Chromium，也可以手动执行 '
					'playwright install chromium。'
				) from exc
			raise
		return image.data
	if template_to_pic is not None:
		return await template_to_pic(
			template_dir, template_name, context, pages=_VIEWPORT
		)
	raise RuntimeError(
		'没有找到可用的 htmlrender 渲染接口，请检查 nonebot-plugin-htmlrender 版本。'
	)


async def persist_id2user_id(ids: List[int]) -> Dict[int, str]:
	"""将用户持久化 id 映射为平台用户 id

	Args:
	    ids (List[int]): 用户持久化 id 列表

	Returns:
	    Dict[int, str]: 持久化 id 到平台用户 id 的映射
	"""
	if not ids:
		return {}

	async with get_session() as db_session:
		statement = select(UserModel.id, UserModel.user_id).where(
			UserModel.id.in_(ids)
		)
		result = await db_session.execute(statement)
		return dict(result.all())


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


async def get_rank_image(rank: List[UserRankInfo]) -> bytes:
	path = _resolve_template_file()
	path_dir, filename = os.path.split(path)

	# 自定义模板目录里没有样式表时，退回插件自带的样式
	css_path = os.path.join(path_dir, 'css', 'style.css')
	if not os.path.exists(css_path):
		css_path = os.path.join(_PLUGIN_TEMPLATE_DIR, 'css', 'style.css')

	logger.debug(f'渲染排行榜模板: {path}')
	return await _render_template_to_pic(
		path_dir,
		filename,
		{
			'users': rank,
			'inline_css': _build_inline_css(css_path),
		},
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
	with open(
		os.path.dirname(os.path.abspath(__file__))
		+ '/template/avatar/default.jpg',
		'rb',
	) as f:
		return f.read()


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
		pool = [
			_get_user_avatar(info, client)
			if info and info.user_avatar
			else _get_user_default_avatar()
			for info in user_infos
		]
		results = await asyncio.gather(*pool, return_exceptions=True)

	user_avatars = []
	for result in results:
		if isinstance(result, BaseException):
			logger.warning(f'获取用户头像失败，已使用默认头像: {result}')
			user_avatars.append(await _get_user_default_avatar())
		else:
			user_avatars.append(result)

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
		# 按“包含”匹配，autoescape 会把 % / _ 转义成普通字符
		whereclause.append(
			MessageRecord.plain_text.icontains(keyword, autoescape=True)
		)

	# filter_statement 的条件会引用 Bot/Scene/User 表，必须一并 join，
	# 否则 SQLAlchemy 会退化成隐式笛卡尔积，统计结果会被成倍放大
	statement = (
		select(
			SessionModel.user_persist_id,
			func.count(MessageRecord.id).label('message_count'),
		)
		.select_from(MessageRecord)
		.join(SessionModel, SessionModel.id == MessageRecord.session_persist_id)
		.join(UserModel, UserModel.id == SessionModel.user_persist_id)
		.join(SceneModel, SceneModel.id == SessionModel.scene_persist_id)
		.join(BotModel, BotModel.id == SessionModel.bot_persist_id)
		.where(*whereclause)
		.group_by(SessionModel.user_persist_id)
	)

	async with get_session() as db_session:
		result = await db_session.execute(statement)
		# 转换为字典格式返回
		return {user_id: count for user_id, count in result.all()}
