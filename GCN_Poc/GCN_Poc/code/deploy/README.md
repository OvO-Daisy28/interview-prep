# 131 上的部署与自启动

两个 systemd unit，装在**宿主机**上。原则：**只用 `docker exec`，绝不 restart / recreate 容器**——`docker-ragflow-cpu-1` 是 RAGFlow 自己在用的，不是我们能中断的。

## 为什么是这个形态

摄入服务必须跑在 RAGFlow 容器**内部**：MySQL、Elasticsearch、MinIO、embedding 服务都只在那个 docker 网络里可达。

但容器内用 `docker exec` 起的进程**不会随容器一起回来**，而容器本身是 `restart=unless-stopped`（会自己重启）。所以需要宿主上有个东西去发现并重新拉起——就是 `keepalive.sh`。

宿主访问不到容器端口，又不能为了发布端口而重建容器（会中断 RAGFlow），所以用 `demo_forward.py` 做 TCP 转发。

```
浏览器 ──> 宿主 :9800 ──[gcn-demo-forward]──> 容器 192.168.80.6:9800
                                                    ▲
                              [gcn-ingest] 每 15s 查一次，挂了就 docker exec 拉起
```

## 安装

```bash
# 1. 目录与文件
mkdir -p /opt/gcn
cp keepalive.sh demo_forward.py /opt/gcn/
chmod +x /opt/gcn/keepalive.sh

# 2. 环境变量（含密码，600，不进 git）
cat > /etc/gcn-ingest.env << 'EOF'
GCN_TENANT_ID=<租户 id>
GCN_DB_HOST=mysql
GCN_DB_PASSWORD=<mysql 密码>
GCN_WARM_KB=<预热用的知识库 id>
GCN_MAX_CONCURRENT=3
MINERU_URL=http://172.17.0.1:8010
EOF
chmod 600 /etc/gcn-ingest.env

# 3. unit
cp gcn-ingest.service gcn-demo-forward.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now gcn-ingest gcn-demo-forward
```

`GCN_DB_HOST=mysql`、`MINERU_URL` 用宿主网关 `172.17.0.1`——这两个是**容器内**的视角，因为服务进程跑在容器里。

## 运维

| 想干什么 | 命令 |
|---|---|
| 看状态 | `systemctl status gcn-ingest gcn-demo-forward` |
| 看拉起记录 | `journalctl -u gcn-ingest -n 50` |
| 看服务自身日志 | `docker exec docker-ragflow-cpu-1 tail -50 /tmp/ingest_service.log` |
| 改代码后重启 | `docker exec docker-ragflow-cpu-1 pkill -f ingest.service`（15s 内自动拉起新代码） |
| 停掉 | `systemctl stop gcn-ingest` |

**改代码后不用 `systemctl restart`**：直接 kill 容器内进程即可，keepalive 会用新代码拉起来。这也是为什么 keepalive 用轮询而不是前台 `docker exec`。

## 部署代码到容器

宿主与本机之间 scp 被 JumpServer 拦，用 base64 走 ssh 管道：

```bash
base64 -w0 ingest/demo_page.py | ssh wenge-ragflow-131 "base64 -d > /tmp/demo_page.py"
ssh wenge-ragflow-131 "docker cp /tmp/demo_page.py docker-ragflow-cpu-1:/ragflow/ingest/demo_page.py"
```

传完**核对 md5**再重启，别凭文件大小判断。

## 注意

- 容器没起来时 keepalive 只等待，**不会去启动容器**——启不启是 RAGFlow 那边的事。
- `systemctl stop gcn-ingest` 会顺带 `pkill` 容器内进程（`ExecStop`，失败不阻塞）。
- 预热要 ~17s（`init_settings` 16.5s），所以拉起后不是立刻可用，`/demo` 会有十几秒打不开。
