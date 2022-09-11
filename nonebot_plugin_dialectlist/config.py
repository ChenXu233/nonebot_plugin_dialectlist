from typing import Optional
from nonebot import get_driver
from pydantic import BaseModel, Extra
from pathlib import Path

import os

class Config(BaseModel, extra=Extra.ignore):

    timezone: Optional[str]
    dialectlist_string_format: str = '第{index}名：\n{nickname},{chatdatanum}条消息\n'
    dialectlist_string_suffix_format: str = '你们的职业是水群吗？————MYX\n计算花费时间:{timecost}秒'
    dialectlist_path:str = os.path.dirname(__file__)
    dialectlist_image_path: Path = Path(dialectlist_path)/'image.png'
    dialectlist_imageSvg_path: Path = Path(dialectlist_path)/'image.svg'
    dialectlist_json_path:Path = Path(dialectlist_path)/'qqguild.json'
    dialectlist_get_num:int = 10
    dialectlist_visualization:bool = True

global_config = get_driver().config
plugin_config = Config.parse_obj(global_config)