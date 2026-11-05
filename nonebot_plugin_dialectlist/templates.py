# 模板包：templates/<名字>/rank_template.j2
#
# 内置模板在插件目录 template/rank 下，自己做的模板丢到
# <插件配置目录>/templates/<名字>/ 里就能用，不用改代码。

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from nonebot.log import logger
from nonebot_plugin_localstore import get_plugin_config_dir

PLUGIN_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = PLUGIN_DIR / 'template'
BUILTIN_ROOT = TEMPLATE_DIR / 'rank'
PAGES_DIR = TEMPLATE_DIR / 'pages'
DEFAULT_FILENAME = 'rank_template.j2'
DEFAULT_NAME = 'classic'


@dataclass(frozen=True)
class Template:
	name: str
	path: Path
	filename: str
	title: str
	description: str = ''
	author: str = ''
	builtin: bool = False

	@property
	def file(self) -> Path:
		return self.path / self.filename

	@property
	def extra_css(self) -> Optional[Path]:
		path = self.path / 'extra.css'
		return path if path.is_file() else None

	@property
	def style_css(self) -> Optional[Path]:
		"""模板自带整套样式时（老写法）用它，不再套主题"""
		path = self.path / 'css' / 'style.css'
		return path if path.is_file() else None


def user_root() -> Path:
	return get_plugin_config_dir() / 'templates'


def _load(name: str, path: Path, builtin: bool) -> Optional[Template]:
	meta: Dict[str, str] = {}
	meta_file = path / 'meta.json'
	if meta_file.is_file():
		try:
			meta = json.loads(meta_file.read_text(encoding='utf-8'))
		except Exception as e:
			logger.warning(f'模板 {name} 的 meta.json 解析失败: {e}')
			meta = {}
	filename = str(meta.get('file') or DEFAULT_FILENAME)
	if not (path / filename).is_file():
		logger.debug(f'模板 {name} 里没有 {filename}，跳过')
		return None
	return Template(
		name=name,
		path=path,
		filename=filename,
		title=str(meta.get('name') or name),
		description=str(meta.get('description') or ''),
		author=str(meta.get('author') or ''),
		builtin=builtin,
	)


def _scan(root: Path, builtin: bool) -> Dict[str, Template]:
	found: Dict[str, Template] = {}
	if not root.is_dir():
		return found
	for entry in sorted(root.iterdir()):
		if not entry.is_dir() or entry.name.startswith(('.', '_')):
			continue
		template = _load(entry.name, entry, builtin)
		if template is not None:
			found[entry.name] = template
	return found


def list_templates() -> Dict[str, Template]:
	"""内置的 + 自己放的，同名的以自己放的为准"""
	merged = _scan(BUILTIN_ROOT, True)
	merged.update(_scan(user_root(), False))
	return merged


def find_template(name: Optional[str]) -> Optional[Template]:
	if not name:
		return None
	key = str(name).strip()
	templates = list_templates()
	if key in templates:
		return templates[key]
	lowered = key.lower()
	for template in templates.values():
		if template.name.lower() == lowered or template.title == key:
			return template
	return None


def default_template() -> Template:
	templates = list_templates()
	if not templates:
		raise RuntimeError('找不到任何排行榜模板，插件可能装坏了')
	return templates.get(DEFAULT_NAME) or next(iter(templates.values()))


def get_template(name: Optional[str]) -> Template:
	return find_template(name) or default_template()


def resolve(
	template: Optional[str] = None, template_path: Optional[str] = None
) -> Tuple[Path, str]:
	"""返回 (模板目录, 模板文件名)

	``template_path`` 是 3.x 早期那种直接指一个 .j2 的写法，继续兼容；
	但它指向的文件不存在时，退回按模板名选。
	"""
	if template_path:
		raw = str(template_path).strip()
		path = PLUGIN_DIR / raw[2:] if raw.startswith('./') else Path(raw)
		if path.is_file():
			return path.parent, path.name
		logger.warning(f'配置里的 template_path={raw} 不存在，改用模板名')
	chosen = get_template(template)
	return chosen.path, chosen.filename


def describe() -> str:
	"""给指令用的模板清单"""
	templates = list_templates()
	if not templates:
		return '还没有任何模板。'
	lines = ['可用的排行榜模板：']
	for template in templates.values():
		author = f' — {template.author}' if template.author else ''
		lines.append(
			f'  {template.title}（{template.name}）：'
			f'{template.description or "没有说明"}{author}'
		)
	lines.append('')
	lines.append(f'自己做的模板放到：{user_root()}')
	lines.append(
		'目录结构：<名字>/rank_template.j2，可选 meta.json / extra.css'
	)
	lines.append(
		'换模板：/B话榜配置 模板 <名字>，或者 /B话榜模板 <名字> 先看看效果'
	)
	return '\n'.join(lines)
