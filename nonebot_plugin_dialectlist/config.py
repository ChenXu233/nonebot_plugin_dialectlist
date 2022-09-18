from typing import Optional, Union, Literal
from nonebot import get_driver
from pydantic import BaseModel, Extra


class Config(BaseModel, extra=Extra.ignore):

    timezone: Optional[str]
    dialectlist_string_format: str = '第{index}名：\n{nickname},{chatdatanum}条消息\n' #消息格式
    dialectlist_string_suffix_format: str = '你们的职业是水群吗？————MYX\n计算花费时间:{timecost}秒' #消息后缀格式
    dialectlist_get_num:int = 10 #获取人数数量
    dialectlist_visualization:bool = True #是否可视化
    dialectlist_visualization_type:Literal['饼图','圆环图','柱状图'] = '圆环图' #可视化方案

global_config = get_driver().config
plugin_config = Config.parse_obj(global_config)