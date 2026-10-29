# 月印 Moonprint · 上线部署指南

把「月印」网页永久上线，并支持后续迭代更新。目标形态：**云服务器 + Docker 常驻运行**。

代码仓库（私有）：`https://github.com/Trace-2001/moonprint`

---

## 一、总体架构

```
用户浏览器
    │  http://你的域名或IP:8765
    ▼
云服务器（腾讯云轻量 / 阿里云 ECS）
    │  运行 Docker 容器「moonprint」
    ├── Python 渲染服务（numpy 逐像素 + ephem 星历）
    └── NASA 贴图（挂载卷 /data，首次运行自动下载）
```

关键点：
- **贴图不打进镜像**，首次运行自动从 NASA 下载到 `/data/textures`（挂载卷持久化，重启不丢）。
- 代码更新 = 拉新镜像重启，几秒钟完成，不影响数据。

---

## 二、第一步：买服务器（一次性）

任选一家，最低配即可（月印是 CPU 渲染，不吃内存/带宽）：

| 平台 | 推荐产品 | 参考价格 |
|---|---|---|
| 腾讯云 | 轻量应用服务器（2核2G） | ~¥50–100/月 |
| 阿里云 | 轻量应用服务器 / ECS（2核2G） | ~¥50–100/月 |

选系统镜像时选 **Ubuntu 22.04**（或 Debian 12）。

> 服务器地域建议选离你和访客近的（国内就选境内节点）。
> 用 IP 直接访问可先不备案；要绑自己域名并稳定访问，国内服务器需完成 **ICP 备案**（腾讯云/阿里云控制台可免费代办）。

拿到服务器后，你会得到：
- **公网 IP**（例如 `123.45.67.89`）
- **SSH 登录方式**（密码或密钥）

---

## 三、第二步：服务器装 Docker（一次性，约 2 分钟）

SSH 登录服务器后执行（Ubuntu/Debian 通用）：

```bash
# 一键安装 Docker
curl -fsSL https://get.docker.com | sh

# 把当前用户加入 docker 组（免 sudo）
sudo usermod -aG docker $USER

# 重新登录使组生效
exit   # 然后重新 SSH 登录

# 验证
docker --version
docker compose version
```

---

## 四、第三步：拉取代码并启动（约 3 分钟）

服务器上执行：

```bash
# 1. 拉取代码（私有仓库，用你的账号）
git clone git@github.com:Trace-2001/moonprint.git
cd moonprint

# 2. 构建并后台启动
docker compose up -d --build

# 3. 查看运行状态
docker compose ps
docker compose logs -f moonprint   # 看日志，Ctrl+C 退出
```

首次启动会看到它自动下载 NASA 贴图（约 92MB，视服务器网络 1–3 分钟）。

**打开防火墙端口 8765**（腾讯云/阿里云控制台 → 防火墙/安全组 → 放行 TCP 8765）。

完成后，浏览器访问：

```
http://你的服务器IP:8765
```

就能看到月印网页了。

---

## 五、绑定域名（可选）

1. 在域名服务商（或腾讯云/阿里云）买域名，完成 ICP 备案。
2. 域名解析加一条 A 记录指向服务器 IP。
3. 用 **Nginx 反向代理** 或直接改端口为 80：

   ```bash
   # 简单做法：让容器直接映射到 80 端口
   # 编辑 docker-compose.yml，把 "8765:8765" 改成 "80:8765"
   # 然后 docker compose up -d
   ```

   之后直接 `http://你的域名` 访问。

---

## 六、迭代更新（以后每次改代码的流程）

这是「永久上线 + 可迭代」的核心闭环：

```bash
# 在本地（Cursor 里）改完代码后：

# 1. 提交并推送
git add -A
git commit -m "描述这次改了什么"
git push origin main

# 2. SSH 到服务器，拉取并重启
ssh 你的服务器
cd moonprint
git pull
docker compose up -d --build    # 重建镜像并重启
```

改完即上线，几秒钟完成。贴图在挂载卷里，重启不会重新下载。

---

## 七、常见问题

| 问题 | 处理 |
|---|---|
| 端口访问不通 | 检查云控制台防火墙/安全组是否放行 8765 |
| 贴图下载失败 | 服务器网络受限，手动下载后放到 `/data/textures/`（目录名见 `render.py` 的 `_TEX_SOURCES`） |
| 想换端口 | 改 `docker-compose.yml` 的 `ports`，`docker compose up -d` 生效 |
| 更新后没变化 | 确认 `git pull` 成功、`--build` 有重新构建 |
| 看实时日志 | `docker compose logs -f moonprint` |

---

## 附：不需要 Docker 的裸机跑法

如果不想用 Docker，服务器上直接装 Python 环境：

```bash
sudo apt install -y python3-pip fonts-noto-cjk
git clone git@github.com:Trace-2001/moonprint.git
cd moonprint
pip install .
python3 -m moonbirthday serve --host 0.0.0.0 --port 8765 --no-browser
```

（推荐用 Docker，环境隔离、升级迁移都更省心。）
