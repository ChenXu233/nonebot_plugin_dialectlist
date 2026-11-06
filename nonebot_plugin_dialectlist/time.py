from calendar import monthrange
from datetime import datetime, timedelta
from typing import Optional, Tuple, Union
from zoneinfo import ZoneInfo

from nonebot.adapters import Message
from nonebot.params import Arg
from nonebot.typing import T_State
from nonebot_plugin_alconna import AlconnaMatcher

from .config import plugin_config


def parse_datetime(key: str):
	"""解析数字，并将结果存入 state 中"""

	async def _key_parser(
		matcher: AlconnaMatcher,
		state: T_State,
		input: Optional[Union[datetime, Message]] = Arg(key),
	):
		# 全量历史会把 start/stop 显式设成 None，不需要再解析日期
		if input is None or isinstance(input, datetime):
			return

		plaintext = input.extract_plain_text()
		try:
			state[key] = get_datetime_fromisoformat_with_timezone(plaintext)
		except ValueError:
			await matcher.reject_arg(
				key, '请输入正确的日期，不然我没法理解呢！'
			)

	return _key_parser


def resolve_period_range(
	period: str, now: datetime
) -> Optional[Tuple[datetime, datetime]]:
	"""把 今日/昨日/本周/上周/本月/上月/年度 解析成一个时间区间

	Args:
	    period (str): 时间类型
	    now (datetime): 当前时间（带时区）

	Returns:
	    Optional[Tuple[datetime, datetime]]: (start, stop)，不认识的类型返回 None
	"""
	midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
	if period == '今日':
		return midnight, now
	if period == '昨日':
		return midnight - timedelta(days=1), midnight
	if period == '本周':
		return midnight - timedelta(days=now.weekday()), now
	if period == '上周':
		stop = midnight - timedelta(days=now.weekday())
		return stop - timedelta(days=7), stop
	if period == '本月':
		return now.replace(
			day=1, hour=0, minute=0, second=0, microsecond=0
		), now
	if period == '上月':
		stop = now.replace(
			day=1, hour=0, minute=0, second=0, microsecond=0
		) - timedelta(microseconds=1)
		return stop.replace(
			day=1, hour=0, minute=0, second=0, microsecond=0
		), stop
	if period == '年度':
		return now.replace(
			month=1, day=1, hour=0, minute=0, second=0, microsecond=0
		), now
	return None


def _shift_months(value: datetime, months: int) -> datetime:
	"""按自然月平移；目标月没有这一天就取月末（1 月 31 日 → 2 月 28 日）"""
	total = value.year * 12 + (value.month - 1) + months
	year, month = divmod(total, 12)
	month += 1
	day = min(value.day, monthrange(year, month)[1])
	return value.replace(year=year, month=month, day=day)


def _shift_years(value: datetime, years: int) -> datetime:
	year = value.year + years
	day = min(value.day, monthrange(year, value.month)[1])
	return value.replace(year=year, day=day)


def previous_period_range(
	period: Optional[str], start: Optional[datetime], stop: Optional[datetime]
) -> Optional[Tuple[datetime, datetime]]:
	"""算出环比要对比的上一期区间

	今日对比昨天同一时段、昨日对比前天，本周 / 上周 往前挪一周，
	本月 / 上月 挪到上个月的同一天，年度 挪到去年的同一天。
	自定义的「历史 a~b」按等长区间往前推；没有区间可推时返回 None。
	"""
	if start is None or stop is None or stop <= start:
		return None
	if period in ('今日', '昨日'):
		delta = timedelta(days=1)
		return start - delta, stop - delta
	if period in ('本周', '上周'):
		delta = timedelta(days=7)
		return start - delta, stop - delta
	if period in ('本月', '上月'):
		return _shift_months(start, -1), _shift_months(stop, -1)
	if period == '年度':
		return _shift_years(start, -1), _shift_years(stop, -1)
	duration = stop - start
	return start - duration, start


def get_datetime_now_with_timezone() -> datetime:
	"""获取当前时间，并包含时区信息"""
	if plugin_config.timezone:
		return datetime.now(ZoneInfo(plugin_config.timezone))
	else:
		return datetime.now().astimezone()


def get_datetime_fromisoformat_with_timezone(date_string: str) -> datetime:
	"""从 ISO-8601 格式字符串中获取时间，并包含时区信息"""
	if not plugin_config.timezone:
		return datetime.fromisoformat(date_string).astimezone()
	raw = datetime.fromisoformat(date_string)
	return (
		raw.astimezone(ZoneInfo(plugin_config.timezone))
		if raw.tzinfo
		else raw.replace(tzinfo=ZoneInfo(plugin_config.timezone))
	)
