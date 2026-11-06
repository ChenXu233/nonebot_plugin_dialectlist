"""环比（名次变化）的单元测试：上一期区间 + 名次差

仓库没有引入 pytest，这个文件可以直接跑：

    .venv\\Scripts\\python.exe tests/test_delta.py
"""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_TMP = Path(tempfile.mkdtemp(prefix='dialectlist-delta-'))
os.environ['SQLALCHEMY_DATABASE_URL'] = (
	f'sqlite+aiosqlite:///{_TMP / "test.sqlite3"}'
)
os.environ['ALEMBIC_STARTUP_CHECK'] = 'false'
os.environ.setdefault('RENDER__PROVIDER', 'playwright')

import nonebot  # noqa: E402

nonebot.init(driver='~none')
for _plugin in (
	'nonebot_plugin_orm',
	'nonebot_plugin_uninfo',
	'nonebot_plugin_chatrecorder',
	'nonebot_plugin_htmlrender',
	'nonebot_plugin_dialectlist',
):
	nonebot.load_plugin(_plugin)

from nonebot_plugin_dialectlist.time import previous_period_range  # noqa: E402
from nonebot_plugin_dialectlist.utils import (  # noqa: E402
	_build_rank_infos,
	delta_for_user,
	get_previous_message_counts,
	previous_rank_map,
)

TZ = ZoneInfo('Asia/Shanghai')


def at(text: str) -> datetime:
	return datetime.fromisoformat(text).replace(tzinfo=TZ)


def test_previous_period_range() -> None:
	assert previous_period_range(
		'今日', at('2026-11-05T00:00'), at('2026-11-05T22:00')
	) == (at('2026-11-04T00:00'), at('2026-11-04T22:00'))
	assert previous_period_range(
		'昨日', at('2026-11-04T00:00'), at('2026-11-05T00:00')
	) == (at('2026-11-03T00:00'), at('2026-11-04T00:00'))
	assert previous_period_range(
		'本周', at('2026-11-02T00:00'), at('2026-11-05T22:00')
	) == (at('2026-10-26T00:00'), at('2026-10-29T22:00'))
	assert previous_period_range(
		'本月', at('2026-11-01T00:00'), at('2026-11-05T22:00')
	) == (at('2026-10-01T00:00'), at('2026-10-05T22:00'))
	# 目标月没有 31 号时夹到月末
	assert previous_period_range(
		'本月', at('2026-03-31T10:00'), at('2026-03-31T12:00')
	) == (at('2026-02-28T10:00'), at('2026-02-28T12:00'))
	assert previous_period_range(
		'年度', at('2026-01-01T00:00'), at('2026-11-05T22:00')
	) == (at('2025-01-01T00:00'), at('2025-11-05T22:00'))
	# 闰年 2 月 29 日夹到 28 日
	assert previous_period_range(
		'年度', at('2028-01-01T00:00'), at('2028-02-29T12:00')
	) == (at('2027-01-01T00:00'), at('2027-02-28T12:00'))
	# 自定义历史区间：同样长度往前挪
	assert previous_period_range(
		'历史', at('2026-01-01T00:00'), at('2026-01-08T00:00')
	) == (at('2025-12-25T00:00'), at('2026-01-01T00:00'))
	assert previous_period_range('历史', None, None) is None
	assert previous_period_range('历史', at('2026-01-08T00:00'), None) is None
	print('previous_period_range ok')


def test_previous_rank_map() -> None:
	assert previous_rank_map({1: 10, 2: 10, 3: 5}) == {1: 1, 2: 1, 3: 3}
	assert previous_rank_map({}) == {}
	print('previous_rank_map ok')


def test_delta_for_user() -> None:
	up = delta_for_user(2, 7, {7: 5})
	assert up == {
		'user_delta_rank': 3,
		'user_prev_rank': 5,
		'user_delta_label': '↑3',
		'user_delta_class': 'up',
	}
	down = delta_for_user(2, 7, {7: 1})
	assert (down['user_delta_rank'], down['user_delta_label']) == (-1, '↓1')
	assert down['user_delta_class'] == 'down'
	same = delta_for_user(2, 7, {7: 2})
	assert (same['user_delta_rank'], same['user_delta_label']) == (0, '')
	assert same['user_delta_class'] == ''
	new = delta_for_user(2, 8, {7: 2})
	assert (new['user_delta_rank'], new['user_delta_label']) == (None, '新')
	assert new['user_delta_class'] == 'new'
	none = delta_for_user(2, 8, None)
	assert (none['user_delta_rank'], none['user_delta_label']) == (None, '')
	assert none['user_delta_class'] == ''
	print('delta_for_user ok')


async def test_build_rank_infos() -> None:
	from nonebot_plugin_userinfo import UserInfo

	users = [
		UserInfo(user_id=str(user_id), user_name=f'user{user_id}')
		for user_id in (1, 2, 3)
	]
	# 上一期：user2 第一、user1 第二、user3 第三
	rank = [[1, 30], [2, 20], [3, 10]]
	infos = await _build_rank_infos(rank, users, {1: 10, 2: 30, 3: 5})
	assert [
		(item.user_index, item.user_delta_rank, item.user_delta_label)
		for item in infos
	] == [(1, 1, '↑1'), (2, -1, '↓1'), (3, 0, '')]
	print('build_rank_infos ok')


async def test_previous_counts_no_range() -> None:
	assert await get_previous_message_counts('历史', None, None, ['1']) is None
	print('previous_message_counts ok')


async def test_parse_datetime_accepts_none() -> None:
	from nonebot_plugin_dialectlist.time import parse_datetime

	parser = parse_datetime('start')
	await parser(None, {}, None)  # type: ignore[arg-type]
	print('parse_datetime none ok')


if __name__ == '__main__':
	import asyncio

	test_previous_period_range()
	test_previous_rank_map()
	test_delta_for_user()
	asyncio.run(test_build_rank_infos())
	asyncio.run(test_previous_counts_no_range())
	asyncio.run(test_parse_datetime_accepts_none())
	print('all delta tests passed')
