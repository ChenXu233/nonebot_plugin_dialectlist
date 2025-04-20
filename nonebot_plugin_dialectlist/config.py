from typing import List, Optional

from nonebot import get_driver, get_plugin_config
from pydantic import BaseModel


class ScopedConfig(BaseModel):
    get_num: int = 5  # 获取人数数量
    font: str = "SimHei"  # 字体格式
    suffix: bool = True  # 是否显示后缀
    excluded_self: bool = True  # 是否排除自己
    visualization: bool = True  # 是否可视化
    show_text_rank: bool = True  # 是否显示文本排名
    counting_cache: bool = False  # 计数缓存(能够提高回复速度)
    excluded_people: List[str] = []  # 排除的人的QQ号
    use_user_info_cache: bool = False  # 是否使用用户信息缓存
    aggregate_transmission: bool = False  # 是否聚合转发消息
    timezone: Optional[str] = "Asia/Shanghai"  # 时区，影响统计时间
    string_suffix: str = "统计花费时间:{timecost}秒"  # 消息格式后缀
    template_path: str = "./template/rank_template.j2"  # 模板路径
    string_format: str = "第{index}名：\n{nickname},{chatdatanum}条消息\n"  # 消息格式


class Config(BaseModel):
    dialectlist: ScopedConfig = ScopedConfig()


global_config = get_driver().config
plugin_config = get_plugin_config(Config).dialectlist
