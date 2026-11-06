"""按群配置：存 JSON，改完即时生效（带 mtime 缓存）"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from nonebot.log import logger
from nonebot_plugin_localstore import get_plugin_config_dir
from pydantic import BaseModel

from .config import PushGroupConfig, ScopedConfig, plugin_config


class GroupConfig(BaseModel):
	"""单个群的覆盖配置，None 表示沿用全局"""

	enabled: Optional[bool] = None  # 这个群是否允许查询/推送
	template: Optional[str] = None
	template_path: Optional[str] = None
	theme: Optional[str] = None
	layout: Optional[str] = None
	get_num: Optional[int] = None
	visualization: Optional[bool] = None
	show_text_rank: Optional[bool] = None
	suffix: Optional[bool] = None
	excluded_people: Optional[List[str]] = None
	show_delta: Optional[bool] = None
	push_target: Optional[Dict[str, Any]] = None  # 定时推送的 SAA 目标（多平台）

	push_enabled: Optional[bool] = None
	push_cron: Optional[str] = None
	push_period: Optional[str] = None
	push_min_messages: Optional[int] = None
	push_min_members: Optional[int] = None
	push_get_num: Optional[int] = None


# 能覆盖全局 ScopedConfig 的字段
OVERRIDE_KEYS = (
	'enabled',
	'template',
	'template_path',
	'theme',
	'layout',
	'get_num',
	'visualization',
	'show_text_rank',
	'suffix',
	'excluded_people',
	'show_delta',
)


class GroupConfigStore:
	def __init__(self) -> None:
		self._path: Optional[Path] = None
		self._cache: Dict[str, GroupConfig] = {}
		self._mtime: Optional[float] = None

	@property
	def path(self) -> Path:
		if self._path is None:
			self._path = get_plugin_config_dir() / 'groups.json'
		return self._path

	def _load(self) -> None:
		try:
			if not self.path.exists():
				self._cache, self._mtime = {}, None
				return
			mtime = self.path.stat().st_mtime
			if mtime == self._mtime:
				return
			with open(self.path, encoding='utf-8') as f:
				raw = json.load(f)
			self._cache = {
				str(group_id): GroupConfig(**data)
				for group_id, data in raw.items()
			}
			self._mtime = mtime
			logger.debug(f'[dialectlist] 已加载群配置: {len(self._cache)} 个')
		except Exception as e:
			logger.error(f'[dialectlist] 读取群配置失败 {self.path}: {e}')

	def reload(self) -> None:
		self._mtime = None
		self._load()

	def all(self) -> Dict[str, GroupConfig]:
		self._load()
		return dict(self._cache)

	def get(self, group_id: str) -> GroupConfig:
		self._load()
		return self._cache.get(str(group_id), GroupConfig())

	def update(self, group_id: str, **fields: Any) -> GroupConfig:
		self._load()
		current = self._cache.get(str(group_id), GroupConfig())
		updated = current.model_copy(update=fields)
		self._cache[str(group_id)] = updated
		self.save()
		return updated

	def reset(self, group_id: str) -> None:
		self._load()
		self._cache.pop(str(group_id), None)
		self.save()

	def save(self) -> None:
		self.path.parent.mkdir(parents=True, exist_ok=True)
		tmp = self.path.with_suffix('.json.tmp')
		with open(tmp, 'w', encoding='utf-8') as f:
			json.dump(
				{
					group_id: cfg.model_dump()
					for group_id, cfg in self._cache.items()
				},
				f,
				ensure_ascii=False,
				indent=2,
			)
		os.replace(tmp, self.path)
		self._mtime = self.path.stat().st_mtime


store = GroupConfigStore()


def effective_config(group_id: str) -> ScopedConfig:
	"""全局配置 + 该群的覆盖项"""
	group = store.get(group_id)
	updates = {
		key: getattr(group, key)
		for key in OVERRIDE_KEYS
		if getattr(group, key) is not None
	}
	if not updates:
		return plugin_config
	return plugin_config.model_copy(update=updates)


def resolve_push_config(group_id: str) -> Optional[PushGroupConfig]:
	"""合并 .env 的 push_groups 与该群配置，返回 None 表示这个群不推送"""
	if not plugin_config.push_enabled:
		return None

	group = store.get(group_id)
	if group.push_enabled is False or not effective_config(group_id).enabled:
		return None

	env_cfg = plugin_config.push_groups.get(str(group_id))
	if env_cfg is None and group.push_enabled is not True:
		return None

	base = env_cfg or PushGroupConfig()
	updates: Dict[str, Any] = {}
	if group.push_cron:
		updates['cron'] = group.push_cron
	if group.push_period:
		updates['period'] = group.push_period
	if group.push_min_messages is not None:
		updates['min_messages'] = group.push_min_messages
	if group.push_min_members is not None:
		updates['min_members'] = group.push_min_members
	if group.push_get_num is not None:
		updates['get_num'] = group.push_get_num
	if env_cfg is None:
		updates['enabled'] = True

	return base.model_copy(update=updates)


def all_push_groups() -> Dict[str, PushGroupConfig]:
	"""所有需要推送的群（.env 里的 + 群配置里显式开启的）"""
	group_ids = set(plugin_config.push_groups) | set(store.all())
	resolved: Dict[str, PushGroupConfig] = {}
	for group_id in group_ids:
		cfg = resolve_push_config(str(group_id))
		if cfg is not None and cfg.enabled:
			resolved[str(group_id)] = cfg
	return resolved
