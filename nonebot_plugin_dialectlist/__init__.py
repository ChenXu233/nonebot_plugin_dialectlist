from nonebot import get_driver, require

from .render_env import TROUBLESHOOTING, ensure_render_backend

# 必须在 htmlrender 被 require 之前：0.8+ 没有默认渲染后端，这里补默认值
ensure_render_backend()

require('nonebot_plugin_chatrecorder')
require('nonebot_plugin_htmlrender')
require('nonebot_plugin_userinfo')
require('nonebot_plugin_alconna')
require('nonebot_plugin_uninfo')
require('nonebot_plugin_saa')
require('nonebot_plugin_apscheduler')
require('nonebot_plugin_localstore')

import re
import time as t
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import nonebot_plugin_saa as saa
from arclet.alconna import ArparmaBehavior, MultiVar
from arclet.alconna.arparma import Arparma
from nonebot import on_command
from nonebot.adapters import Bot, Event, Message
from nonebot.log import logger
from nonebot.params import Arg, CommandArg, Depends
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot.typing import T_State
from nonebot_plugin_alconna import (
	Alconna,
	Args,
	At,
	Field,
	Match,
	Option,
	on_alconna,
)
from nonebot_plugin_uninfo import Session, Uninfo, get_session

from .charts import (
	WEEKDAY_LABELS,
	compare_report,
	histogram_report,
	member_report,
	resolve_group_names,
	user_display_name,
)
from .config import Config, plugin_config
from .group_config import effective_config, resolve_push_config, store
from .push import register_push_jobs
from .templates import (
	describe as describe_templates,
	find_template,
	get_template,
	list_templates,
)
from .styles import (
	find_layout,
	find_theme,
	get_layout,
	get_theme,
	list_layouts,
	list_themes,
	theme_list,
)
from .time import (
	get_datetime_fromisoformat_with_timezone,
	get_datetime_now_with_timezone,
	parse_datetime,
	resolve_period_range,
)
from .usage import __usage__
from .utils import (
	RenderError,
	close_http_client,
	warmup_http_client,
	format_rank_text,
	get_rank_image,
	get_user_infos,
	got_rank,
	persist_id2user_id,
	get_previous_message_counts,
	get_user_message_counts,
)

__plugin_meta__ = PluginMetadata(
	name='B话排行榜',
	description='调查群U的B话数量，以一定的顺序排序后排序出来。',
	usage=__usage__,
	homepage='https://github.com/ChenXu233/nonebot_plugin_dialectlist',
	type='application',
	supported_adapters=inherit_supported_adapters(
		'nonebot_plugin_chatrecorder',
		'nonebot_plugin_saa',
		'nonebot_plugin_alconna',
	),
	config=Config,
)


# 抄的词云，不过真的很适合B话榜。
class SameTime(ArparmaBehavior):
	def operate(self, interface: Arparma):
		type = interface.query('type')
		time = interface.query('time')
		if type is None and time:
			interface.behave_fail()


def wrapper(slot: Union[int, str], content: Optional[str], context) -> str:
	if slot == 'type' and content:
		return content
	return ''  # pragma: no cover


b_cmd = on_alconna(
	Alconna(
		'看看B话',
		Args['at', [str, At], Field(completion=lambda: '请想要查询的人的QQ号')],
		Option('-g|--group_id', Args['group_id?', str]),
		Option('-k|--keyword', Args['keyword?', str]),
	),
	aliases={'kkb'},
	use_cmd_start=True,
)


@b_cmd.handle()
async def handle_b_cmd(
	at: Match[str | At],
	group_id: Match[str],
	keyword: Match[str],
	uninfo: Uninfo,
	session: Session = Depends(get_session),
):
	id = at.result
	if isinstance(id, At):
		id = id.target
	if group_id.available:
		gid = group_id.result
	else:
		gid = session.scene.id

	if not gid:
		await b_cmd.finish('请指定群号。')

	cfg = effective_config(str(gid))
	if not cfg.enabled:
		await b_cmd.finish('这个群的排行榜功能被关掉了，找管理员开一下。')

	# 未使用 -k 时 Match.result 为 None，不能直接拼进文案
	keyword_text = keyword.result if keyword.available else None
	keyword_desc = f'关于“{keyword_text}”的' if keyword_text else ''

	d = await get_user_message_counts(
		keyword=keyword_text,
		scene_ids=[gid],
		user_ids=[id],
		types=['message'],  # 只统计收到的消息，机器人自己发的不计入
		exclude_user_ids=cfg.excluded_people,
	)

	rank = got_rank(d)
	if not rank:
		await b_cmd.finish(
			f'该用户在群“{uninfo.scene.name}”{keyword_desc}B话数量为0。'
		)

	await saa.Text(
		f'该用户在群“{uninfo.scene.name}”{keyword_desc}B话数量为{rank[0][1]}。'
	).send(reply=True)


rank_cmd = on_alconna(
	Alconna(
		'B话榜',
		Args[
			'type?',
			[
				'今日',
				'昨日',
				'本周',
				'上周',
				'本月',
				'上月',
				'年度',
				'历史',
				'帮助',
			],
		][
			'time?',
			str,
		],
		Option('-g|--group_id', Args['group_id?', str]),
		Option('-k|--keyword', Args['keyword?', str]),
		Option('-m|--template', Args['template?', str]),
		behaviors=[SameTime()],
	),
	aliases={'废话榜'},
	use_cmd_start=True,
	block=True,
)


rank_cmd.shortcut(
	r'(?P<type>今日|昨日|本周|上周|本月|上月|年度|历史)B话榜',
	{
		'prefix': True,
		'command': 'B话榜',
		'wrapper': wrapper,
		'args': ['{type}'],
	},
)
rank_cmd.shortcut(
	r'(?P<type>今日|昨日|本周|上周|本月|上月|年度|历史)废话榜',
	{
		'prefix': True,
		'command': '废话榜',
		'wrapper': wrapper,
		'args': ['{type}'],
	},
)


# 这段函数完全抄的词云
@rank_cmd.handle()
async def _group_message(
	state: T_State,
	session: Session = Depends(get_session),
	type: Optional[str] = None,
	time: Optional[str] = None,
	group_id: Optional[str] = None,
	keyword: Optional[str] = None,
):
	t1 = t.time()
	state['t1'] = t1

	if not group_id:
		group_id = session.scene.id
		logger.debug(f'session id2: {group_id}')
	if group_id:
		state['group_id'] = group_id

	state['keyword'] = keyword
	state['period'] = type

	if not type or type == '帮助':
		await rank_cmd.finish(__plugin_meta__.usage)

	dt = get_datetime_now_with_timezone()

	if type == '历史':
		if time:
			plaintext = time
			if match := re.match(r'^(.+?)(?:~(.+))?$', plaintext):
				start = match[1]
				stop = match[2]
				try:
					state['start'] = get_datetime_fromisoformat_with_timezone(
						start
					)
					if stop:
						state['stop'] = (
							get_datetime_fromisoformat_with_timezone(stop)
						)
					else:
						# 如果没有指定结束日期，则认为是所给日期的当天的词云
						state['start'] = state['start'].replace(
							hour=0, minute=0, second=0, microsecond=0
						)
						state['stop'] = state['start'] + timedelta(days=1)
				except ValueError:
					await rank_cmd.finish(
						'请输入正确的日期，不然我没法理解呢！'
					)
		else:
			# 没给日期就是全部历史，别去问用户要日期
			state['start'] = None
			state['stop'] = None
	else:
		time_range = resolve_period_range(type, dt)
		if time_range is None:
			await rank_cmd.finish(f'不认识的时间类型：{type}')
		state['start'], state['stop'] = time_range


@rank_cmd.got(
	'start',
	prompt='请输入你要查询的起始日期（如 2022-01-01）',
	parameterless=[Depends(parse_datetime('start'))],
)
@rank_cmd.got(
	'stop',
	prompt='请输入你要查询的结束日期（如 2022-02-22）',
	parameterless=[Depends(parse_datetime('stop'))],
)
@rank_cmd.got('group_id', prompt='请输入你要查询的群号。')
async def handle_rank(
	state: T_State,
	bot: Bot,
	event: Event,
	template: Match[str],
	session: Session = Depends(get_session),
	start: datetime = Arg(),
	stop: datetime = Arg(),
):
	if id := state['group_id']:
		id = str(id)
		logger.debug(f'group_id: {id}')
	else:
		id = session.scene.id
		logger.debug(f'group_id: {id}')

	if not id:
		await saa.Text('没有指定群哦').finish()

	cfg = effective_config(str(id))
	if not cfg.enabled:
		await saa.Text('这个群的排行榜功能被关掉了，找管理员开一下。').finish()

	# -m 只在这一次生效，不改群配置
	chosen = template.result if getattr(template, 'available', False) else None
	if chosen and find_template(chosen) is None:
		await saa.Text(
			f'没有「{chosen}」这个模板。\n\n{describe_templates()}'
		).finish()

	keyword = state['keyword']

	t1 = t.time()
	raw_rank = await get_user_message_counts(
		keyword=keyword,
		scene_ids=[id],
		types=['message'],  # 排除机器人自己发的消息
		time_start=start,
		time_stop=stop,
		exclude_user_ids=cfg.excluded_people,
	)
	logger.debug(f'获取计数消息花费时间:{t.time() - t1}')

	if not raw_rank:
		await saa.Text(
			'没有获取到排行榜数据哦，请确认时间范围和群号是否正确或者关键词是否存在~'
		).finish()

	rank = got_rank(raw_rank, cfg.get_num)
	# 必须按 user_persist_id 精确映射，不能依赖查询返回顺序
	persist_ids = [item[0] for item in rank]
	id_map = await persist_id2user_id(persist_ids)
	for item in rank:
		user_id = id_map.get(item[0])
		if user_id is None:
			logger.warning(f'未找到持久化 id {item[0]} 对应的平台用户')
			user_id = str(item[0])
		item[0] = user_id
		logger.debug(item)

	t1 = t.time()
	previous_counts = None
	if cfg.show_delta:
		previous_counts = await get_previous_message_counts(
			state.get('period'),
			start,
			stop,
			[str(id)],
			keyword=keyword,
			exclude_user_ids=cfg.excluded_people,
		)
	rank2 = await get_user_infos(
		bot,
		event,
		rank,
		cfg.use_user_info_cache,
		previous_counts,
		persist_ids,
	)
	logger.debug(f'获取用户信息花费时间:{t.time() - t1}')

	string = format_rank_text(rank2, keyword, cfg)
	msg = saa.Text(string)

	if cfg.visualization:
		t1 = t.time()
		try:
			image = await get_rank_image(
				rank2,
				cfg.template_path,
				cfg.theme,
				cfg.layout,
				chosen or cfg.template,
			)
		except RenderError as e:
			logger.error(TROUBLESHOOTING)
			msg += saa.Text(
				f'\n（图片渲染失败：{e}，管理员可以在日志里看到排查步骤）'
			)
		else:
			msg += saa.Image(image)
			logger.debug(f'群聊消息渲染图片花费时间:{t.time() - t1}')

	if cfg.suffix:
		timecost = t.time() - state['t1']
		suffix = saa.Text(cfg.string_suffix.format(timecost=timecost))
		msg += suffix
	if not msg:
		await saa.Text('你把可视化都关了哪来的排行榜？').finish()

	if plugin_config.aggregate_transmission:
		await saa.AggregatedMessageFactory([msg]).finish()
	else:
		await msg.finish(reply=True)


@get_driver().on_startup
async def _register_push_jobs() -> None:
	"""启动时按配置注册定时推送任务"""
	register_push_jobs()


@get_driver().on_startup
async def _warmup_avatars_http_client() -> None:
	"""启动时预建头像连接池，别把首次建连算进第一条命令"""
	try:
		await warmup_http_client()
	except Exception as e:  # noqa: BLE001 - 代理配置坏了也不能拦启动
		logger.warning(f'[dialectlist] 头像下载连接池初始化失败: {e}')


@get_driver().on_shutdown
async def _close_avatars_http_client() -> None:
	"""退出时关掉头像下载共用的连接池"""
	await close_http_client()


# ---------------- 群配置 ----------------

_CONFIG_KEYS: Dict[str, str] = {
	'开关': 'enabled',
	'启用': 'enabled',
	'enabled': 'enabled',
	'模板': 'template',
	'template': 'template',
	'模板路径': 'template_path',
	'template_path': 'template_path',
	'样式': 'theme',
	'主题': 'theme',
	'配色': 'theme',
	'theme': 'theme',
	'布局': 'layout',
	'排版': 'layout',
	'layout': 'layout',
	'人数': 'get_num',
	'get_num': 'get_num',
	'图片': 'visualization',
	'visualization': 'visualization',
	'文字': 'show_text_rank',
	'show_text_rank': 'show_text_rank',
	'后缀': 'suffix',
	'suffix': 'suffix',
	'排除': 'excluded_people',
	'excluded_people': 'excluded_people',
	'环比': 'show_delta',
	'show_delta': 'show_delta',
	'推送': 'push_enabled',
	'push_enabled': 'push_enabled',
	'推送时间': 'push_cron',
	'push_cron': 'push_cron',
	'推送区间': 'push_period',
	'push_period': 'push_period',
	'推送阈值': 'push_min_messages',
	'push_min_messages': 'push_min_messages',
	'推送群人数': 'push_min_members',
	'push_min_members': 'push_min_members',
	'推送人数': 'push_get_num',
	'push_get_num': 'push_get_num',
}

_BOOL_TRUE = {'1', '开', '开启', 'on', 'true', 'yes', '是'}
_BOOL_FALSE = {'0', '关', '关闭', 'off', 'false', 'no', '否', '禁用'}
_BOOL_KEYS = {
	'enabled',
	'visualization',
	'show_text_rank',
	'suffix',
	'show_delta',
	'push_enabled',
}
_INT_KEYS = {'get_num', 'push_min_messages', 'push_min_members', 'push_get_num'}

_CONFIG_DESC: Dict[str, str] = {
	'enabled': '这个群是否允许排行榜（查询和推送都会停）',
	'template': '这个群用哪套模板（/B话榜模板 可以看有哪些）',
	'template_path': '直接指定模板文件的老写法，填了就优先用这个文件',
	'theme': '图片配色：暗夜 / 浅色 / 简约 / 暖阳',
	'layout': '图片排版：竖排 / 横排',
	'get_num': '榜单展示人数',
	'visualization': '是否输出排行榜图片',
	'show_text_rank': '是否输出文字榜单',
	'suffix': '是否显示统计耗时',
	'excluded_people': '统计时排除的 QQ 号，逗号分隔，清空 = 取消',
	'show_delta': '榜单里显示和上一期比的名次变化（↑2 / ↓1 / 新）',
	'push_enabled': '这个群是否定时推送',
	'push_cron': '推送时间，5 段式 cron，如 0 8 * * *',
	'push_period': '推送统计区间：今日/昨日/本周/上周/本月/上月/年度',
	'push_min_messages': '推送的消息量下限',
	'push_min_members': '推送的群人数下限',
	'push_get_num': '推送榜单的人数',
}


def _config_help() -> str:
	lines = [
		'B话榜群配置',
		'',
		'用法：',
		'  /B话榜配置              查看当前群的配置',
		'  /B话榜配置 <键>         查看某一项',
		'  /B话榜配置 <键> <值>    改某一项',
		'  /B话榜配置 重置         恢复成全局默认',
		'  /B话榜重载              重新读配置文件并刷新定时任务',
		'',
		'可用的键（中英文都行）：',
	]
	seen: set[str] = set()
	for name, key in _CONFIG_KEYS.items():
		if key in seen:
			continue
		seen.add(key)
		names = [n for n, k in _CONFIG_KEYS.items() if k == key]
		lines.append(f'  {" / ".join(names)}：{_CONFIG_DESC[key]}')
	lines += [
		'',
		'例子：',
		'  /B话榜配置 人数 3',
		'  /B话榜配置 排除 123456,789012',
		'  /B话榜配置 推送时间 0 8 * * *',
		'  /B话榜配置 推送区间 本周',
	]
	return '\n'.join(lines)


def _is_admin(event: Event, session: Session) -> bool:
	"""超级用户，或者群管理/群主"""
	if str(session.user.id) in {str(u) for u in get_driver().config.superusers}:
		return True
	sender = getattr(event, 'sender', None)
	if getattr(sender, 'role', None) in ('admin', 'owner'):
		return True
	member = getattr(session, 'member', None)
	for role in getattr(member, 'roles', None) or []:
		if getattr(role, 'id', None) in ('admin', 'owner'):
			return True
	return False


def _parse_config_value(key: str, raw: str) -> Any:
	text = raw.strip()
	if key in _BOOL_KEYS:
		lowered = text.lower()
		if lowered in _BOOL_TRUE:
			return True
		if lowered in _BOOL_FALSE:
			return False
		raise ValueError('请用 开 / 关')
	if key in _INT_KEYS:
		value = int(text)
		if value < 0:
			raise ValueError('不能是负数')
		return value
	if key == 'excluded_people':
		if text in ('清空', '空', 'none', ''):
			return []
		return [p for p in re.split(r'[,，\s]+', text) if p]
	if key == 'push_period':
		if resolve_period_range(text, get_datetime_now_with_timezone()) is None:
			raise ValueError('只能是 今日/昨日/本周/上周/本月/上月/年度')
		return text
	if key == 'push_cron':
		if len(text.split()) != 5:
			raise ValueError('cron 需要 5 段，比如 0 8 * * *')
		return text
	if key == 'template':
		template = find_template(text)
		if template is None:
			raise ValueError(
				'可选：' + '、'.join(t.name for t in list_templates().values())
			)
		return template.name
	if key == 'theme':
		theme = find_theme(text)
		if theme is None:
			raise ValueError(
				'可选：' + '、'.join(t.name for t in list_themes().values())
			)
		return theme.id
	if key == 'layout':
		layout = find_layout(text)
		if layout is None:
			raise ValueError(
				'可选：' + '、'.join(g.name for g in list_layouts().values())
			)
		return layout.id
	return text


def _format_group_config(group_id: str) -> str:
	group = store.get(group_id)
	cfg = effective_config(group_id)
	push_cfg = resolve_push_config(group_id)

	def on_off(value: bool) -> str:
		return '开' if value else '关'

	rows = [
		('开关', on_off(cfg.enabled), group.enabled),
		(
			'模板',
			get_template(cfg.template).title
			if not cfg.template_path
			else f'文件 {cfg.template_path}',
			group.template or group.template_path,
		),
		(
			'样式',
			f'{get_theme(cfg.theme).name} / {get_layout(cfg.layout).name}',
			(group.theme or group.layout),
		),
		('人数', str(cfg.get_num), group.get_num),
		('图片', on_off(cfg.visualization), group.visualization),
		('文字', on_off(cfg.show_text_rank), group.show_text_rank),
		('后缀', on_off(cfg.suffix), group.suffix),
		('排除', ','.join(cfg.excluded_people) or '无', group.excluded_people),
		('环比', on_off(cfg.show_delta), group.show_delta),
	]
	if push_cfg is None:
		rows.append(('推送', '关', group.push_enabled))
	else:
		period = push_cfg.period or plugin_config.push_period
		cron = push_cfg.cron or plugin_config.push_cron
		rows.append(('推送', f'开（{cron}，{period}）', group.push_enabled))
	if group.push_target:
		rows.append(
			(
				'推送目标',
				str(group.push_target.get('platform_type') or '未知'),
				group.push_target,
			)
		)

	lines = [f'群 {group_id} 的配置：']
	for name, value, override in rows:
		lines.append(f'{"*" if override is not None else " "} {name}: {value}')
	lines.append('')
	lines.append('带 * 的是这个群单独改过的，其余跟随全局配置。')
	lines.append(f'配置文件：{store.path}')
	return '\n'.join(lines)


def _remember_push_target(
	event: Event, bot: Bot, group_id: str, force: bool = False
) -> None:
	"""把当前会话的 SAA 发送目标记到群配置里，定时推送才不限于 QQ 群"""
	existing = store.get(group_id).push_target
	if existing and not force:
		return
	if not force and resolve_push_config(group_id) is None:
		# 没开推送的群不用记，等真的开了再存
		return
	try:
		target = saa.get_target(event, bot)
	except Exception as e:  # noqa: BLE001 - 平台没注册提取器很正常
		logger.debug(f'[dialectlist] 取当前会话的推送目标失败: {e}')
		return
	if target is None:
		return
	try:
		payload = (
			target.model_dump(mode='json')
			if hasattr(target, 'model_dump')
			else target.dict()
		)
	except Exception as e:  # noqa: BLE001
		logger.debug(f'[dialectlist] 序列化推送目标失败: {e}')
		return
	if payload == existing:
		return
	store.update(group_id, push_target=payload)
	logger.info(
		f'[dialectlist] 已记录群 {group_id} 的推送目标: '
		f'{payload.get("platform_type")}'
	)


config_cmd = on_command(
	'B话榜配置', aliases={'话痨榜配置', 'b话榜配置'}, block=True, priority=5
)


@config_cmd.handle()
async def handle_group_config(
	event: Event,
	bot: Bot,
	args: Message = CommandArg(),
	session: Session = Depends(get_session),
):
	if session.scene.is_private:
		await config_cmd.finish('这个指令要在群里用哦。')
	if not _is_admin(event, session):
		await config_cmd.finish('只有群主、管理员和 bot 主人能改配置。')

	group_id = str(session.scene.id)
	# 推送开着但还没存目标的老群，随便发一次配置命令就把目标补上
	_remember_push_target(event, bot, group_id)
	text = args.extract_plain_text().strip()

	if not text or text in ('查看', '列表', 'list'):
		await config_cmd.finish(_format_group_config(group_id))
	if text in ('帮助', 'help', '?', '-h', '用法'):
		await config_cmd.finish(_config_help())
	if text in ('重置', '清空', 'reset'):
		store.reset(group_id)
		register_push_jobs()
		await config_cmd.finish(f'群 {group_id} 的配置已重置为全局默认。')

	parts = text.split(maxsplit=1)
	key = _CONFIG_KEYS.get(parts[0].lower()) or _CONFIG_KEYS.get(parts[0])
	if key is None:
		await config_cmd.finish(
			'不认识的配置项，可用：'
			+ '、'.join(dict.fromkeys(_CONFIG_KEYS.keys()))
		)

	if len(parts) == 1:
		await config_cmd.finish(_format_group_config(group_id))

	try:
		value = _parse_config_value(key, parts[1])
	except ValueError as e:
		await config_cmd.finish(f'{parts[0]} 的值不对：{e}')

	store.update(group_id, **{key: value})
	if key.startswith('push_'):
		_remember_push_target(event, bot, group_id, force=True)
	if key == 'enabled' or key.startswith('push_'):
		register_push_jobs()
	await config_cmd.finish(
		f'已把 {parts[0]} 设为 {value}，立即生效。\n\n'
		+ _format_group_config(group_id)
	)


reload_cmd = on_command(
	'B话榜重载', aliases={'话痨榜重载'}, block=True, priority=5
)


@reload_cmd.handle()
async def handle_reload(
	event: Event,
	session: Session = Depends(get_session),
):
	if not _is_admin(event, session):
		await reload_cmd.finish('只有群主、管理员和 bot 主人能用这个指令。')
	store.reload()
	register_push_jobs()
	await reload_cmd.finish(
		f'已重新读取 {len(store.all())} 个群的配置，定时任务已刷新。'
	)


# ---------------- 帮助 ----------------


help_cmd = on_command(
	'B话榜帮助',
	aliases={'话痨榜帮助', '排行榜帮助', 'B话榜用法'},
	block=True,
	priority=5,
)


@help_cmd.handle()
async def handle_help():
	await help_cmd.finish(__plugin_meta__.usage)


# ---------------- 样式 / 模板预览 ----------------


async def _preview_image(
	bot: Bot,
	event: Event,
	session: Session,
	cfg: Any,
	theme: Optional[str],
	layout: Optional[str],
	template: Optional[str],
	template_path: Optional[str] = None,
) -> Any:
	"""拿今天的数据渲一张预览图，今天没消息就退回历史"""
	now = get_datetime_now_with_timezone()
	period = '今日'
	start, stop = resolve_period_range(period, now) or (now, now)
	counts = await get_user_message_counts(
		scene_ids=[session.scene.id],
		types=['message'],
		time_start=start,
		time_stop=stop,
		exclude_user_ids=cfg.excluded_people,
	)
	if not counts:
		# 今天还没人说话，就用历史数据凑一张，不然预览是白图
		period = '历史'
		start = stop = None
		counts = await get_user_message_counts(
			scene_ids=[session.scene.id],
			types=['message'],
			exclude_user_ids=cfg.excluded_people,
		)
	if not counts:
		return None

	rank = got_rank(counts, cfg.get_num)
	persist_ids = [item[0] for item in rank]
	id_map = await persist_id2user_id(persist_ids)
	for item in rank:
		item[0] = id_map.get(item[0], str(item[0]))
	previous_counts = None
	if cfg.show_delta:
		previous_counts = await get_previous_message_counts(
			period,
			start,
			stop,
			[session.scene.id],
			exclude_user_ids=cfg.excluded_people,
		)
	rank2 = await get_user_infos(
		bot,
		event,
		rank,
		cfg.use_user_info_cache,
		previous_counts,
		persist_ids,
	)
	return await get_rank_image(rank2, template_path, theme, layout, template)


style_cmd = on_command(
	'B话榜样式', aliases={'话痨榜样式', '排行榜样式'}, block=True, priority=5
)


@style_cmd.handle()
async def handle_style(
	bot: Bot,
	event: Event,
	args: Message = CommandArg(),
	session: Session = Depends(get_session),
):
	if session.scene.is_private:
		await style_cmd.finish('这个指令要在群里用哦。')

	cfg = effective_config(str(session.scene.id))
	text = args.extract_plain_text().strip()
	if not text:
		await style_cmd.finish(
			f'当前群是 {get_theme(cfg.theme).name} / {get_layout(cfg.layout).name}'
			f'\n\n{theme_list()}'
		)

	parts = text.split()
	theme = find_theme(parts[0])
	if theme is None:
		await style_cmd.finish(
			f'没有「{parts[0]}」这个样式。\n\n{theme_list()}'
		)
	layout = get_layout(cfg.layout)
	if len(parts) > 1:
		picked = find_layout(parts[1])
		if picked is None:
			await style_cmd.finish(
				f'没有「{parts[1]}」这种排版。\n\n{theme_list()}'
			)
		layout = picked

	try:
		image = await _preview_image(
			bot,
			event,
			session,
			cfg,
			theme.id,
			layout.id,
			cfg.template,
			cfg.template_path,
		)
	except RenderError as e:
		logger.error(TROUBLESHOOTING)
		await style_cmd.finish(f'渲染失败：{e}')
	if image is None:
		await style_cmd.finish('这个群还没有聊天记录，没法预览。')

	hint = f'\n\n样式预览：{theme.name} / {layout.name}'
	if theme.id != get_theme(cfg.theme).id:
		hint += f'\n想用就发 /B话榜配置 样式 {theme.name}'
	if layout.id != get_layout(cfg.layout).id:
		hint += f'\n排版就用 /B话榜配置 布局 {layout.name}'
	await (saa.Image(image) + saa.Text(hint)).finish(reply=True)


template_cmd = on_command(
	'B话榜模板', aliases={'话痨榜模板', '排行榜模板'}, block=True, priority=5
)


@template_cmd.handle()
async def handle_template(
	bot: Bot,
	event: Event,
	args: Message = CommandArg(),
	session: Session = Depends(get_session),
):
	if session.scene.is_private:
		await template_cmd.finish('这个指令要在群里用哦。')

	cfg = effective_config(str(session.scene.id))
	text = args.extract_plain_text().strip()
	if not text:
		current = get_template(cfg.template)
		await template_cmd.finish(
			f'当前群用的是「{current.title}」（{current.name}）'
			f'\n\n{describe_templates()}'
		)

	chosen = find_template(text)
	if chosen is None:
		await template_cmd.finish(
			f'没有「{text}」这个模板。\n\n{describe_templates()}'
		)

	try:
		image = await _preview_image(
			bot,
			event,
			session,
			cfg,
			cfg.theme,
			cfg.layout,
			chosen.name,
		)
	except RenderError as e:
		logger.error(TROUBLESHOOTING)
		await template_cmd.finish(f'渲染失败：{e}')
	if image is None:
		await template_cmd.finish('这个群还没有聊天记录，没法预览。')

	hint = f'\n\n模板预览：{chosen.title}（{chosen.name}）'
	if chosen.name != get_template(cfg.template).name:
		hint += f'\n想用就发 /B话榜配置 模板 {chosen.name}'
	await (saa.Image(image) + saa.Text(hint)).finish(reply=True)


# ---------------- 分布图 ----------------


dist_cmd = on_alconna(
	Alconna(
		'B话榜分布',
		Args['type?', ['今日', '昨日', '本周', '上周', '本月', '上月', '年度']][
			'dim?', ['小时', '星期']
		],
		Option('-g|--group_id', Args['group_id?', str]),
		Option('-k|--keyword', Args['keyword?', str]),
	),
	aliases={'话痨榜分布'},
	use_cmd_start=True,
	block=True,
)


@dist_cmd.handle()
async def handle_dist(
	bot: Bot,
	type: Optional[str] = None,
	dim: Optional[str] = None,
	group_id: Optional[str] = None,
	keyword: Optional[str] = None,
	session: Session = Depends(get_session),
):
	gid = str(group_id or session.scene.id)
	cfg = effective_config(gid)
	if not cfg.enabled:
		await dist_cmd.finish('这个群的排行榜功能被关掉了，找管理员开一下。')

	period = type or '今日'
	mode = 'week' if dim in ('星期', '周', 'week') else 'hour'
	now = get_datetime_now_with_timezone()
	time_range = resolve_period_range(period, now)
	if time_range is None:
		await dist_cmd.finish(f'不认识的时间类型：{period}')
	start, stop = time_range

	names = await resolve_group_names(bot, [gid])
	try:
		values, image = await histogram_report(
			[gid], names[gid], period, start, stop, mode, cfg, keyword
		)
	except RenderError as e:
		logger.error(TROUBLESHOOTING)
		await dist_cmd.finish(f'渲染失败：{e}')

	total = sum(values)
	if total <= 0:
		await dist_cmd.finish('这段时间没有消息，画不出来。')

	peak_index = max(range(len(values)), key=lambda index: values[index])
	peak_label = (
		f'{peak_index:02d} 点' if mode == 'hour' else WEEKDAY_LABELS[peak_index]
	)
	await (
		saa.Image(image)
		+ saa.Text(
			f'\n{names[gid]} · {period} · 共 {total} 条\n'
			f'{"时段" if mode == "hour" else "星期"}扛把子是 {peak_label}，'
			f'{values[peak_index]} 条'
		)
	).finish(reply=True)


# ---------------- 多群对比 ----------------


compare_cmd = on_alconna(
	Alconna(
		'B话榜对比',
		Args['groups', MultiVar(str, '+')],
		Option(
			'-t|--time',
			Args[
				'type?',
				['今日', '昨日', '本周', '上周', '本月', '上月', '年度'],
			],
		),
		Option('-k|--keyword', Args['keyword?', str]),
	),
	aliases={'多群B话榜', 'B话榜多群'},
	use_cmd_start=True,
	block=True,
)

MAX_COMPARE = 6


@compare_cmd.handle()
async def handle_compare(
	bot: Bot,
	groups: List[str],
	type: Optional[str] = None,
	keyword: Optional[str] = None,
	session: Session = Depends(get_session),
):
	group_ids = [str(gid).strip() for gid in groups if str(gid).strip()]
	if len(group_ids) < 2:
		await compare_cmd.finish(
			'至少给两个群号才有对比的意义吧，比如 /B话榜对比 123 456'
		)
	note = ''
	if len(group_ids) > MAX_COMPARE:
		group_ids = group_ids[:MAX_COMPARE]
		note = f'\n（一次最多对比 {MAX_COMPARE} 个群，多的下次再发）'

	period = type or '今日'
	now = get_datetime_now_with_timezone()
	time_range = resolve_period_range(period, now)
	if time_range is None:
		await compare_cmd.finish(f'不认识的时间类型：{period}')
	start, stop = time_range

	enabled = [gid for gid in group_ids if effective_config(gid).enabled]
	if len(enabled) < 2:
		await compare_cmd.finish(
			'这些群里能查的不够两个，先把关了排行榜的群开了。'
		)

	cfg = effective_config(enabled[0])
	# 群一多就少列几个人，不然图会长到没法看
	top = min(cfg.get_num, max(3, 18 // len(enabled)))
	try:
		rows, image = await compare_report(
			bot, enabled, period, start, stop, cfg, keyword, top
		)
	except RenderError as e:
		logger.error(TROUBLESHOOTING)
		await compare_cmd.finish(f'渲染失败：{e}')

	summary = '\n'.join(f'{row["name"]}：{row["total"]} 条' for row in rows)
	await (
		saa.Image(image) + saa.Text(f'\n{period} · 多群对比{note}\n{summary}')
	).finish(reply=True)


# ---------------- 成员跨群 ----------------


member_cmd = on_alconna(
	Alconna(
		'B话榜成员',
		Args['at', [str, At], Field(completion=lambda: '请想查询的人的QQ号')],
		Args[
			'type?',
			['今日', '昨日', '本周', '上周', '本月', '上月', '年度', '历史'],
		],
	),
	aliases={'成员B话榜', '多群成员B话'},
	use_cmd_start=True,
	block=True,
)


@member_cmd.handle()
async def handle_member(
	bot: Bot,
	at: Match[Union[str, At]],
	type: Optional[str] = None,
	session: Session = Depends(get_session),
):
	user_id = at.result
	if isinstance(user_id, At):
		user_id = user_id.target
	if not user_id:
		await member_cmd.finish('要 @ 一下或者给个 QQ 号。')

	period = type or '历史'
	start: Optional[datetime] = None
	stop: Optional[datetime] = None
	if period != '历史':
		now = get_datetime_now_with_timezone()
		time_range = resolve_period_range(period, now)
		if time_range is None:
			await member_cmd.finish(f'不认识的时间类型：{period}')
		start, stop = time_range

	cfg = effective_config(str(session.scene.id))
	label = await user_display_name(str(user_id))
	try:
		rows, total, image = await member_report(
			bot, str(user_id), label, period, start, stop, cfg
		)
	except RenderError as e:
		logger.error(TROUBLESHOOTING)
		await member_cmd.finish(f'渲染失败：{e}')

	if not rows:
		await member_cmd.finish(f'没有找到 {label} 的聊天记录。')

	top = rows[0]
	await (
		saa.Image(image)
		+ saa.Text(
			f'\n{label} · {period} · 一共 {total} 条\n'
			f'在「{top["label"]}」说得最多，{top["value"]} 条'
		)
	).finish(reply=True)
