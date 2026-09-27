# 慢速連線上的 Deploy：可續傳地把映像放進主機
# Deploying a Release over a Slow Link with a Resumable Pull

> 對象：maintainer / 支援人員。本文件是**程序**，不是測試計劃。
>
> 用語依 `CONTEXT.md`：把 Release 裝到真機上叫 **Deploy**。本程序不改變 Deploy
> 的定義，只是在連線太慢時，先用可續傳的方式把映像放進主機的 Docker，
> 再讓 Supervisor 完成它原本的更新。
>
> 使用者看到的說明在 `odoo18ce/DOCS.md` 的 "Updates and images"。那一節
> **不會**連到本文件；本文件只給內部使用。

---

## 1. 何時用

Supervisor 的 pull **不能續傳**。連線一斷，Docker 就丟掉已下載的 layer，
重試從 0 開始。0.4.4 有一個 693 MiB 的 layer，在 160 KiB/s 的線路上需要
約 75 分鐘不中斷的連線；線路會斷的話，重試永遠不會收斂（#153）。

症狀是 Supervisor log 裡的：

```
Can't install ghcr.io/woowtech/woow-ha-odoo-amd64:<version>: [0] unexpected EOF
Could not pull image to update app 1b7b4ce7_odoo18ce: ...
```

失敗不會改變任何東西：pull 發生在停止 add-on 之前，所以 add-on 還在跑舊版本。

本程序用 `curl -C -` 從最後一個 byte 續傳，逐一驗 sha256，`docker load` 進主機，
然後才由人執行 `ha apps update`。2026-09-24 在測試機上實測可行：795,546,245
bytes 在約 40 分鐘內下載完成，中間斷線或重連約 10 次，沒有掉資料。

## 2. 前置條件

**SSH add-on。** 需要 **Advanced SSH & Web Terminal** add-on，並且**關閉
protection mode**。官方的 **Terminal & SSH** add-on 裡**沒有 `docker`**，
只能做到第 6 節的 `--dry-run`，不能載入映像。

**工具。** 腳本需要 `curl`、`jq`、`sha256sum`、`tar` 與 `docker`。
Advanced SSH & Web Terminal 都有。缺哪一個腳本會直接報出來（exit 3）。

**指令名稱。** 本文件一律用 `ha apps`；`ha addons` 是同一組指令的別名，
舊文件和舊筆記裡看到的是後者。備份指令挑 add-on 的旗標同樣改了名：
現在是 `--app`，`--addons` 還收但已標為 deprecated；舊版 CLI 只認 `--addons`。
`ha backups new --help` 會說目前這台認哪一個。

**slug。** 商店安裝的實例是 `1b7b4ce7_odoo18ce`，也是腳本的預設值。
用 `ha apps` 確認；本地建置的實例（`local_odoo18ce`）不走這條路，
它沒有預建映像，見 `docs/testing/LOCAL_BUILD_ON_HOST.md`。

## 3. 先備份

**更新成功後，Supervisor 會刪掉舊的映像。** 備份是唯一的回頭路。

```bash
ha backups new --name "before-<version>" --app 1b7b4ce7_odoo18ce
ha backups            # 確認新的備份在清單裡
```

備份是 `cold` 策略：HA 會先停掉 add-on，需要停機時間。

> 使用者如果已經因為失敗的更新做過好幾次備份，先請他們關掉 add-on 更新對話框裡的
> **backup before update**，再刪掉多餘的備份；每一次失敗的重試都留下一份完整備份。

## 4. 磁碟空間

```bash
df -h /share /mnt/data
```

準備：

| 需要 | 大約 |
|---|---|
| `/share` 下的 blob（壓縮後的 layer） | 0.4.4 為 **795 MB**；之後的 Release 看 Release notes 的 size 表 |
| `docker load` 解 tar 用的暫存（`/mnt/data/docker/tmp`） | 再一份 **795 MB**，載入後釋放 |
| Docker 解開後的映像（`/mnt/data/docker`） | 再約 **2 GB** |
| 舊映像（更新完成前不會被刪） | 再一份 |

空間不夠時下載會在中途失敗；腳本會留著工作目錄，清出空間後重跑即可續傳。

## 5. 取腳本：從 pinned Release tag，不是 `main`

依 [ADR 0001](../adr/0001-distribution-follows-release-tags.md)，真機上跑的東西
來自 Release tag。`main` 隨時會動，而這支腳本會決定往主機的 Docker 裡放什麼。

**取腳本的 tag ≠ 要裝的版本。** 這兩件事是分開的：

- **腳本**從**含有這支腳本的最新 Release tag** 取。本腳本是在 0.4.4 之後才進
  repo 的，`v0.4.4` 以前的 tag **沒有** `docs/runbooks/`，去抓會拿到 404。
  用 `git ls-remote --tags` 或 GitHub 的 tag 清單找最新的那個。
- **要裝的版本**是腳本的第二個參數（第 7 節），可以比腳本的 tag 舊。

```bash
TAG=v0.4.5        # 含有本腳本的最新 Release tag，不是要裝的版本
curl -fsSL -o /share/slow-link-pull.sh \
  "https://raw.githubusercontent.com/WOOWTECH/Woow_ha_odoo/${TAG}/docs/runbooks/slow-link-pull.sh"
chmod +x /share/slow-link-pull.sh
```

抓到 404 就是那個 tag 還沒有這支腳本，換一個更新的 tag。

**還沒有任何 tag 含有它的那段期間。** 這支腳本是文件，不帶版本號，所以它進
`main` 之後要等**下一個 Release**才會出現在某個 tag 裡（#153 的決議就是那個
Release 的 test-host Deploy 要用它）。在那之前只能從 commit 取，而且**用
commit SHA，不要用 `main`**——`main` 會動，SHA 不會：

```bash
SHA=<把 docs/runbooks/ 加進來的那個 commit>
curl -fsSL -o /share/slow-link-pull.sh \
  "https://raw.githubusercontent.com/WOOWTECH/Woow_ha_odoo/${SHA}/docs/runbooks/slow-link-pull.sh"
```

## 6. 先 dry run

`--dry-run` 只抓 manifest 和 config 並驗證，不碰 layer，也不載入。
用來確認 token、網路、slug 和版本都對：

```bash
/share/slow-link-pull.sh --dry-run
```

輸出應該是這樣（每行前面還有一個 `HH:MM:SS` 時間戳，這裡略去；版本號會不同）：

```
add-on 1b7b4ce7_odoo18ce, arch amd64
image  ghcr.io/woowtech/woow-ha-odoo-amd64:0.4.4
work   /share/slow-link-pull/1b7b4ce7_odoo18ce/0.4.4 (kept between runs so a re-run resumes)
manifest sha256:64f44e6e… (1632 bytes) ok
config sha256:d835d8b9… (9934 bytes)
  the config blob ok (9934 bytes)
dry run: the manifest and the config are verified.
dry run: 7 layers, 795536311 bytes, not downloaded.
dry run: /share/slow-link-pull/1b7b4ce7_odoo18ce/0.4.4 is kept; run again without --dry-run to finish.
```

以上是 2026-09-27 對 live ghcr 跑出來的實際輸出。

## 7. 下載並載入

```bash
/share/slow-link-pull.sh                      # 預設 slug，版本取 version_latest
/share/slow-link-pull.sh 1b7b4ce7_odoo18ce 0.4.4   # 指定 slug 與版本
```

**會跑很久。** 在慢速線路上以小時計。工作目錄在 `/share/slow-link-pull/<slug>/<version>/`，
所以 SSH 斷線不會損失進度：**重跑同一行指令就從斷掉的 byte 繼續**。
建議在 `tmux` 或 Web Terminal 裡跑。

> **一次只能跑一個。** 在 `tmux` 裡跑的話，SSH 斷線時它還活著，這時再開一個
> 只會兩個 `curl` 互相覆蓋同一個半成品。腳本自己擋掉了：第二個會以 exit 11
> 停住並印出前一個的 pid。先 `tmux attach` 看看前一個還在不在。
>
> 鎖是工作目錄下的 `.lock`，裡面記了 pid 和開機 id；重開機或程序被 kill 掉
> 之後的舊鎖會被自動判定為過期並清掉。真的卡住就手動刪：
> `rm -rf /share/slow-link-pull/<slug>/<version>/.lock`。

過程中看到這幾種行會重連再續傳，是正常的，不要中斷它：

```
  layer 4 is at 51249152/726952302 bytes and the connection went; resuming
  retrying in 5s
  the resume did not complete (HTTP 000); keeping the 51249152 bytes already here
  layer 4 got no further than 51249152/726952302 bytes (1/30)
  layer 4 starts again from zero (1/5)
  the resume was not answered with 206 (HTTP 200); starting this blob again
  layer 4 is sha256:…, expected sha256:…; deleting and downloading again
```

腳本每一次嘗試都重新取一個匿名 ghcr token，並且**永遠從
`ghcr.io/v2/.../blobs/<digest>` 重新開始**，不重用 ghcr 轉址過去的簽章 URL——
那個 URL 約 10 分鐘就過期。它只連 `ghcr.io` 和 ghcr 轉址過去的儲存主機。

## 8. 驗證結果

腳本自己有一道 gate，過不了就不會往下走：載入後的 image ID
（`docker image inspect`）必須等於 manifest 裡 config 的 digest。通過時會印：

```
gate ok: the loaded image ID is the manifest's config digest
removed /share/slow-link-pull/1b7b4ce7_odoo18ce/0.4.4
```

工作目錄**只有在 gate 通過後**才會被刪掉。映像已經在主機上而且 ID 正確時，
重跑腳本只會再確認一次並印出同一段指令，不會重抓 795 MB。

要自己再確認一次：

```bash
docker image inspect --format '{{.Id}}' ghcr.io/woowtech/woow-ha-odoo-amd64:0.4.4
docker images ghcr.io/woowtech/woow-ha-odoo-amd64
```

退出碼：

| 碼 | 意思 |
|---|---|
| 0 | 載入完成且 gate 通過（或 dry run 驗證完成） |
| 2 | 參數用錯 |
| 3 | 少了 `curl`/`jq`/`sha256sum`/`tar`/`docker`/`ha` |
| 4 | 問不到 Supervisor，或它的回答不能用（slug 打錯、image 不在 ghcr.io） |
| 5 | 取 ghcr token 失敗 |
| 6 | 抓不到 manifest，或 media type 不支援 |
| 7 | 大小或 sha256 對不上且沒有復原（同一個 blob 重抓 5 次仍不符） |
| 8 | 某個 blob 連續 30 次嘗試都沒有比之前更前面，或被迫從零重來 5 次（有前進的嘗試不算進這個額度；另有 500 次的絕對上限） |
| 9 | `docker load` 失敗 |
| 10 | gate 失敗：載入的 image ID 不是 config 的 digest |
| 11 | 同一個工作目錄已經有另一個執行中的 run |

## 9. 執行更新

腳本**不會**自己更新，它只印出指令。由人在選定的時間執行：

```bash
ha apps update 1b7b4ce7_odoo18ce
```

映像已經在本機，Supervisor 的 pull 什麼都不會下載，整個更新在數秒內完成，
log 出現 `App '1b7b4ce7_odoo18ce' successfully updated`。之後確認：

```bash
ha apps info 1b7b4ce7_odoo18ce | grep -E 'version|state'
```

再依 `docs/testing/COMMERCIAL_PREDEPLOY.md` 做該版本的檢查。

## 10. 回滾

回滾靠第 3 節的備份，但**在慢速線路上有兩步，順序不能顛倒**。

**陷阱：備份裡沒有映像。** 商店安裝的 add-on 的備份只含 `/data` 與設定；
映像不在裡面（Supervisor 只有在 add-on 不在任何商店裡時才把映像存進備份）。
還原時 Supervisor 會安裝備份裡記的那個版本，主機上沒有那個 tag 就**回去 ghcr
pull**——正是本程序要繞開的那條不能續傳的 pull。而 `ha apps update` 成功後，
舊映像已經被刪掉了。

**第 1 步：先把舊版本的映像放回主機。**

```bash
docker images ghcr.io/woowtech/woow-ha-odoo-amd64        # 舊 tag 還在嗎？
/share/slow-link-pull.sh 1b7b4ce7_odoo18ce 0.4.2         # 不在就抓回來，換成備份裡的版本
```

舊 tag 還在的話這一步可以跳過；腳本自己也會認出映像已經在，不會重抓
（見第 8 節）。

> **忽略腳本最後印出來的那一行。** 它印的是 `ha apps update <slug>`，而
> `ha apps update` 裝的是 `version_latest`，也就是你正要退掉的那一版。
> 回滾時**不要**執行它，直接走第 2 步的 `ha backups restore`。

> 預先省事的做法：更新後、確認新版本沒問題之前，**不要**跑
> `docker image prune` 之類會清掉舊 tag 的東西。Supervisor 自己刪掉的那一份
> 救不回來，但至少不要再多刪。

**第 2 步：還原備份。**

```bash
ha backups restore <backup-slug> --app 1b7b4ce7_odoo18ce
```

還原的是備份當下的 add-on 版本與它的 `/data`（PostgreSQL、filestore、密碼）。
如果新版本已經跑過而且做了資料庫 migration，還原會把資料一起退回備份的時間點；
在更新後到回滾之間輸入的資料會不見。

## 11. 驗證過的版本與已知限制

2026-09-24 在測試機上驗過：

| | |
|---|---|
| Home Assistant | HA OS，Supervisor **2026.09.2** |
| Docker | **28.3.3** |
| storage driver | **overlay2** |
| 架構 | amd64 |
| 映像 | `ghcr.io/woowtech/woow-ha-odoo-amd64:0.4.4`，7 layers 795,536,311 bytes，加上 manifest 與 config 共 795,546,245 bytes（腳本印的是 layer 的那個數字） |

**已知限制：**

- **containerd image store。** 本程序靠的是 `docker load` 會把映像放進
  Supervisor 之後 pull 時看得到的同一個 image store。HA OS 若改用
  containerd 的 image store，`docker load` 進去的東西不一定會被看到，
  這支腳本就要重寫。換 HA OS 版本後第一次用，請先在測試機上驗。
- **layer 的壓縮格式。** 映像的 layer 混用 `tar+zstd` 與 `tar+gzip`，
  兩種 `docker load` 都吃。出現其他 media type 時腳本會直接停（exit 6），
  不會猜。
- **index / manifest list。** 目前每個架構各有自己的 repo，tag 指向單一
  manifest。若哪天改成 index，腳本會依 `ha info` 的架構自己挑對應的
  manifest；挑不到就停。
