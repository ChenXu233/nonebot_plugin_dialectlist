"""定时推送排行榜"""

from typing import Any, Optional

import nonebot
import nonebot_plugin_saa as saa
from apscheduler.triggers.cron import CronTrigger
from nonebot.adapters import Bot
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler

from .config import PushGroupConfig, plugin_config
from .group_config import all_push_groups, effective_config, store
from .time import get_datetime_now_with_timezone, resolve_period_range
from .utils import (
	RenderError,
	format_rank_text,
	get_previous_message_counts,
	get_rank_image,
	get_user_infos_from_db,
	get_user_message_counts,
	got_rank,
)


def _resolve_target(group_id: str) -> Optional[Any]:
	"""优先用群配置里存下来的 SAA 目标（多平台），老配置回退到 QQ 群"""
	payload = store.get(group_id).push_target
	if payload:
		try:
			return saa.PlatformTarget.deserialize(payload)
		except Exception as e:  # noqa: BLE001 - 目标格式变了也不能让推送炸掉
			logger.warning(
				f'[push] 群 {group_id} 的推送目标解析失败，回退到 QQ 群: {e}'
			)
	try:
		return saa.TargetQQGroup(group_id=int(group_id))
	except ValueError:
		return None


def _pick_bot(target: Any) -> Optional[Bot]:
	"""挑一个能给这个 target 发消息的 bot"""
	for bot in nonebot.get_bots().values():
		try:
			target.arg_dict(bot)
		except Exception:
			continue
		return bot
	return None


async def _check_member_count(
	bot: Bot, group_id: str, min_members: int
) -> bool:
	"""群人数低于阈值就跳过；拿不到群信息时不拦"""
	if min_members <= 0:
		return True
	try:
		info = await bot.call_api('get_group_info', group_id=int(group_id))
	except Exception as e:
		logger.debug(f'[push] 群 {group_id} 取群信息失败，跳过人数检查: {e}')
		return True

	count = getattr(info, 'member_count', None)
	if count is None and isinstance(info, dict):
		count = info.get('member_count')
	if count is None:
		return True
	if count < min_members:
		logger.info(f'[push] 群 {group_id} 人数 {count} < {min_members}，跳过')
		return False
	return True


async def push_rank(group_id: str, cfg: PushGroupConfig) -> None:
	"""给一个群推送排行榜（定时任务入口）"""
	group_cfg = effective_config(group_id)
	if not group_cfg.enabled:
		logger.info(f'[push] 群 {group_id} 已关闭排行榜，跳过')
		return

	period = cfg.period or plugin_config.push_period
	now = get_datetime_now_with_timezone()
	time_range = resolve_period_range(period, now)
	if time_range is None:
		logger.warning(f'[push] 不支持的统计区间: {period}')
		return
	start, stop = time_range

	target = _resolve_target(group_id)
	if target is None:
		logger.warning(
			f'[push] 群 {group_id} 没有可用的推送目标：'
			'非 QQ 群请在本群发一次 /B话榜配置 推送 开'
		)
		return

	bot = _pick_bot(target)
	if bot is None:
		logger.warning(f'[push] 没有可用的 bot 能给群 {group_id} 发消息')
		return

	# 群人数只有 QQ 群拿得到；其他平台跳过这项检查
	if isinstance(target, saa.TargetQQGroup) and not await _check_member_count(
		bot, group_id, cfg.min_members
	):
		return

	counts = await get_user_message_counts(
		scene_ids=[group_id],
		types=['message'],
		time_start=start,
		time_stop=stop,
		exclude_user_ids=group_cfg.excluded_people,
	)
	total = sum(counts.values())
	if total <= 0:
		logger.info(f'[push] 群 {group_id} 在“{period}”没有消息，跳过')
		return
	if total < cfg.min_messages:
		logger.info(
			f'[push] 群 {group_id} 消息量 {total} < {cfg.min_messages}，跳过'
		)
		return

	# 推送配置里的 get_num 优先，其次用该群自己的展示人数
	rank = got_rank(dict(counts), cfg.get_num or group_cfg.get_num)
	if not rank:
		return
	previous_counts = None
	if group_cfg.show_delta:
		previous_counts = await get_previous_message_counts(
			period,
			start,
			stop,
			[group_id],
			exclude_user_ids=group_cfg.excluded_people,
		)
	# get_user_infos_from_db 要的是持久化 id，这里不能先换成平台号
	rank2 = await get_user_infos_from_db(group_id, rank, previous_counts)
	text = format_rank_text(rank2, cfg=group_cfg)
	msg = saa.Text(text) if text else None
	if group_cfg.visualization:
		try:
			image = await get_rank_image(
				rank2,
				group_cfg.template_path,
				group_cfg.theme,
				group_cfg.layout,
				group_cfg.template,
			)
		except RenderError as e:
			logger.exception(f'[push] 群 {group_id} 渲染图片失败，改为只发文字')
			note = saa.Text(f'\n（图片渲染失败：{e}，管理员可以看日志）')
			msg = msg + note if msg else note
		else:
			msg = msg + saa.Image(image) if msg else saa.Image(image)
	if msg is None:
		logger.warning('[push] 文字和图片都被关掉了，没有内容可发')
		return

	try:
		await msg.send_to(target, bot)
	except Exception as e:
		logger.exception(f'[push] 群 {group_id} 推送失败: {e}')
		return

	logger.info(f'[push] 群 {group_id} 推送成功（{period}，共 {total} 条）')


def build_trigger(cron: str) -> CronTrigger:
	if plugin_config.timezone:
		return CronTrigger.from_crontab(cron, timezone=plugin_config.timezone)
	return CronTrigger.from_crontab(cron)


def register_push_jobs() -> None:
	"""按配置同步每个群的定时任务（可重复调用）"""
	# 全局关掉时 all_push_groups 返回空，这里正好顺带把旧任务清掉
	resolved = all_push_groups()

	# 先清掉已经不该存在的任务，保证热重载后不会留下孤儿任务
	expected_ids = {f'dialectlist_push_{gid}' for gid in resolved}
	for job in scheduler.get_jobs():
		if (
			job.id.startswith('dialectlist_push_')
			and job.id not in expected_ids
		):
			scheduler.remove_job(job.id)
			logger.info(f'[push] 已移除任务 {job.id}')

	if not resolved:
		if plugin_config.push_enabled:
			logger.warning(
				'[push] 已开启定时推送，但没有任何群需要推送'
				'（dialectlist__push_groups 和群配置里的推送都是空的）'
			)
		else:
			logger.debug('[push] 定时推送未开启')
		return

	# 任务挂在 nonebot-plugin-apscheduler 的调度器上，它没启动就不会触发
	from nonebot_plugin_apscheduler import plugin_config as apscheduler_config

	if not apscheduler_config.apscheduler_autostart:
		logger.warning(
			'[push] apscheduler_autostart 是 false，定时任务不会自动运行，'
			'需要自己调用 scheduler.start()'
		)

	for group_id, cfg in resolved.items():
		if not cfg.enabled:
			continue
		cron = cfg.cron or plugin_config.push_cron
		try:
			trigger = build_trigger(cron)
		except ValueError as e:
			logger.error(
				f'[push] 群 {group_id} 的 cron 表达式不合法({cron}): {e}'
			)
			continue

		job_id = f'dialectlist_push_{group_id}'
		# 热重载时可能会重复注册，先清掉同 id 的旧任务
		for job in scheduler.get_jobs():
			if job.id == job_id:
				scheduler.remove_job(job_id)
				break

		scheduler.add_job(
			push_rank,
			trigger,
			args=[group_id, cfg],
			id=job_id,
			replace_existing=True,
			misfire_grace_time=3600,
		)
		logger.info(
			f'[push] 已注册群 {group_id} 的定时推送: {cron} '
			f'(区间 {cfg.period or plugin_config.push_period})'
		)
