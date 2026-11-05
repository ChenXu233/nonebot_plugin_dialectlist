import asyncio
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
from nonebot_plugin_userinfo.image_source import ImageUrl


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
from .styles import get_theme, rank_css, read_css
from .templates import PAGES_DIR, resolve as resolve_template

# 0.8 的 render_template 用 variables/width/height，0.7 的签名仍是 request/**kwargs
_NEW_RENDER_API = (
	render_template is not None
	and 'variables' in inspect.signature(render_template).parameters
)
_VIEWPORT = {'viewport': {'width': 1000, 'height': 10}}


class RenderError(RuntimeError):
	"""渲染环境不可用（缺后端配置、浏览器没装好、超时等）"""


def _describe_render_error(exc: Exception) -> str:
	"""把渲染异常翻译成一句人话"""
	name = type(exc).__name__
	text = str(exc)
	if name == 'CapabilityUnavailable':
		return 'htmlrender 没有可用的渲染后端（0.8+ 要配 RENDER__PROVIDER）'
	if 'Executable doesn' in text or 'executable doesn' in text:
		return 'Playwright 浏览器没装好'
	if 'Timeout' in name or 'timeout' in text.lower():
		return '渲染超时'
	if 'download' in text.lower() and 'fail' in text.lower():
		return '下载浏览器或资源失败'
	return f'{name}: {text}'[:160]


async def _render_template_to_pic(
	template_dir: str,
	template_name: str,
	context: Dict[str, Any],
	width: int = 1000,
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
				width=width,
				height=None,
				device_pixel_ratio=2,
			)
		except Exception as exc:
			logger.exception(f'渲染排行榜图片失败: {exc}')
			raise RenderError(_describe_render_error(exc)) from exc
		return image.data
	if template_to_pic is not None:
		try:
			return await template_to_pic(
				template_dir, template_name, context, pages=_VIEWPORT
			)
		except Exception as exc:
			logger.exception(f'渲染排行榜图片失败: {exc}')
			raise RenderError(_describe_render_error(exc)) from exc
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


def got_rank(
	msg_dict: Dict[int, int], num: Optional[int] = None
) -> List[List[Any]]:
	"""### 获得排行榜

	Args:
	    msg_dict (Dict[int,int]): 要处理的字典
	    num (Optional[int]): 榜单长度，默认为配置里的 get_num

	Returns:
	    List[Tuple[int,int]]: 排行榜列表(已排序)
	"""
	limit = num or plugin_config.get_num
	rank = []
	while len(rank) < limit:
		try:
			max_key = max(msg_dict.items(), key=lambda x: x[1])
			rank.append(list(max_key))
			msg_dict.pop(max_key[0])
		except ValueError:
			logger.error(
				'群内拥有聊天记录的人数不足，无法获取到长度为{}的排行榜,已将长度变化为：{}'.format(
					limit, len(rank)
				)
			)
			break

	return rank


async def render_page(
	template_name: str,
	context: Dict[str, Any],
	width: int = 1000,
) -> bytes:
	"""渲染插件自带的其它模板（分布图 / 多群对比）"""
	return await _render_template_to_pic(
		str(PAGES_DIR), template_name, context, width
	)


def _rank_css_for(
	path_dir: str, theme: Optional[str], layout: Optional[str]
) -> str:
	"""模板目录自带 style.css 就整套用它，否则套主题 + 模板的 extra.css"""
	style_css = os.path.join(path_dir, 'css', 'style.css')
	if os.path.isfile(style_css):
		return read_css(style_css)
	return rank_css(theme, layout, os.path.join(path_dir, 'extra.css'))


async def get_rank_image(
	rank: List[UserRankInfo],
	template_path: Optional[str] = None,
	theme: Optional[str] = None,
	layout: Optional[str] = None,
	template: Optional[str] = None,
) -> bytes:
	path_dir, filename = resolve_template(template, template_path)
	path_dir_str = str(path_dir)

	logger.debug(
		f'渲染排行榜模板: {os.path.join(path_dir_str, filename)}'
		f'（{get_theme(theme).name}）'
	)
	return await _render_template_to_pic(
		path_dir_str,
		filename,
		{
			'users': rank,
			'inline_css': _rank_css_for(path_dir_str, theme, layout),
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


async def _load_avatars(user_infos: List[Optional[UserInfo]]) -> List[bytes]:
	"""并发下载头像，任何一步失败都回落到默认头像"""
	default = await _get_user_default_avatar()
	try:
		async with httpx.AsyncClient() as client:
			pool = [
				_get_user_avatar(info, client)
				if info and info.user_avatar
				else _get_user_default_avatar()
				for info in user_infos
			]
			results = await asyncio.gather(*pool, return_exceptions=True)
	except Exception as e:
		# 例如环境里的代理配置异常，连 client 都创建不出来
		logger.warning(f'初始化 HTTP 客户端失败，头像统一使用默认图: {e}')
		return [default for _ in user_infos]

	user_avatars: List[bytes] = []
	for result in results:
		if isinstance(result, BaseException):
			logger.warning(f'获取用户头像失败，已使用默认头像: {result}')
			user_avatars.append(default)
		else:
			user_avatars.append(result)
	return user_avatars


async def _build_rank_infos(
	rank: List, user_infos: List[Optional[UserInfo]]
) -> List[UserRankInfo]:
	"""把 (user_persist_id, 消息数) 和用户信息拼成渲染用的结构"""
	user_avatars = await _load_avatars(user_infos)

	total = sum(item[1] for item in rank) or 1
	rank2 = []
	for i in range(len(rank)):
		user_info = user_infos[i] or get_default_user_info()
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


async def get_user_infos(
	bot: Bot,
	event: Event,
	rank: List,
	use_cache: bool = plugin_config.use_user_info_cache,
) -> List[UserRankInfo]:
	"""事件响应里用：走 userinfo 拿实时信息"""
	user_ids = [str(item[0]) for item in rank]
	user_infos = await asyncio.gather(
		*[get_user_info(bot, event, user_id, use_cache) for user_id in user_ids]
	)
	return await _build_rank_infos(rank, list(user_infos))


def _user_info_from_db(
	user_id: str, user_data: Dict[str, Any], member_data: Dict[str, Any]
) -> UserInfo:
	avatar = user_data.get('avatar')
	return UserInfo(
		user_id=user_id,
		user_name=user_data.get('name') or user_id,
		user_displayname=member_data.get('nick') or user_data.get('nick'),
		user_remark=None,
		user_avatar=ImageUrl(url=avatar) if avatar else None,
		user_gender=user_data.get('gender') or 'unknown',
	)


async def get_user_infos_from_db(
	scene_id: str, rank: List
) -> List[UserRankInfo]:
	"""定时推送用：没有事件上下文，直接从 uninfo 的缓存里取用户信息"""
	persist_ids = [item[0] for item in rank]
	async with get_session() as db_session:
		rows = await db_session.execute(
			select(UserModel.id, UserModel.user_id, UserModel.user_data).where(
				UserModel.id.in_(persist_ids)
			)
		)
		user_map = {
			uid: (user_id, user_data or {})
			for uid, user_id, user_data in rows.all()
		}

		scene_rows = await db_session.scalars(
			select(SceneModel.id).where(SceneModel.scene_id == str(scene_id))
		)
		scene_pks = scene_rows.all()

		member_map: Dict[int, Dict[str, Any]] = {}
		if scene_pks:
			member_rows = await db_session.execute(
				select(SessionModel.user_persist_id, SessionModel.member_data)
				.where(SessionModel.scene_persist_id.in_(scene_pks))
				.where(SessionModel.user_persist_id.in_(persist_ids))
			)
			for persist_id, member_data in member_rows.all():
				member_map.setdefault(persist_id, member_data or {})

	user_infos: List[Optional[UserInfo]] = []
	for persist_id in persist_ids:
		entry = user_map.get(persist_id)
		if not entry:
			user_infos.append(None)
			continue
		user_id, user_data = entry
		user_infos.append(
			_user_info_from_db(
				user_id, user_data, member_map.get(persist_id, {})
			)
		)

	return await _build_rank_infos(rank, user_infos)


def format_rank_text(
	rank: List[UserRankInfo],
	keyword: Optional[str] = None,
	cfg: Optional[Any] = None,
) -> str:
	"""按 string_format 拼出文字榜单（命令和定时推送共用）"""
	cfg = cfg or plugin_config
	if not cfg.show_text_rank:
		return ''
	header = f'关于{keyword}的话痨榜结果：\n' if keyword else '话痨榜：\n'
	return header + ''.join(
		cfg.string_format.format(
			index=item.user_index,
			nickname=item.user_nickname,
			chatdatanum=item.user_bnum,
		)
		for item in rank
	)


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
