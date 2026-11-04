"""htmlrender 渲染环境的前置检查与兜底

htmlrender 0.8 起没有默认渲染后端，浏览器也可能没装好。这些错误原本会在
命令执行到一半才炸出来，群里一点反应都没有。这里在插件导入的最早期
（htmlrender 被 require 之前）把能自动补的补上，不能补的给出明确的修复步骤。
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from typing import Any, Dict, Optional, Tuple

from nonebot import get_driver
from nonebot.log import logger

PROVIDER_ENV = 'RENDER__PROVIDER'
BACKEND_ENV = 'RENDER_BACKEND'
DEFAULT_PROVIDER = 'playwright'

TROUBLESHOOTING = (
	'渲染环境没准备好，可以按这几步排查：\n'
	f'1. .env 里加一行 {PROVIDER_ENV}={DEFAULT_PROVIDER}（0.8+ 必填）\n'
	'2. 执行 playwright install chromium 安装浏览器\n'
	'3. 装不动的话，把已有的浏览器目录用 PLAYWRIGHT_BROWSERS_PATH 指过去\n'
	'改完重启 bot 再试一次。'
)


def htmlrender_version() -> Optional[str]:
	try:
		return pkg_version('nonebot-plugin-htmlrender')
	except PackageNotFoundError:
		return None


def _major_minor(ver: str) -> Tuple[int, int]:
	numbers = []
	for part in ver.split('.')[:2]:
		digits = ''.join(ch for ch in part if ch.isdigit())
		numbers.append(int(digits) if digits else 0)
	while len(numbers) < 2:
		numbers.append(0)
	return numbers[0], numbers[1]


def _merge_provider(render: Any) -> Optional[Dict[str, Any]]:
	"""把 provider 塞进 render 配置，返回新的 dict（None 表示不用动）"""
	if render is None:
		return {'provider': DEFAULT_PROVIDER}
	if isinstance(render, dict):
		if render.get('provider'):
			return None
		return {**render, 'provider': DEFAULT_PROVIDER}
	provider = getattr(render, 'provider', None)
	if provider:
		return None
	if hasattr(render, 'model_dump'):
		return {**render.model_dump(), 'provider': DEFAULT_PROVIDER}
	return None


def ensure_render_backend() -> None:
	"""在 require htmlrender 之前调用，把缺失的渲染后端补上"""
	ver = htmlrender_version()
	if ver is None:
		logger.debug(
			'[dialectlist] 没装 nonebot-plugin-htmlrender，跳过渲染后端检查'
		)
		return

	major, minor = _major_minor(ver)

	if (major, minor) >= (0, 8):
		config = get_driver().config
		merged = _merge_provider(getattr(config, 'render', None))
		if merged is None:
			return
		try:
			config.render = merged  # type: ignore[attr-defined]
		except Exception as e:
			logger.warning(
				f'[dialectlist] htmlrender {ver} 需要 {PROVIDER_ENV}，'
				f'自动设置失败：{e}。请在 .env 里手动加上 {PROVIDER_ENV}={DEFAULT_PROVIDER}'
			)
			return
		logger.warning(
			f'[dialectlist] 检测到 htmlrender {ver}，未配置 {PROVIDER_ENV}，'
			f'已自动使用 {DEFAULT_PROVIDER}。'
			f'想换后端的话在 .env 里显式写上 {PROVIDER_ENV}=...'
		)
		return

	if (major, minor) == (0, 7):
		config = get_driver().config
		if getattr(config, 'render_backend', None):
			return
		try:
			config.render_backend = DEFAULT_PROVIDER  # type: ignore[attr-defined]
		except Exception as e:
			logger.warning(
				f'[dialectlist] htmlrender {ver} 需要 {BACKEND_ENV}，'
				f'自动设置失败：{e}。请在 .env 里加上 {BACKEND_ENV}={DEFAULT_PROVIDER}'
			)
			return
		logger.warning(
			f'[dialectlist] 检测到 htmlrender {ver}，未配置 {BACKEND_ENV}，'
			f'已自动使用 {DEFAULT_PROVIDER}'
		)
		return

	logger.debug(f'[dialectlist] htmlrender {ver} 开箱即用，无需额外配置')
