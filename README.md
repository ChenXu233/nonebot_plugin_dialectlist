<div align="center">
  <a href="https://v2.nonebot.dev/store"><img src="https://s2.loli.net/2022/06/16/opBDE8Swad5rU3n.png" width="180" height="180" alt="NoneBotPluginLogo"></a>
  <br>
  <p><img src="https://s2.loli.net/2022/06/16/xsVUGRrkbn1ljTD.png" width="240" alt="NoneBotPluginText"></p>
</div>

<div align="center">

# 📃话痨排行榜
nonebot-plugin-dialectlist

\>💬**看看群友们这些天在群里水了多少话**💬<
</div>

## 💿 安装

通过`pip`或`nb`安装；

>**通过 pip **安装

`pip install nonebot-plugin-dialectlist`

>**通过 nb **安装

`nb plugin install nonebot-plugin-dialectlist`

### ✅ 插件依赖于

1. [nonebot-plugin-datastore](https://github.com/he0119/nonebot-plugin-datastore) ————储存历史的消息
2. [nonebot-plugin-userinfo](https://github.com/noneplugin/nonebot-plugin-userinfo) ————获取用户信息
3. [nonebot-plugin-apscheduler](https://github.com/nonebot/plugin-apscheduler) ————定时发送排行榜信息
4. [nonebot-plugin-alconna](https://github.com/ArcletProject/nonebot-plugin-alconna) ————实现命令解析
5. [nonebot-plugin-cesaa](https://github.com/MountainDash/nonebot-plugin-send-anything-anywhere) ————实现多平台
  
## ⚙ 配置

需要**提前配置**本插件所**依赖的插件**！

在 .env 中，可以添加以下配置项
```python
dialectlist__string_format = '第{index}名：\n{nickname},{chatdatanum}条消息、n' #消息格式
dialectlist__string_suffix_format = '你们的职业是水群吗？————MYX\n 计算花费时间：{timecost}秒' #消息后缀格式
dialectlist__get_num = 10 #获取人数数量
dialectlist__visualization = True #是否可视化
dialectlist__visualization_type = '圆环图' #可视化方案
dialectlist__font = 'SimHei'#字体格式
dialectlist__excluded_people = []#排除的人的 QQ 号（或频道号？（未经测试）)
dialectlist__excluded_self = True #是否排除机器人自己 QQ
```
💭也可以不进行配置，这将会使插件按照默认配置运行

 ### ⚠ 注意！！

> 在旧版插件（2.0.0 以下）中，dialectlist 与后面的配置项只隔了一个下划线，若更新到新版本以后需要俩个下划线。

## 🗨命令
__！！注意！！__
新版本指令调用方式改变，改为更易理解也更好打的 B 话榜。
同时也可以用类似 `/今日废话榜` 的方式(只要改前面的就好了)（算是给[盘古之白](https://github.com/vinta/pangu.js)风格爱好者的福利吧？）

### 🎨一般用法

-`/B话榜` ————看看有史以来（机器人存在以来）群友们发了多少消息！ (好像没写)

-`/今日B话榜` ————看看今天的群友发了多少消息！

-`/昨日B话榜` ————看看昨天的群友发了多少消息！

-`/前日B话榜` ————看看前天的群友发了多少消息！

-`/本周B话榜` ————看看本周的群友发了多少消息！
  
-`/上周B话榜` ————看看上周的群友发了多少消息！

-`/本月B话榜` ————看看这个月的群友发了多少消息！

-`/年度B话榜` ————看看今年的群友发了多少消息！

-`/历史B话榜` ————看看历史上（机器人存在以来）的群友发了多少消息！

### 🚀进阶用法

`/{时间类型(今日|年度)?}{B话榜|废话榜} {时间类型?} {ISO8601格式时间} {群号}`

如：`/B话榜 历史 2024-01-01~2024-01-02 12345678`


## 📖版本
  
### V1.0
  
  - 看看群里群友能有多话痨
  
### V1.1
  
  - 支持频道咯！(*^_^*)
  
### V1.2
  
  - 排行榜可视化
  
### V1.3

  - 添加了一些可配置项
  
### V1.4

  - 适配新版本的 chatrecorder, 暂时停止频道支持

### V2.0

  - 理论支持全平台！暂停图片支持。

## 💪 目前支持的平台

| 平台 | 是否经过测试 | 是否能够正常工作 | 测试环境 |
|:-----:|:----:|:----:| :----: |
| Onebot | ✅ | ✅ | NapCat + Window11|
| 飞书  | ❌ | ❓ | 🤔 |
| Red  | ❌ | ❓ | 🤔 |
| DoDo  | ❌ | ❓ | 🤔 |
| Mirai  | ❌ | ❓ | 🤔 |
| 开黑啦  | ❌ | ❓ | 🤔 |
| Kritor  | ❌ | ❓ | 🤔 |
| Ntchat  | ❌ | ❓ | 🤔 |
| Satori  | ❌ | ❓ | 🤔 |
| Telegram | ❌ | ❓ | 🤔  |
| Discord  | ❌ | ❓ | 🤔 |
| Tailchat  | ❌ | ❓ | 🤔 |
| QQ 官方接口  | ❌ | ❓ | 🤔 |
| Rocket.Chat  | ❌ | ❓ | 🤔 |

- 如果你测试过能够使用，请在 Issue 中指出

## 📦另外

### 💕感谢

本插件的__init__.py 中的处理函数参考了词云中的方法 ~~（其实大部分都是 Ctrl+C Ctr+V）~~

[nonebot-plugin-wordcloud](https://github.com/he0119/nonebot-plugin-wordcloud)
  
### 🎀TODO

- [x] 适配全平台

- [ ] 私聊的查询（超级用户可以任意查询群聊的信息）

- [ ] 关键词查询

- [ ] 尝试利用 jinja2 模板引擎制作可视化图片 ((（真的可以吗？))
  
 待补充。.....

### 👾题外话
~~整个项目快被我写成屎山了~~
