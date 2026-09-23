# Windows 上把它跑起来

给完全没接触过命令行的人写的。**照着做，一步都别跳。**
遇到看不懂的报错，把整个窗口截图发出来问。

---

## 第 1 步：装 Python

1. 打开 **python.org/downloads/windows**，下载最新的 **Python 3.11 或 3.12**
   （别下 3.13，有些库还没跟上）
2. 双击安装包。**装之前务必勾上最下面那个 `Add Python to PATH`** ← 这一步漏了后面全错
3. 点 `Install Now`，等它装完

**验证装好了**：按 `Win + R`，输入 `cmd` 回车，在黑窗口里输入：

```
python --version
```

看到 `Python 3.11.x` 之类就对了。如果提示「不是内部或外部命令」，说明第 2 步的勾没打上——
重新运行安装包，选 `Modify`，把 `Add Python to PATH` 勾上。

## 第 2 步：拿到代码

装 Git（**git-scm.com** 下载，一路下一步即可），然后在 cmd 里：

```
cd %USERPROFILE%\Desktop
git clone https://github.com/COLDDCC/SuDa-Pro.git
cd SuDa-Pro\backend
```

> 不想装 Git 也行：在 GitHub 页面点绿色的 `Code` → `Download ZIP`，
> 解压到桌面，然后 `cd %USERPROFILE%\Desktop\SuDa-Pro\backend`

## 第 3 步：装依赖（只需做一次）

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

第二行执行后，命令行前面会多出一个 `(.venv)`，**说明进对了环境**。
第三行会下载一堆东西，等一两分钟。

> 以后每次重新打开 cmd，都要先 `cd` 到 backend 目录再执行 `.venv\Scripts\activate`，
> 否则会提示找不到模块。

## 第 4 步：填配置

在 backend 目录下，**每次启动前**都要先设这几个（关掉窗口就没了）：

```
set PYTHONUTF8=1
set WX_APPID=wx48aef7da6d3d6b6a
set WX_SECRET=你的AppSecret
set STAFF_KEY=随便设一个只有你和仓库知道的字符串
set JWT_SECRET=随便设另一个长一点的随机字符串
```

> **`PYTHONUTF8=1` 这条不能省。** 中文版 Windows 的命令行默认不认 `¥` 这类符号，
> 不设的话程序打印金额时会直接崩掉。

嫌每次敲麻烦？在 backend 目录新建一个 `start.bat`，把上面几行加上启动命令写进去，
以后双击它就行：

```bat
@echo off
cd /d %~dp0
call .venv\Scripts\activate
set PYTHONUTF8=1
set WX_APPID=wx48aef7da6d3d6b6a
set WX_SECRET=你的AppSecret
set STAFF_KEY=你设的仓库密钥
set JWT_SECRET=你设的随机字符串
uvicorn app.main:app --host 0.0.0.0 --port 8811
```

> `start.bat` 里有密钥，**别上传到 GitHub**（已经在 .gitignore 里了）。

## 第 5 步：启动

```
uvicorn app.main:app --host 0.0.0.0 --port 8811
```

看到 `Application startup complete` 就是成功了。**这个窗口不能关**，关了服务就停。

**验证**：浏览器打开 `http://127.0.0.1:8811/health`，看到 `{"ok":true}` 就对了。

仓库后台：浏览器打开 `http://127.0.0.1:8811/admin/`，填入你设的 `STAFF_KEY`。

## 第 6 步：确认后端没问题

**另开一个** cmd 窗口（原来那个要留着跑服务）：

```
cd %USERPROFILE%\Desktop\SuDa-Pro\backend
.venv\Scripts\activate
set PYTHONUTF8=1
set STAFF_KEY=你第4步设的那个值
python scripts\smoke_test.py
```

它会把「登录 → 预报 → 称重入库 → 拍照 → 下单 → 收款 → 发货 → 签收」整条线走一遍。
看到最后一行 `[PASS] 全流程走通了` 就说明后端完全正常。

---

## 第 7 步：让手机能连上（内网穿透）

手机上的 `127.0.0.1` 指的是手机自己，连不到你电脑，所以需要一个临时公网地址。

1. 打开 **cpolar.com**，注册（免费），下载 Windows 版
2. 安装后按它的说明填入你的 authtoken
3. 开一个新 cmd 窗口，执行：

```
cpolar http 8811
```

4. 窗口里会显示一个 `https://xxxx.cpolar.cn` 的网址，**复制它**

> 免费版每次重启地址会变，变了就要回到下一步重新填一次。

## 第 8 步：小程序连上后端

1. 用记事本打开 `SuDa-Pro\miniprogram\utils\config.js`
2. 把 `BASE_URL` 改成刚才复制的那个网址（**结尾不要带斜杠**）：

```js
module.exports = {
  BASE_URL: 'https://xxxx.cpolar.cn',
};
```

3. 微信开发者工具 →「导入项目」→ 选 `miniprogram` 目录（AppID 会自动带出来）
4. 详情 → 本地设置 → 勾上 **「不校验合法域名」**
5. 点「编译」，模拟器里就能用了

## 第 9 步：上体验版，让别人也能测

1. 开发者工具点「**上传**」，版本号随便填 `1.0.0`
2. 打开 **mp.weixin.qq.com** →「版本管理」→ 在开发版那一行点「**选为体验版**」
3. 「成员管理」→「体验成员」→ 把要测试的人的微信号加进去
4. 他们在微信里搜「**小程序开发助手**」→ 找到你的小程序 → **把「调试」开关打开** ← 不开的话请求全被拦

---

## 常见问题

| 现象 | 原因 / 怎么办 |
|---|---|
| `python 不是内部或外部命令` | 装 Python 时没勾 `Add Python to PATH`，重装并勾上 |
| `无法加载文件 activate.ps1` | 你开的是 PowerShell，改用 cmd（Win+R 输 `cmd`） |
| `ModuleNotFoundError: No module named 'fastapi'` | 忘了 `.venv\Scripts\activate`，前面没有 `(.venv)` |
| 打印金额时崩溃 `UnicodeEncodeError` | 忘了 `set PYTHONUTF8=1` |
| 小程序里「网络异常」 | 后端窗口关了？`BASE_URL` 填错了？「不校验合法域名」没勾？ |
| 小程序里「服务端配置的微信 AppSecret 不正确」 | `WX_SECRET` 填错了，回公众平台重新生成 |
| 手机上打不开，模拟器可以 | cpolar 地址变了，重新复制填进 `config.js` 再上传一次 |
| 后台点「标记发货」说没确认收款 | 这是故意的，先去「待收款」点「已收款」 |

## 每天重新开始时

1. 双击 `start.bat`（或者手动 activate + set + uvicorn）
2. 开另一个窗口跑 `cpolar http 8811`
3. 如果 cpolar 地址变了，更新 `config.js` 并重新上传小程序
