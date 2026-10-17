# MOS 65xx

以 Python 實現的 65xx 系列共十六款晶片，由 MOS 6502 到 WDC W65C816S，每次推進一個匯流排週期，並以 SingleStepTests 的逐操作碼測試套件及各製造商的數據表作為檢驗標準。

[English](README.md) &nbsp;|&nbsp; [日本語](README.ja.md) &nbsp;|&nbsp; [简体中文](README.zh-Hans.md) &nbsp;|&nbsp; 繁體中文（香港）

[![CI](https://github.com/gufranco/mos65xx-python/actions/workflows/ci.yml/badge.svg)](https://github.com/gufranco/mos65xx-python/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/gufranco/mos65xx-python)](https://github.com/gufranco/mos65xx-python/releases)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**16** 款晶片，比對了 **17,900,000** 個狀態案例及 **17,870,080** 個週期精確案例，**0** 個未獲解釋的失敗，**1,360** 個測試，**100%** 語句及分支覆蓋率，無任何依賴

```python
from mos65xx import Cpu, SparseMemory

memory = SparseMemory()
for address, value in enumerate(bytes.fromhex("18fbc230a93412")):
    memory.write8(0x8000 + address, value)
memory.write8(0xFFFC, 0x00)
memory.write8(0xFFFD, 0x80)

cpu = Cpu("65816", memory)
cpu.reset()
costs = [cpu.step() for _ in range(4)]

print(costs, hex(cpu.a), cpu.emulation, cpu.m8)
print(cpu.steps, cpu.cycles)
```

```
[2, 2, 3, 3] 0x1234 False False
4 18
```

位於 `$8000` 的程式是 `CLC`、`XCE`、`REP #$30` 及 `LDA #$1234`。`reset()` 耗用 8 個週期，並從 `$FFFC` 的向量載入程式計數器。`CLC` 及 `XCE` 離開模擬模式，`REP` 把累加器及索引暫存器擴闊為 16 位元，其後的載入指令便取用 16 位元的運算元。每次 `step()` 都會傳回該指令耗用的週期：這四條指令共 10 個，自晶片建立以來共 18 個。

## 安裝

| 需求 | 版本 |
|:--|:--|
| Python | 3.12 或更新 |
| git | 任何版本，用於複製儲存庫 |

```bash
git clone https://github.com/gufranco/mos65xx-python.git
cd mos65xx-python
python3 mos65xx/doctor.py
```

本套件只匯入標準程式庫內的模組。`pip install git+https://github.com/gufranco/mos65xx-python.git` 會安裝本套件，並附帶一個執行同一份報告的 `mos65xx-doctor` 指令。

診斷腳本會檢查機器、建立並重設每款晶片，並報告已取得哪些一致性測試套件。它以檔案形式執行，而非使用 `-m`，因此即使套件無法匯入，它仍能提交報告。它以一行輸出作結。請把完整輸出貼到任何錯誤報告中。

```
  26 checks, nothing to report
```

發佈版本遵循[語義化版本](https://semver.org/)，由 semantic-release 根據提交歷史產生。每個發佈版本都會加上標籤，並列於[發佈頁面](https://github.com/gufranco/mos65xx-python/releases)。

## 介面

`Cpu(model, memory=None, fill=None, **options)` 建立一顆晶片，已通電但未重設。`model` 為必填，省略時會引發 `UnknownModelError`，並列出所有可接受的名稱。十六個名稱及其別名見[型號](#models)。名稱中的大小寫、`-` 及 `_` 均會被忽略。`memory` 可以是任何具備 `read8(address)` 及 `write8(address, value)` 的物件。若不提供，晶片會取得一個 `SparseMemory`；若提供了 `fill`，則取得一個以 `fill` 填充的 16 MB `Memory`。

| 選項 | 晶片 | 效果 |
|:--|:--|:--|
| `seed=` | 全部 | 為通電時被打亂的暫存器設定種子。預設為 `UNSET_SEED` |
| `decimal=` | 8 位元 | 是否接有十進制加法器。由型號設定，只有 `2a03` 將其設為 false |
| `table=` | 8 位元 | 操作碼表。由型號設定 |

### 呼叫

| 呼叫 | 效果 | 傳回 |
|:--|:--|:--|
| `reset(seed=UNSET_SEED)` | 驅動 RESET：六個週期，然後用兩個週期讀取 `$FFFC` 的向量。W65C02S 分別用五個及兩個。清除 `steps`，設定中斷禁止旗標，並在 CMOS 晶片上清除十進制旗標。65816 亦會進入模擬模式，使用 8 位元暫存器，`d`、`db` 及 `pb` 均為 0 | 晶片本身 |
| `step()` | 執行一條指令，然後取樣中斷線 | 耗用的週期，包括進入中斷的週期 |
| `run_for(cycles)` | 執行完整指令，直至至少經過 `cycles` 個週期。停機的晶片每次呼叫 `held_cycle()` 耗用一個週期 | 耗用的週期，可能超過 `cycles` |
| `run_until(check, limit=None)` | 在 `check(part)` 為假時持續單步執行。執行 `limit` 條指令後引發 `RunLimit` | 晶片本身 |
| `call(address, limit=None)` | 跳至 `address` 並單步執行，直至下一條指令是對應的 `RTS`，在 65816 上則是 `RTL`。巢狀呼叫會被計算在內 | 晶片本身 |
| `held()` | 晶片是否處於卡死、停止或等待狀態 | `bool` |
| `held_cycle()` | 停機晶片的一個週期。卡死的 NMOS 晶片會讀取 `$FFFF`。其他晶片則耗用一個沒有匯流排存取的週期 | 無 |
| `irq()` | 除非中斷禁止旗標已設定，否則立即接受中斷請求 | 接受時為 `True` |
| `nmi()` | 立即接受不可遮蔽中斷 | 8 位元晶片上無，65816 上為 `True` |
| `abort()` | 僅限 65816。立即接受中止 | 接受時為 `True` |
| `status()` | 以位元組表示的狀態暫存器 | `int` |
| `set_status(byte)` | 由一個位元組設定所有旗標 | 無 |
| `set_emulation(flag)` | 僅限 65816。進入或離開模擬模式，模擬模式強制使用 8 位元暫存器及位於第一頁的堆疊 | 無 |
| `read8(address)` / `write8(address, value)` | 經由晶片位址線的一個匯流排週期，會被追蹤及計數 | 讀取的位元組，或無 |
| `power_on(seed)` | 再次打亂暫存器，與建立時相同 | 無 |

若晶片的封裝沒有引出某條線，`irq()` 及 `nmi()` 會引發 `NoSuchPin`。65816 及 65802 三條線均有引出。

### 狀態

| 屬性 | 意義 |
|:--|:--|
| `a`, `x`, `y`, `s`, `pc` | 暫存器。在 65816 上，`a`、`x`、`y` 及 `s` 為 16 位元 |
| `db`, `pb`, `d` | 僅限 65816。數據記憶庫、程式記憶庫及直接頁暫存器 |
| `n`, `v`, `z`, `c` | 在每款晶片上意義相同的旗標，各為一個 `bool` |
| `i`, `d`, `b`, `decimal` | 8 位元晶片。中斷禁止旗標、十進制旗標、break 旗標，以及是否接有十進制加法器 |
| `irq_disable`, `decimal`, `m8`, `x8`, `emulation` | 僅限 65816。中斷禁止、十進制旗標、8 位元累加器、8 位元索引暫存器、模擬模式 |
| `irq_line` | 以電平表示的請求線。它在每條指令之後取樣，因此在此之前撤回的請求不會被接受 |
| `nmi_line` | 不可遮蔽中斷線。由低變高時中斷一次，維持高電平不會再次中斷 |
| `ready_line` | 為假時，讀取會持續耗用週期直至它再次為真，因此主機要在 `on_cycle` 中清除它。CMOS 晶片及 65816 以同樣方式暫停寫入，NMOS 晶片則不會 |
| `cycles` | 自建立以來的週期數。重設會累加到其中 |
| `steps` | 自上次重設以來的指令數 |
| `stopped`, `jammed`, `waiting` | 三種停機狀態。`jammed` 僅見於 NMOS，`waiting` 見於 CMOS 晶片及 65816 |
| `trace` | 把它設為一個列表，每個匯流排週期都會以 `(address, value, kind)` 附加到列表中。在 8 位元晶片上，`kind` 為 `read` 或 `write`；在 65816 上則為八個針腳字母：數據、程式、向量讀取、寫入、模擬、`m`、`x`、記憶體鎖定。65816 的內部週期以 `None` 記錄其數值，惟模擬模式中的修改週期除外；停機週期則記錄為 `(None, None, "--------")` |
| `on_cycle` | 每個週期呼叫一次，在該週期的匯流排活動之後 |
| `model` | 標準型號名稱 |
| `package_pins` | 封裝引出的中斷線及就緒線，例如 `("irq", "nmi", "rdy")` |
| `address_mask` | 封裝引出的位址線。6507 讀取 `$F234` 時落在 `$1234` |
| `reset_cycles` | 重設耗用的週期，8 或 7 |
| `memory` | 記憶體物件 |
| `cycle_budget` | 僅限 65816。設定後，`MVN` 及 `MVP` 只會搬移該週期數內容納得下的位元組 |

```python
from mos65xx import Cpu, Memory

space = Memory(size=0x10000, fill=0xEA)
for address, value in {0xFFFC: 0x00, 0xFFFD: 0x02, 0xFFFE: 0x00, 0xFFFF: 0x30}.items():
    space.write8(address, value)
space.write8(0xFFFA, 0x00)
space.write8(0xFFFB, 0x40)
space.write8(0x0200, 0x58)

cpu = Cpu("6502", space).reset()
cpu.irq_line = True
print(cpu.step(), hex(cpu.pc))
cpu.irq_line = False
cpu.nmi_line = True
print(cpu.step(), hex(cpu.pc))
print(cpu.step(), hex(cpu.pc))
```

```
9 0x3000
9 0x4000
2 0x4001
```

位於 `$0200` 的 `CLI` 在請求線保持有效時清除中斷禁止旗標，因此同一步會經由 `$FFFE` 接受中斷：`CLI` 用 2 個週期，進入中斷用 7 個。拉高不可遮蔽中斷線會經由 `$FFFA` 中斷一次。第三步在該線仍為高電平時執行一條 `NOP`。

### 錯誤

| 錯誤 | 引發時機 |
|:--|:--|
| `UnknownModelError` | `Cpu()` 沒有取得名稱，或取得的名稱不屬於任何型號或別名 |
| `NoSuchPin` | 對封裝沒有引出該線的 8 位元晶片呼叫 `irq()` 或 `nmi()` |
| `RunLimit` | `run_until()` 或 `call()` 達到其 `limit` |
| `Stopped` | 對已執行 `STP` 或已卡死的晶片呼叫 `step()` |
| `Waiting` | 對已執行 `WAI` 的晶片呼叫 `step()`。它是 `Stopped` 的子類別。`irq()` 及 `nmi()` 會將其釋放 |
| `ClockClosed` | 對已關閉的 `Clock` 呼叫 `tick()` |
| `Truncated` | `decode()` 在指令結束前用盡位元組 |
| `UnsupportedError` | 操作碼表列出核心沒有處理程序的指令或定址模式 |

### 模組內容

| 名稱 | 內容 |
|:--|:--|
| `MODELS` | 十六個 `Model` 記錄，以標準名稱為鍵 |
| `Model` | `name`、`summary`、`address_bits`、`data_bits`、`decimal`、`pins`、`reset_cycles`、`aliases`、`narrows`、`revision`、`address_mask`，以及 `build(memory, **options)` |
| `Clock(cpu)` | 每次一個週期地執行晶片。見[逐個週期驅動](#driving-it-one-cycle-at-a-time) |
| `Memory(size=0x1000000, image=None, seed=UNSET_SEED, fill=None)` | 一個平面位元組陣列，先由 `seed` 打亂，再以 `fill` 填充，然後疊上 `image`。其位元組為 `data` |
| `SparseMemory(seed=UNSET_SEED)` | 24 位元的位址空間，只儲存已寫入的內容。已寫入的位元組為 `cells` |
| `scramble(size, seed=UNSET_SEED)` | 兩種記憶體及每款晶片起始時使用的打亂 `bytearray` |
| `UNSET_SEED` | 預設種子，`0x5A5A5A5A` |
| `Cpu65816(memory, seed=UNSET_SEED)` | 65816 核心類別，用於型別檢查 |
| `OPCODES`, `MODE_SIZE`, `FLAG_DEPENDENT` | 以 `(mnemonic, mode)` 配對表示的 65816 操作碼表、每種模式的運算元位元組數，以及寬度取決於 `m` 或 `x` 的兩種模式 |
| `decode(data, offset=0, address=0, m=True, x=True)` | 一條 65816 `Instruction`：`address`、`offset`、`opcode`、`mnemonic`、`mode`、`operand`、`size`、`text` |
| `disassemble(data, offset=0, address=0, count=None, m=True, x=True, stop_at_return=False)` | 65816 指令列表，會追蹤 `REP` 及 `SEP`。它在最後一條完整指令處停止 |
| `operand_size(mode, m, x)`, `branch_target(address, size, operand, width)`, `render(mode, operand, address, size, width)`, `apply_flags(instruction, m, x)` | 組成 `decode` 及 `disassemble` 的各個步驟 |
| `FLAG_C`, `FLAG_Z`, `FLAG_I`, `FLAG_D`, `FLAG_X`, `FLAG_M`, `FLAG_V`, `FLAG_N` | 65816 狀態位元，由 `0x01` 至 `0x80` |
| `__version__` | 已安裝的版本 |

8 位元操作碼表分佈於兩個模組。`mos65xx.opcodes6502` 提供 `NMOS`、`decode(data, offset, address, table=NMOS)` 及 `disassemble(data, offset, address, count=None, table=NMOS, stop_at_return=False)`，後者產生帶有 `undocumented` 及 `unstable` 屬性的指令。`mos65xx.opcodes65c02.TABLES` 包含 `65c02`、`rockwell` 及 `wdc` 三個表。

```python
import mos65xx
from mos65xx import MODELS, Cpu, NoSuchPin, RunLimit, SparseMemory, UnknownModelError

for name in ("6502", "6507", "2a03", "65802"):
    model = MODELS[name]
    print(name, model.address_bits, model.data_bits, model.decimal, model.pins, model.reset_cycles)

print(Cpu("Rockwell65C02").model, Cpu("w65c816s").model)

try:
    Cpu("z80")
except UnknownModelError as refused:
    print(refused)

try:
    Cpu("6507", SparseMemory()).nmi()
except NoSuchPin as refused:
    print(refused)

try:
    Cpu("6502", fill=0xEA).run_until(lambda part: part.a == 0x99, limit=100)
except RunLimit as refused:
    print(refused)
```

```
6502 16 8 True ('irq', 'nmi', 'rdy') 8
6507 13 8 True ('rdy',) 8
2a03 16 8 False ('irq', 'nmi', 'rdy') 8
65802 16 16 True ('irq', 'nmi', 'rdy') 8
r65c02 65816
z80 is not a model this family covers; it has 2a03, 6502, 6503, 6504, 6505, 6506, 6507, 6512, 6513, 6514, 6515, 65802, 65816, 65c02, r65c02, w65c02
the 6507 has no nmi pin; it brings out rdy
gave up after 100 instructions at $31D0
```

### 命令列工具

| 指令 | 參數 | 結束代碼 |
|:--|:--|:--|
| `python3 mos65xx/doctor.py` | 無 | 所有檢查通過時為 0，否則為 1 |
| `python3 -m conformance.fetch` | `[directory] [--latest]`。預設為 `~/.cache/conformance-suites`。`--latest` 取用每個上游的最新提交，而非固定的版本 | 0，或在無法連接上游時為 1 |
| `python3 -m conformance.singlestep` | `<suite directory> [tests per file] [filter] [--model name]`。預設型號為 `65816` | 所有案例一致或沒有測試套件時為 0，出現不一致時為 1，參數錯誤時為 2 |
| `python3 -m conformance.cycles` | 與 `singlestep` 相同 | 與 `singlestep` 相同 |
| `python3 -m conformance.documents` | `[--check] [--only substring]` | 所有摘要相符時為 0，有檔案被拒絕或參數錯誤時為 1 |
| `python3 -m conformance.quotes` | 無 | 每段引文都能在其文件中找到，或此處沒有文件時為 0，否則為 1 |
| `python3 -m conformance.speed` | `[--instructions N] [--repeats N]`。預設為 200,000 及 7 | 高於每秒 700,000 個週期的下限時為 0，低於時為 1，參數錯誤時為 2 |
| `python3 -m conformance.netlist` | 無。讀取 `NETLIST` 變數 | 所有案例一致或未設定模擬時為 0，否則為 1 |
| `python3 -m conformance.links` | 無 | 0，或在引用的位址回應 404 或 410 時為 1 |
| `python3 -m conformance.watch` | `[definition] [--moved]` | 0，或在無法讀取定義或定義互相矛盾時為 1 |
| `python3 -m conformance.package` | `<wheel>` | 所有模組都在 wheel 中且其中沒有任何測試時為 0，否則為 1，沒有參數時為 2 |

## 以真實速度執行

`step()` 及 `run_for()` 會報告耗用的週期，因此主機可以讓晶片跟隨晶體振盪器的速度。Ricoh 2A03 以 1,789,773 Hz 運行。

```python
import time

from mos65xx import Cpu

HERTZ = 1_789_773
SLICE = 0.02

cpu = Cpu("2a03", fill=0xEA).reset()
per_slice = round(HERTZ * SLICE)
owed = 0

for _ in range(4):
    began = time.perf_counter()
    owed += per_slice
    owed -= cpu.run_for(owed)
    print(per_slice, owed, cpu.cycles)
    time.sleep(max(0.0, SLICE - (time.perf_counter() - began)))
```

```
35795 -1 35804
35795 0 71598
35795 -1 107394
35795 0 143188
```

以 `NOP` 填充的記憶體每條指令耗用 2 個週期，而每個時間片的 35,795 個週期是奇數。`run_for()` 無法把一條指令切成兩半，因此會多跑一個週期。把欠下的週期帶到下一個時間片，可令總數與時鐘相差不超過一個週期。停機的晶片仍會耗用分配給它的每個週期：卡死的 NMOS 晶片會持續讀取 `$FFFF`，而執行了 `STP` 或 `WAI` 的 65816 會產生沒有位址的週期。

<a id="driving-it-one-cycle-at-a-time"></a>

## 逐個週期驅動

`Clock(cpu)` 可在任意兩個週期之間暫停晶片，電路板可在此時改變之後某次讀取會得到的值。

```python
from mos65xx import Clock, Cpu, Memory

space = Memory(image=bytes([0xA5, 0x10]))
space.write8(0x0010, 0x11)
cpu = Cpu("6502", space)
cpu.reset()
cpu.pc = 0x0000
cpu.trace = []

with Clock(cpu) as clock:
    clock.tick()
    clock.tick()
    space.write8(0x0010, 0x99)
    clock.run_for(1)

print([(hex(address), hex(value)) for address, value, _ in cpu.trace])
```

```
[('0x0', '0xa5'), ('0x1', '0x10'), ('0x10', '0x99')]
```

`$0010` 的位元組改變時，`LDA $10` 已取得其操作碼及運算元，而它的第三個週期讀到的是新值。

| 呼叫 | 效果 |
|:--|:--|
| `tick()` | 把晶片執行至其下一個週期結束，並傳回時鐘的週期計數 |
| `run_for(cycles)` | 執行 `cycles` 次 tick。傳回時鐘的週期計數 |
| `close()` | 停止工作執行緒，並還原晶片的 `on_cycle` |
| `cycles`, `closed`, `cpu` | 至今的 tick 次數、是否已關閉、所驅動的晶片 |

`Clock` 是一個上下文管理器，也是一個每次產生一個 tick 的迭代器。停機的晶片會經由 `held_cycle()` 繼續 tick。Python 無法暫停呼叫堆疊，因此時鐘在工作執行緒上執行晶片，並在每個週期經由兩個號誌交接控制權。追求吞吐量時用 `step()`，要知道某件事發生在哪個週期時用 `Clock`。

<a id="models"></a>

## 型號

型號決定位址線、中斷線、十進制加法器及指令集。

| 建立方式 | 位址位元 | 針腳 | 十進制 | 晶片 | 別名 |
|:--|:--:|:--|:--:|:--|:--|
| `Cpu("6502")` | 16 | IRQ, NMI, RDY | 是 | MOS 6502 | `mos6502`, `nmos6502`, `6510`, `8500` |
| `Cpu("6503")` | 12 | IRQ, NMI | 是 | MOS 6503 | `mos6503` |
| `Cpu("6504")` | 13 | IRQ | 是 | MOS 6504 | `mos6504` |
| `Cpu("6505")` | 12 | IRQ, RDY | 是 | MOS 6505 | `mos6505` |
| `Cpu("6506")` | 12 | IRQ | 是 | MOS 6506，以第二個時鐘輸出取代 RDY | `mos6506` |
| `Cpu("6507")` | 13 | RDY | 是 | MOS 6507 | `mos6507` |
| `Cpu("6512")` | 16 | IRQ, NMI, RDY | 是 | MOS 6512，使用外部兩相時鐘的 6502 | `mos6512` |
| `Cpu("6513")` | 12 | IRQ, NMI | 是 | MOS 6513，使用外部時鐘的 6503 | `mos6513` |
| `Cpu("6514")` | 13 | IRQ | 是 | MOS 6514，使用外部時鐘的 6504 | `mos6514` |
| `Cpu("6515")` | 12 | IRQ, RDY | 是 | MOS 6515，使用外部時鐘的 6505 | `mos6515` |
| `Cpu("2a03")` | 16 | IRQ, NMI, RDY | 否 | Ricoh 2A03 及 2A07 | `ricoh2a03`, `2a07`, `ricoh2a07`, `nes6502`, `famicom` |
| `Cpu("65c02")` | 16 | IRQ, NMI, RDY | 是 | 基本 CMOS 設計 | `synertek65c02`, `s65c02`, `cmos6502` |
| `Cpu("r65c02")` | 16 | IRQ, NMI, RDY | 是 | Rockwell R65C02，新增 32 條單位元指令 | `rockwell65c02`, `rockwell` |
| `Cpu("w65c02")` | 16 | IRQ, NMI, RDY | 是 | WDC W65C02S，新增 `STP` 及 `WAI` | `wdc65c02`, `w65c02s` |
| `Cpu("65802")` | 16 | IRQ, NMI, RDY | 是 | WDC W65C802，具 16 條位址線的 65816 核心 | `w65c802`, `65c802` |
| `Cpu("65816")` | 24 | IRQ, NMI, RDY | 是 | WDC W65C816S | `w65c816`, `w65c816s`, `65c816`, `65816s` |

十一款 NMOS 型號共用一個核心，三款 65C02 型號共用第二個，65816 及 65802 共用第三個。較窄的封裝可存取的範圍較少：65802 讀取 `$7E0012` 時落在 `$0012`，6507 讀取 `$F234` 時落在 `$1234`。在 2A03 上，十進制旗標可以設定，但不會改變任何東西。

```python
from mos65xx import Cpu, SparseMemory

memory = SparseMemory()
memory.write8(0x0012, 0x5A)
memory.write8(0x7E0012, 0xA5)

for name in ("65816", "65802"):
    print(name, hex(Cpu(name, memory).read8(0x7E0012)))

for name in ("6502", "2a03"):
    cpu = Cpu(name, SparseMemory())
    cpu.a, cpu.c, cpu.d = 0x19, False, True
    cpu.add_with_carry(0x01)
    print(name, hex(cpu.a))
```

```
65816 0xa5
65802 0x5a
6502 0x20
2a03 0x1a
```

每款 8 位元晶片都能執行全部 256 個操作碼。MOS 為其中一百五十一個提供了文件。其餘一百零五個按測試套件所記錄的方式執行，包括 `JAM`，而 [`conformance/instruction-set.json`](conformance/instruction-set.json) 按 Appendix B 所印的內容記錄有文件記載與否的劃分。

## 不執行而讀取

`disassemble()` 無需晶片執行即可讀取位元組。

```python
from mos65xx import disassemble
from mos65xx.opcodes6502 import NMOS, render
from mos65xx.opcodes6502 import disassemble as disassemble8
from mos65xx.opcodes65c02 import TABLES

for instruction in disassemble(bytes.fromhex("c230a9341260"), address=0x018000):
    print(f"{instruction.address:06X}  {instruction.size}  {instruction.text}")

code = bytes.fromhex("a9ff8f3412")
for table in (NMOS, TABLES["wdc"]):
    for found in disassemble8(code, 0, 0xC000, table=table):
        operand = render(found.mode, found.operand, found.address, found.size)
        print(f"{found.address:04X}  {found.mnemonic} {operand}  {found.undocumented}")
```

```
018000  2  rep #$30
018002  3  lda #$1234
018005  1  rts
C000  lda #$FF  False
C002  sax $1234  True
C000  lda #$FF  False
C002  bbs0 $34,$C017  False
```

在 65816 上，立即運算元的寬度取決於較早設定的旗標。`disassemble` 開始時 `m` 及 `x` 均已設定，並跟隨每條 `REP` 及 `SEP`，因此在 `REP #$30` 之後，載入指令取用兩個運算元位元組。同樣的 8 位元位元組在 NMOS 晶片上解碼為未有文件記載的 `SAX`，在 W65C02S 上則解碼為 `BBS0`。

## 沒有東西以乾淨狀態啟動

暫存器及記憶體通電時帶有可重現的打亂模式，因此程式讀取一個從未被寫入的位元組時，得到的不是零。暫存器沒有可將其清除的選項。記憶體只有在以 `fill` 建立時才會被清除。

```python
from mos65xx import Cpu, Memory, SparseMemory

print(hex(SparseMemory().read8(0x123456)))
print(Memory(size=0x1000).data == bytearray(0x1000))

powered = Cpu("65816", Memory(size=0x1000000))
print(hex(powered.pc), powered.cycles)
```

```
0x1d
False
0xd8ef 0
```

`SparseMemory` 由位址及種子推導出未寫入的位元組，因此一個觸及十二個位元組的測試只會儲存十二個。兩種記憶體及每款晶片都接受 `seed`，因此與另一個實現對照的執行能完全重現。`Memory` 接受 `image`，即電路板通電時所載有的內容。

## 它是否正確

每個核心都與為其晶片錄製的 SingleStepTests 測試套件比對，每個操作碼 10,000 個案例，橫跨六個測試套件：65816、6502、nes6502、synertek65c02、rockwell65c02 及 wdc65c02。狀態比對檢查暫存器、旗標及每個案例觸及的每個記憶體位元組：**17,900,000 個案例，沒有未獲解釋的失敗**。週期比對按次序檢查每個匯流排週期，逐個位址比對並區分讀取與寫入，在 65816 上亦比對八個針腳：**17,870,080 個案例，沒有未獲解釋的失敗**。

```bash
python3 -m conformance.fetch ~/.cache/conformance-suites
python3 -m conformance.singlestep ~/.cache/conformance-suites/6502/6502/v1 --model 6502
python3 -m conformance.cycles ~/.cache/conformance-suites/6502/6502/v1 --model 6502
```

兩個總數均由 [`conformance/suites.json`](conformance/suites.json) 推導得出，並有測試確保本頁與之一致。wdc65c02 測試套件中 `WAI` 及 `STP` 的檔案是空的。週期總數不包括 29,920 個 CMOS 十進制案例，這些案例的額外週期記錄在一個沒有任何暫存器會產生的固定位址上。兩個執行器均按條件排除三十七個 65816 案例，並列印排除的數目：當模擬模式的堆疊指標位於第一頁頂部時，測試套件與數據表對單位元組彈出落在何處意見不一，而本核心依從數據表。

[`conformance/hardware.json`](conformance/hardware.json) 記錄取自製造商頁面的每項事實，連同其出處的句子及頁面，並有測試確保程式碼與之相符。[`conformance/addressing-cycles.json`](conformance/addressing-cycles.json) 及 [`conformance/instruction-set.json`](conformance/instruction-set.json) 按原樣收錄硬件手冊的 Appendix A 及程式設計手冊的 Appendix B。[`conformance/divergences.json`](conformance/divergences.json) 記錄兩個來源互相矛盾的 19 處、本套件依從哪一方，以及甚麼可以解決每一處分歧。`python3 -m conformance.quotes` 會在其文件中找出每一段引文。

測試套件以提交固定版本。一個每週執行的工作會以每個上游的最新提交執行它們，新版測試套件通過時開啟一個 pull request，失敗時則開啟一個 issue。[OPEN-QUESTIONS.md](OPEN-QUESTIONS.md) 列出 16 個文件及測試套件都未能解決的問題，每個都附有可以解決它的真實晶片量度方法。

## 參與開發

| 需要 | 位置 |
|:--|:--|
| 每項關卡檢查及其執行次序 | [CONTRIBUTING.md](CONTRIBUTING.md) |
| 供編程代理使用的相同內容 | [AGENTS.md](AGENTS.md) |
| 本儲存庫與系列其他成員共用的標準 | [FAMILY.md](FAMILY.md) |
| 錯誤報告 | [GitHub Issues](https://github.com/gufranco/mos65xx-python/issues) |
| 安全報告 | [SECURITY.md](SECURITY.md) |

```bash
uvx ruff@0.16.3 format --check .
uvx ruff@0.16.3 check .
uvx --python 3.12 mypy==1.14.1
python3 mos65xx/mos6502.test.py
```

每個模組旁邊都有一個以其命名的測試檔案，每個都能如上所示獨立執行。覆蓋率是一項硬性關卡檢查，要求 100% 語句及分支覆蓋率。

## 參考資料

以下每份文件的版權均屬其出版者，本儲存庫並不包含任何一份。[`conformance/documents.json`](conformance/documents.json) 載有每份文件的完整 SHA-256、位元組數及位址。`python3 -m conformance.documents` 會把全部十二份下載至 git 忽略的 `docs/`，並拒絕任何摘要不符的檔案。`--check` 會驗證已存在的檔案。

| 文件 | 日期 | 頁數 | SHA-256 |
|:--|:--|--:|:--|
| [MOS Technology, Inc., *MCS6500 Microcomputer Family Hardware Manual*](https://archive.org/download/mcs-6500-family-hardware-manual-1976-01/MCS6500_family_hardware_manual_1976-01.pdf) | 1976-01 | 182 | `81ea570c9d68deff64d67365bdf24534df93a8c62121e53036aeac6a557cea23` |
| [MOS Technology, Inc., *MCS6500 Microcomputer Family Programming Manual*](https://archive.org/download/6500-50A_MCS6500_Programming_Manual_1976_Jan/6500-50A_MCS6500_Programming_Manual_1976_Jan.pdf) | 1976-01 | 262 | `a2d54dd8b6557c7f2f275b4ddaa9180b5754274a762df122d79392f03264b483` |
| [MOS Technology, Inc., *MOS 6500 Microprocessors*](https://6502.org/documents/datasheets/mos/mos_6500_mpu_nov_1985.pdf) | 1985-11 | 12 | `ccd72376d1e5db1fb13777de538417f4799ab38e1f746452f9695465c422dcd7` |
| [MOS Technology, Inc., *MOS 6500 Microprocessors*](https://6502.org/documents/datasheets/mos/mos_6500_mpu_mar_1980.pdf) | 1980-03 | 12 | `a564c4de593ea178868a43eaf7e00fe7d3460016d2a7880d20eb756f2bf2d030` |
| [Synertek, Inc., *SY6500 Microprocessors*](https://6502.org/documents/datasheets/synertek/synertek_sy6500_microprocessors.pdf) | 未註明日期 | 6 | `f20b50961df60bb0e1980f271ad49b4b788c46a143127ccc58e8d3ce84d99193` |
| [Synertek, Inc., *SY6500 Hardware Manual*](https://6502.org/documents/datasheets/synertek/synertek_hardware_manual.pdf) | 未註明日期 | 178 | `9cd0991dcbb4a46bf63747528282ad175ed15e1957d08bd755ef14b978b67a1c` |
| [Rockwell International, *R65C00 Microprocessors: R65C02, R65C102 and R65C112*](https://6502.org/documents/datasheets/rockwell/rockwell_r65c00_microprocessors.pdf) | 1987-06 | 16 | `63deee76c8d0d4faee7bb8f9c50ff21662c73f2e82093ebacfb284f527faf134` |
| [The Western Design Center, Inc., *W65C02S 8-bit Microprocessor Data Sheet*](https://westerndesigncenter.com/wdc/documentation/w65c02s.pdf) | 2022-04-08 | 32 | `a6af3ca9da45c8a03504c94c7399cb6b08f15ce14185dd3e1e880433cdaa8cf5` |
| [The Western Design Center, Inc., *W65C816S 8/16-bit Microprocessor Data Sheet*](https://datasheets.chipdb.org/Western%20Design/w65c816s.pdf) | 2004-06-14 | 62 | `60f21a3da0331273c6b92963ba7660408ab1ba3cf9dca2e37b1e55e7950ff313` |
| [The Western Design Center, Inc., *W65C816S 8/16-bit Microprocessor Data Sheet*](https://6502.org/documents/datasheets/wdc/wdc_w65c816s_jul_1994.pdf) | 1994-07 | 72 | `823c2f286a97102fc3695596f7c03e26e2f01cff0f45023dc3bb71688e689bc7` |
| [The Western Design Center, Inc., *W65C816S Datasheet*](https://westerndesigncenter.com/wdc/documentation/w65c816s.pdf) | 2024-03-13 | 55 | `b9177e1b045d2c8a801d1b23619abb4e5b29b88868fa491df7296dbc0b13447e` |
| [The Western Design Center, Inc., David Eyes and Ron Lichty, *Programming the 65816, including the 6502, 65C02 and 65802*](https://github.com/gilligan/snesdev/blob/master/docs/programming_the_65816.pdf) | 2007 | 469 | `dbccafcc47d6e53436bdc1c0049b3c54ffacfc9034a4041a7d92b6e6c5d72bb5` |

Ricoh 沒有為 2A03 發佈數據表，因此由 MOS 的文件涵蓋其所基於的核心。三個 W65C816S 修訂版均沒有提及 W65C802，因此由 65816 的文件涵蓋其核心，而其封裝沒有文件記載。

測試套件來自 [SingleStepTests](https://github.com/SingleStepTests)，並以提交固定版本於 [`conformance/suites.json`](conformance/suites.json)。出版者沒有為任何一個測試套件指明生成它的實現，因此它們的地位低於製造商的陳述。

## 引用本專案

[CITATION.cff](CITATION.cff) 會在每次發佈時，由寫入套件版本號的腳本更新。

## 授權

MIT。見 [LICENSE](LICENSE)。
