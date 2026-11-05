"""排行榜外观：一套模板配多套样式，换样式不用改模板

样式按目录组织，丢一个目录进去就自动被认出来，不用改代码注册：

template/themes/dark/
├── meta.json     # 名字、说明、别名
├── base.css      # 变量和通用外观（没有就回落到默认样式的）
├── rank.css      # 可选：这套样式对榜单的额外调整
├── chart.css     # 可选：对分布图的
└── compare.css   # 可选：对多群对比的

layouts/ 同理，目录里放 layout.css。自己做的样式丢到插件配置目录的
themes/ 或 layouts/ 下也能用。
"""

import base64
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from nonebot.log import logger

from .config import plugin_config

PLUGIN_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = PLUGIN_DIR / 'template'
CSS_DIR = TEMPLATE_DIR / 'css'
THEMES_DIR = TEMPLATE_DIR / 'themes'
LAYOUTS_DIR = TEMPLATE_DIR / 'layouts'

DEFAULT_THEME = 'dark'
DEFAULT_LAYOUT = 'list'

# 一种图 = 一套结构 css + 样式目录里同名的额外 css
KIND_FILES: Dict[str, List[str]] = {
	'rank': ['rank.css'],
	'chart': ['chart.css'],
	'compare': ['rank.css', 'compare.css'],
}

# CSS 里的 url() 都是相对路径，渲染时整段内联，所以要换成 data URI
_URL_RE = re.compile(r'url\(\s*["\']?([^"\'()]+?)["\']?\s*\)')

_MIME = {
	'.woff2': 'font/woff2',
	'.woff': 'font/woff',
	'.ttf': 'font/ttf',
	'.otf': 'font/otf',
	'.png': 'image/png',
	'.jpg': 'image/jpeg',
	'.jpeg': 'image/jpeg',
	'.gif': 'image/gif',
	'.svg': 'image/svg+xml',
	'.webp': 'image/webp',
}


@dataclass(frozen=True)
class Theme:
	"""样式目录里的一个样式"""

	id: str
	name: str
	description: str = ''
	aliases: Tuple[str, ...] = ()
	path: Optional[Path] = None
	builtin: bool = True

	def css(self, name: str) -> Optional[Path]:
		if self.path is None:
			return None
		path = self.path / f'{name}.css'
		return path if path.is_file() else None


@dataclass(frozen=True)
class Layout:
	"""榜单的排列方式"""

	id: str
	name: str
	description: str = ''
	aliases: Tuple[str, ...] = ()
	path: Optional[Path] = None
	builtin: bool = True

	@property
	def css_path(self) -> Optional[Path]:
		if self.path is None:
			return None
		path = self.path / 'layout.css'
		return path if path.is_file() else None


def _user_root(name: str) -> Optional[Path]:
	"""插件配置目录下的自定义 themes/ layouts/，拿不到就只认内置的"""
	try:
		from nonebot_plugin_localstore import get_plugin_config_dir

		return get_plugin_config_dir() / name
	except Exception as e:  # 插件不是被 nonebot 加载的时候会拿不到
		logger.debug(f'拿不到配置目录，只用内置 {name}: {e}')
		return None


def _read_meta(path: Path) -> Dict[str, object]:
	meta_file = path / 'meta.json'
	if not meta_file.is_file():
		return {}
	try:
		data = json.loads(meta_file.read_text(encoding='utf-8'))
	except Exception as e:
		logger.warning(f'{path.name}/meta.json 解析失败: {e}')
		return {}
	return data if isinstance(data, dict) else {}


def _aliases(meta: Dict[str, object]) -> Tuple[str, ...]:
	raw = meta.get('aliases')
	if isinstance(raw, list):
		return tuple(str(item) for item in raw if item)
	if isinstance(raw, str):
		return tuple(part.strip() for part in raw.split(',') if part.strip())
	return ()


def _theme_from_dir(path: Path, builtin: bool) -> Optional[Theme]:
	meta = _read_meta(path)
	has_css = any(
		(path / f'{name}.css').is_file()
		for name in ('base', 'rank', 'chart', 'compare')
	)
	if not meta and not has_css:
		logger.debug(f'目录 {path.name} 里没有 meta.json 也没有 css，跳过')
		return None
	return Theme(
		id=path.name,
		name=str(meta.get('name') or path.name),
		description=str(meta.get('description') or ''),
		aliases=_aliases(meta),
		path=path,
		builtin=builtin,
	)


def _layout_from_dir(path: Path, builtin: bool) -> Optional[Layout]:
	meta = _read_meta(path)
	if not meta and not (path / 'layout.css').is_file():
		logger.debug(f'目录 {path.name} 里没有 meta.json 也没有 css，跳过')
		return None
	return Layout(
		id=path.name,
		name=str(meta.get('name') or path.name),
		description=str(meta.get('description') or ''),
		aliases=_aliases(meta),
		path=path,
		builtin=builtin,
	)


def _scan(root: Optional[Path], builtin: bool, loader) -> Dict[str, object]:
	found: Dict[str, object] = {}
	if root is None or not root.is_dir():
		return found
	for entry in sorted(root.iterdir()):
		if not entry.is_dir() or entry.name.startswith(('.', '_')):
			continue
		item = loader(entry, builtin)
		if item is not None:
			found[entry.name] = item
	return found


def list_themes() -> Dict[str, Theme]:
	"""内置样式 + 自己放的，同名的以自己放的为准"""
	themes: Dict[str, Theme] = {}
	for root, builtin in ((THEMES_DIR, True), (_user_root('themes'), False)):
		themes.update(_scan(root, builtin, _theme_from_dir))  # type: ignore[arg-type]
	return themes


def list_layouts() -> Dict[str, Layout]:
	layouts: Dict[str, Layout] = {}
	for root, builtin in ((LAYOUTS_DIR, True), (_user_root('layouts'), False)):
		layouts.update(_scan(root, builtin, _layout_from_dir))  # type: ignore[arg-type]
	return layouts


def _match(value: Optional[str], items, default):
	if not value:
		return default
	key = str(value).strip().lower()
	for item in items:
		if key == item.id or key == item.name.lower() or key in item.aliases:
			return item
	return default


def find_theme(value: Optional[str]) -> Optional[Theme]:
	"""只做精确匹配，给配置校验用"""
	if not value:
		return None
	return _match(value, list_themes().values(), None)


def find_layout(value: Optional[str]) -> Optional[Layout]:
	if not value:
		return None
	return _match(value, list_layouts().values(), None)


def default_theme() -> Theme:
	themes = list_themes()
	if not themes:
		raise RuntimeError('找不到任何排行榜样式，插件可能装坏了')
	return themes.get(DEFAULT_THEME) or next(iter(themes.values()))


def get_theme(value: Optional[str]) -> Theme:
	"""认不出来就退回默认样式"""
	found = _match(value, list_themes().values(), None)
	return found or default_theme()


def get_layout(value: Optional[str]) -> Layout:
	layouts = list_layouts()
	found = _match(value, layouts.values(), None)
	if found is not None:
		return found
	default = layouts.get(DEFAULT_LAYOUT)
	return default or Layout(DEFAULT_LAYOUT, '竖排')


def _theme_css(theme: Theme, name: str) -> Optional[Path]:
	"""先找这个样式自己的，没有就用默认样式的（缺失就回落）"""
	for candidate in (theme, default_theme()):
		path = candidate.css(name)
		if path is not None:
			return path
	return None


_file_cache: Dict[Tuple[str, str], str] = {}
_bundle_cache: Dict[str, str] = {}

# 内置字体是完整字库的 GB2312 一级常用字子集（3755 字 + 常用标点 + ASCII）。
# 完整字库 4.27MB，内联进每张图的 HTML 要多花约 1 秒；子集只有 483KB。
# 生僻字会回落到系统字体，需要全字库时把 font 配成 full。
_FONT_NAME = 'HarmonyOS_Sans_SC.woff2'
_FONT_FILES = {
	'subset': 'HarmonyOS_Sans_SC.subset.woff2',
	'full': _FONT_NAME,
}
_FONT_FACE_RE = re.compile(r'@font-face\s*\{[^}]*\}')
FONT_MODES: Tuple[str, ...] = ('subset', 'full', 'system')


def get_font_mode(value: Optional[str]) -> str:
	"""把配置值归一化；认不出来就用默认子集，避免启动时炸掉"""
	mode = str(value).strip().lower() if value else ''
	return mode if mode in FONT_MODES else 'subset'


def _font_file(mode: str) -> Optional[str]:
	if mode == 'system':
		return None
	name = _FONT_FILES[mode]
	if mode != 'full' and not os.path.isfile(
		os.path.join(TEMPLATE_DIR, 'res', name)
	):
		return _FONT_FILES['full']
	return name


def _font_css(css: str, mode: str) -> str:
	"""按字体模式改写 @font-face：去掉 / 换成子集 / 用完整字库"""
	name = _font_file(mode)
	if name is None:
		return _FONT_FACE_RE.sub('', css)
	if name == _FONT_NAME:
		return css
	return css.replace(_FONT_NAME, name)


def _inline_urls(css: str, base_dir: str) -> str:
	"""把指向本地文件的 url() 换成 data URI，渲染时就不依赖本地路径了"""

	def replace(match: 're.Match[str]') -> str:
		target = match.group(1).strip()
		if target.startswith(('data:', 'http://', 'https://', '//')):
			return match.group(0)
		path = os.path.normpath(os.path.join(base_dir, target))
		if not os.path.isfile(path):
			return match.group(0)
		with open(path, 'rb') as f:
			data = base64.b64encode(f.read()).decode('ascii')
		suffix = os.path.splitext(path)[1].lower()
		mime = _MIME.get(suffix, 'application/octet-stream')
		return f'url("data:{mime};base64,{data}")'

	return _URL_RE.sub(replace, css)


def read_css(path_or_name: str, font: Optional[str] = None) -> str:
	"""读一个 css 文件（带缓存）并把字体、图片内联"""
	mode = get_font_mode(font or plugin_config.font)
	key = (mode, str(path_or_name))
	if key not in _file_cache:
		path = (
			str(path_or_name)
			if os.path.isabs(str(path_or_name))
			else os.path.join(CSS_DIR, str(path_or_name))
		)
		with open(path, encoding='utf-8') as f:
			css = _font_css(f.read(), mode)
		_file_cache[key] = _inline_urls(
			css, os.path.dirname(os.path.abspath(path))
		)
	return _file_cache[key]


def build_css(
	kind: str,
	theme: Optional[str] = None,
	layout: Optional[str] = None,
	extra: Optional[str] = None,
	font: Optional[str] = None,
) -> str:
	"""拼一种图的样式：结构 + 样式目录 + 排版 + 模板自带的 extra.css"""
	if kind not in KIND_FILES:
		raise ValueError(f'不认识的图片种类: {kind}')
	mode = get_font_mode(font or plugin_config.font)
	theme_cfg = get_theme(theme)
	# 图表页面不分竖排横排
	layout_cfg = get_layout(layout) if kind != 'chart' else None
	extra_path = str(extra) if extra and os.path.isfile(str(extra)) else ''
	key = (
		f'{kind}:{mode}:{theme_cfg.id}:'
		f'{layout_cfg.id if layout_cfg else "-"}:{extra_path}'
	)
	if key in _bundle_cache:
		return _bundle_cache[key]

	files: List[str] = [
		str(CSS_DIR / 'base.css'),
		str(CSS_DIR / 'chrome.css'),
	]
	files += [str(CSS_DIR / name) for name in KIND_FILES[kind]]
	for name in ('base', kind):
		path = _theme_css(theme_cfg, name)
		if path is not None:
			files.append(str(path))
	if layout_cfg is not None and layout_cfg.css_path is not None:
		files.append(str(layout_cfg.css_path))

	css = '\n'.join(read_css(name, mode) for name in files)
	if extra_path:
		css += '\n' + read_css(extra_path, mode)
	_bundle_cache[key] = css
	return css


def rank_css(
	theme: Optional[str] = None,
	layout: Optional[str] = None,
	extra: Optional[str] = None,
	font: Optional[str] = None,
) -> str:
	"""榜单用的样式"""
	return build_css('rank', theme, layout, extra, font)


def chart_css(theme: Optional[str] = None, font: Optional[str] = None) -> str:
	"""分布图 / 成员跨群用的样式"""
	return build_css('chart', theme, None, None, font)


def compare_css(
	theme: Optional[str] = None,
	layout: Optional[str] = None,
	font: Optional[str] = None,
) -> str:
	"""多群对比用的样式"""
	return build_css('compare', theme, layout, None, font)


def theme_list() -> str:
	lines = ['可用的样式：']
	for theme in list_themes().values():
		lines.append(f'  {theme.name}（{theme.id}）：{theme.description}')
	lines += ['', '可用的排版：']
	for layout in list_layouts().values():
		lines.append(f'  {layout.name}（{layout.id}）：{layout.description}')
	root = _user_root('themes')
	if root is not None:
		lines += [
			'',
			f'自己做的样式放到：{root}',
			'目录结构：<名字>/meta.json + base.css，'
			'可选 rank.css / chart.css / compare.css',
		]
	return '\n'.join(lines)
