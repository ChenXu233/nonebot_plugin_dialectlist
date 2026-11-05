# CHANGELOG

每个版本一个文件，命名 `v<版本号>.md`，与 git tag 一一对应（tag 的 `V` 前缀在这里省略）。

- 发布 workflow 会把对应版本的文件作为 GitHub Release 的正文
- 打 tag 时如果找不到对应文件，workflow 会直接失败，不会把包发到 PyPI
- 2.x 的内容是从提交历史自动整理的，3.0 之后是手写的

新增版本时，先写好 `v3.5.0.md`，再打 `V3.5.0` 的 tag。
