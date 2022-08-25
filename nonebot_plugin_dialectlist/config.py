from typing import Optional

from nonebot import get_driver
from pydantic import BaseModel, Extra


class Config(BaseModel, extra=Extra.ignore):

    timezone: Optional[str]




global_config = get_driver().config
plugin_config = Config.parse_obj(global_config)