<div align="center">
  <a href="https://v2.nonebot.dev/store"><img src="https://s2.loli.net/2022/06/16/opBDE8Swad5rU3n.png" width="180" height="180" alt="NoneBotPluginLogo"></a>
  <br>
  <p><img src="https://s2.loli.net/2022/06/16/xsVUGRrkbn1ljTD.png" width="240" alt="NoneBotPluginText"></p>
</div>

<div align="center">

# 话痨排行榜
nonebot-plugin-dialectlist

\>📄看看群友们这些天在群里水了多少话📄<
</div>

## 版本

v1.0 支持频道咯！(*^_^*)

⚠ 适配nonebot2-2.0.0b5+

## 安装

1. 通过`pip`或`nb`安装；

>**通过pip**安装

`pip install nonebot-plugin-dialectlist`

>**通过nb**安装

`nb plugin install nonebot-plugin-dialectlist`

### 插件依赖于

1. [nonebot-plugin-chatrecorder](https://github.com/noneplugin/nonebot-plugin-chatrecorder) ————获取历史的消息

2. [nonebot-plugin-datastore](https://github.com/he0119/nonebot-plugin-datastore) ————储存历史的消息

3. [nonebot-plugin-guild-patch](https://github.com/mnixry/nonebot-plugin-guild-patch) —————适配频道消息
  
## 配置

需要提前配置本插件所依赖的插件！

在环境配置中，可以添加以下配置项
```python
dialectlist_string_format: str = '第{index}名：\n{nickname},{chatdatanum}条消息\n' #格式
dialectlist_string_suffix_format: str = '\n你们的职业是水群吗？————MYX\n计算花费时间:{timecost}秒' #后缀字符
dialectlist_get_num:int = 10 #排行榜长度
```
也可以完全不配置，直接默认！


## 命令

-`/群话痨排行榜` ————看看有史以来（机器人存在以来）群友们发了多少消息！

-`/今日群话痨排行榜` ————看看今天的群友发了多少消息！

-`/昨日群话痨排行榜` ————看看昨天的群友发了多少消息！

-`/本周群话痨排行榜` ————看看本周的群友发了多少消息！

-`/本月群话痨排行榜` ————看看这个月的群友发了多少消息！

-`/年度群话痨排行榜` ————看看今年的群友发了多少消息！

-`/历史群话痨排行榜` ————看看历史上（机器人存在以来）的群友发了多少消息！

## 另外

### 感谢

本插件的__init__.py中的处理函数参考了词云中的方法 ~~（其实大部分都是Ctrl+C Ctr+V）~~

[nonebot-plugin-wordcloud](https://github.com/he0119/nonebot-plugin-wordcloud)
  
  
## TODO

1.私聊的查询 ~~（让我先咕一会）~~

  
## 已知BUG

### 频道中同名的人会出现计数重复
  - 这是因为！！因为chatrecorder其实不支持频道消息，所有我写了一个保存在json中的版本，然后频道api怎么样都通过不了user_id获取nickname，于是我就放弃了（悲）
  - *今后会试试~~写一个~~适配频道的chatrecorder*（（（（（
  
