import base64
from typing import Union

from nonebot_plugin_userinfo import UserInfo


def _image_mime(data: bytes) -> str:
	"""按文件头猜测头像的 MIME 类型"""
	if data.startswith(b'\x89PNG\r\n\x1a\n'):
		return 'image/png'
	if data.startswith(b'GIF8'):
		return 'image/gif'
	if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
		return 'image/webp'
	return 'image/jpeg'


class UserRankInfo(UserInfo):
	user_bnum: int
	user_proportion: float
	user_nickname: str
	user_index: Union[int, str]
	user_avatar_bytes: bytes

	@property
	def user_avatar_data_uri(self) -> str:
		"""把头像内联成 data URI，模板不再依赖任何本地文件"""
		return (
			f'data:{_image_mime(self.user_avatar_bytes)};base64,'
			+ base64.b64encode(self.user_avatar_bytes).decode('ascii')
		)
