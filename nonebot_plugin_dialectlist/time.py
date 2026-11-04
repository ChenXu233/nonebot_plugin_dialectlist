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
		input: Union[datetime, Message] = Arg(key),
	):
		if isinstance(input, datetime):
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
