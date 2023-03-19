<div align="center">
  <a href="https://v2.nonebot.dev/store"><img src="https://s2.loli.net/2022/06/16/opBDE8Swad5rU3n.png" width="180" height="180" alt="NoneBotPluginLogo"></a>
  <br>
  <p><img src="https://s2.loli.net/2022/06/16/xsVUGRrkbn1ljTD.png" width="240" alt="NoneBotPluginText"></p>
</div>

<div align="center">

# 话痨排行榜
nonebot-plugin-dialectlist

\>💬**看看群友们这些天在群里水了多少话**💬<
</div>


## 安装

1. 通过`pip`或`nb`安装；

>**通过pip**安装

`pip install nonebot-plugin-dialectlist`

>**通过nb**安装

`nb plugin install nonebot-plugin-dialectlist`

### 插件依赖于

1. [nonebot-plugin-datastore](https://github.com/he0119/nonebot-plugin-datastore) ————储存历史的消息

2. [nonebot-plugin-guild-patch](https://github.com/mnixry/nonebot-plugin-guild-patch) —————适配频道消息
  
## 配置

需要**提前配置**本插件所**依赖的插件**！

在环境配置中，可以添加以下配置项
```python
    dialectlist_string_format: str = '第{index}名：\n{nickname},{chatdatanum}条消息\n' #消息格式
    dialectlist_string_suffix_format: str = '你们的职业是水群吗？————MYX\n计算花费时间:{timecost}秒' #消息后缀格式
    dialectlist_get_num:int = 10 #获取人数数量
    dialectlist_visualization:bool = True #是否可视化
    dialectlist_visualization_type:Literal['饼图','圆环图','柱状图'] = '圆环图' #可视化方案
    dialectlist_font:str = 'SimHei'#字体格式
    dialectlist_excluded_people:List[str] = []#排除的人的QQ号(或频道号?(未经测试))
    dialectlist_excluded_self:bool = True #是否排除机器人自己QQ
```
💭也可以不进行配置，这将会使插件按照默认配置运行

 ### ⚠ 注意！！
 
  需要提前安装好[GTK+](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer)
  
  在windows以外的环境中可能不存在插件默认的字体！请自行改为系统中拥有的字体！

## 命令

-`/群话痨排行榜` ————看看有史以来（机器人存在以来）群友们发了多少消息！

-`/今日群话痨排行榜` ————看看今天的群友发了多少消息！

-`/昨日群话痨排行榜` ————看看昨天的群友发了多少消息！

-`/前日群话痨排行榜` ————看看前天的群友发了多少消息！

-`/本周群话痨排行榜` ————看看本周的群友发了多少消息！
  
-`/上周群话痨排行榜` ————看看上周的群友发了多少消息！

-`/本月群话痨排行榜` ————看看这个月的群友发了多少消息！

-`/年度群话痨排行榜` ————看看今年的群友发了多少消息！

-`/历史群话痨排行榜` ————看看历史上（机器人存在以来）的群友发了多少消息！


# 注意💥,在目前版本中不支持频道
  
## 版本
  
### V1.0
  
  - 看看群里群友能有多话痨
  
### V1.1
  
  - 支持频道咯！(*^_^*)
  
### V1.2
  
  - 排行榜可视化
  
### V1.3

  - 添加了一些可配置项
  
### V1.4

  - 适配新版本的chatrecorder,暂时停止频道支持

## 另外

### 感谢

本插件的__init__.py中的处理函数参考了词云中的方法 ~~（其实大部分都是Ctrl+C Ctr+V）~~

[nonebot-plugin-wordcloud](https://github.com/he0119/nonebot-plugin-wordcloud)
  
  
## TODO

1. 私聊的查询 ~~（让我先咕一会）~~

2. 频道重新支持

3. 查询机器人自己的消息量

4. 待补充......

## 已知BUG
  
1. 字体可能要自己配置(bug?)

# 题外话
**学业问题可能只有周末才能看iusse和更新插件**
~~整个项目快被我写成屎山了~~
