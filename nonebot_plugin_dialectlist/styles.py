"""排行榜外观：一套模板配多套 CSS，换样式不用改模板"""

import base64
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(PLUGIN_DIR, 'template')
CSS_DIR = os.path.join(TEMPLATE_DIR, 'css')

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
	"""一套配色"""

	id: str
	name: str
	description: str
	background: str
	foreground: str
	accent: str
	palette: Tuple[str, ...]
	aliases: Tuple[str, ...] = ()

	@property
	def css_file(self) -> str:
		return f'theme-{self.id}.css'


@dataclass(frozen=True)
class Layout:
	"""榜单的排列方式"""

	id: str
	name: str
	description: str
	css_file: Optional[str] = None
	aliases: Tuple[str, ...] = ()


THEMES: Tuple[Theme, ...] = (
	Theme(
		'dark',
		'暗夜',
		'霓虹描边 + 深色底，插件默认样式',
		'#1a1a1a',
		'#e0e0e0',
		'#00ffff',
		('#00ffff', '#4dd4ff', '#ff00ae', '#8f6bff', '#ffffff'),
		('暗', '黑', '霓虹', 'neon', 'night', '默认'),
	),
	Theme(
		'light',
		'浅色',
		'白底 + 淡紫渐变进度条，白天看着舒服',
		'#f5f6fa',
		'#2b2b33',
		'#3a7afe',
		('#3a7afe', '#7c6bff', '#4f8bff', '#ff6b9a', '#8a90a0'),
		('亮', '浅', '白', 'day', 'blue'),
	),
	Theme(
		'minimal',
		'简约',
		'纯黑白，去掉发光和圆角',
		'#ffffff',
		'#111111',
		'#111111',
		('#111111', '#3d3d3d', '#666666', '#8f8f8f', '#b4b4b4'),
		('极简', '黑白', 'mono', 'simple', 'plain'),
	),
	Theme(
		'warm',
		'暖阳',
		'米色底 + 橙粉渐变，看着热闹',
		'#fff8f0',
		'#3d2b1f',
		'#ff7a45',
		('#ff7a45', '#ff5f8f', '#ffa14a', '#c96a2f', '#a08a78'),
		('暖', '橙', '粉', 'sunset', 'cream'),
	),
)

LAYOUTS: Tuple[Layout, ...] = (
	Layout(
		'list',
		'竖排',
		'一人一行，默认',
		None,
		('行', '纵向', 'list', 'vertical'),
	),
	Layout(
		'grid',
		'横排',
		'卡片横着铺开，人多时一眼看全',
		'layout-grid.css',
		('横', '横向', '平铺', 'horizontal', 'flat', 'tile'),
	),
)


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
	for theme in THEMES:
		if _match(value, (theme,), None) is not None:
			return theme
	return None


def find_layout(value: Optional[str]) -> Optional[Layout]:
	if not value:
		return None
	for layout in LAYOUTS:
		if _match(value, (layout,), None) is not None:
			return layout
	return None


def get_theme(value: Optional[str]) -> Theme:
	"""认不出来就退回默认主题"""
	return _match(value, THEMES, THEMES[0])


def get_layout(value: Optional[str]) -> Layout:
	return _match(value, LAYOUTS, LAYOUTS[0])


_file_cache: Dict[str, str] = {}
_bundle_cache: Dict[str, str] = {}


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


def read_css(path_or_name: str) -> str:
	"""读一个 css 文件（带缓存）并把字体、图片内联"""
	if path_or_name not in _file_cache:
		path = (
			path_or_name
			if os.path.isabs(path_or_name)
			else os.path.join(CSS_DIR, path_or_name)
		)
		with open(path, encoding='utf-8') as f:
			_file_cache[path_or_name] = _inline_urls(
				f.read(), os.path.dirname(os.path.abspath(path))
			)
	return _file_cache[path_or_name]


def rank_css(
	theme: Optional[str] = None,
	layout: Optional[str] = None,
	extra: Optional[str] = None,
) -> str:
	"""榜单用的样式：结构 + 配色 + 排版 + 模板自带的 extra.css"""
	theme_cfg = get_theme(theme)
	layout_cfg = get_layout(layout)
	has_extra = bool(extra) and os.path.isfile(str(extra))
	key = f'rank:{theme_cfg.id}:{layout_cfg.id}:{extra if has_extra else ""}'
	if key in _bundle_cache:
		return _bundle_cache[key]
	files: List[str] = ['base.css', 'rank.css', theme_cfg.css_file]
	if layout_cfg.css_file:
		files.append(layout_cfg.css_file)
	css = '\n'.join(read_css(name) for name in files)
	if has_extra:
		css += '\n' + read_css(str(extra))
	_bundle_cache[key] = css
	return css


def chart_css(theme: Optional[str] = None) -> str:
	"""分布图 / 多群对比用的样式"""
	theme_cfg = get_theme(theme)
	key = f'chart:{theme_cfg.id}'
	if key in _bundle_cache:
		return _bundle_cache[key]
	files = ['base.css', 'rank.css', 'chart.css', theme_cfg.css_file]
	css = '\n'.join(read_css(name) for name in files)
	_bundle_cache[key] = css
	return css


def theme_list() -> str:
	lines = ['可用的样式：']
	for theme in THEMES:
		lines.append(f'  {theme.name}（{theme.id}）：{theme.description}')
	lines.append('')
	lines.append('可用的排版：')
	for layout in LAYOUTS:
		lines.append(f'  {layout.name}（{layout.id}）：{layout.description}')
	return '\n'.join(lines)
