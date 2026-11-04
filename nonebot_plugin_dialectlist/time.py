from datetime import datetime
from typing import Union
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
