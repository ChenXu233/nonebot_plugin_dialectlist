import asyncio
import base64
import inspect
import os
import time
from datetime import datetime
from urllib.parse import unquote_to_bytes
from typing import Any, Dict, List, Optional, Tuple

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
from .time import previous_period_range

# 0.8 的 render_template 用 variables/width/height，0.7 的签名仍是 request/**kwargs
_NEW_RENDER_API = (
	render_template is not None
	and 'variables' in inspect.signature(render_template).parameters
)
_VIEWPORT = {'viewport': {'width': 1000, 'height': 10}}

# 头像：共享连接 + 按 URL 缓存；单次失败不再拖住整条命令
_AVATAR_TIMEOUT = 10.0
_AVATAR_RETRY_DELAYS = (1.0, 2.0)
_AVATAR_CACHE_TTL = 3600.0
_AVATAR_CACHE_MAX = 256
_avatar_cache: Dict[str, Tuple[bytes, float]] = {}
_default_avatar: Optional[bytes] = None
_http_client: Optional[httpx.AsyncClient] = None
_http_client_lock: Optional[asyncio.Lock] = None


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


def previous_rank_map(previous_counts: Dict[int, int]) -> Dict[int, int]:
	"""上一期每个用户的名次；并列的人算同一名（1,1,3……）"""
	ordered = sorted(
		previous_counts.items(), key=lambda item: item[1], reverse=True
	)
	ranks: Dict[int, int] = {}
	last_count: Optional[int] = None
	last_rank = 0
	for position, (persist_id, count) in enumerate(ordered, start=1):
		if count != last_count:
			last_count = count
			last_rank = position
		ranks[persist_id] = last_rank
	return ranks


def delta_for_user(
	index: int, persist_id: int, previous_ranks: Optional[Dict[int, int]]
) -> Dict[str, Any]:
	"""当前名次和上一期比：正数上升、负数下降，上期不在榜上算「新」"""
	if previous_ranks is None:
		return {
			'user_delta_rank': None,
			'user_prev_rank': None,
			'user_delta_label': '',
			'user_delta_class': '',
		}
	previous = previous_ranks.get(persist_id)
	if previous is None:
		return {
			'user_delta_rank': None,
			'user_prev_rank': None,
			'user_delta_label': '新',
			'user_delta_class': 'new',
		}
	delta = previous - index
	label, css_class = '', ''
	if delta > 0:
		label, css_class = f'↑{delta}', 'up'
	elif delta < 0:
		label, css_class = f'↓{-delta}', 'down'
	return {
		'user_delta_rank': delta,
		'user_prev_rank': previous,
		'user_delta_label': label,
		'user_delta_class': css_class,
	}


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
	"""默认头像只读一次，别每个用户都开一次文件"""
	global _default_avatar
	if _default_avatar is None:
		path = os.path.join(
			os.path.dirname(os.path.abspath(__file__)),
			'template',
			'avatar',
			'default.jpg',
		)
		with open(path, 'rb') as f:
			_default_avatar = f.read()
	return _default_avatar


async def _get_http_client() -> httpx.AsyncClient:
	"""全插件共用一个连接池，避免每条命令都新建 AsyncClient"""
	global _http_client, _http_client_lock
	client = _http_client
	if client is not None and not client.is_closed:
		return client
	if _http_client_lock is None:
		_http_client_lock = asyncio.Lock()
	async with _http_client_lock:
		if _http_client is None or _http_client.is_closed:
			try:
				_http_client = httpx.AsyncClient(
					timeout=httpx.Timeout(_AVATAR_TIMEOUT),
					follow_redirects=True,
				)
			except Exception as e:  # noqa: BLE001 - 坏代理配置很常见
				logger.warning(
					f'创建共享 HTTP 客户端失败，改用忽略系统代理的配置: {e}'
				)
				_http_client = httpx.AsyncClient(
					timeout=httpx.Timeout(_AVATAR_TIMEOUT),
					follow_redirects=True,
					trust_env=False,
				)
		return _http_client


async def warmup_http_client() -> None:
	"""启动时先把连接池建好，坏代理只影响一次启动日志"""
	await _get_http_client()


async def close_http_client() -> None:
	"""bot 退出时释放连接池"""
	global _http_client
	client = _http_client
	_http_client = None
	if client is not None and not client.is_closed:
		await client.aclose()


def clear_avatar_cache() -> None:
	_avatar_cache.clear()


def _cache_get_avatar(url: str) -> Optional[bytes]:
	entry = _avatar_cache.get(url)
	if entry is None:
		return None
	data, expires_at = entry
	if expires_at <= time.monotonic():
		_avatar_cache.pop(url, None)
		return None
	return data


def _cache_put_avatar(url: str, data: bytes) -> None:
	now = time.monotonic()
	if len(_avatar_cache) >= _AVATAR_CACHE_MAX:
		for key in [
			key
			for key, (_, expires_at) in _avatar_cache.items()
			if expires_at <= now
		]:
			_avatar_cache.pop(key, None)
		while len(_avatar_cache) >= _AVATAR_CACHE_MAX:
			_avatar_cache.pop(next(iter(_avatar_cache)))
	_avatar_cache[url] = (data, now + _AVATAR_CACHE_TTL)


def _data_uri_payload(url: str) -> Optional[bytes]:
	header, separator, payload = url.partition(',')
	if not separator:
		return None
	try:
		if ';base64' in header:
			return base64.b64decode(payload)
		return unquote_to_bytes(payload)
	except Exception:  # noqa: BLE001 - 坏 data URI 直接当失败处理
		return None


async def _download_avatar(
	url: str, client: Optional[httpx.AsyncClient]
) -> bytes:
	"""下载单个头像：先查缓存，失败时短退避重试两次"""
	cached = _cache_get_avatar(url)
	if cached is not None:
		return cached
	if url.startswith('data:'):
		payload = _data_uri_payload(url)
		if payload is None:
			raise NetworkError('用户头像的 data URI 不合法')
		_cache_put_avatar(url, payload)
		return payload
	if client is None:
		raise NetworkError(f'{url} 没有可用的 HTTP 客户端')

	last_error: Optional[Exception] = None
	for attempt in range(len(_AVATAR_RETRY_DELAYS) + 1):
		try:
			resp = await client.get(url, timeout=_AVATAR_TIMEOUT)
			resp.raise_for_status()
			if not resp.content:
				raise NetworkError(f'{url} 返回了空内容')
			_cache_put_avatar(url, resp.content)
			return resp.content
		except Exception as e:  # noqa: BLE001 - 网络问题统一重试
			last_error = e
			if attempt < len(_AVATAR_RETRY_DELAYS):
				delay = _AVATAR_RETRY_DELAYS[attempt]
				logger.warning(
					f'Error downloading {url}, retry {attempt + 1}/'
					f'{len(_AVATAR_RETRY_DELAYS)} after {delay}s: {e}'
				)
				await asyncio.sleep(delay)
	raise NetworkError(f'{url} 下载失败！') from last_error


async def _get_user_avatar(
	user: UserInfo, client: Optional[httpx.AsyncClient]
) -> bytes:
	if not user.user_avatar:
		return await _get_user_default_avatar()
	return await _download_avatar(user.user_avatar.get_url(), client)


def get_default_user_info() -> UserInfo:
	user_info = UserInfo(
		user_id='114514',
		user_name='鬼知道这谁，bot获取不了',
	)
	return user_info


def _get_avatar_url(info: Optional[UserInfo]) -> Optional[str]:
	"""取头像地址；用户信息源的实现坏了也不能拖垮整条命令"""
	if info is None or not info.user_avatar:
		return None
	try:
		return info.user_avatar.get_url()
	except Exception as e:  # noqa: BLE001 - 第三方头像源可能抛任何异常
		logger.warning(f'读取用户头像地址失败，已使用默认头像: {e}')
		return None


async def _load_avatars(
	user_infos: List[Optional[UserInfo]],
) -> List[bytes]:
	"""并发下载头像：同 URL 只下一次，结果按 URL 缓存"""
	default = await _get_user_default_avatar()
	urls: List[Optional[str]] = [_get_avatar_url(info) for info in user_infos]
	unique_urls: List[str] = []
	seen: set[str] = set()
	for url in urls:
		if url is not None and url not in seen:
			seen.add(url)
			unique_urls.append(url)
	if not unique_urls:
		# 没有头像就别创建 HTTP 客户端
		return [default for _ in user_infos]

	needs_http = any(not url.startswith('data:') for url in unique_urls)
	client: Optional[httpx.AsyncClient] = None
	if needs_http:
		try:
			client = await _get_http_client()
		except Exception as e:  # noqa: BLE001 - 例如代理配置异常
			logger.warning(f'初始化 HTTP 客户端失败，头像统一使用默认图: {e}')
			return [default for _ in user_infos]

	fetched = await asyncio.gather(
		*[_download_avatar(url, client) for url in unique_urls],
		return_exceptions=True,
	)
	by_url: Dict[str, bytes] = {}
	for url, result in zip(unique_urls, fetched):
		if isinstance(result, BaseException):
			logger.warning(f'获取用户头像失败，已使用默认头像: {result}')
		else:
			by_url[url] = result
	return [by_url.get(url, default) if url else default for url in urls]


async def _build_rank_infos(
	rank: List,
	user_infos: List[Optional[UserInfo]],
	previous_counts: Optional[Dict[int, int]] = None,
	persist_ids: Optional[List[int]] = None,
) -> List[UserRankInfo]:
	"""把 (user_persist_id, 消息数) 和用户信息拼成渲染用的结构

	previous_counts 是上一期的全量计数，传了才会算名次变化。
	"""
	user_avatars = await _load_avatars(user_infos)
	previous_ranks = (
		previous_rank_map(previous_counts) if previous_counts else None
	)

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
			**delta_for_user(
				i + 1,
				persist_ids[i] if persist_ids else rank[i][0],
				previous_ranks,
			),
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
	previous_counts: Optional[Dict[int, int]] = None,
	persist_ids: Optional[List[int]] = None,
) -> List[UserRankInfo]:
	"""事件响应里用：走 userinfo 拿实时信息

	rank 里的用户 id 会被换成平台号，算环比时用 persist_ids 记住原来的
	持久化 id（顺序和 rank 一致）。
	"""
	user_ids = [str(item[0]) for item in rank]
	user_infos = await asyncio.gather(
		*[get_user_info(bot, event, user_id, use_cache) for user_id in user_ids]
	)
	return await _build_rank_infos(
		rank, list(user_infos), previous_counts, persist_ids
	)


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
	scene_id: str,
	rank: List,
	previous_counts: Optional[Dict[int, int]] = None,
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

	return await _build_rank_infos(rank, user_infos, previous_counts)


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
			delta=item.user_delta_label,
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


async def get_previous_message_counts(
	period: Optional[str],
	start: Optional[datetime],
	stop: Optional[datetime],
	scene_ids: List[str],
	keyword: Optional[str] = None,
	exclude_user_ids: Optional[List[str]] = None,
) -> Optional[Dict[int, int]]:
	"""环比要用的上一期全量计数；没有可比的上一期就返回 None"""
	previous = previous_period_range(period, start, stop)
	if previous is None:
		return None
	return await get_user_message_counts(
		keyword=keyword,
		scene_ids=scene_ids,
		types=['message'],
		time_start=previous[0],
		time_stop=previous[1],
		exclude_user_ids=exclude_user_ids or [],
	)
