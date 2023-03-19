from typing import Optional, Literal, List
from nonebot import get_driver
from pydantic import BaseModel, Extra


class Config(BaseModel, extra=Extra.ignore):

    timezone: Optional[str]
    dialectlist_string_format: str = '第{index}名：\n{nickname},{chatdatanum}条消息\n' #消息格式
    dialectlist_string_suffix_format: Optional[str] = '数你们聊天记录都要花{timecost}秒,你看看你们多能聊!' #消息后缀格式
    dialectlist_get_num:int = 5 #获取人数数量
    dialectlist_visualization:bool = True #是否可视化
    dialectlist_visualization_type:Literal['饼图','圆环图','柱状图'] = '圆环图' #可视化方案
    dialectlist_font:str = 'SimHei'#字体格式
    dialectlist_excluded_people:List[str] = []#排除的人的QQ号(或频道号?(未经测试))
    dialectlist_excluded_self:bool = True

global_config = get_driver().config
plugin_config = Config(**global_config.dict())