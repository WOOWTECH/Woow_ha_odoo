# 在真實主機上驗一個 branch：本地 add-on 建置程序
# Verifying a Branch on a Real Host with a Local Add-on Build

> 對象：maintainer。本文件是**程序**，不是測試計劃；要跑的檢測項目在同目錄的
> `INGRESS_VS_PUBLIC_PARITY.md` 與 `COMMERCIAL_PREDEPLOY.md`。
>
> 用語依 `CONTEXT.md`：本地建置**不是** Deploy，也**不是** Release。它只是讓
> Supervisor 在主機上從原始碼建出一個 `local_<slug>` add-on，與已安裝的
> Released 實例並存。

---

## 1. 何時用

要在真實 Home Assistant 主機上驗一個**還沒 Release** 的 branch 時（例如 Live tier
測試需要的 cont-init 渲染路徑，#70）。

依 [ADR 0001](../adr/0001-distribution-follows-release-tags.md)，映像只在 Release
時產生，Deploy 只裝 Release；branch 不會有預建映像。所以在真機上跑一個 branch 的
**唯一**辦法，就是把它放進主機的 `/addons/`，讓 Supervisor 在本機建置。
`.6` 測試機上的 `local_odoo18ce` 就是這樣來的。

## 2. 把來源放到 `/addons/<dir>`

把 branch 的 `odoo18ce/` 整個目錄複製到主機的 `/addons/<dir>`（透過 SSH add-on
或 Samba add-on 看得到的 `addons` 分享）。`<dir>` 取什麼名字都可以，Supervisor
看的是 `config.yaml` 的 `slug:`，不是目錄名。例如在一份已 checkout 該 branch 的
工作目錄：

```bash
ssh root@<host> rm -rf /addons/odoo18ce_branch
scp -O -r odoo18ce root@<host>:/addons/odoo18ce_branch
```

先刪再複製：目錄已存在時 `scp -r` 會把新內容放進 `/addons/odoo18ce_branch/odoo18ce/`
這個子目錄，而不是覆蓋，結果建的還是舊的程式碼。`-O` 讓新版 OpenSSH 改用舊的 scp
協定，因為 SSH add-on 不一定提供 SFTP。同一個 `slug:` 在 `/addons/` 下只能有一份。

## 3. 只在本地副本改 `config.yaml`

以下修改**只做在主機上 `/addons/<dir>/config.yaml` 這份副本**，**永遠不 commit
回 branch**。repo 裡的 `config.yaml` 必須保留 `image:`，它是 Release 流程的一部分。

| 鍵 | 動作 | 原因 |
|---|---|---|
| `image:` | **整行移除** | 留著它，Supervisor 會去 pull 預建映像而不是本地建置（陷阱 a） |
| `version:` | 加上本地標記，用 **`-`**，**不能用 `+`**，且後綴要**逐次遞增**，例如時間戳 `0.4.2-202609230551` | 版本會成為 Docker tag，`+` 不合法（陷阱 b）；Supervisor 只在新版本比已安裝的**大**時才提供更新，commit hash 不會遞增 |
| `slug:` | **不動** | Supervisor 會自己加上 `local_` 前綴，變成 `local_odoo18ce`，不會和商店安裝的實例衝突 |
| `name:`、`panel_title:` | 可選：`name:` 改成例如 `Woow Odoo 18 (local f441477)`，`panel_title:` 改成例如 `Odoo local` | `name:` 決定 add-on 清單中的名稱，側邊欄顯示的是 `panel_title:`；兩者都改，兩個實例才分得出來，commit hash 也記在這裡 |

## 4. 指令

以下在主機的 shell 執行。`ha` 指令在任何 SSH add-on 裡都有；`docker` 指令（陷阱 a、d 與還原）
需要 Advanced SSH & Web Terminal add-on 並關閉 protection mode，或主機的 console。
`ha addons` 與 `ha apps` 是同一組指令。

**第一次安裝：**

```bash
ha store reload
ha addons install local_odoo18ce   # 觸發本地建置，見第 6 節的耗時
```

**開始前先改埠。** 本地實例的預設埠和 Released 實例一樣是 8069/8072；Released
實例還在跑時直接 start 會撞埠（見陷阱 c），所以先用陷阱 c 的 API 呼叫把埠改掉，
再：

```bash
ha addons start local_odoo18ce
```

**之後要換成 branch 的新 commit：**

1. 用第 2 節的方式覆蓋 `/addons/<dir>` 的內容；
2. 重新做第 3 節的修改，`version:` 換一個**更大的**後綴（新的時間戳），Supervisor
   才會看到有可更新的版本；
3. 執行：

```bash
ha store reload
ha addons update local_odoo18ce    # CLI 會逾時，見陷阱 d
```

4. 更新後**重新設一次埠**（陷阱 c），再 `ha addons start local_odoo18ce`。

## 5. 四個陷阱

### (a) 留著 `image:`：靜默地驗錯對象

- **症狀：** 沒有任何錯誤。安裝或更新會「成功」，但 Supervisor pull 的是 Release
  的預建映像，不是你的 branch。你驗到的是 Release 的東西。
- **處置：** 在本地副本移除 `image:`（第 3 節）。建置期間應該看得到 builder 容器
  `app_builder_local_odoo18ce`；本地建出的映像 tag 是
  `local/<arch>-addon-<slug>:<version>`（這裡的 `<slug>` 不含 `local_`），例如
  `local/amd64-addon-odoo18ce:0.4.2-202609230551`。
  沒有 builder 容器、映像也不是 `local/` 開頭，就是 pull 了預建映像。

### (b) 版本字串含 `+`：建置失敗

- **症狀：**

  ```
  ERROR: failed to build: invalid tag "local/amd64-addon-odoo18ce:0.4.2+f441477":
    invalid reference format
  ```

- **原因：** Supervisor 以版本當 Docker tag，`+` 不是合法的 tag 字元。語意化版本的
  build metadata（`0.4.2+sha`）是最自然的寫法，但在這裡會直接失敗。
- **處置：** 用 `-`，並讓後綴遞增（第 3 節）：`0.4.2-202609230551`。

### (c) `update` 丟失自訂的埠對應

- **症狀：** 更新後 Supervisor 以 `config.yaml` 的預設埠（8069/8072）起容器，先前在
  HA 設定的對應不見了。Released 實例佔著這些埠的主機上，啟動失敗：

  ```
  Can't start app_local_odoo18ce: [500] failed to set up container networking:
    Bind for :::8069 failed: port is already allocated
  ```

- **原因：** 這是 Supervisor 的行為，我們改不了，只能每次更新後重設。
- **處置：** `ha apps options` **沒有** `--network` 旗標，CLI 做不到；走 Supervisor
  API（在 SSH add-on 的 shell 裡，`$SUPERVISOR_TOKEN` 已存在）：

  ```bash
  curl -X POST -H "Authorization: Bearer $SUPERVISOR_TOKEN" -H 'Content-Type: application/json' \
    -d '{"network":{"8069/tcp":8169,"8072/tcp":8172}}' \
    http://supervisor/addons/local_odoo18ce/options
  ```

  第一次安裝後、第一次 start 前也要做同一件事。

### (d) `ha addons update` 的 CLI 逾時，但建置沒有停

- **症狀：**

  ```
  Error: Post "http://supervisor/addons/local_odoo18ce/update":
    context deadline exceeded (Client.Timeout exceeded while awaiting headers)
  ```

- **原因：** 這是 CLI 客戶端放棄等待，**不是**建置失敗。建置在
  `app_builder_local_odoo18ce` 容器裡繼續跑。
- **處置：** 不要重跑。用 `docker logs -f app_builder_local_odoo18ce`（或
  `docker ps` 找出實際的 builder 容器名）看進度，等它結束，再用
  `ha addons info local_odoo18ce` 確認 `version` 已是新的後綴。把逾時當失敗
  而重跑，只會多浪費一次完整建置。

## 6. 預期耗時與預期警告

**耗時（量測值）：** 2026-09-23 在 `.6`（x86 / amd64）上從零建置約 **72 分鐘**。
瓶頸是 `deb.debian.org` 的頻寬（約 75 KB/s），不是 CPU。這正是
[ADR 0001](../adr/0001-distribution-follows-release-tags.md) 不再讓使用者在自己
的裝置上建置的原因；開始前請預留時間。

**預期警告：** 本地建置期間會出現 `addon_config` 的 legacy map 型別警告；它不代表
失敗，改名見 #126。`build.yaml` 已棄用的警告不會再出現：#124 之後 base image 的
pin 在 `Dockerfile` 的 `ARG BASE_IMAGE_TAG`，Supervisor 只傳 `BUILD_ARCH`。如果
你的 Supervisor 仍印出 `build.yaml` 警告，代表 `/addons/<dir>` 裡還留著舊檔，刪掉它。

## 7. 驗完之後還原

1. 停止並移除本地 add-on：

   ```bash
   ha addons stop local_odoo18ce
   ha addons uninstall local_odoo18ce
   ```

   > **注意：** uninstall 會刪除本地實例的 `/data`，包括它內建的 PostgreSQL
   > 資料庫。要留的東西先匯出。

2. 刪除來源：`rm -rf /addons/<dir>`
3. `ha store reload`，確認 `local_odoo18ce` 不再出現在清單中。
4. 可選：刪除本地映像，例如
   `docker rmi local/amd64-addon-odoo18ce:0.4.2-202609230551`（`docker images 'local/*'`
   列出全部）。
5. **確認 Released 實例未受影響：** 用 `ha addons` 找出它的 slug，
   `ha addons info <slug>` 應顯示 `state: started`，且埠對應仍是原本的
   8069/8072；從 LAN 開 `http://<host>:8069/web/login` 應正常回應。整個程序從頭到尾
   都不應動到 Released 實例。
