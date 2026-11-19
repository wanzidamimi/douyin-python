

# douyin_python —— 抖音弹幕纯协议直连（研究版）

按 `jd-captcha-reverse` skill 的手法实现：**官方运行时在 Node 补环境里执行，Python 侧用 curl_cffi 复刻 Chrome TLS 指纹直连接口**，不逆向签名算法本身。

## 运行

```bash
pip install -r requirements.txt
双击 启动弹幕GUI.bat        # 或 python -m uvicorn app:app --host 127.0.0.1 --port 8800
```

浏览器打开 `http://127.0.0.1:8800`，输入直播地址 → 连接，弹幕在列表滚动显示。

- 顶部「显示类别」可勾选要展示的弹幕种类（弹幕 / 勋章·等级 / 礼物 / 点赞 / 进场 / 互动 / 粉丝团 / 数据 / 排行 / 系统 / 其他），默认全选，切换即时生效。
- 连接→停止期间自动累计弹幕，停止时写入 `exports/danmu_*.csv`（UTF-8-BOM，Excel 直接打开）；也可随时点「导出CSV」，或用「历史」面板查看并下载过往文件。

自检（不依赖网络）：

```bash
python selftest.py          # 签名 + 解码 + 昵称 + 分类 + 文案翻译 + CSV 导出（27 项）
python signer.py            # stub 与抓包实证比对
```

## 架构与归属

| 文件 | 归属 | 作用 |
|---|---|---|
| `vendor/*.js` | **官方 vendor 包（加载，非编写）** | 抖音 webmssdk / bdms / secsdk 官方运行时 |
| `node_env/env_core.js` | 项目自写 | Proxy 补环境 + navigator/canvas/WebGL 指纹伪装 + `setFuncNative` |
| `node_env/sign.js` | 项目自写 | `vm` 加载官方 SDK（filename 伪装 CDN URL）+ stdio JSON-RPC 签名桥 |
| `signer.py` | 项目自写 | 13 参数固定串 → md5 → X-MS-STUB → Node 官方 SDK → X-Bogus |
| `http_client.py` | 项目自写 | curl_cffi(impersonate=chrome) + Chrome 头，负责会话初始化 |
| `dyproto/decoder.py` | 项目自写 | 无 schema 的 protobuf wire 递归解码 + gzip + mojibake 修复 + User 昵称精确提取 |
| `category.py` | 项目自写 | 消息类型 → 可筛选类别映射 + 勋章文案识别 + 内容细分 |
| `recorder.py` | 项目自写 | 会话弹幕累计 + CSV 导出 + 历史列表与安全下载 |
| `danmu_client.py` / `app.py` | 项目自写 | WS 直连 / FastAPI + SSE + 滚动列表 + 分类/导出接口 |

## 已闭环（实测）

1. **签名闭环**：`X-MS-STUB = md5(13参数固定串)`，串格式 `live_id=1,aid=6383,...,identity=audience`（顺序固定、空值保留 `k=`），已与抓包 `46e23ef...` 完全一致；Node 补环境跑官方 webmssdk 产出 16 位 `X-Bogus`，非确定性与真浏览器一致。
2. **数据解码闭环**：真实 WS 帧经 protobuf wire 递归解析 + pb 字段 gunzip，正确还原 `WebcastLiveEcomGeneralMessage` / `为主播点赞了` 等中文内容。数据侧无加密，不需密钥。
3. **传输层**：curl_cffi(chrome) 复刻 TLS/H2 指纹。

## 已完全闭环（借鉴 saermart/DouyinLiveWebFetcher 后）

### 关键突破：补环境"补得太多反而错了"

早期用完整补环境（canvas/WebGL/策略栈/服务端证书/全部 localStorage 指纹）签名，服务端**一律 200 拒绝**。对照实验（见 `test_*.py`）证明：握手只需「合法签名 + 有效 ttwid」，cookie 侧极简（UIFID/fpk/CSRF 都不需要）。

参考 `DouyinLiveWebFetcher/sign.js` 发现根因：官方 webmssdk 初始化时会跑一组**浏览器环境检测**（`sign.js` 第 6979-6985 行 `setTimeout(function(){ _0x18a9f7(), _0x1dbe74(), ... })`）。该项目的做法是**把这段检测注释掉**，只保留纯签名函数 `crawler = _0x5c2014`（即 `frontierSign`），并用极简 document/navigator stub 在 MiniRacer 里跑。我原补环境让检测函数跑了、喂了伪指纹，反而触发错误 attestation 导致拒签。

### 落地方案

- `vendor/webmssdk_stripped.js`：从项目 `sign.js` 复制（官方 vendor 包，加载非编写；关键改动是注释环境检测 + 暴露 `get_sign`）
- `node_env/sign_stripped.js`：极简 stub 的 JSON-RPC 签名桥（本项目自写）
- `signer.py` 的 `NodeSigner(mode="stripped")` 为默认，产出服务端认可的 X-Bogus
- `http_client.py` 的 curl_cffi 自己访问直播间页拿 `ttwid` + 真实 `room_id`（SSR 里 `roomId`/`room.id_str` 字段）
- `danmu_client.py` + `app.py` 用以上链路，GUI 实时滚动弹幕

### 实测结果（全链路，无真浏览器依赖）

- 项目裁剪签名 + 真机会话 → 101 + 真实弹幕（`test_project_sign.py`）
- **纯独立客户端**：curl_cffi 自建会话 + 裁剪签名 → 101 + 2 帧（`test_standalone.py`）
- **GUI 同款路径**：`test_e2e.py` → `WebSocket 已握手 (101)` + 持续滚动弹幕（在线人数/排行榜/进场/点击/商品推荐）
- 核心自检 `selftest.py` 27/27 PASS

启动：双击 `启动弹幕GUI.bat` → 打开 `http://127.0.0.1:8800` → 输入直播地址即可。

## 弹幕分类与历史导出

`category.py` 把 `WebcastXxxMessage` 映射为 11 个可筛选类别，并识别 `荣誉等级N级勋章` / `【…勋章…】` 文案归入「勋章/等级」；对电商通用消息按**主 content** 关键词细分为点赞/互动（避免噪声字段误判）。真机 25 秒采集验证：勋章（11/13/15 级）、小时榜→排行、进场、数据、点赞均能正确分类。

`recorder.py` 在连接时 `begin()`、每条弹幕 `add()`、停止时 `save()` 到 `exports/`；CSV 列含 时间/类别/消息类型/用户/内容/原文/seq。后端提供 `/api/categories`、`/api/export`、`/api/history`、`/api/download/{name}`，`path_for` 防目录穿越。

## 用户昵称提取

抖音网页端下发的昵称本身是**脱敏**的（如 `年***`、`雲***`），页面看到的就是这个。早期解码器把所有字符串拍平后取"短串"当用户，误把 `#b8ffffff` 颜色码、`room_follow_msg` 字段名当昵称。对照 `douyin.proto` 的 `User{nickName=3, AvatarThumb=9}`，在递归解析时按「field3 文本 + field9 头像图床 URL」的结构特征定位 User 子消息，精确取 nickName。真机 60 秒采集 12 条 `WebcastChatMessage` 昵称全部正确显示。

## 进场内部标识的中文翻译

`enterroom_normal` / `enter_room_downgrade_aggregate_message` 是 protobuf `MemberMessage.action_description`、`RoomMessage.biz_scene` 的**内部枚举标识**，不是给用户看的文案。对照抖音前端真实 JS（`island_237ab.*.js`，`950481` 模块）确认：前端用 `biz_scene==="enter_room_downgrade_aggregate_message"` 判断把进场消息降级为聚合提示，进场中文由服务端下发的 `common.display_text` 渲染，并不直接显示英文标识。无 schema 解码把它们误当正文，`decoder.py` 的 `_ACTION_TEXT` 已映射为中文（如"进入了直播间（聚合进场）"），并过滤 mime/图片路径等技术串。

`LivePopMessage` 同理：抖音前端 JS（`967.261109ce.js`）里它是 `WebcastLiveEcomGeneralMessage.content_type` 的值，前端解析 `payload.data` 里的 `msg_type`（POP_APPEAR / POP_DISAPPEAR）来控制**商品推广弹窗卡**的出现/消失，并不显示在聊天列表。本工程把它译为"商品推广弹窗提示"，并单独归入「电商」类别，可在前端筛选掉；其中的"为主播点赞了"等内容仍会细分为「点赞」。

### 与参考项目的核心区别

| 维度 | DouyinLiveWebFetcher | 本工程 |
|---|---|---|
| 签名运行时 | MiniRacer 跑裁剪 sign.js | Node vm 跑裁剪 sign.js（等价） |
| HTTP 客户端 | `requests`（普通 TLS） | `curl_cffi(chrome)`（TLS/H2 指纹更接近真机） |
| room_id 提取 | 正则 `roomId\\":\\"` | SSR 反转义后多模式提取 |
| protobuf | 官方 `douyin.proto` + protoc 生成类（精确） | 无 schema 的 wire 递归解码（免 protoc，字段语义靠启发式） |
| 消息类型 | `method` 精确分发 14 种 | 从可读串启发式提取类型/用户/内容 |
| a_bogus | 有独立 a_bogus.js（room/enter 接口用） | 仅 WS 签名，room_id 从 SSR 拿故不需要 |
| GUI | 无（命令行打印） | FastAPI + SSE + 滚动列表 |

**可借鉴点已吸收**：裁剪环境检测（决定性）、签名参数串与 md5 流程（本工程独立验证一致）、msToken 形态。`protobuf` 精确 schema 分发（`douyin.proto`）是本工程可进一步吸收的方向——当前无 schema 解码在复杂消息上字段归属会有偏差。

## 合规

仅限学习研究，遵守目标站服务条款，控制访问频率，不传播任何隐私数据。
