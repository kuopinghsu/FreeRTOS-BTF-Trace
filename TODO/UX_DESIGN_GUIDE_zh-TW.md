
# BTFViewer UX 設計指南

## 1. 目的

本指南定義 BTFViewer 的 UX 方向、互動模型、資訊架構與設計規則。

BTFViewer 已具備相當完整的工程分析環境，包括：

- Task/Core 互動式 Timeline；
- Zoom、Pan、Fit 與 Cursor Range 導覽；
- 多 Cursor；
- Statistics 與 Analysis Findings；
- Bookmark 與 Annotation；
- Find；
- Legend 與 Filter；
- Migration / Core Affinity 分析；
- Trace Compare；
- Report 與 Snapshot；
- AI 輔助調查與驗證。

因此，目前 UX 的主要問題**不是缺少功能**。

真正的挑戰是：如何把這些能力組織成一套清楚、連續、以 Evidence 為核心的調查流程。

---

# 2. 產品 UX 模型

BTFViewer 應讓使用者感受到這是一套完整、連續的 Trace 分析環境：

```text
觀察 SEE
 ↓
初步判讀 TRIAGE
 ↓
縮小範圍 SCOPE
 ↓
深入調查 INVESTIGATE
 ↓
找出證據 EVIDENCE
 ↓
驗證 VERIFY
 ↓
比較 COMPARE
 ↓
做出判斷 DECIDE
````

換成工程師實際會問的問題：

```text
發生了什麼？
      ↓
哪裡看起來有問題？
      ↓
問題發生在哪個範圍？
      ↓
什麼行為可能解釋它？
      ↓
支持這個判斷的 Trace Evidence 在哪裡？
      ↓
這些 Evidence 是否真的支持結論？
      ↓
修改後有改善嗎？
      ↓
下一步應該接受、退回，還是繼續調查？
```

整個產品都應以這條流程來組織。

UI 不應像一堆彼此獨立的工具。

Statistics、Migration、AI、Find 與 Trace Compare 應讓使用者感受到它們是同一套 Investigation Workflow 的不同部分。

---

# 3. UX 核心設計原則

## 3.1 Timeline 是 Evidence Layer

Timeline 應持續作為 BTFViewer 最主要的事實依據。

Statistics、Find、Migration View、Trace Compare 與 AI 可以協助發現或解釋問題，但只要實務上可行，都應能把使用者帶回具體的 Trace Evidence。

Evidence 可以是：

* Timestamp；
* Task Segment；
* Core；
* Task/Core Pair；
* Migration；
* Preemption；
* Mutex / Blocking Event；
* Cursor Range；
* Statistics 中具有代表性的 p95、p99、Max、WCET Event。

如果某個功能可以產生分析結論，卻沒有實際可行的方式回到 Evidence，從 UX 角度來看就是尚未完整。

---

## 3.2 Scope、Filter、Selection 與 Highlight 是不同概念

這四個概念必須明確區分，不能混用。

### Scope

Scope 回答：

> 現在分析的是哪一段時間？

例如：

```text
Scope: Full Trace
```

```text
Scope: C1–C2 · 282 µs
```

Scope 主要描述的是**時間範圍**。

---

### Filter

Filter 回答：

> 在目前 Scope 內，哪些資料會被納入分析？

例如：

```text
Task: Worker[3] ×
```

```text
Core: Core_2 ×
```

```text
Migration: Core_2 → Core_5 ×
```

Filter 會改變分析輸入。

---

### Selection

Selection 回答：

> 目前選取哪一個物件進行檢視或操作？

Selection 不應自動等同於 Filter。

---

### Highlight

Highlight 回答：

> 哪個物件應該在視覺上被強調？

Highlight 不應偷偷改變分析輸入。

例如：

```text
Highlight: Worker[3]
```

不能自動變成：

```text
Filter: Worker[3]
```

除非使用者明確要求 Filter。

---

## 3.3 重要的 Investigation State 必須可見

任何會影響解讀結果的狀態，都不應只存在內部。

使用者應隨時能知道：

* Active Trace；
* Current Scope；
* Active Filters；
* 目前 Selection；
* 目前 Highlight；
* Task/Core View Mode；
* Trace Compare 中的 Baseline / Candidate。

對工程分析工具來說，Hidden State 是非常高風險的 UX 問題。

---

## 3.4 漸進式揭露

BTFViewer 是工程工具。

高資訊密度是合理的，但複雜度應逐步揭露。

新使用者應依序經歷：

1. Open and Orient
2. 找出可疑行為
3. 縮小 Scope
4. 調查一個假設
5. 找到支持這個假設的 Evidence
6. 驗證解讀是否合理
7. 比較修改後的 Trace
8. 做出判斷

不要要求使用者先理解所有 Table、Migration Metric、Cursor 操作或 AI 模式，才有辦法開始分析。

---

## 3.5 保留 Investigation Context

在以下區域之間切換：

* Statistics
* Marks
* Find
* Legend
* Migration View
* AI
* Trace Compare

不應意外清除或改變：

* Zoom
* Timeline Position
* Cursors
* Active Trace
* Scope
* Relevant Filters
* Bookmark / Annotation
* Statistics Scroll Position
* AI Conversation

只有當使用者明確執行 Navigation Action 時，Context 才應改變。

---

## 3.6 同一概念使用同一套名稱

以下區域應使用一致的 Canonical Terms：

* Toolbar
* Menu
* Statistics
* Analysis Findings
* Migration View
* Trace Compare
* AI
* Report
* CLI
* Documentation

| 概念               | 建議名稱        |
| ---------------- | ----------- |
| 整份資料             | Full Trace  |
| Cursor 定義的時間區間   | C1–Cn       |
| 目前分析的時間範圍        | Scope       |
| Scope 內被納入分析的資料  | Filter      |
| 目前檢視中的物件         | Selection   |
| 純視覺強調            | Highlight   |
| 顯示完整 Timeline    | Fit Trace   |
| 顯示 Cursor Range  | Fit Cursors |
| 比較基準 Trace       | Baseline    |
| 新版本 Trace        | Candidate   |
| 比較後變差            | Regressed   |
| 比較後改善            | Improved    |
| 支持分析結論的 Trace 位置 | Evidence    |

Desktop UI、AI、Report 與 Documentation 之間不應出現術語漂移。

---

# 4. 主要資訊架構

保留中央 Timeline + 右側 Analysis Panel 的架構。

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Menu                                                                 │
├──────────────────────────────────────────────────────────────────────┤
│ Primary Toolbar                                                      │
├──────────────────────────────────────────┬───────────────────────────┤
│ Trace Tabs                               │ Analysis Tabs             │
│                                          │ Statistics                │
│                                          │ Marks                     │
│                 Timeline                 │ Find                      │
│                                          │ Legend                    │
│                                          │ AI                        │
├──────────────────────────────────────────┴───────────────────────────┤
│ Investigation Context / Scope / Filters / Cursors / Zoom / Status    │
└──────────────────────────────────────────────────────────────────────┘
```

Trace Tabs 回答：

> 我現在分析哪一份資料？

Analysis Tabs 回答：

> 我要用什麼方式分析這份資料？

這兩者概念不同，視覺上應維持清楚區分。

---

# 5. Timeline 應維持主體地位

Timeline 應維持主要視覺區域。

一般桌面配置建議：

```text
Timeline        68–75%
Analysis Panel  25–32%
```

Analysis Panel 應：

* 可調整寬度；
* 記住合理的使用者設定寬度；
* 有可用的最小寬度；
* 優先使用垂直捲動；
* 避免一般內容需要水平捲動；
* 不要過度壓縮 Timeline Label。

不要用縮小字體來解決窄視窗問題。

---

# 6. Persistent Investigation Context

加入一條精簡、持續顯示的 Context Bar。

例如：

```text
Scope: C1–C2 · 282 µs    Task: Worker[3] ×    Core: All    Zoom: 25%
```

Full Trace：

```text
Scope: Full Trace         Filters: None         Zoom: Fit
```

Context Bar 應回答：

> 我現在到底在看什麼、分析什麼？

當以下狀態改變時應立即更新：

* Scope
* Cursors
* Filters
* View Mode
* Zoom

Context Bar 不應塞入低價值資訊。

只顯示會影響解讀或 Navigation 的狀態。

---

# 7. Visible Filter State

任何會改變分析內容的 Filter，都必須有可見表示。

例如：

```text
Task: Worker[3] ×
```

多個 Filter：

```text
Task: Worker[3] ×    Migration: Core_2 → Core_5 ×
```

規則：

* 所有 Active Filter 都可見；
* `×` 可清除單一 Filter；
* 提供 `Clear All`；
* 在相關 Analysis Tabs 間切換時保留 Filter；
* Statistics 應指出目前是否為 Filtered；
* AI 應指出目前套用了哪些 Filters；
* Report / Export 應包含重要 Filter Metadata。

不要偷偷把 Selection 或 Highlight 轉成 Filter。

---

# 8. Task/Core View 與 Selection Model

Task 與 Core 是互斥的 Timeline View Mode。

應使用 Segmented Control：

```text
┌────────┬────────┐
│  Task  │  Core  │
└────────┴────────┘
```

目前模式必須一眼可辨識。

切換 Task/Core View Mode 時，一般情況應保留：

* Timeline Position
* Zoom
* Cursors
* Scope

Selection 行為應在以下區域保持一致：

* Timeline
* Statistics
* Legend
* Migration View
* AI

始終區分：

```text
View Mode
Selection
Highlight
Filter
```

---

# 9. Cursor Model

Cursor 應視為共用的 Measurement 與 Scope 機制。

例如：

```text
C1 1.205 ms    C2 1.487 ms    Δ 282 µs
```

多個 Cursor：

```text
C1 1.205 ms   C2 1.320 ms   C3 1.487 ms   Span 282 µs
```

要求：

* 穩定的 C1–Cn 編號；
* 精確 Timestamp；
* 清楚的 Marker；
* 容易刪除；
* 清楚顯示 Range Duration；
* 明確的 Cursor Limit 行為；
* 避免 Cursor Label 互相重疊而無法閱讀。

同一套 Cursor Model 應用於：

* Measurement
* Fit Cursors
* Statistics Scope
* AI Region Analysis
* Trace Compare Range
* Evidence Verification
* Export Metadata

不要讓不同功能各自發展獨立的 Range 概念。

---

# 10. Universal Evidence Navigation

Evidence Navigation 應成為 BTFViewer 最重要的共用互動模式之一。

適用於：

* Statistics
* Analysis Findings
* AI
* Find
* Migration Analysis
* Trace Compare

例如：

```text
Response p99    48 µs ↗
```

Hover：

```text
Jump to p99 example at 1.487 ms
```

啟動後應：

1. 將 Timeline Center 到 Evidence；
2. 必要時放置或重用 Cursor；
3. 必要時 Highlight 對應 Task/Core；
4. 保留 Analysis Panel 狀態；
5. 保留 Analysis Panel Scroll Position；
6. 不要偷偷改變 Scope；
7. 不要偷偷改變 Filters。

所有 Evidence Action 應使用一致的視覺提示。

---

# 11. Timeline Interaction

建議的 Pointer Interaction：

| 操作                 | 行為                        |
| ------------------ | ------------------------- |
| Wheel / Trackpad   | Scroll                    |
| Ctrl+Wheel / Pinch | Zoom                      |
| Drag               | Pan                       |
| 左鍵點擊               | 放置／操作 Cursor              |
| 雙擊 Segment         | Zoom / Inspect Segment    |
| 右鍵                 | Context Actions           |
| Shift              | Snap / Precision Behavior |

一致性比增加更多操作模式更重要。

重要的 Pointer Action 應盡量提供 Keyboard Alternative。

---

# 12. Timeline Hover

Hover 應只回答即時檢查問題。

建議：

```text
Worker[3]
Core_2
1.205–1.226 ms
Duration: 21 µs
```

Hover 一般只需要回答：

* 哪個 Task？
* 哪個 Core？
* 什麼時間？
* 持續多久？

不要把 Hover 做成縮小版 Statistics。

更深入資訊應放在 Analysis Panel。

---

# 13. Toolbar 設計

Toolbar 應提供高頻 Investigation Action，而不是複製完整 Menu。

建議分組：

```text
[Open]

[−] [+] [Fit Trace] [Fit Cursors] [25% ▾]

[Task | Core] [STI] [Grid]

[Find] [Migration] [AI]
```

功能群組之間使用間距或 Separator。

低頻與進階功能應放在：

* Menu
* Overflow
* Command Palette
* Settings

不要因為功能增加就持續新增 Toolbar Button。

---

# 14. Fit 與 Zoom Feedback

**Fit Trace**

顯示完整 Trace。

**Fit Cursors**

顯示最早到最晚 Cursor 之間的範圍。

兩者差異應保持明確。

建議同時顯示 Relative Zoom 與 Physical Scale：

```text
25% · 120 µs/pixel
```

對工程分析工具來說，Physical Scale 很有價值，因為使用者可以直接理解目前畫面的時間解析度。

---

# 15. Statistics 應成為 Triage 中心

Statistics 應先回答：

> 哪裡值得注意？

之後才顯示完整低階 Metric。

建議層級：

## Triage

1. Analysis Findings
2. Timeline Anomalies
3. Worst Events
4. Response Time
5. Task Health

## Timing Investigation

6. Execution Time
7. Blocking / Off-CPU
8. Dispatch Latency
9. Critical Path
10. Period / Jitter
11. Unified Jitter

## SMP / Scheduling

12. Task × Core
13. Core Utilization Over Time
14. Core Migrations
15. Core Affinity
16. Preemption Matrix
17. Priority Inheritance

## Synchronization / Detail

18. Waiter × Owner
19. Mutex Blocking
20. Mutex / Semaphore
21. Queue
22. Interval
23. Tag
24. Detailed Tables

這不是移除 Expert 功能。

而是調整預設 Investigation Order。

---

# 16. Statistics Section 設計

所有 Statistics Section 應使用一致的結構。

例如：

```text
▼ Response Time                         Warning
  Scope: C1–C2
```

Section Header 可包含：

* Title
* Severity / Status
* Scope
* Filtered State
* Collapse / Expand
* Help
* Plot
* Export
* Drag / Reorder

不要讓 Section Header 佔用過多垂直空間。

---

# 17. Statistical Distribution 呈現

建議採用：

```text
Typical → Tail → Worst
```

例如：

|   p50 |   p95 |   p99 |    Max |
| ----: | ----: | ----: | -----: |
| 21 µs | 38 µs | 48 µs | 113 µs |

視覺優先順序：

1. p50 — Typical
2. p95 / p99 — Tail
3. Max / WCET — Worst
4. CV / Outlier Metrics

如果 Tail 比 Max 更能代表問題，不要讓 Max 在每張表裡都成為最強視覺焦點。

Numeric Presentation 應在 Statistics 與 Report 中保持一致。

---

# 18. Analysis Findings 應成為 Investigation Inbox

Analysis Findings 不應只是被動文字。

建議使用可操作的 Finding Card。

例如：

```text
⚠ High — Response-time tail

Worker[3] p99 = 61 µs

Evidence
1.487 ms ↗

[Show Evidence] [Investigate] [Ask AI]
```

Migration：

```text
⚠ Medium — Migration burst

Worker[3]
17 migrations inside C1–C2

[Show Evidence] [Task × Core] [Investigate]
```

理想流程：

```text
Finding
   ↓
Evidence
   ↓
Relevant Analysis
   ↓
Timeline Verification
```

使用者不應先理解整套 Statistics Hierarchy，才有辦法開始 Investigation。

---

# 19. Migration 與 Core Affinity UX

Migration Analysis 應採 Progressive Drill-down。

```text
Migration Summary
       ↓
Task × Core
       ↓
Suspicious Task/Core
       ↓
Migration Corridor / Detail
       ↓
Timeline Evidence
```

先提供容易理解的工程指標：

* Total Migrations
* Migration Rate
* Most Migrated Task
* Most Active Core Pair
* Median Dwell
* Ping-pong / Thrash

不要要求使用者一開始就先解讀複雜 Heatmap。

---

# 20. Task × Core Heatmap

Heatmap 應回答：

> 哪些 Task 在哪些 Core 上執行？

Hover / Selection 顯示：

```text
Worker[3]
Core_2
31.7% of scoped execution
```

操作：

```text
[Highlight Task]
[Filter Timeline]
[Show Migrations]
```

這三個 Action 的語意必須清楚分開。

選取 Heatmap Cell 應該是 Investigation 的開始，不是終點。

---

# 21. Migration Corridor / Core-Pair Detail

選取 Core Pair 後應顯示可操作的詳細資訊。

例如：

```text
Core_2 → Core_5

47 migrations
Task: Worker[3]
Median dwell: …
Ping-pong: …

[Show Events]
[Filter Timeline]
[Open Statistics]
```

內容應包括：

* Direction
* Count
* Involved Tasks
* Dwell / Gap
* Ping-pong Indication
* Event / Evidence Navigation

Visualization 是 Discovery，不是 Proof。

永遠要提供回到具體 Timeline Evidence 的路徑。

---

# 22. AI 的角色

AI 應定位為：

> **Evidence Navigator + Engineering Explainer + Investigation Assistant**

不應像脫離 BTFViewer 的一般 Chatbot。

AI 應協助：

* 解釋 Findings
* 解釋 Cursor Region
* 排定 Suspicious Metric 優先順序
* 調查 Timing Tail
* 調查 Migration / Core Imbalance
* 用 Trace Evidence 驗證假設
* 比較 Traces
* 建議下一個 BTFViewer Action

---

# 23. AI Landing Page

不要從空白 Conversation 開始。

應先以 Investigation Intent 引導。

```text
Trace: candidate.btf
Scope: C1–C2 · 282 µs
Filters: Task Worker[3]

What do you want to investigate?

[Explain Findings]
[Explain Cursor Region]
[Investigate Top Issue]
[Check Migrations]
[Compare Traces]

More analyses ▾

Ask anything about this trace…
```

Template 依 Intent 分組：

## Start

* Explain Findings
* Triage Findings

## Investigate

* Investigate
* Explain Region
* Highest Latency
* WCET / Hot CPU
* Task Profile

## SMP

* Migration Thrash
* Core Balance

## Verify

* Verify Finding
* Explain Finding
* Auto Investigate

## Compare

* Compare Open Traces
* Diagnostic Report

低頻功能放在：

```text
More analyses ▾
```

---

# 24. AI Context

AI 上方應持續顯示目前 Context。

例如：

```text
Trace: candidate.btf
Scope: C1–C2 · 282 µs
Filters: Task Worker[3]
Context: Compact
```

使用者不應需要猜：

* AI 正在談哪一個 Trace？
* Scope 是 Full Trace 還是 C1–Cn？
* 是否有 Filter？
* Context 是否已經過期？

---

# 25. AI 採 Evidence-First 回覆結構

建議：

```text
Summary

Evidence

Confidence

Next check
```

例如：

```text
Summary

Worker[3] shows a long execution-time tail.

Evidence

p50     21 µs
p99     48 µs
max    113 µs

WCET at 1.487 ms ↗

Confidence

High · Directly observed

Next check

Open Response Time → Worker[3]
```

避免長篇、無結構的分析文字。

---

# 26. AI Confidence 與 Evidence Vocabulary

## Confidence

* High
* Medium
* Low

## Evidence Strength

* Directly observed
* Strong correlation
* Possible explanation
* Insufficient evidence

重要規則：

* Observation 與 Interpretation 分開；
* 不要把 Correlation 當成 Causation；
* 重要 Claim 應引用 Trace Evidence；
* AI Report 應盡量沿用同一套 Vocabulary。

---

# 27. AI Actionable Links

AI 中的 Evidence 應可直接操作。

例如：

```text
[Jump to 1.487 ms]
[Open Response Time]
[Highlight Worker[3]]
[Zoom C1–C2]
```

這些 Action 必須重用 BTFViewer 正常的：

* Scope Model
* Filter Model
* Highlight Model
* Cursor Model
* Evidence Navigation

AI 不應建立另一套獨立的 Navigation System。

---

# 28. AI Busy、Failure 與 Privacy UX

AI 執行期間：

* Timeline 保持可操作；
* 舊 Conversation 保持可閱讀；
* 支援時保留 Cancel；
* 只 Disable 衝突 Action；
* 顯示精簡 Status；
* Provider / Model 維持次要層級。

失敗時：

* 盡量保留使用者 Prompt；
* 合理時提供 Retry；
* 把 Provider / Network Error 轉成可處理的訊息；
* 不要用 Raw Exception 當主要 UI。

Privacy 應以白話說明。

Local：

```text
Local AI
Trace data stays on this computer
```

Cloud：

```text
Cloud AI
Scoped trace information may be sent to the configured provider
```

Networking 與 TLS 細節放在 Advanced Settings。

---

# 29. Trace Compare

Trace Compare 應回答：

> Candidate 相對 Baseline 是改善還是退步？

第一個畫面應以 Decision 為導向。

例如：

```text
Baseline                      Candidate
baseline.btf                  candidate.btf
Scope: Full Trace             Scope: C1–C2 · 4.8 ms

3 REGRESSIONS    5 IMPROVEMENTS    1 WARNING

Largest regression

Response p99
48 µs → 61 µs
+13 µs (+27%)

Why?
Response tail moved with mutex blocking.

[Inspect Baseline] [Inspect Candidate]
```

---

# 30. Trace Compare 排序

建議：

1. Regressions
2. Major Improvements
3. Validation Warnings
4. Lower-impact Changes
5. Unchanged Detail

使用者開 Compare 最常問的是：

> 我有沒有把東西改壞？

所以 Regression 應排最前面。

---

# 31. Delta Presentation

同時顯示 Absolute 與 Relative Delta。

建議：

```text
48 µs → 61 µs
+13 µs (+27%)
```

當 Baseline 很小時，不要只顯示 Percentage。

---

# 32. Compare 應走到 Decision

Trace Compare 不應停在 Delta Table。

應協助回答：

* 這個 Change 可接受嗎？
* 是否有重要 Regression？
* 是否需要繼續 Investigation？
* Target Metric 是否改善？
* 是否有其他 Metric 變差？

如果沒有明確 Engineering Threshold，不要自動下 Pass / Fail 結論。

---

# 33. Find

建議：

```text
Find task, annotation…

Match: Contains ▾

3 of 18 matches

[Previous] [Next]
```

使用者應隨時知道：

* 總共有多少 Match；
* 現在是第幾個；
* 如何 Previous / Next。

選取 Match 後：

* Center Timeline；
* Highlight Match；
* 除非明確要求，不改變 Scope。

長篇 Match Mode 說明應放到 Contextual Help。

---

# 34. Marks、Bookmarks 與 Annotations

三者應保持不同概念。

## Cursor

暫時性的 Measurement / Investigation Point。

## Bookmark

之後預期會再回來看的 Saved Location。

## Annotation

綁定 Trace Time 的人工註解。

建議：

```text
Bookmarks | Annotations

Range
C1–C2 · 282 µs

[Import Marks] [Export Marks]

[Import Session] [Export Session]
```

當物件類型已知時，不要全部叫做 `Marker`。

---

# 35. Legend

Interactive Legend Entry 應看起來像可以操作。

提供：

* Pointer Cursor
* Hover State
* Active State
* Concise Tooltip
* Highlight / Filter 的明確差異
* Visible Filter State
* Reset Behavior

Legend 應重用整個 Application 的 Task/Core Selection 與 Filter Model。

---

# 36. Command Palette

Command Palette 用來支援 Expert Productivity，同時避免 Toolbar 過度擁擠。

應支援：

* Keyboard Shortcut
* Useful Disabled Command
* Disabled Prerequisite
* Synonym Search
* 與 Menu 一致的 Command Name
* Keyboard-only Execution

例如：

```text
Fit Cursor Range                         Ctrl+R
```

Disabled：

```text
Compare Traces
Unavailable — open at least two traces
```

---

# 37. Settings

Settings 依使用者目的分類。

## Appearance

* Theme
* UI Font
* Timeline Font
* Colorblind-safe Palette

## Display

* Grid
* STI
* Analysis Tab Visibility
* Overlays

## Layout

* Orientation
* Row Size
* Label Dimensions
* Panel Defaults
* Cursor Limits

## AI

1. Enable AI
2. Provider / Preset
3. Model
4. Authentication / Connection
5. Response Language
6. Context Level
7. Privacy / Redaction
8. Advanced Networking / TLS

一般設定不應需要先穿越進階 Networking Option。

---

# 38. Application State UX

## Loading

顯示實際階段：

```text
Reading trace…
Parsing events…
Building Timeline…
Computing Statistics…
```

如果無法精準量測 Progress，不要顯示假的百分比。

---

## Empty

例如：

```text
Open a BTF trace to begin.
```

```text
Place two cursors to measure a range.
```

```text
Open at least two traces to compare.
```

Empty State 應說明：

* 為什麼沒有內容；
* 下一步可以做什麼。

---

## Disabled

Disabled Action 應說明 Prerequisite。

例如：

* 需要 Multi-Core；
* 需要兩個以上 Cursor；
* 需要兩份以上 Trace；
* AI 尚未設定；
* Trace 不包含對應資料。

---

## Error

Error 應說明：

1. 哪個 Operation 失敗；
2. 哪個 Trace / File 受影響；
3. 已知的話，說明原因；
4. 使用者可以怎麼處理。

例如：

```text
Could not open trace

example.btf contains an invalid timestamp near line 482.
```

Technical Detail 可以保留給 Debug，但不應作為主要訊息。

---

# 39. Typography 與 Information Density

BTFViewer 應維持工程工具的資訊密度，但不要依賴過小字體。

定義三個主要文字層級：

## Section Heading

主要 Analysis Structure。

## Body / Metric

Control、Table、Metric。

## Secondary Metadata

Scope、Unit、Hint、Confidence。

避免：

* 長期顯示 9–10 px Helper Text；
* 過大 Heading；
* 不必要的大量空白；
* 過多 Border；
* 一般畫面經常需要水平捲動；
* Button Label 被截斷。

---

# 40. Numeric Presentation

Engineering Table 應：

* 數字靠右；
* 同欄位 Unit 一致；
* 使用適當 Decimal Precision；
* Comparable Value 視覺對齊；
* 避免不必要的 Raw Timestamp；
* 統一 µs / ms / s 的轉換規則。

例如：

```text
 21.4 µs
 48.1 µs
113.0 µs
```

---

# 41. Color Roles

Data Color 與 Semantic Color 應分開。

## Data Colors

用於：

* Task Identity
* Core Identity
* Heatmap
* Data Series

## Semantic Colors

用於：

* Regression / Error
* Warning
* Improvement
* Selection / Focus

如果會造成誤解，不要把 Warning / Error Color 同時用作任意 Task Color。

---

# 42. Colorblind Safety

重要意義不能只依靠顏色。

可以組合：

* Text
* Icon
* Numeric Value
* Border
* Pattern
* Shape
* Color

檢查：

* Task/Core Difference
* Selection
* Highlight
* Severity
* Regression / Improvement
* Heatmap
* Migration View

---

# 43. Light / Dark Theme

Dark 與 Light 都必須測試：

* Timeline
* Grid
* Task/Core Colors
* Selected Segment
* Cursor
* Marks
* Statistics
* Findings
* Heatmap
* Migration View
* AI Conversation
* Trace Compare
* Tooltip
* Evidence Link
* Disabled Control

不能把其中一個 Theme 當成次要支援模式。

---

# 44. High-DPI 與 Responsive Desktop

測試：

* High-DPI Scaling
* Long Task Name
* Long Translated Label
* Narrow Analysis Panel
* Toolbar Overflow
* Statistics Card
* AI Controls
* Find Controls
* Cursor Label

定義明確的 Adaptive Behavior。

## Wide

* Full Timeline + Analysis Panel
* 適當時顯示完整 Toolbar Label

## Medium

* Analysis Panel 變窄
* Helper Text 縮短
* Toolbar Label 必要時 Compact

## Narrow

* Analysis Panel 可 Hide / Show
* Secondary Toolbar Action 進 Overflow
* 保持正常 Font Size
* Statistics 避免讓整個 Window 水平捲動

不要把縮小字體當成主要 Responsive Strategy。

---

# 45. Workspace Persistence

可記住：

* Analysis Panel Width
* Theme
* 適當 Layout Preference
* 適當 Statistics Collapse State

不要意外恢復：

* Stale Temporary Filters
* Invalid Cursor State
* 不屬於目前 Trace 的舊 Scope

明確定義：

```text
Session-persistent state
Application-persistent state
```

---

# 46. Onboarding

使用輕量 First-run Guidance。

例如：

```text
New to BTFViewer?

Start with Statistics → Analysis Findings.

[Show Me] [Dismiss]
```

要求：

* 可 Dismiss；
* 記住 Dismiss；
* 可直接 Navigate；
* 不使用 Blocking Tutorial Wizard；
* 第一次使用不要灌輸過多 Advanced Feature。

---

# 47. Contextual Help

優先使用 Contextual Help，而不是永久佔據畫面的說明文字。

長篇說明移到：

* Tooltip
* Info Button
* Help Affordance
* Documentation

只有對目前狀態解讀必要的 Prerequisite，才應持續顯示。

---

# 48. Developer UX Rules

1. Timeline 保持作為 Evidence Layer。
2. Scope 必須明確可見。
3. 明確區分 Scope、Filter、Selection、Highlight。
4. 會影響解讀的 State 不得隱藏。
5. 每個 Filter 都要有可見 State 與 Reset Path。
6. 時間相關的分析結果應在可行時回到 Evidence。
7. 除非明確 Navigation，否則保留 Timeline Position。
8. 在不同 Analysis Surface 間保留 Cursors 與相關 Context。
9. C1–Cn 用法保持一致。
10. 使用 Canonical Terminology。
11. Primary Action 保持可見。
12. Advanced Variant 放 Menu、Overflow、Command Palette 或 Settings。
13. 低頻功能不要直接增加 Toolbar Button。
14. Disabled Action 必須說明 Prerequisite。
15. Timeline Inspection 時仍需參考的資訊，避免使用阻擋式 Modal。
16. 重要 State 不要只存在 Tooltip。
17. 不要只用顏色表示狀態。
18. 重要操作維持 Keyboard Access。
19. 驗證 Narrow Panel 與 High-DPI。
20. 驗證 Light、Dark、Colorblind-safe。
21. GUI、Report、CLI、Documentation、AI 術語保持同步。
22. 比起增加孤立 Visualization，優先建立回到 Evidence 的路徑。
23. AI 應重用正常的 Scope、Filter、Highlight、Cursor、Evidence Model。
24. Compare 是 Decision 的輸入，不是最終使用者目標。

---

# 49. UX Review Checklist

每一個重要 UI 變更都應確認：

* [ ] Main Action 是否明確？
* [ ] Active Trace 是否明確？
* [ ] Current Scope 是否明確？
* [ ] Scope 與 Filter 是否語意分離？
* [ ] Active Filters 是否可見？
* [ ] Filter 是否容易清除？
* [ ] Selection 與 Highlight 是否可區分？
* [ ] Highlight 與 Filter 是否可區分？
* [ ] 是否適當保留 Timeline Context？
* [ ] Analysis Result 是否可回到 Evidence？
* [ ] Evidence Navigation 是否避免意外改變 State？
* [ ] Disabled State 是否說明原因？
* [ ] Empty State 是否有用？
* [ ] Loading State 是否容易理解？
* [ ] Error 是否可採取行動？
* [ ] Narrow Layout 是否正常？
* [ ] High-DPI 是否正常？
* [ ] Light Mode 是否正常？
* [ ] Dark Mode 是否正常？
* [ ] Colorblind-safe 是否正常？
* [ ] Keyboard Access 是否保留？
* [ ] Terminology 是否一致？
* [ ] Hidden State 是否最小化？
* [ ] 是否有回到 Timeline Evidence 的路徑？
* [ ] 下一個 Useful Action 是否明確？
* [ ] 是否符合整體 Investigation Workflow？

---

# 50. Implementation Roadmap

UX Design Guide 負責定義 Interaction Model 與 Design Rules。

實作優先順序另外維護在三份 TODO 文件中。

## Step 1 — Core Clarity and Investigation Foundation

參考：

```text
TODO-step1.md
```

重點：

* Canonical Terminology
* Investigation Context
* Filters
* Task/Core Model
* Cursors
* Triage-first Statistics
* Findings
* Find
* Marks
* Legend
* Toolbar
* 基礎 Timeline Interaction
* 基礎 Application State

---

## Step 2 — Evidence-Driven Analysis and Guided Investigation

參考：

```text
TODO-step2.md
```

重點：

* Universal Evidence Navigation
* Investigation Context Preservation
* Statistics Drill-down
* Migration Workflow
* AI Workflow
* AI Evidence / Confidence
* Trace Compare
* Compare → Decision
* Exported Context
* Expert Navigation

---

## Step 3 — Polish, Accessibility and Validation

參考：

```text
TODO-step3.md
```

重點：

* Loading / Empty / Disabled / Error Coverage
* Typography
* Numeric Presentation
* Semantic Colors
* Accessibility
* High-DPI
* Responsive Desktop
* Settings
* Workspace Persistence
* Onboarding
* Contextual Help
* Cross-surface Audit
* UX Regression Testing
* End-to-End New-user Validation

整體 Implementation Model：

```text
FOUNDATION
    ↓
EVIDENCE-DRIVEN WORKFLOW
    ↓
POLISH & VALIDATION
```

---

# 51. 最終 UX 方向

BTFViewer **不應為了變得容易使用，而降低原本的工程分析深度**。

更好的方向，是把既有深度整理成一套可看懂的 Investigation Process：

```text
Timeline
   ↓
Statistics / Findings
   ↓
Scope
   ↓
Detailed Analysis
   ↓
Timeline Evidence
   ↓
Verification / AI
   ↓
Trace Compare
   ↓
Decision
```

或從產品層級來看：

```text
SEE
 ↓
TRIAGE
 ↓
SCOPE
 ↓
INVESTIGATE
 ↓
EVIDENCE
 ↓
VERIFY
 ↓
COMPARE
 ↓
DECIDE
```

最高層 Design Rule 是：

> **BTFViewer 的每一個分析功能，都應讓目前的 Scope 清楚可見、揭露支持結果的 Evidence、保留 Investigation Context，並讓下一個有用的操作明確可見。**

這樣可以保留 BTFViewer 原本專業的 RTOS Trace Analysis 深度，同時大幅降低新使用者的學習成本與 Navigation 負擔。

```
