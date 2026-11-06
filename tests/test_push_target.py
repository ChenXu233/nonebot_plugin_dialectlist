"""推送目标的多平台抽象：SAA 目标序列化 + 老配置回退

仓库没有引入 pytest，这个文件可以直接跑：

    .venv\\Scripts\\python.exe tests/test_push_target.py
"""

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix='dialectlist-target-'))
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

import nonebot_plugin_saa as saa  # noqa: E402

from nonebot_plugin_dialectlist.push import _resolve_target  # noqa: E402


def test_qq_falls_back_without_stored_target() -> None:
	# 没有存目标的 QQ 群还是按老路子走
	target = _resolve_target('999999999999999999')
	assert isinstance(target, saa.TargetQQGroup)
	assert target.group_id == 999999999999999999
	print('qq fallback ok')


def test_non_numeric_without_target() -> None:
	assert _resolve_target('not-a-number') is None
	print('non-numeric skip ok')


def test_telegram_target_roundtrip() -> None:
	original = saa.TargetTelegramCommon(chat_id=-1001234567890)
	payload = original.model_dump(mode='json')
	assert payload['platform_type']
	assert saa.PlatformTarget.deserialize(payload) == original
	print('telegram roundtrip ok')


if __name__ == '__main__':
	test_qq_falls_back_without_stored_target()
	test_non_numeric_without_target()
	test_telegram_target_roundtrip()
	print('all push target tests passed')
