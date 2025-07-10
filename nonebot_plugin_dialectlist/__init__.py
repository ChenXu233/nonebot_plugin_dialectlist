from nonebot import require

require('nonebot_plugin_chatrecorder')
require('nonebot_plugin_apscheduler')
require('nonebot_plugin_htmlrender')
require('nonebot_plugin_userinfo')
require('nonebot_plugin_alconna')
require('nonebot_plugin_uninfo')
require('nonebot_plugin_cesaa')

import re
import time as t
from datetime import datetime, timedelta
from typing import Optional, Union

import nonebot_plugin_saa as saa
from arclet.alconna import ArparmaBehavior
from arclet.alconna.arparma import Arparma
from nonebot import on_command
from nonebot.adapters import Bot, Event
from nonebot.log import logger
from nonebot.params import Arg, Depends
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
from nonebot_plugin_chatrecorder import get_message_records
from nonebot_plugin_uninfo import Session, Uninfo, get_session

from .config import Config, plugin_config
# from .storage import build_cache, get_cache
from .time import (
	get_datetime_fromisoformat_with_timezone,
	get_datetime_now_with_timezone,
	parse_datetime,
)
from .usage import __usage__
from .utils import (
	get_rank_image,
	get_user_infos,
	got_rank,
	msg_counter,
	persist_id2user_id,
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


build_cache_cmd = on_command('build_cache', aliases={'重建缓存'}, block=True)


@build_cache_cmd.handle()
async def _build_cache(bot: Bot, event: Event):
    return 
	await saa.Text('正在重建缓存，请稍等。').send(reply=True) # type: ignore
	await build_cache()
	await saa.Text('重建缓存完成。').send(reply=True)


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

	if keyword.available:
		keywords = keyword.result
	else:
		keywords = None

	messages = await get_message_records(
		scene_ids=[gid],
		user_ids=[id],
		types=['message'],  # 排除机器人自己发的消息
		exclude_user_ids=plugin_config.excluded_people,
	)
	d = msg_counter(messages, keywords)
	rank = got_rank(d)
	if not rank:
		await b_cmd.finish(
			f'该用户在群“{uninfo.scene.name}”关于“{keyword.result}”的B话数量为0。'
		)

	await saa.Text(
		f'该用户在群“{uninfo.scene.name}”关于“{keyword.result}”的B话数量为{rank[0][1]}。'
	).send(reply=True)


rank_cmd = on_alconna(
	Alconna(
		'B话榜',
		Args[
			'type?',
			['今日', '昨日', '本周', '上周', '本月', '上月', '年度', '历史'],
		][
			'time?',
			str,
		],
		Option('-g|--group_id', Args['group_id?', str]),
		Option('-k|--keyword', Args['keyword?', str]),
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
	dt = get_datetime_now_with_timezone()

	if not group_id:
		group_id = session.scene.id
		logger.debug(f'session id2: {group_id}')
	if group_id:
		state['group_id'] = group_id

	state['keyword'] = keyword

	if not type:
		await rank_cmd.finish(__plugin_meta__.usage)

	dt = get_datetime_now_with_timezone()

	if type == '今日':
		state['start'] = dt.replace(hour=0, minute=0, second=0, microsecond=0)
		state['stop'] = dt
	elif type == '昨日':
		state['stop'] = dt.replace(hour=0, minute=0, second=0, microsecond=0)
		state['start'] = state['stop'] - timedelta(days=1)
	elif type == '本周':
		state['start'] = dt.replace(
			hour=0, minute=0, second=0, microsecond=0
		) - timedelta(days=dt.weekday())
		state['stop'] = dt
	elif type == '上周':
		state['stop'] = dt.replace(
			hour=0, minute=0, second=0, microsecond=0
		) - timedelta(days=dt.weekday())
		state['start'] = state['stop'] - timedelta(days=7)
	elif type == '本月':
		state['start'] = dt.replace(
			day=1, hour=0, minute=0, second=0, microsecond=0
		)
		state['stop'] = dt
	elif type == '上月':
		state['stop'] = dt.replace(
			day=1, hour=0, minute=0, second=0, microsecond=0
		) - timedelta(microseconds=1)
		state['start'] = state['stop'].replace(
			day=1, hour=0, minute=0, second=0, microsecond=0
		)
	elif type == '年度':
		state['start'] = dt.replace(
			month=1, day=1, hour=0, minute=0, second=0, microsecond=0
		)
		state['stop'] = dt
	elif type == '历史':
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

	keyword = state['keyword']

	if plugin_config.counting_cache:
		await saa.Text("缓存暂不支持").finish()
		# if keyword:
		# 	await saa.Text('已开启缓存~缓存不支持关键词查询哦').finish()
		# t1 = t.time()
		# raw_rank = await get_cache(start, stop, id)
		# logger.debug(f'获取计数消息花费时间:{t.time() - t1}')
	else:
		t1 = t.time()
		messages = await get_message_records(
			scene_ids=[id],
			types=['message'],  # 排除机器人自己发的消息
			time_start=start,
			time_stop=stop,
			exclude_user_ids=plugin_config.excluded_people,
		)
		raw_rank = msg_counter(messages, keyword)
		logger.debug(f'获取计数消息花费时间:{t.time() - t1}')

	if not raw_rank:
		await saa.Text(
			'没有获取到排行榜数据哦，请确认时间范围和群号是否正确或者关键词是否存在~'
		).finish()

	rank = got_rank(raw_rank)
	ids = await persist_id2user_id([int(i[0]) for i in rank])
	for i in range(len(rank)):
		rank[i][0] = str(ids[i])
		logger.debug(rank[i])

	t1 = t.time()
	rank2 = await get_user_infos(bot, event, rank)
	logger.debug(f'获取用户信息花费时间:{t.time() - t1}')

	string: str = ''
	if plugin_config.show_text_rank:
		if keyword:
			string += f'关于{keyword}的话痨榜结果：\n'
		else:
			string += '话痨榜：\n'

		for i in rank2:
			logger.debug(i.user_name)
		for i in range(len(rank2)):
			str_example = plugin_config.string_format.format(
				index=rank2[i].user_index,
				nickname=rank2[i].user_nickname,
				chatdatanum=rank2[i].user_bnum,
			)
			string += str_example

	msg = saa.Text(string)

	if plugin_config.visualization:
		t1 = t.time()
		image = await get_rank_image(rank2)
		msg += saa.Image(image)
		logger.debug(f'群聊消息渲染图片花费时间:{t.time() - t1}')

	if plugin_config.suffix:
		timecost = t.time() - state['t1']
		suffix = saa.Text(plugin_config.string_suffix.format(timecost=timecost))
		msg += suffix
	if not msg:
		await saa.Text('你把可视化都关了哪来的排行榜？').finish()

	if plugin_config.aggregate_transmission:
		await saa.AggregatedMessageFactory([msg]).finish()
	else:
		await msg.finish(reply=True)
