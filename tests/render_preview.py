"""把所有配色 / 排版 / 模板渲成图，改样式时用来看效果

用法：python tests/render_preview.py，图片输出到 preview/
"""

import asyncio
import io
import os

import nonebot
from PIL import Image

os.environ.setdefault('RENDER__PROVIDER', 'playwright')
nonebot.init(driver='~none')
for name in (
	'nonebot_plugin_orm',
	'nonebot_plugin_uninfo',
	'nonebot_plugin_chatrecorder',
	'nonebot_plugin_htmlrender',
	'nonebot_plugin_dialectlist',
):
	nonebot.load_plugin(name)

from nonebot_plugin_dialectlist.schema import UserRankInfo  # noqa: E402
from nonebot_plugin_dialectlist.styles import chart_css  # noqa: E402
from nonebot_plugin_dialectlist.utils import get_rank_image, render_page  # noqa: E402

OUT = 'preview'
os.makedirs(OUT, exist_ok=True)

NAMES = ['摸鱼大师', '不许加班', '早八人', '阿伟', '群里的猫', '水群第一']
COUNTS = [1823, 1440, 986, 733, 412, 208]
COLORS = [
	(255, 129, 158),
	(120, 180, 255),
	(255, 200, 100),
	(160, 220, 170),
	(190, 160, 255),
	(255, 170, 120),
]


def avatar(color):
	buffer = io.BytesIO()
	Image.new('RGB', (120, 120), color).save(buffer, format='PNG')
	return buffer.getvalue()


def make_rank():
	total = sum(COUNTS)
	rank = []
	for index, (name, count) in enumerate(zip(NAMES, COUNTS), start=1):
		rank.append(
			UserRankInfo(
				user_id=str(10000 + index),
				user_name=name,
				user_nickname=name,
				user_bnum=count,
				user_proportion=round(count / total * 100, 2),
				user_index=index,
				user_gender=['♂', '♀', '🤔'][index % 3],
				user_avatar_bytes=avatar(COLORS[index - 1]),
			)
		)
	return rank


async def save(name, coro):
	with open(f'{OUT}/{name}.png', 'wb') as f:
		f.write(await coro)
	print(name, 'ok')


async def main():
	rank = make_rank()
	for theme in ('dark', 'light', 'minimal', 'warm'):
		await save(
			f'rank-{theme}',
			get_rank_image(rank, None, theme, 'list', 'classic'),
		)
	await save('rank-light-grid', get_rank_image(rank, None, 'light', 'grid', 'classic'))
	await save('podium-dark', get_rank_image(rank, None, 'dark', 'list', 'podium'))
	await save('podium-warm', get_rank_image(rank, None, 'warm', 'list', 'podium'))

	hours = [40, 18, 9, 5, 3, 2, 8, 60, 210, 380, 420, 460,
			520, 610, 700, 660, 640, 720, 880, 1020, 1140, 980, 620, 300]
	peak = max(hours)
	items = [
		{
			'label': f'{hour:02d}',
			'value': value,
			'height': max(3, round(value / peak * 300)),
			'percent': round(value / peak * 100, 1),
		}
		for hour, value in enumerate(hours)
	]
	await save('chart-hour', render_page('chart_template.j2', {
		'title': '群消息时段分布',
		'subtitle': '摸鱼交流群 · 今日 · 共 11233 条消息',
		'mode': 'bar',
		'items': items,
		'footer': 'Designed By ChenXu233',
		'inline_css': chart_css('dark'),
	}))

	weekdays = [2100, 1980, 2400, 2260, 3100, 3900, 3500]
	peak = max(weekdays)
	items = [
		{
			'label': label,
			'value': value,
			'height': max(3, round(value / peak * 300)),
			'percent': round(value / peak * 100, 1),
		}
		for label, value in zip(
			['周一', '周二', '周三', '周四', '周五', '周六', '周日'], weekdays
		)
	]
	await save('chart-week', render_page('chart_template.j2', {
		'title': '群消息星期分布',
		'subtitle': '摸鱼交流群 · 本月 · 共 19240 条消息',
		'mode': 'bar',
		'items': items,
		'footer': 'Designed By ChenXu233',
		'inline_css': chart_css('light'),
	}))

	groups = []
	for group_name, factor in (
		('摸鱼交流群', 1.0),
		('女装爱好者', 0.75),
		('猫猫图鉴', 0.5),
	):
		users = [
			item.model_copy(update={
				'user_index': index,
				'user_bnum': int(item.user_bnum * factor),
				'user_proportion': round(item.user_proportion * factor, 2),
			})
			for index, item in enumerate(rank, start=1)
		]
		groups.append({
			'name': group_name,
			'total': sum(u.user_bnum for u in users),
			'users': users,
		})
	await save('compare', render_page('compare_template.j2', {
		'title': '多群 B 话对比',
		'subtitle': '今日 · 共 3 个群',
		'groups': groups,
		'inline_css': chart_css('dark'),
	}))

	items = [
		{'label': '摸鱼交流群', 'value': 1823, 'percent': 100.0},
		{'label': '女装爱好者', 'value': 640, 'percent': 35.1},
		{'label': '猫猫图鉴', 'value': 288, 'percent': 15.8},
		{'label': '早八人互助会', 'value': 42, 'percent': 2.3},
	]
	await save('member', render_page('chart_template.j2', {
		'title': 'TA 在各群说了多少',
		'subtitle': '摸鱼大师 · 历史 · 共 2793 条消息',
		'mode': 'hbar',
		'items': items,
		'footer': 'Designed By ChenXu233',
		'inline_css': chart_css('warm'),
	}))


asyncio.run(main())