# MOS 65xx

用 Python 实现的 65xx 系列十六款芯片，从 MOS 6502 到 WDC W65C816S，每次推进一个总线周期，并以 SingleStepTests 的逐操作码测试套件和制造商的数据手册为准。

[English](README.md) | [日本語](README.ja.md) | 简体中文 | [繁體中文（香港）](README.zh-HK.md)

[![CI](https://github.com/gufranco/mos65xx-python/actions/workflows/ci.yml/badge.svg)](https://github.com/gufranco/mos65xx-python/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/gufranco/mos65xx-python)](https://github.com/gufranco/mos65xx-python/releases)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**16** 款芯片，比对了 **17,900,000** 个状态用例和 **17,870,080** 个周期精确用例，**0** 个无法解释的失败，**1,478** 个测试，**100%** 语句和分支覆盖率，无依赖

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

`$8000` 处的程序是 `CLC`、`XCE`、`REP #$30` 和 `LDA #$1234`。`reset()` 花费 8 个周期，并从 `$FFFC` 处的向量加载程序计数器。`CLC` 和 `XCE` 退出仿真模式，`REP` 把累加器和变址寄存器扩展为 16 位，随后的加载指令取一个 16 位操作数。每次 `step()` 返回该指令花费的周期数：这四条共 10 个，自芯片构建以来共 18 个。

## 安装

| 要求   | 版本               |
| :----- | :----------------- |
| Python | 3.12 或更高        |
| git    | 任意版本，用于克隆 |

```bash
git clone https://github.com/gufranco/mos65xx-python.git
cd mos65xx-python
python3 mos65xx/doctor.py
```

该包只导入标准库中的内容。`pip install git+https://github.com/gufranco/mos65xx-python.git` 会安装它，并附带一个运行同一报告的 `mos65xx-doctor` 命令。

诊断脚本检查本机环境，构建并复位每一款芯片，并报告已获取哪些一致性测试套件。它以文件方式运行而不是用 `-m`，因此即使包无法导入，它仍能给出报告。它以一行结束。提交 bug 报告时请粘贴它的全部输出。

```
  26 checks, nothing to report
```

版本遵循 [Semantic Versioning](https://semver.org/)，由 semantic-release 根据提交历史发布。每个版本都打了标签，并列在[发布页面](https://github.com/gufranco/mos65xx-python/releases)上。

## 接口

`Cpu(model, memory=None, fill=None, **options)` 构建一款芯片，已上电但未复位。`model` 是必需参数，省略它会抛出 `UnknownModelError`，并列出所有可接受的名称。十六个名称及其别名见[型号](#models)。名称中的大小写、`-` 和 `_` 会被忽略。`memory` 是任何具有 `read8(address)` 和 `write8(address, value)` 的对象。不提供时，芯片会得到一个 `SparseMemory`；若给出了 `fill`，则得到一个以 `fill` 填充的 16 MB `Memory`。

| 选项       | 芯片 | 作用                                                         |
| :--------- | :--- | :----------------------------------------------------------- |
| `seed=`    | 全部 | 为上电时被打乱的寄存器提供种子。默认为 `UNSET_SEED`          |
| `decimal=` | 8 位 | 是否接有十进制加法器。由型号设置，只有 `2a03` 将其设为 false |
| `table=`   | 8 位 | 操作码表。由型号设置                                         |

### 调用

| 调用                                        | 作用                                                                                                                                                                                                                 | 返回                                    |
| :------------------------------------------ | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :-------------------------------------- |
| `reset(seed=UNSET_SEED)`                    | 驱动 RESET：六个周期，然后用两个周期读取 `$FFFC` 处的向量。W65C02S 分别用五个和两个。清零 `steps`，设置中断禁止标志，在 CMOS 芯片上还会清除十进制标志。65816 还会进入仿真模式，寄存器为 8 位，`d`、`db` 和 `pb` 为 0 | 芯片本身                                |
| `step()`                                    | 运行一条指令，然后采样中断线                                                                                                                                                                                         | 花费的周期数，包括进入中断              |
| `run_for(cycles)`                           | 运行完整的指令，直到至少经过 `cycles` 个周期。停机的芯片每调用一次 `held_cycle()` 花费一个周期                                                                                                                       | 花费的周期数，可能超过 `cycles`         |
| `run_until(check, limit=None)`              | 在 `check(part)` 为假时持续单步执行。执行 `limit` 条指令后抛出 `RunLimit`                                                                                                                                            | 芯片本身                                |
| `call(address, limit=None)`                 | 跳转到 `address` 并单步执行，直到下一条是与之匹配的 `RTS`，在 65816 上则是 `RTL`。嵌套调用会被计数                                                                                                                   | 芯片本身                                |
| `held()`                                    | 芯片是否处于卡死、停止或等待状态                                                                                                                                                                                     | `bool`                                  |
| `held_cycle()`                              | 停机芯片的一个周期。卡死的 NMOS 芯片读取 `$FFFF`。其他芯片花费一个没有总线访问的周期                                                                                                                                 | 无                                      |
| `irq()`                                     | 除非设置了中断禁止标志，否则立即响应中断请求                                                                                                                                                                         | 响应时返回 `True`                       |
| `nmi()`                                     | 立即响应不可屏蔽中断                                                                                                                                                                                                 | 8 位芯片上无返回值，65816 上返回 `True` |
| `abort()`                                   | 仅 65816。立即响应中止                                                                                                                                                                                               | 响应时返回 `True`                       |
| `status()`                                  | 以一个字节表示的状态寄存器                                                                                                                                                                                           | `int`                                   |
| `set_status(byte)`                          | 用一个字节设置所有标志                                                                                                                                                                                               | 无                                      |
| `set_emulation(flag)`                       | 仅 65816。进入或退出仿真模式，仿真模式强制使用 8 位寄存器和第一页中的栈                                                                                                                                              | 无                                      |
| `read8(address)` / `write8(address, value)` | 通过芯片地址线的一个总线周期，会被追踪和计数。在两条指令之间调用时，该周期在调用当时计入，因此下一次 `step()` 只返回它自己那条指令的周期                                                                             | 读到的字节，或无                        |
| `power_on(seed)`                            | 像构建时一样再次打乱寄存器                                                                                                                                                                                           | 无                                      |

在封装未引出某条线的芯片上，`irq()` 和 `nmi()` 会抛出 `NoSuchPin`。65816 和 65802 引出了全部三条线。

### 状态

| 属性                                              | 含义                                                                                                                                                                                                                                                                                                               |
| :------------------------------------------------ | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `a`、`x`、`y`、`s`、`pc`                          | 寄存器。在 65816 上 `a`、`x`、`y` 和 `s` 保存 16 位                                                                                                                                                                                                                                                                |
| `db`、`pb`、`d`                                   | 仅 65816。数据存储体、程序存储体和直接页寄存器                                                                                                                                                                                                                                                                     |
| `n`、`v`、`z`、`c`                                | 在每款芯片上含义相同的标志，各为一个 `bool`                                                                                                                                                                                                                                                                        |
| `i`、`d`、`b`、`decimal`                          | 8 位芯片。中断禁止、十进制标志、中断指令标志，以及是否接有十进制加法器                                                                                                                                                                                                                                             |
| `irq_disable`、`decimal`、`m8`、`x8`、`emulation` | 仅 65816。中断禁止、十进制标志、8 位累加器、8 位变址寄存器、仿真模式                                                                                                                                                                                                                                               |
| `irq_line`                                        | 以电平表示的请求线。它在每条指令之后采样，因此在此之前撤回的请求不会被响应                                                                                                                                                                                                                                         |
| `nmi_line`                                        | 不可屏蔽中断线。由低到高的变化触发一次中断，保持为高不会再次中断。在 NMOS 芯片上，在 `BRK` 执行期间、读取其向量之前到达的变化，会如 WDC 和 Rockwell 所印，用 NMI 向量取代 `BRK` 向量                                                                                                                               |
| `ready_line`                                      | 为假时，读操作会持续花费周期直到它再次为真，因此主机从 `on_cycle` 中将其清除。CMOS 芯片和 65816 以同样方式挂起写操作，NMOS 芯片则不会                                                                                                                                                                              |
| `cycles`                                          | 自构建以来的周期数。复位会累加到其中                                                                                                                                                                                                                                                                               |
| `steps`                                           | 自上次复位以来的指令数                                                                                                                                                                                                                                                                                             |
| `stopped`、`jammed`、`waiting`                    | 三种停机状态。`jammed` 仅限 NMOS，`waiting` 适用于 CMOS 芯片和 65816                                                                                                                                                                                                                                               |
| `trace`                                           | 将其设为一个列表后，每个总线周期都会以 `(address, value, kind)` 的形式追加进去。`kind` 在 8 位芯片上是 `read` 或 `write`，在 65816 上是八个引脚字母：数据、程序、向量读取、写、仿真、`m`、`x`、存储器锁定。65816 的内部周期以 `None` 记录其值，仿真模式下的修改周期除外；停机周期记录为 `(None, None, "--------")` |
| `on_cycle`                                        | 每个周期调用一次，在该周期结束时，在其总线活动及随后的处理之后                                                                                                                                                                                                                                                     |
| `model`                                           | 规范型号名称                                                                                                                                                                                                                                                                                                       |
| `package_pins`                                    | 封装引出的中断线和就绪线，例如 `("irq", "nmi", "rdy")`                                                                                                                                                                                                                                                             |
| `address_mask`                                    | 封装引出的地址线。6507 在 `$1234` 处读到的是 `$F234`                                                                                                                                                                                                                                                               |
| `reset_cycles`                                    | 复位花费的周期数，8 或 7                                                                                                                                                                                                                                                                                           |
| `memory`                                          | 存储器对象                                                                                                                                                                                                                                                                                                         |
| `cycle_budget`                                    | 仅 65816。设置后，`MVN` 和 `MVP` 只移动该周期数内能容纳的字节数                                                                                                                                                                                                                                                    |

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

`$0200` 处的 `CLI` 在请求线保持有效时清除中断禁止标志，因此同一步会经由 `$FFFE` 进入中断：`CLI` 用 2 个周期，进入中断用 7 个。拉高不可屏蔽中断线会经由 `$FFFA` 中断一次。第三步在该线仍为高时运行一条 `NOP`。

### 错误

| 错误                | 抛出时机                                                                                                                                                                  |
| :------------------ | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `UnknownModelError` | `Cpu()` 没有得到名称，或得到的名称不属于任何型号或别名                                                                                                                    |
| `NoSuchPin`         | 在封装未引出该线的 8 位芯片上调用 `irq()` 或 `nmi()`                                                                                                                      |
| `InsideInstruction` | 在 `Clock` 暂停于一条指令或中断进入过程的中途，或暂停于某条线的中断进入待处理的边界时，从外部调用 `irq()` 或 `nmi()`。应 tick 到指令边界，或设置 `irq_line` 或 `nmi_line` |
| `RunLimit`          | `run_until()` 或 `call()` 达到其 `limit`                                                                                                                                  |
| `Stopped`           | 在执行了 `STP` 或已卡死的芯片上调用 `step()`                                                                                                                              |
| `Waiting`           | 在执行了 `WAI` 的芯片上调用 `step()`。它是 `Stopped` 的子类。`irq()` 和 `nmi()` 会将其释放                                                                                |
| `ClockClosed`       | 在已关闭的 `Clock` 上调用 `tick()`                                                                                                                                        |
| `Truncated`         | `decode()` 在指令结束前用完了字节                                                                                                                                         |
| `UnsupportedError`  | 操作码表中出现了内核没有处理程序的指令或寻址模式                                                                                                                          |

### 模块内容

| 名称                                                                                                                                                        | 内容                                                                                                                                                                 |
| :---------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `MODELS`                                                                                                                                                    | 十六条 `Model` 记录，以规范名称为键                                                                                                                                  |
| `Model`                                                                                                                                                     | `name`、`summary`、`address_bits`、`data_bits`、`decimal`、`pins`、`reset_cycles`、`aliases`、`narrows`、`revision`、`address_mask`，以及 `build(memory, **options)` |
| `Clock(cpu)`                                                                                                                                                | 每次一个周期地运行芯片。见[逐周期驱动](#driving-it-one-cycle-at-a-time)                                                                                              |
| `Memory(size=0x1000000, image=None, seed=UNSET_SEED, fill=None)`                                                                                            | 一个扁平字节数组，先由 `seed` 打乱，再以 `fill` 填充，然后覆盖上 `image`。其字节为 `data`                                                                            |
| `SparseMemory(seed=UNSET_SEED)`                                                                                                                             | 24 位地址空间，只存储写入过的内容。其写入过的字节为 `cells`                                                                                                          |
| `scramble(size, seed=UNSET_SEED)`                                                                                                                           | 两种存储器和每款芯片起始时使用的打乱后的 `bytearray`                                                                                                                 |
| `UNSET_SEED`                                                                                                                                                | 默认种子，`0x5A5A5A5A`                                                                                                                                               |
| `Cpu65816(memory, seed=UNSET_SEED)`                                                                                                                         | 65816 内核类，用于类型检查                                                                                                                                           |
| `OPCODES`、`MODE_SIZE`、`FLAG_DEPENDENT`                                                                                                                    | 以 `(mnemonic, mode)` 对表示的 65816 操作码表、每种模式的操作数字节数，以及宽度随 `m` 或 `x` 变化的两种模式                                                          |
| `decode(data, offset=0, address=0, m=True, x=True)`                                                                                                         | 一条 65816 `Instruction`：`address`、`offset`、`opcode`、`mnemonic`、`mode`、`operand`、`size`、`text`                                                               |
| `disassemble(data, offset=0, address=0, count=None, m=True, x=True, stop_at_return=False)`                                                                  | 一个 65816 指令列表，会跟踪 `REP` 和 `SEP`。它在最后一条完整指令处停止                                                                                               |
| `operand_size(mode, m, x)`、`branch_target(address, size, operand, width)`、`render(mode, operand, address, size, width)`、`apply_flags(instruction, m, x)` | 构成 `decode` 和 `disassemble` 的各个步骤                                                                                                                            |
| `FLAG_C`、`FLAG_Z`、`FLAG_I`、`FLAG_D`、`FLAG_X`、`FLAG_M`、`FLAG_V`、`FLAG_N`                                                                              | 65816 状态位，`0x01` 到 `0x80`                                                                                                                                       |
| `NMOS`、`TABLES`                                                                                                                                            | 以 `(mnemonic, mode)` 对表示的 8 位操作码表：`NMOS` 用于十一款 NMOS 芯片，`TABLES` 以 `65c02`、`rockwell` 和 `wdc` 为键，用于三款 CMOS 芯片                          |
| `decode8(data, offset, address, table=NMOS)`                                                                                                                | 一条 8 位指令：`address`、`opcode`、`mnemonic`、`mode`、`operand`、`size`，以及 `undocumented` 和 `unstable` 属性。字节不足时抛出 `Truncated`                        |
| `disassemble8(data, offset, address, count=None, table=NMOS, stop_at_return=False)`                                                                         | 按顺序产生 8 位指令。它在最后一条完整指令处停止                                                                                                                      |
| `render8(mode, operand, address, size)`                                                                                                                     | 以汇编文本表示的 8 位操作数，分支则表示为其到达的地址                                                                                                                |
| `__version__`                                                                                                                                               | 已安装的版本                                                                                                                                                         |

三个 8 位函数的名称以 `8` 结尾，因此不会遮蔽 65816 的同名函数。

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

### 命令行工具

| 命令                                | 参数                                                                                                                                                                                | 退出码                                                              |
| :---------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------ |
| `python3 mos65xx/doctor.py`         | 无                                                                                                                                                                                  | 所有检查通过时为 0，否则为 1                                        |
| `python3 -m conformance.fetch`      | `[directory] [--latest]`。默认为 `~/.cache/conformance-suites`。`--latest` 使用每个上游的最新提交，而不是固定的版本。已有的副本会被移到固定版本，最终不在固定版本上的副本会终止运行 | 0，无法访问某个上游时为 1                                           |
| `python3 -m conformance.singlestep` | `<suite directory> [tests per file] [filter] [--model name]`。默认型号为 `65816`                                                                                                    | 所有用例一致或没有测试套件时为 0，出现不一致时为 1，参数错误时为 2  |
| `python3 -m conformance.cycles`     | 与 `singlestep` 相同                                                                                                                                                                | 与 `singlestep` 相同                                                |
| `python3 -m conformance.documents`  | `[--check] [--only substring]`                                                                                                                                                      | 所有摘要都匹配时为 0，有文件被拒绝或参数错误时为 1                  |
| `python3 -m conformance.quotes`     | 无                                                                                                                                                                                  | 每条引文都在其文档中找到或本地没有文档时为 0，否则为 1              |
| `python3 -m conformance.speed`      | `[--instructions N] [--repeats N]`。默认分别为 200,000 和 7                                                                                                                         | 高于每秒 700,000 个周期的下限时为 0，低于时为 1，参数错误时为 2     |
| `python3 -m conformance.netlist`    | 无。读取 `NETLIST` 变量                                                                                                                                                             | 所有用例一致或未配置仿真时为 0，否则为 1                            |
| `python3 -m conformance.links`      | 无                                                                                                                                                                                  | 0，某个引用的地址返回 404 或 410 时为 1                             |
| `python3 -m conformance.watch`      | `[definition] [--moved]`                                                                                                                                                            | 0，定义无法读取或互相矛盾时为 1                                     |
| `python3 -m conformance.package`    | `<wheel>`                                                                                                                                                                           | 每个模块都在 wheel 中且没有测试混入时为 0，否则为 1，没有参数时为 2 |

## 以真实速度运行

`step()` 和 `run_for()` 报告花费的周期数，因此主机可以让芯片与晶振保持同步。Ricoh 2A03 以 1,789,773 Hz 运行。

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

以 `NOP` 填充的存储器每条指令运行 2 个周期，而 35,795 个周期的时间片是奇数。`run_for()` 无法把一条指令切成两半，因此会多出一个周期。把欠下的周期带入下一个时间片，可以使总数与时钟相差不超过一个周期。停机的芯片仍会花费给它的每个周期：卡死的 NMOS 芯片持续读取 `$FFFF`，执行 `STP` 或 `WAI` 后的 65816 产生没有地址的周期。

<a id="driving-it-one-cycle-at-a-time"></a>

## 逐周期驱动

`Clock(cpu)` 可以让芯片停在任意两个周期之间，电路板会在此处改变之后某次读取的应答。

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

`$0010` 处的字节改变时，`LDA $10` 已经取得了操作码和操作数，它的第三个周期读到了新值。

| 调用                      | 作用                                             |
| :------------------------ | :----------------------------------------------- |
| `tick()`                  | 运行芯片到其下一个周期结束，并返回时钟的周期计数 |
| `run_for(cycles)`         | `cycles` 次 tick。返回时钟的周期计数             |
| `close()`                 | 停止工作线程并恢复芯片的 `on_cycle`              |
| `cycles`、`closed`、`cpu` | 到目前为止的 tick 数、是否已关闭、它驱动的芯片   |

`Clock` 是一个上下文管理器，也是一个每次产生一个 tick 的迭代器。停机的芯片通过 `held_cycle()` 继续 tick。Python 无法挂起调用栈，因此时钟在工作线程上运行芯片，并在每个周期通过两个信号量交接控制权。追求吞吐量时用 `step()`，关心某件事发生在哪个周期时用 `Clock`。停在一条指令最后一个周期上的时钟，无论之后是否关闭，都使芯片处于与 `step()` 相同的状态。在时钟暂停于指令边界时调用的 `irq()` 或 `nmi()` 会像在两次 `step()` 之间一样立即生效，其周期计入 `cpu.cycles`，但不计为 tick。暂停于指令或中断进入过程的中途时不存在这样的位置，因此调用会抛出 `InsideInstruction` 且不改变任何状态：应 tick 到边界，或设置芯片在指令完成时采样的 `irq_line` 或 `nmi_line`。在引脚线将要开始一次中断进入的边界上也是如此，例如尚未处理的 `nmi_line` 边沿，或在中断允许时保持的 `irq_line`：该步尚未结束，错误会指出待处理的线。

<a id="models"></a>

## 型号

型号决定地址线、中断线、十进制加法器和指令集。

| 构建方式        | 地址位数 | 引脚          | 十进制 | 芯片                                     | 别名                                                   |
| :-------------- | :------: | :------------ | :----: | :--------------------------------------- | :----------------------------------------------------- |
| `Cpu("6502")`   |    16    | IRQ, NMI, RDY |   是   | MOS 6502                                 | `mos6502`、`nmos6502`、`6510`、`8500`                  |
| `Cpu("6503")`   |    12    | IRQ, NMI      |   是   | MOS 6503                                 | `mos6503`                                              |
| `Cpu("6504")`   |    13    | IRQ           |   是   | MOS 6504                                 | `mos6504`                                              |
| `Cpu("6505")`   |    12    | IRQ, RDY      |   是   | MOS 6505                                 | `mos6505`                                              |
| `Cpu("6506")`   |    12    | IRQ           |   是   | MOS 6506，用第二个时钟输出代替 RDY       | `mos6506`                                              |
| `Cpu("6507")`   |    13    | RDY           |   是   | MOS 6507                                 | `mos6507`                                              |
| `Cpu("6512")`   |    16    | IRQ, NMI, RDY |   是   | MOS 6512，使用外部两相时钟的 6502        | `mos6512`                                              |
| `Cpu("6513")`   |    12    | IRQ, NMI      |   是   | MOS 6513，使用外部时钟的 6503            | `mos6513`                                              |
| `Cpu("6514")`   |    13    | IRQ           |   是   | MOS 6514，使用外部时钟的 6504            | `mos6514`                                              |
| `Cpu("6515")`   |    12    | IRQ, RDY      |   是   | MOS 6515，使用外部时钟的 6505            | `mos6515`                                              |
| `Cpu("2a03")`   |    16    | IRQ, NMI, RDY |   否   | Ricoh 2A03 和 2A07                       | `ricoh2a03`、`2a07`、`ricoh2a07`、`nes6502`、`famicom` |
| `Cpu("65c02")`  |    16    | IRQ, NMI, RDY |   是   | 基础 CMOS 设计                           | `synertek65c02`、`s65c02`、`cmos6502`                  |
| `Cpu("r65c02")` |    16    | IRQ, NMI, RDY |   是   | Rockwell R65C02，增加了 32 条单比特指令  | `rockwell65c02`、`rockwell`                            |
| `Cpu("w65c02")` |    16    | IRQ, NMI, RDY |   是   | WDC W65C02S，增加了 `STP` 和 `WAI`       | `wdc65c02`、`w65c02s`                                  |
| `Cpu("65802")`  |    16    | IRQ, NMI, RDY |   是   | WDC W65C802，带 16 条地址线的 65816 内核 | `w65c802`、`65c802`                                    |
| `Cpu("65816")`  |    24    | IRQ, NMI, RDY |   是   | WDC W65C816S                             | `w65c816`、`w65c816s`、`65c816`、`65816s`              |

十一个 NMOS 型号共用一个内核，三个 65C02 型号共用第二个，65816 和 65802 共用第三个。封装越窄，可访问的范围越小：65802 在 `$0012` 处读到的是 `$7E0012`，6507 在 `$1234` 处读到的是 `$F234`。在 2A03 上，十进制标志可以设置，但不改变任何结果。

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

所有 256 个操作码都能在每款 8 位芯片上运行。MOS 为其中一百五十一个编写了文档。其余一百零五个按测试套件记录的行为运行，包括 `JAM`；[`conformance/instruction-set.json`](conformance/instruction-set.json) 按 Appendix B 印刷的内容保存了有文档与无文档的划分。

## 只读不运行

`disassemble()` 读取字节，无需芯片来运行它们。

```python
from mos65xx import NMOS, TABLES, disassemble, disassemble8, render8

for instruction in disassemble(bytes.fromhex("c230a9341260"), address=0x018000):
    print(f"{instruction.address:06X}  {instruction.size}  {instruction.text}")

code = bytes.fromhex("a9ff8f3412")
for table in (NMOS, TABLES["wdc"]):
    for found in disassemble8(code, 0, 0xC000, table=table):
        operand = render8(found.mode, found.operand, found.address, found.size)
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

在 65816 上，立即数操作数的宽度取决于之前设置的标志。`disassemble` 开始时 `m` 和 `x` 处于置位状态，并跟踪每条 `REP` 和 `SEP`，因此在 `REP #$30` 之后，加载指令取两个操作数字节。同样的 8 位字节在 NMOS 芯片上解码为无文档的 `SAX`，在 W65C02S 上解码为 `BBS0`。

## 没有什么是干净启动的

寄存器和存储器上电时保存着可复现的打乱图案，因此程序读取一个从未被写入的字节时，得到的不是零。寄存器没有清零选项。存储器只有在用 `fill` 构建时才会被清零。

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

`SparseMemory` 根据地址和种子推导未写入的字节，因此一个只触及十几个字节的测试也只存储十几个字节。两种存储器和每款芯片都接受 `seed`，因此与另一个实现对照的运行可以完全重现。`Memory` 接受 `image`，即电路板在上电时保存的内容。

## 它是否正确

每个内核都与为其芯片录制的 SingleStepTests 测试套件比对，每个操作码 10,000 个用例，共六个套件：65816、6502、nes6502、synertek65c02、rockwell65c02 和 wdc65c02。状态比对检查寄存器、标志以及每个用例触及的每个存储器字节：**17,900,000 个用例，没有无法解释的失败**。周期比对按顺序检查每个总线周期，逐个比对地址和读写方向，在 65816 上还比对八个引脚：**17,870,080 个用例，没有无法解释的失败**。

```bash
python3 -m conformance.fetch ~/.cache/conformance-suites
python3 -m conformance.singlestep ~/.cache/conformance-suites/6502/6502/v1 --model 6502
python3 -m conformance.cycles ~/.cache/conformance-suites/6502/6502/v1 --model 6502
```

这两个总数都由 [`conformance/suites.json`](conformance/suites.json) 推导，并有一个测试确保本页与之一致。wdc65c02 套件中 `WAI` 和 `STP` 的文件是空的。周期总数排除了 29,920 个 CMOS 十进制用例，它们额外的周期记录在一个任何寄存器都无法产生的固定地址上。凡本内核遵循数据手册而非测试套件之处，两个运行器都打印另行处理的 65816 用例数量。按条件排除的有三十八个：仿真模式栈指针位于第一页顶部时的单字节出栈有三十七个，指针从已对齐直接页末尾开始的 `(d,x)` 有一个。其余用例除两种读法不同之处外全部比对：19,924 个仿真模式 `BRK` 和 `COP` 用例中的数据存储体寄存器，以及栈指针位于第一页底部的四十三个 `JSR (a,x)` 用例中一次入栈写入的地址。

[`conformance/hardware.json`](conformance/hardware.json) 保存了取自制造商文档页面的每一项事实，连同原句及其所在页面，并有测试确保代码与之一致。[`conformance/addressing-cycles.json`](conformance/addressing-cycles.json) 和 [`conformance/instruction-set.json`](conformance/instruction-set.json) 按印刷原样保存了硬件手册的 Appendix A 和编程手册的 Appendix B。[`conformance/divergences.json`](conformance/divergences.json) 记录了两个来源互相矛盾的 20 处、本包遵循哪一方，以及什么能解决每一处分歧。`python3 -m conformance.quotes` 会在各自的文档中找到每一句引文。

测试套件按提交固定。一个每周任务会在每个上游的最新提交上运行它们，较新的套件通过时打开一个 pull request，失败时打开一个 issue。[OPEN-QUESTIONS.md](OPEN-QUESTIONS.md) 列出了文档和测试套件都无法解决的 13 个问题，每个问题都附有能解决它的真实芯片测量方法。

## 参与开发

| 需要                             | 位置                                                               |
| :------------------------------- | :----------------------------------------------------------------- |
| 每一项门禁检查及其运行顺序       | [CONTRIBUTING.md](CONTRIBUTING.md)                                 |
| 面向编码智能体的相同内容         | [AGENTS.md](AGENTS.md)                                             |
| 本仓库与该系列其他仓库共享的标准 | [FAMILY.md](FAMILY.md)                                             |
| bug 报告                         | [GitHub Issues](https://github.com/gufranco/mos65xx-python/issues) |
| 安全报告                         | [SECURITY.md](SECURITY.md)                                         |

```bash
uvx ruff@0.16.3 format --check .
uvx ruff@0.16.3 check .
uvx --python 3.12 --with types-setuptools==84.0.0.20260812 mypy==1.14.1
python3 mos65xx/mos6502.test.py
```

每个模块旁边都有一个以其命名的测试文件，每个测试文件都可以像上面那样单独运行。覆盖率是一项硬性门禁检查，要求 100% 语句和分支覆盖率。

## 参考资料

以下每份文档的版权归其出版者所有，本仓库不包含任何一份。[`conformance/documents.json`](conformance/documents.json) 记录了每份文档完整的 SHA-256、字节数和地址。`python3 -m conformance.documents` 会把全部十二份下载到 git 忽略的 `docs/` 中，并拒绝任何摘要不匹配的文件。`--check` 会校验已有的文件。

| 文档                                                                                                                                                                                                       | 日期       | 页数 | SHA-256                                                            |
| :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------- | ---: | :----------------------------------------------------------------- |
| [MOS Technology, Inc., _MCS6500 Microcomputer Family Hardware Manual_](https://archive.org/download/mcs-6500-family-hardware-manual-1976-01/MCS6500_family_hardware_manual_1976-01.pdf)                    | 1976-01    |  182 | `81ea570c9d68deff64d67365bdf24534df93a8c62121e53036aeac6a557cea23` |
| [MOS Technology, Inc., _MCS6500 Microcomputer Family Programming Manual_](https://archive.org/download/6500-50A_MCS6500_Programming_Manual_1976_Jan/6500-50A_MCS6500_Programming_Manual_1976_Jan.pdf)      | 1976-01    |  262 | `a2d54dd8b6557c7f2f275b4ddaa9180b5754274a762df122d79392f03264b483` |
| [MOS Technology, Inc., _MOS 6500 Microprocessors_](https://6502.org/documents/datasheets/mos/mos_6500_mpu_nov_1985.pdf)                                                                                    | 1985-11    |   12 | `ccd72376d1e5db1fb13777de538417f4799ab38e1f746452f9695465c422dcd7` |
| [MOS Technology, Inc., _MOS 6500 Microprocessors_](https://6502.org/documents/datasheets/mos/mos_6500_mpu_mar_1980.pdf)                                                                                    | 1980-03    |   12 | `a564c4de593ea178868a43eaf7e00fe7d3460016d2a7880d20eb756f2bf2d030` |
| [Synertek, Inc., _SY6500 Microprocessors_](https://6502.org/documents/datasheets/synertek/synertek_sy6500_microprocessors.pdf)                                                                             | 未注明日期 |    6 | `f20b50961df60bb0e1980f271ad49b4b788c46a143127ccc58e8d3ce84d99193` |
| [Synertek, Inc., _SY6500 Hardware Manual_](https://6502.org/documents/datasheets/synertek/synertek_hardware_manual.pdf)                                                                                    | 未注明日期 |  178 | `9cd0991dcbb4a46bf63747528282ad175ed15e1957d08bd755ef14b978b67a1c` |
| [Rockwell International, _R65C00 Microprocessors: R65C02, R65C102 and R65C112_](https://6502.org/documents/datasheets/rockwell/rockwell_r65c00_microprocessors.pdf)                                        | 1987-06    |   16 | `63deee76c8d0d4faee7bb8f9c50ff21662c73f2e82093ebacfb284f527faf134` |
| [The Western Design Center, Inc., _W65C02S 8-bit Microprocessor Data Sheet_](https://westerndesigncenter.com/wdc/documentation/w65c02s.pdf)                                                                | 2022-04-08 |   32 | `a6af3ca9da45c8a03504c94c7399cb6b08f15ce14185dd3e1e880433cdaa8cf5` |
| [The Western Design Center, Inc., _W65C816S 8/16-bit Microprocessor Data Sheet_](https://datasheets.chipdb.org/Western%20Design/w65c816s.pdf)                                                              | 2004-06-14 |   62 | `60f21a3da0331273c6b92963ba7660408ab1ba3cf9dca2e37b1e55e7950ff313` |
| [The Western Design Center, Inc., _W65C816S 8/16-bit Microprocessor Data Sheet_](https://6502.org/documents/datasheets/wdc/wdc_w65c816s_jul_1994.pdf)                                                      | 1994-07    |   72 | `823c2f286a97102fc3695596f7c03e26e2f01cff0f45023dc3bb71688e689bc7` |
| [The Western Design Center, Inc., _W65C816S Datasheet_](https://westerndesigncenter.com/wdc/documentation/w65c816s.pdf)                                                                                    | 2024-03-13 |   55 | `b9177e1b045d2c8a801d1b23619abb4e5b29b88868fa491df7296dbc0b13447e` |
| [The Western Design Center, Inc., David Eyes and Ron Lichty, _Programming the 65816, including the 6502, 65C02 and 65802_](https://github.com/gilligan/snesdev/blob/master/docs/programming_the_65816.pdf) | 2007       |  469 | `dbccafcc47d6e53436bdc1c0049b3c54ffacfc9034a4041a7d92b6e6c5d72bb5` |

Ricoh 没有为 2A03 发布数据手册，因此由 MOS 的文档覆盖它所基于的内核。三个 W65C816S 修订版都没有提到 W65C802，因此由 65816 的文档覆盖其内核，而其封装没有文档。

测试套件来自 [SingleStepTests](https://github.com/SingleStepTests)，按提交固定在 [`conformance/suites.json`](conformance/suites.json) 中。发布者没有说明任何一个套件是由哪个实现生成的，因此它们的可信度排在制造商的说明之后。

## 引用本项目

[CITATION.cff](CITATION.cff) 会在每次发布时由标记包版本的脚本更新。

## 许可证

MIT。见 [LICENSE](LICENSE)。
