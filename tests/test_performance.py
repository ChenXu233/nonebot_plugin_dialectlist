"""性能回归测试：字体子集、头像复用与缓存。

仓库没有引入 pytest，这个文件可以直接跑：

    .venv\\Scripts\\python.exe tests/test_performance.py

它只依赖开发环境里已安装的 nonebot 依赖，不需要真实的 bot 实例。
"""

import asyncio
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# 本地头像服务器必须绕过系统代理（Windows 上常见坏 NO_PROXY）。
for _key in (
	'HTTP_PROXY',
	'HTTPS_PROXY',
	'http_proxy',
	'https_proxy',
	'ALL_PROXY',
	'all_proxy',
):
	os.environ.pop(_key, None)
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'

_TMP = Path(tempfile.mkdtemp(prefix='dialectlist-perf-'))
os.environ['SQLALCHEMY_DATABASE_URL'] = (
	f'sqlite+aiosqlite:///{_TMP / "test.sqlite3"}'
)
os.environ['ALEMBIC_STARTUP_CHECK'] = 'false'
os.environ.setdefault('RENDER__PROVIDER', 'playwright')

import nonebot

nonebot.init(driver='~none')
for _plugin in (
	'nonebot_plugin_orm',
	'nonebot_plugin_uninfo',
	'nonebot_plugin_chatrecorder',
	'nonebot_plugin_htmlrender',
	'nonebot_plugin_dialectlist',
):
	nonebot.load_plugin(_plugin)

from nonebot_plugin_userinfo import UserInfo
from nonebot_plugin_userinfo.image_source import ImageUrl

from nonebot_plugin_dialectlist import styles, utils
from nonebot_plugin_dialectlist.config import plugin_config

_AVATAR = b'\x89PNG\r\n\x1a\n' + b'perf-test-avatar' * 8


class _AvatarHandler(BaseHTTPRequestHandler):
	requests = 0
	fail = False

	def do_GET(self):  # noqa: N802 - http.server API
		type(self).requests += 1
		if type(self).fail:
			self.send_response(500)
			self.end_headers()
			return
		self.send_response(200)
		self.send_header('Content-Type', 'image/png')
		self.send_header('Content-Length', str(len(_AVATAR)))
		self.end_headers()
		self.wfile.write(_AVATAR)

	def log_message(self, *args):  # noqa: ARG002 - silence test server
		pass


_SERVER = ThreadingHTTPServer(('127.0.0.1', 0), _AvatarHandler)
threading.Thread(target=_SERVER.serve_forever, daemon=True).start()
_BASE = f'http://127.0.0.1:{_SERVER.server_address[1]}'


def _avatar_info(user_id: str, url: str) -> UserInfo:
	return UserInfo(
		user_id=user_id,
		user_name=user_id,
		user_avatar=ImageUrl(url=url),
	)


# ---------------- 字体 ----------------


def test_default_font_bundle_is_subset() -> None:
	subset = styles.rank_css('dark', 'list')
	full = styles.rank_css('dark', 'list', font='full')
	assert len(subset.encode()) < 1_500_000, len(subset.encode())
	assert len(full.encode()) > 4_000_000, len(full.encode())
	assert subset != full


def test_system_font_removes_font_face() -> None:
	css = styles.rank_css('dark', 'list', font='system')
	assert '@font-face' not in css
	assert len(css.encode()) < 100_000


def test_chart_css_follows_font_mode() -> None:
	assert len(styles.chart_css('dark').encode()) < 1_500_000
	assert '@font-face' not in styles.chart_css('dark', font='system')


def test_subset_font_asset_exists() -> None:
	font = Path(styles.TEMPLATE_DIR) / 'res' / 'HarmonyOS_Sans_SC.subset.woff2'
	assert font.is_file()
	assert font.stat().st_size < 1_000_000


# ---------------- 配置 ----------------


def test_user_info_cache_enabled_by_default() -> None:
	assert plugin_config.use_user_info_cache is True


# ---------------- 头像 ----------------


async def _reset_avatar_state() -> None:
	utils.clear_avatar_cache()
	await utils.close_http_client()
	_AvatarHandler.requests = 0
	_AvatarHandler.fail = False


async def test_avatar_download_is_cached() -> None:
	await _reset_avatar_state()
	info = _avatar_info('1', f'{_BASE}/cached.png')
	first = await utils._load_avatars([info])
	second = await utils._load_avatars([info])
	assert first == second == [_AVATAR]
	assert _AvatarHandler.requests == 1, _AvatarHandler.requests


async def test_avatar_batch_dedupes_same_url() -> None:
	await _reset_avatar_state()
	url = f'{_BASE}/same.png'
	infos = [_avatar_info('1', url), _avatar_info('2', url)]
	avatars = await utils._load_avatars(infos)
	assert avatars == [_AVATAR, _AVATAR]
	assert _AvatarHandler.requests == 1, _AvatarHandler.requests


async def test_no_avatar_skips_http_client() -> None:
	await _reset_avatar_state()
	created = False
	original = utils.httpx.AsyncClient

	class _BoomClient:
		def __init__(self, *args, **kwargs):  # noqa: ARG002
			nonlocal created
			created = True
			raise AssertionError('没有头像时不应该创建 HTTP 客户端')

	utils.httpx.AsyncClient = _BoomClient  # type: ignore[assignment]
	try:
		avatars = await utils._load_avatars(
			[UserInfo(user_id='3', user_name='no-avatar')]
		)
	finally:
		utils.httpx.AsyncClient = original  # type: ignore[assignment]

	assert created is False
	assert avatars == [await utils._get_user_default_avatar()]


async def test_avatar_retry_uses_short_backoff() -> None:
	await _reset_avatar_state()
	_AvatarHandler.fail = True
	delays: list[float] = []
	original_sleep = utils.asyncio.sleep

	async def _fake_sleep(delay: float) -> None:
		delays.append(delay)

	utils.asyncio.sleep = _fake_sleep  # type: ignore[assignment]
	try:
		avatars = await utils._load_avatars(
			[_avatar_info('4', f'{_BASE}/broken.png')]
		)
	finally:
		utils.asyncio.sleep = original_sleep  # type: ignore[assignment]
		_AvatarHandler.fail = False

	assert delays == [1.0, 2.0], delays
	assert avatars == [await utils._get_user_default_avatar()]


async def _run_async_tests() -> list[str]:
	failures: list[str] = []
	tests = (
		test_avatar_download_is_cached,
		test_avatar_batch_dedupes_same_url,
		test_no_avatar_skips_http_client,
		test_avatar_retry_uses_short_backoff,
	)
	for test in tests:
		try:
			await test()
			print(f'PASS {test.__name__}')
		except Exception as error:  # noqa: BLE001 - 测试收集所有失败
			print(f'FAIL {test.__name__}: {type(error).__name__}: {error}')
			failures.append(test.__name__)
	await utils.close_http_client()
	return failures


def main() -> int:
	failures: list[str] = []
	for test in (
		test_default_font_bundle_is_subset,
		test_system_font_removes_font_face,
		test_chart_css_follows_font_mode,
		test_subset_font_asset_exists,
		test_user_info_cache_enabled_by_default,
	):
		try:
			test()
			print(f'PASS {test.__name__}')
		except Exception as error:  # noqa: BLE001 - 测试收集所有失败
			print(f'FAIL {test.__name__}: {type(error).__name__}: {error}')
			failures.append(test.__name__)

	failures.extend(asyncio.run(_run_async_tests()))
	if failures:
		print(f'\n{len(failures)} failed: {", ".join(failures)}')
		return 1
	print('\nall performance regressions passed')
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
