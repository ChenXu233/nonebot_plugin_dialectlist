"""分布图与多群对比：统计结果塞进模板渲染"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, select

from nonebot.adapters import Bot
from nonebot.log import logger
from nonebot_plugin_chatrecorder import MessageRecord
from nonebot_plugin_chatrecorder.record import filter_statement
from nonebot_plugin_orm import get_session
from nonebot_plugin_uninfo import SceneType
from nonebot_plugin_uninfo.orm import (
	BotModel,
	SceneModel,
	SessionModel,
	UserModel,
)

from .config import ScopedConfig
from .group_config import effective_config
from .styles import chart_css
from .time import get_datetime_now_with_timezone
from .utils import (
	get_user_infos_from_db,
	get_user_message_counts,
	got_rank,
	render_page,
)

HOUR_LABELS = [f'{hour:02d}' for hour in range(24)]
WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

# 多群统计只看群，不看私聊
GROUP_SCENES = [SceneType.GROUP, SceneType.GUILD, SceneType.CHANNEL_TEXT]

BAR_HEIGHT = 300

_name_cache: Dict[str, str] = {}


def _offset_hours() -> int:
	offset = get_datetime_now_with_timezone().utcoffset()
	if offset is None:
		return 0
	return int(round(offset.total_seconds() / 3600))


def _where(
	scene_ids: Sequence[str],
	start: datetime,
	stop: datetime,
	keyword: Optional[str] = None,
	exclude_user_ids: Sequence[str] = (),
) -> List[Any]:
	whereclause = filter_statement(
		scene_ids=list(scene_ids),
		types=['message'],
		time_start=start,
		time_stop=stop,
		exclude_user_ids=list(exclude_user_ids),
	)
	if keyword:
		whereclause.append(
			MessageRecord.plain_text.icontains(keyword, autoescape=True)
		)
	return whereclause


def _joined(statement: Any) -> Any:
	"""filter_statement 的条件会引用这几张表，不 join 会变成笛卡尔积"""
	return (
		statement.select_from(MessageRecord)
		.join(SessionModel, SessionModel.id == MessageRecord.session_persist_id)
		.join(UserModel, UserModel.id == SessionModel.user_persist_id)
		.join(SceneModel, SceneModel.id == SessionModel.scene_persist_id)
		.join(BotModel, BotModel.id == SessionModel.bot_persist_id)
	)


def _to_local(value: datetime) -> datetime:
	if value.tzinfo is None:
		value = value.replace(tzinfo=timezone.utc)
	return value.astimezone(get_datetime_now_with_timezone().tzinfo)


async def _histogram_sql(whereclause: List[Any], mode: str) -> Dict[int, int]:
	"""交给数据库分组；先按 UTC 分桶，再用 modifier 挪到本地时区"""
	pattern = '%H' if mode == 'hour' else '%w'
	modifier = f'{_offset_hours():+d} hours'
	bucket = func.strftime(pattern, MessageRecord.time, modifier)
	statement = (
		_joined(select(bucket.label('bucket'), func.count(MessageRecord.id)))
		.where(*whereclause)
		.group_by(bucket)
	)
	async with get_session() as db_session:
		rows = await db_session.execute(statement)
		return {int(b): int(c) for b, c in rows.all() if b is not None}


async def _histogram_python(
	whereclause: List[Any], mode: str
) -> Dict[int, int]:
	"""换数据库时退回 Python 统计（时区也更准）"""
	statement = _joined(select(MessageRecord.time)).where(*whereclause)
	result: Dict[int, int] = {}
	async with get_session() as db_session:
		rows = await db_session.scalars(statement)
		for value in rows.all():
			if value is None:
				continue
			local = _to_local(value)
			# 统一成 SQLite 的 %w：周日 0、周一 1……
			key = local.hour if mode == 'hour' else (local.weekday() + 1) % 7
			result[key] = result.get(key, 0) + 1
	return result


async def histogram(
	scene_ids: Sequence[str],
	start: datetime,
	stop: datetime,
	mode: str = 'hour',
	keyword: Optional[str] = None,
	exclude_user_ids: Sequence[str] = (),
) -> List[int]:
	"""按小时（24 个）或星期（7 个，周一开始）统计消息量"""
	whereclause = _where(scene_ids, start, stop, keyword, exclude_user_ids)
	try:
		raw = await _histogram_sql(whereclause, mode)
	except Exception as e:
		logger.warning(f'按时间分组统计失败，改用 Python 统计: {e}')
		raw = await _histogram_python(whereclause, mode)

	if mode == 'hour':
		return [raw.get(hour, 0) for hour in range(24)]
	# %w：0=周日，1=周一……这里排成 周一..周日
	return [raw.get((index + 1) % 7, 0) for index in range(7)]


def _bar_items(
	values: Sequence[int], labels: Sequence[str]
) -> List[Dict[str, Any]]:
	peak = max(values) or 1
	return [
		{
			'label': label,
			'value': value,
			'height': max(3, round(value / peak * BAR_HEIGHT)),
			'percent': round(value / peak * 100, 1),
		}
		for label, value in zip(labels, values)
	]


async def histogram_report(
	scene_ids: Sequence[str],
	group_label: str,
	period: str,
	start: datetime,
	stop: datetime,
	mode: str,
	cfg: ScopedConfig,
	keyword: Optional[str] = None,
) -> Tuple[List[int], bytes]:
	"""返回 (各桶数量, 图片)"""
	values = await histogram(
		scene_ids,
		start,
		stop,
		mode,
		keyword,
		cfg.excluded_people,
	)
	total = sum(values)
	by_hour = mode == 'hour'
	title = '群消息时段分布' if by_hour else '群消息星期分布'
	if keyword:
		title = f'“{keyword}”的' + ('时段分布' if by_hour else '星期分布')
	subtitle = f'{group_label} · {period} · 共 {total} 条消息'
	image = await render_page(
		'chart_template.j2',
		{
			'title': title,
			'subtitle': subtitle,
			'mode': 'bar',
			'items': _bar_items(
				values, HOUR_LABELS if by_hour else WEEKDAY_LABELS
			),
			'footer': 'Designed By ChenXu233',
			'inline_css': chart_css(cfg.theme),
		},
	)
	return values, image


def _name_from_scene_data(scene_data: Any) -> Optional[str]:
	if not isinstance(scene_data, dict):
		return None
	for key in ('name', 'group_name', 'scene_name', 'title'):
		value = scene_data.get(key)
		if value:
			return str(value)
	return None


async def _name_from_bot(bot: Bot, group_id: str) -> Optional[str]:
	try:
		info = await bot.call_api('get_group_info', group_id=int(group_id))
	except Exception as e:
		logger.debug(f'取群 {group_id} 信息失败: {e}')
		return None
	if isinstance(info, dict):
		name = info.get('group_name') or info.get('name')
	else:
		name = getattr(info, 'group_name', None) or getattr(info, 'name', None)
	return str(name) if name else None


async def resolve_group_names(
	bot: Optional[Bot], group_ids: Sequence[str]
) -> Dict[str, str]:
	"""群名：先看数据库里 uninfo 存的，再问一下在线 bot"""
	group_ids = [str(gid) for gid in group_ids]
	names: Dict[str, str] = {}
	try:
		async with get_session() as db_session:
			rows = await db_session.execute(
				select(SceneModel.scene_id, SceneModel.scene_data).where(
					SceneModel.scene_id.in_(group_ids)
				)
			)
			for scene_id, scene_data in rows.all():
				name = _name_from_scene_data(scene_data)
				if name:
					names.setdefault(str(scene_id), name)
	except Exception as e:
		logger.debug(f'读取群名失败: {e}')

	for group_id in group_ids:
		if group_id in names:
			continue
		if group_id in _name_cache:
			names[group_id] = _name_cache[group_id]
			continue
		if bot is None:
			continue
		name = await _name_from_bot(bot, group_id)
		if name:
			names[group_id] = name
			_name_cache[group_id] = name

	return {gid: names.get(gid) or f'群 {gid}' for gid in group_ids}


async def compare_report(
	bot: Optional[Bot],
	group_ids: Sequence[str],
	period: str,
	start: datetime,
	stop: datetime,
	cfg: ScopedConfig,
	keyword: Optional[str] = None,
	top: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], bytes]:
	"""一张图里放几个群的榜单"""
	group_ids = [str(gid) for gid in group_ids]
	names = await resolve_group_names(bot, group_ids)
	limit = top or cfg.get_num
	groups: List[Dict[str, Any]] = []

	for group_id in group_ids:
		sub_cfg = effective_config(group_id)
		counts = await get_user_message_counts(
			keyword=keyword,
			scene_ids=[group_id],
			types=['message'],
			time_start=start,
			time_stop=stop,
			exclude_user_ids=sub_cfg.excluded_people,
		)
		total = sum(counts.values())
		users: List[Any] = []
		if total:
			# get_user_infos_from_db 要的是持久化 id，别提前换成平台号
			rank = got_rank(dict(counts), limit)
			users = await get_user_infos_from_db(group_id, rank)
		groups.append({'name': names[group_id], 'total': total, 'users': users})

	subtitle = f'{period} · 共 {len(groups)} 个群'
	if keyword:
		subtitle = f'“{keyword}” · {subtitle}'
	image = await render_page(
		'compare_template.j2',
		{
			'title': '多群 B 话对比',
			'subtitle': subtitle,
			'groups': groups,
			'inline_css': chart_css(cfg.theme),
		},
	)
	return groups, image


async def user_scene_counts(
	user_id: str,
	start: Optional[datetime] = None,
	stop: Optional[datetime] = None,
) -> Dict[str, int]:
	"""某个用户在各个群里说了多少"""
	whereclause = filter_statement(
		user_ids=[str(user_id)],
		types=['message'],
		time_start=start,
		time_stop=stop,
		scene_types=GROUP_SCENES,
	)
	statement = (
		_joined(select(SceneModel.scene_id, func.count(MessageRecord.id)))
		.where(*whereclause)
		.group_by(SceneModel.scene_id)
	)
	async with get_session() as db_session:
		rows = await db_session.execute(statement)
		return {str(scene_id): int(count) for scene_id, count in rows.all()}


async def member_report(
	bot: Optional[Bot],
	user_id: str,
	user_label: str,
	period: str,
	start: Optional[datetime],
	stop: Optional[datetime],
	cfg: ScopedConfig,
) -> Tuple[List[Dict[str, Any]], int, bytes]:
	"""一个成员横跨多个群的总量"""
	counts = await user_scene_counts(user_id, start, stop)
	ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
	names = await resolve_group_names(bot, [gid for gid, _ in ordered])
	items: List[Dict[str, Any]] = [
		{'label': names[group_id], 'value': count}
		for group_id, count in ordered
	]
	total = sum(counts.values())
	peak = max((int(item['value']) for item in items), default=0) or 1
	for item in items:
		item['percent'] = round(int(item['value']) / peak * 100, 1)

	image = await render_page(
		'chart_template.j2',
		{
			'title': 'TA 在各群说了多少',
			'subtitle': f'{user_label} · {period} · 共 {total} 条消息',
			'mode': 'hbar',
			'items': items,
			'footer': 'Designed By ChenXu233',
			'inline_css': chart_css(cfg.theme),
		},
	)
	return items, total, image


async def user_display_name(user_id: str) -> str:
	"""从 uninfo 的缓存里翻个昵称出来，翻不到就用 QQ 号"""
	try:
		async with get_session() as db_session:
			rows = await db_session.execute(
				select(UserModel.user_data)
				.where(UserModel.user_id == str(user_id))
				.limit(1)
			)
			data = rows.scalar_one_or_none() or {}
	except Exception as e:
		logger.debug(f'查用户 {user_id} 信息失败: {e}')
		return f'QQ {user_id}'
	if isinstance(data, dict):
		name = data.get('nick') or data.get('name')
		if name:
			return str(name)
	return f'QQ {user_id}'
