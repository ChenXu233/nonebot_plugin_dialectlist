from typing import Dict, List, Optional

from nonebot import get_driver, get_plugin_config
from pydantic import BaseModel


class PushGroupConfig(BaseModel):
	"""单个群的定时推送配置"""

	enabled: bool = True  # 是否给这个群推送
	cron: Optional[str] = None  # 覆盖全局 push_cron
	period: Optional[str] = None  # 覆盖全局 push_period
	min_messages: int = 0  # 区间消息量下限，0 表示不限制
	min_members: int = 0  # 群人数下限，0 表示不限制
	get_num: Optional[int] = None  # 覆盖展示人数


class ScopedConfig(BaseModel):
	get_num: int = 5  # 获取人数数量
	suffix: bool = True  # 是否显示后缀
	visualization: bool = True  # 是否可视化
	show_text_rank: bool = True  # 是否显示文本排名
	excluded_people: List[str] = []  # 排除的人的QQ号
	use_user_info_cache: bool = False  # 是否使用用户信息缓存
	aggregate_transmission: bool = False  # 是否聚合转发消息
	timezone: Optional[str] = 'Asia/Shanghai'  # 时区，影响统计时间
	string_suffix: str = '统计花费时间:{timecost}秒'  # 消息格式后缀
	template_path: str = './template/rank_template.j2'  # 模板路径
	string_format: str = (
		'第{index}名：\n{nickname},{chatdatanum}条消息\n'  # 消息格式
	)
	push_enabled: bool = False  # 是否开启定时推送
	push_cron: str = '0 0 * * *'  # 默认推送时间（cron 表达式）
	push_period: str = '昨日'  # 默认统计区间
	push_groups: Dict[str, PushGroupConfig] = {}  # 群号 -> 该群的推送配置


class Config(BaseModel):
	dialectlist: ScopedConfig = ScopedConfig()


global_config = get_driver().config
plugin_config = get_plugin_config(Config).dialectlist
