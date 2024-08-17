<div align="center">
  <a href="https://v2.nonebot.dev/store"><img src="./docs/NoneBotPlugin.svg" width="400" alt="NoneBotPluginLogo"></a>
  <br>
  <p><img src="https://s2.loli.net/2022/06/16/xsVUGRrkbn1ljTD.png" width="240" alt="NoneBotPluginText"></p>
</div>

<div align="center">

# 📃话痨排行榜
nonebot-plugin-dialectlist

<p align="center">
  <a href="https://pypi.python.org/pypi/nonebot-plugin-dialectlist">
    <img src="https://img.shields.io/pypi/v/nonebot-plugin-dialectlist.svg" alt="pypi">
  </a>
  
  <img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="python">
  
  <a href="https://qm.qq.com/q/Yty2yc9Bee">
    <img src="https://img.shields.io/badge/QQ%E7%BE%A4-1128359833-orange?style=flat-square" alt="QQ Chat Group">
  </a>
</p>

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
dialectlist__string_format = "第{index}名：\n{nickname},{chatdatanum}条消息、\n" #消息格式
dialectlist__get_num = 10 #获取人数数量
dialectlist__visualization = True #是否可视化
# dialectlist__visualization_type = "圆环图" #可视化方案 （不再支持）
dialectlist__font = "SimHei" #字体格式
dialectlist__excluded_people = [] #排除的人的 QQ 号（或频道号？（未经测试）)
dialectlist__excluded_self = True #是否排除机器人自己 QQ
dialectlist__suffix: bool = False  # 是否显示后缀
dialectlist__string_suffix: str = "统计花费时间{timecost}"  # 消息格式后缀
```
💭也可以不进行配置，这将会使插件按照默认配置运行

 ### ⚠ 注意！！

> 在旧版插件（2.0.0 以下）中，dialectlist 与后面的配置项只隔了一个下划线，若更新到新版本以后需要俩个下划线。

## 🗨命令
__！！注意！！__
新版本指令调用方式改变，改为更易理解也更好打的 B 话榜。
同时也可以用类似 `/今日废话榜` 的方式（只要改前面的就好了）（算是给 [盘古之白](https://github.com/vinta/pangu.js) 风格爱好者的福利吧？）

### 🎨一般用法

-`/B话榜` ————看看有史以来（机器人存在以来）群友们发了多少消息！ （好像没写）

-`/今日B话榜` ————看看今天的群友发了多少消息！

-`/昨日B话榜` ————看看昨天的群友发了多少消息！

-`/前日B话榜` ————看看前天的群友发了多少消息！

-`/本周B话榜` ————看看本周的群友发了多少消息！
  
-`/上周B话榜` ————看看上周的群友发了多少消息！

-`/本月B话榜` ————看看这个月的群友发了多少消息！

-`/年度B话榜` ————看看今年的群友发了多少消息！

-`/历史B话榜` ————看看历史上（机器人存在以来）的群友发了多少消息！

### 🚀进阶用法

`/{时间类型（今日|年度）?}{B话榜|废话榜} {时间类型？} {ISO8601 格式时间} {群号}`

如：`/B话榜 历史 2024-01-01~2024-01-02 12345678`

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

### 😳加入作者的 BUG 反馈群 ~~（🥵女装粉丝群）~~

[群连接](https://qm.qq.com/q/Yty2yc9Bee)

<details>
<summary>群二维码 点我展开</summary>

![7a4bd22dea47d25d9b632d4b2696d4cd](https://github.com/ChenXu233/nonebot_plugin_dialectlist/assets/91937041/61fd7010-e2b2-4f13-b209-9c0faf8a517f)

</details>

### 💕感谢

本插件的__init__.py 中的处理函数参考了词云中的方法 ~~（其实大部分都是 Ctrl+C Ctr+V）~~

[nonebot-plugin-wordcloud](https://github.com/he0119/nonebot-plugin-wordcloud)

感谢以下开发者作出的贡献：

<a href="https://github.com/ChenXu233/nonebot_plugin_dialectlist/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=ChenXu233/nonebot_plugin_dialectlist&max=1000" />
</a>
  
### 🎀TODO

- [x] 适配全平台

- [x] 尝试利用 jinja2 模板引擎制作可视化图片

- [x] 私聊的查询（超级用户可以任意查询群聊的信息）一半完成

- [x] 添加一些全新的可配置项

- [x] 更好看的图片渲染

- [ ] 提供多样化的渲染器配置（html 渲染，pillow 渲染，统计绘图软件渲染）
- [ ] 为 pillow 渲染方式提供插件的加载方式（什么？插件里的插件？？？）

- [ ] 查询带某关键词的消息量

- [ ] 使用管理员权限直接获取 QQ 官方统计的今日消息量以优化代码运行速度

- [ ] 特殊的储存方案优化消息统计
  
 待补充。.....

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


### V2.1

  - 恢复图片支持。

### V2.2

  - 优化代码，添加一些新的可配置项。

### 👾题外话
~~整个项目快被我写成屎山了~~
