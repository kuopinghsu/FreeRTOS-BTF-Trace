# BTF Trace Viewer

**版本 1.4.0 — Desktop 與 Web**

![BTFViewer AI 輔助分析](../images/btfviewer-ai.png)

BTFViewer 用於分析即時作業系統（RTOS）的 context-switch trace。它可開啟 **Best Trace Format**（`.btf`）檔案，並提供以下功能：

- 在時間軸上檢視 task 活動；
- 使用游標測量時間；
- 查看排程與同步統計資料；
- 找出負載不均、延遲、阻塞及核心遷移問題；
- 使用選配的 AI Assistant 檢視量測結果。

![BTFViewer](../images/btfviewer.png)

[開啟線上示範](https://apps.kuoping.com/btf_viewer.html?demo)

## 功能

- **時間軸檢視：** 依 task 或 CPU 核心顯示活動，並支援水平及垂直版面。
- **瀏覽與測量：** 縮放、平移、搜尋、放置游標，以及新增書籤或註解。
- **統計與分析結果：** 查看使用率、延遲、核心遷移、mutex、semaphore、queue 及排程資料。
- **多 trace 工作階段：** 以分頁開啟多份 trace 並比較結果。
- **AI 輔助調查：** 請 AI Assistant 說明量測結果，並指出相關佐證資料。
- **匯出：** 儲存 PNG 或 SVG 圖片、CSV 或 HTML 報告、Perfetto trace，以及選取的 BTF 時間範圍。
- **Desktop CLI：** 透過指令稿或持續整合（CI）系統產生報告與圖片。
- **導覽示範：** 播放 8 核心操作導覽，提供英文或繁體中文語音。

## 文件

| 文件 | 用途 |
|---|---|
| `README.md` | 安裝 BTFViewer 並了解主要功能 |
| [WORKFLOWS.md](WORKFLOWS.md) | 依照步驟進行問題調查 |
| [STATISTICS.md](STATISTICS.md) | 了解統計指標的定義、公式與判讀方式 |
| [AI.md](AI.md) | 設定及使用 AI 輔助調查 |
| [demos/README.md](demos/README.md) | 建立及維護導覽示範 |

若是第一次使用 BTFViewer，請先閱讀[快速開始](#快速開始)，再依照[基本分析流程](#基本分析流程)操作。需要詳細步驟或指標定義時，再查閱其他文件。

## 快速開始

### Desktop 應用程式

系統需求：

- Python 3.8 以上版本，建議使用 Python 3.9 以上版本。
- PySide6 6.4 以上版本。以下指令會一併安裝此套件與其他相依套件。

```bash
cd BTFViewer
pip install -r requirements.txt
python builds/btf_viewer.py trace.btf
```

請將 `trace.btf` 換成實際的 trace 檔案路徑。若未指定檔案，BTFViewer 會還原上一次的工作階段。也可以透過 **File → Open**、**File → Open Recent** 或拖放方式開啟檔案。

### Web 應用程式

使用現代瀏覽器開啟單一 HTML 檔案：

```bash
open BTFViewer/builds/btf_viewer.html
```

也可以直接按兩下該檔案，或使用[線上示範](https://apps.kuoping.com/btf_viewer.html)。一般情況下不需要架設本機伺服器。

若要重新建置 Web 應用程式：

```bash
cd BTFViewer
make web
```

### 支援的檔案格式

| 格式 | 說明 |
|---|---|
| `.btf` | Best Trace Format |
| `.btf.gz`、`.gz` | Gzip 壓縮的 trace |
| `.btf.bz2`、`.bz2` | Bzip2 壓縮的 trace |
| `.btf.zip`、`.zip` | 含有一份或多份 BTF trace 的壓縮檔；每份 trace 會在個別分頁中開啟 |
| `.xml` | Web 應用程式使用的示範指令稿 |
| `.xtf` | 包含指令稿、trace 及選用語音的可攜式示範套件 |

`tracedata/` 內提供範例 trace，包括 `example-2cores.btf.gz`。

## 導覽示範

`demo_8cores` 套件使用 8 核心 trace 與語音說明，示範主要分析流程。初次使用時，建議先執行此示範，熟悉介面及分析順序後，再開啟應用程式的 trace。

### 執行示範

Desktop：

```bash
cd BTFViewer
make demo
make demo DEMO_LANG=zh-tw
```

也可以直接開啟以下任一套件：

```bash
python builds/btf_viewer.py demos/demo_8cores/demo_8cores.xml
python builds/btf_viewer.py builds/demo_8cores.xtf
```

Web：

- 選取工具列上的 **Demo**，載入內建導覽。
- 將 `demo_8cores.xtf` 開啟或拖放至 viewer。
- 開啟示範 XML 檔案，並在系統要求時選取其套件資料夾。

預設語音為英文。可從示範列的 **Voice** 選單選取其他語言。按 **Space** 可暫停或繼續；在 2.5 秒內按兩次 **Esc** 可停止示範。

### 建置可攜式示範套件

```bash
make demo-pack
make demo-pack DEMO_LANGS=en,zh-tw
make demo-pack DEMO_LANGS=all
python3 scripts/demo_pack.py demos/demo_8cores --list-voices
```

產生的 `builds/demo_8cores.xtf` 包含指令稿、trace 及選取的語音檔，可在 Desktop 或 Web 應用程式中開啟。

Web 的 **Record** 功能使用瀏覽器畫面擷取。若要錄下語音，請選取目前的分頁，並啟用分頁音訊。

套件結構、語音產生、錄影、XML 動作及示範 API 的詳細說明，請參閱 [demos/README.md](demos/README.md)。

## Viewer 操作

Desktop 與 Web 應用程式採用相同的主要操作流程。平台差異會在相關段落中說明。

### 主要控制項目

| 控制項目 | 用途 |
|---|---|
| **Open** | 開啟 BTF trace 或示範套件 |
| **Task / Core** | 每個 task 顯示一列，或依 CPU 核心分組顯示活動 |
| **Horizontal / Vertical** | 切換時間軸方向 |
| **Zoom in / Zoom out / 1:1 / Fit** | 調整可見的時間範圍 |
| **Load** | 顯示或隱藏 CPU 負載圖 |
| **Heatmap** | 檢視 task 遷移及核心移動情形 |
| **Analysis** | 開啟目前範圍內自動產生的分析結果 |
| **Compare** | 比較兩份以上已開啟的 trace |
| **Find** | 搜尋 task、事件、核心遷移、時間區段或同步物件 |
| **Settings** | 設定顯示方式、版面、游標及 AI 選項 |

Web 工具列另外提供 **Demo**、**Record** 及 **About**。視窗較窄時，部分控制項目會移至 **More**。

### Task View 與 Core View

| 檢視模式 | 用途 |
|---|---|
| **Task View** | 追蹤各 task 在所有核心上的執行情形 |
| **Core View** | 查看各核心執行的 task；核心可以展開或收合 |

Task View 適合檢查 task 的執行及核心遷移情形。Core View 適合檢查使用率、閒置時間及負載分配。

### 縮放、標籤與醒目顯示

- 使用滑鼠滾輪平移。按住 **Ctrl** 再捲動可縮放。
- 按住 **Shift** 再捲動可切換平移軸向。
- 在 macOS 上可使用觸控板的雙指開合手勢縮放。
- 在時間軸上按住滑鼠中鍵拖曳，可放大選取的時間範圍。
- 選取 **Fit** 或按 `Ctrl+0` 可顯示完整 trace。**Range** / `Ctrl+R` 會縮放至 C1–Cn；若已放置這些游標，示範指令 `<fit_view/>` 會使用 Range。
- 選取 **1:1** 可回到設定的縮放密度。
- 點選 task 標籤或圖例項目，可持續醒目顯示該 task。
- 將游標停在時間軸區段上，可查看持續時間、所在核心及鄰近活動。

### CPU 負載

選取 **Load**，在時間軸下方顯示使用率圖。拖曳分隔線可調整圖表大小。

鎖定目前醒目顯示的 task 後，Task View 會顯示該 task 在各核心上的使用率。可利用此畫面確認工作是否依預期分配，或是否過度頻繁地在核心之間移動。

### 游標與時間範圍

游標可標記時間點及定義量測範圍。BTFViewer 預設支援四個游標；可在 **Settings** 中調整數量上限。

| 操作 | 方法 |
|---|---|
| 放置游標 | 點選時間軸，或按 `C` 將游標放在目前畫面中央 |
| 移動游標 | 拖曳游標線 |
| 移除游標 | 點選游標線附近，或使用快顯功能表 |
| 清除所有游標 | 按 `Shift+C`，或按住 Shift 再按滑鼠右鍵 |
| 對齊事件邊界 | 按住 Shift 再點選 |

請在需要檢查的區段前後至少放置兩個游標。Statistics 便可將計算範圍限制在第一個與最後一個游標之間。**Zoom to cursor range**（`Ctrl+R`）只顯示此區段；**Save selection as BTF** 則可將該區段匯出為較小的 trace。

### 書籤、註解與搜尋

| 工具 | 用途 |
|---|---|
| **Bookmark** | 在指定時間點加入名稱 |
| **Annotation** | 在指定時間點加入註解 |
| **Find** | 尋找 task、核心遷移、STI 事件、時間區段、生命週期事件及同步物件 |

按 `Ctrl+F` 開啟 Find。按 `F3` 與 `Shift+F3` 可在搜尋結果之間移動。在時間軸上按滑鼠右鍵，可新增或編輯游標與標記。

### 多份 trace

每份 trace 會在個別分頁中開啟，並保留各自的縮放比例、游標、標記及篩選條件。

- `Ctrl+Tab`：下一個分頁
- `Ctrl+Shift+Tab`：上一個分頁
- `Ctrl+W`：關閉目前分頁

Desktop 會從原始路徑還原檔案。Web 最多可從瀏覽器儲存空間還原八份已封裝的 trace。無痕瀏覽、儲存空間限制或清除網站資料，都可能使還原功能無法使用。

## 基本分析流程

第一次檢查時，請依照以下順序操作：

1. 開啟 trace，並選取 **Fit** 查看完整時間範圍。
2. 選取 **Load**，確認所有核心是否分擔合理的工作量。
3. 開啟 **Analysis**，先查看嚴重程度最高的分析結果。
4. 開啟分析結果所列的 Statistics 項目。
5. 選取偏高數值或離群值，跳至時間軸上的對應事件。
6. 在問題區段前後放置游標，並將 Statistics 限制在該範圍內。
7. 檢查 task、核心、搶占、阻塞、同步或核心遷移的詳細資料。
8. 必要時，請 AI Assistant 說明或驗證量測證據。

請從量測證據開始，不要先假設原因。確認時間軸與 Statistics 中的行為後，再下結論。詳細流程請參閱 [WORKFLOWS.md](WORKFLOWS.md)。

## Analysis 與 Statistics

BTFViewer 的所有結果都由已記錄的 BTF 事件計算而來。它不會檢查原始碼或 ELF 檔案、不會模擬 RTOS 排程器，也不會估算 trace 中沒有記錄的資料。

### 選擇第一個檢查項目

| 現象 | 先檢查 | 接著檢查 |
|---|---|---|
| 問題不明 | **Analysis Findings** | 分析結果所列的 Statistics 項目 |
| Tick jitter 或 tickless 行為 | **Trace Health (TICK)** | 執行時間離群值 |
| SMP 負載不均 | **Core Utilisation** | 同時運作的核心數，再檢查核心遷移 |
| 排程器成本過高 | **Kernel Switch Overhead** | 核心時間分布 |
| Task 執行緩慢 | **Execution Time** | 搶占及 mutex 活動 |
| 等待時間過長 | **Blocking Time** | Mutex 擁有者及搶占活動 |
| Ready-to-run 延遲 | **Dispatch Latency** | 阻塞及搶占 |
| 優先權反轉 | **Priority Inheritance** | Mutex 配對及阻塞 |
| 頻繁在核心間移動 | **Core Migrations** | 負載平衡、核心遷移熱圖及 mutex bounce |
| Lock 或 queue 問題 | **Mutex / Semaphore / Queue** | 阻塞及核心遷移 |
| 比較修改前後結果 | **Trace Compare** | 兩份 trace 中相符的時間範圍 |

統計指標的詳細定義與公式請參閱 [STATISTICS.md](STATISTICS.md)。

### Analysis Findings

選取 **Analysis**，查看目前 trace 或游標範圍內的可能問題。分析結果可能包括負載不均、執行時間熱點、阻塞、優先權反轉、頻繁的核心遷移、未達 deadline、tick 健康狀態問題，以及同步物件在核心間移動等情形。

每項結果都包含嚴重程度、相關的 Statistics 項目，以及可取得時的時間範圍。選取結果後，可開啟統計證據、放置游標、在時間軸上顯示其範圍、啟動 AI 輔助調查，或將結果儲存為文字。

對於可量測使用率的多核心 trace，核心平衡分析會顯示 **Load Balance Score** 與相關分布數值。分數越高，表示工作分配越平均。判斷分配方式是否適合目前工作負載前，仍應檢查時間軸及核心遷移資料。

### Max、p95 與 p99 的判讀方式

- **Max** 是量測到的最大值，用於尋找觀察期間內最差的事件。
- **p95** 表示 95% 的樣本不超過此數值。它能反映正常運作中較慢的一段，同時避免結果被單一罕見事件主導。
- **p99** 表示 99% 的樣本不超過此數值。它可找出平均值可能掩蓋、但仍會重複發生的嚴重延遲。

p95 很重要，因為只看平均值無法完整判斷即時效能。即使平均值良好，仍可能反覆出現緩慢事件。請一起比較 p95、p99 與 Max，以區分常見的尾端延遲和較少發生的極端值。

### 核心遷移檢查

判讀核心遷移次數前，請先檢查負載平衡。SMP 排程器可能會將 task 移至閒置核心以分配工作，因此出現一定程度的核心遷移是正常現象。

確認負載平衡後，再檢查 task 是否過度頻繁地在核心間移動。頻繁的核心遷移可能增加 L1 快取未命中（cache miss）。在 Xtensa 處理器上，核心遷移也可能降低 lazy context switching 的效益：task 移至另一個核心時，可能必須儲存 coprocessor registers，因而增加 context-switch overhead。

請一併檢查 Task View、各核心負載、**Core Migrations** 及核心遷移熱圖。若偏高的核心遷移次數同時伴隨快取行為變差、context-switch overhead 增加、延遲升高或負載分配不穩，才具有較明確的分析意義。

### Trace Compare

開啟至少兩份 trace，再選取 **Compare**。比較內容包括使用率、核心遷移、執行、阻塞、回應時間、同步活動及未達 deadline。比較前，可使用各 trace 自己的游標範圍限制資料。

兩份 trace 應採用相同的工作負載與量測期間。只有測試條件相當時，差異才具有分析意義。

## AI Assistant

選配的 AI Assistant 可說明 BTFViewer 量測出的 Analysis Findings 與 Statistics。它不能取代時間軸驗證，也不會產生 trace 中缺少的量測資料。

建議操作方式：

1. 選取一項分析結果，或使用游標定義時間範圍。
2. 請 AI Assistant 調查或說明該項結果。
3. 查看 AI 引用的 Statistics 與時間軸證據。
4. 使用 **Verify with AI** 檢查提出的原因是否成立。
5. 若建議修改系統，請擷取新的 trace 並比較結果。

可用的 context level 包括 **Compact**、**Balanced** 及 **Full evidence**。Compact 使用較少 token，預設值為 Balanced。可在 **Settings → AI** 中設定模型、endpoint、驗證方式、context、隱私選項及回覆語言。

匯入 `examples/ai/presets.json`，可取得 Ollama、OpenAI、Gemini、DeepSeek 及 Grok 的範例設定。使用本機 Ollama 不需要 API key。雲端服務可能會將 trace 證據傳送給外部服務供應商；處理敏感 trace 時，請視需要啟用匿名化及敏感資料選項。

設定、隱私、模型選項、工具、疑難排解、CLI 測試及評估方式的詳細說明，請參閱 [AI.md](AI.md)。

## 匯出

| 輸出格式 | Desktop | Web |
|---|---|---|
| 含註記的 PNG | Snapshot editor | Snapshot editor |
| 目前畫面圖片 | 複製到剪貼簿 | 複製到剪貼簿 |
| SVG | **Save SVG** | **Save SVG** |
| Perfetto JSON | **Export Perfetto** | **Perfetto** |
| 選取的 BTF 範圍 | **Save selection as BTF** | 下載選取範圍 |
| Statistics 報告 | CSV 或 HTML | CSV 或 HTML |
| Trace 比較結果 | CSV 或 HTML | CSV 或 HTML |

## Desktop 命令列

Desktop CLI 與圖形介面使用相同的分析引擎。在沒有顯示器的環境中執行時，請設定 `QT_QPA_PLATFORM=offscreen`。

| 指令 | 用途 |
|---|---|
| `info` | 顯示 trace 摘要 |
| `report` | 產生 Statistics 報告 |
| `compare` | 比較兩份 trace |
| `analyze` | 在 CI 中以 baseline 檢查 trace |
| `ai-test` | 執行 AI 證據與驗證測試 |
| `migrations` | 將核心遷移表匯出為 CSV |
| `snapshot` | 儲存時間軸、核心遷移或指標圖片 |
| `perfetto` | 匯出 Chrome Trace JSON |
| `slice` | 將選取的時間範圍儲存為較小的 BTF 檔案 |

```bash
python builds/btf_viewer.py info trace.btf
python builds/btf_viewer.py report trace.btf -o report.html --format html
python builds/btf_viewer.py compare before.btf after.btf -o diff.html
python builds/btf_viewer.py analyze candidate.btf --baseline baseline.btf --fail-on-regression
python builds/btf_viewer.py snapshot trace.btf -o view.png --view timeline
python builds/btf_viewer.py perfetto trace.btf -o trace.json
python builds/btf_viewer.py slice trace.btf -o window.btf --lo 100000 --hi 500000
```

執行 `python builds/btf_viewer.py <command> -h` 可查看所有選項。

## 設定

從工具列開啟 **Settings**，或按 `Ctrl+,`。

| 區域 | 選項 |
|---|---|
| **Appearance** | 佈景主題、字型及色盲友善色盤 |
| **Display** | 面板、時間軸疊加資訊、CPU budget 及 task deadline |
| **Layout** | 標籤寬度、列高、縮放密度、游標數量上限、時間精度及圖表大小 |
| **AI** | 啟用狀態、context level、隱私、服務供應商、模型、驗證方式及回覆語言 |

Desktop 將設定儲存在 viewer 旁的 `btf_viewer.rc`。Web 則儲存在瀏覽器的 `localStorage`。變更會立即預覽；選取 **OK** 儲存，或選取 **Cancel** 還原先前的設定值。

## 鍵盤與滑鼠操作

### 常用快速鍵

| 按鍵 | 動作 |
|---|---|
| `Ctrl+O` | 開啟檔案 |
| `Ctrl+W` | 關閉目前分頁 |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | 切換分頁 |
| `Ctrl++` / `Ctrl+-` | 放大或縮小 |
| `Ctrl+0` / `F` | 顯示完整 trace |
| `Ctrl+R` | 縮放至游標範圍 |
| `Ctrl+F` / `F3` / `Shift+F3` | 搜尋、下一個結果或上一個結果 |
| `Ctrl+G` | 跳至指定時間點 |
| `Ctrl+K` | 開啟 command palette |
| `C` / `Shift+C` | 放置游標或清除所有游標 |
| `Ctrl+B` | 新增書籤 |
| `A` | 新增註解 |
| `Ctrl+S` | 開啟 Snapshot editor |
| `Ctrl+Shift+S` | 儲存 SVG |
| `Ctrl+Shift+E` | 匯出 Perfetto JSON |
| `?` | 顯示 Web 快速鍵 |

### 滑鼠操作

| 操作 | 結果 |
|---|---|
| 滑鼠滾輪 | 平移 |
| Ctrl+滾輪 | 縮放 |
| 在背景按住滑鼠左鍵拖曳 | 平移 |
| 按住滑鼠中鍵拖曳 | 縮放至選取範圍 |
| 按住 Ctrl 並以滑鼠左鍵拖曳 | 測量兩點之間的時間 |
| 點選時間軸 | 放置游標 |
| 拖曳游標或標記 | 移動游標或標記 |
| 按滑鼠右鍵 | 開啟快顯功能表 |

## 建置與測試

一般使用者不需要執行本節中的操作。

| 工作 | 指令 |
|---|---|
| 建置 Desktop 與 Web | `make -C BTFViewer` |
| 建置 Desktop 套件 | `make -C BTFViewer bundle` |
| 建置 Web 應用程式 | `make -C BTFViewer web` |
| 執行導覽示範 | `make -C BTFViewer demo` |
| 執行 Desktop 測試 | `make -C BTFViewer test` |
| 執行 Web 測試 | `make -C BTFViewer test-web` |
| 執行所有測試 | `make -C BTFViewer test-all` |
| 建置 PDF 文件 | `make -C BTFViewer doc` |
| 從原始碼執行 | 在 `BTFViewer/` 中執行 `python -m btf_viewer_pkg trace.btf` |

Desktop 原始碼位於 `btf_viewer_pkg/`，Web 原始碼位於 `web/`。修改原始碼時，請一併提交 `builds/` 下重新產生的檔案。共用解析器與 Statistics 結果會使用 `tests/fixtures/` 下的測試資料進行檢查。

BTF 欄位定義請參閱上層目錄中的 `TRACE_FORMAT.md`。

## 貢獻者

感謝所有為本專案提供貢獻的人員。

| 貢獻者 | 貢獻內容 |
|---|---|
| [DiogoRoseira](https://github.com/DiogoRoseira) | CPU Load Graph 與指標分布圖 |
