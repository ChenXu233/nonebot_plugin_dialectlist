from typing import Optional, Literal, List
from nonebot import get_driver, get_plugin_config
from pydantic import BaseModel


class ScopedConfig(BaseModel):
    font: str = "SimHei"  # 字体格式
    get_num: int = 5  # 获取人数数量
    timezone: Optional[str] = "Asia/Shanghai"
    excluded_self: bool = True
    string_format: str = "第{index}名：\n{nickname},{chatdatanum}条消息\n"  # 消息格式
    template_path: str = "./template/rank_template.j2"  # 模板路径
    visualization: bool = True  # 是否可视化
    excluded_people: List[str] = []  # 排除的人的QQ号
    suffix: bool = False  # 是否显示后缀
    string_suffix: str = "统计花费时间:{timecost}秒"  # 消息格式后缀


class Config(BaseModel):
    dialectlist: ScopedConfig = ScopedConfig()


global_config = get_driver().config
plugin_config = get_plugin_config(Config).dialectlist
