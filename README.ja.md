# MOS 65xx

65xxファミリの16品種をPythonで実装しています。MOS 6502からWDC W65C816Sまでを1バスサイクルずつ進め、SingleStepTestsのオペコードごとのスイートとメーカーのデータシートに照らして検証しています。

[English](README.md) | 日本語 | [简体中文](README.zh-Hans.md) | [繁體中文（香港）](README.zh-HK.md)

[![CI](https://github.com/gufranco/mos65xx-python/actions/workflows/ci.yml/badge.svg)](https://github.com/gufranco/mos65xx-python/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/gufranco/mos65xx-python)](https://github.com/gufranco/mos65xx-python/releases)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**16**品種、**17,900,000**件の状態ケースと**17,870,080**件のサイクル精度ケースを比較、説明のつかない失敗は**0**件、テスト**1,439**件、ステートメントとブランチのカバレッジ**100%**、依存関係なし

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

`$8000`のプログラムは`CLC`、`XCE`、`REP #$30`、`LDA #$1234`です。`reset()`は8サイクルかかり、`$FFFC`のベクタからプログラムカウンタを読み込みます。`CLC`と`XCE`でエミュレーションモードを抜け、`REP`でアキュムレータとインデックスレジスタを広げ、続くロードは16ビットのオペランドを取ります。各`step()`はその命令にかかったサイクル数を返します。4命令で10、品種の生成からは18です。

## インストール

| 要件 | バージョン |
|:--|:--|
| Python | 3.12以降 |
| git | 任意、クローン用 |

```bash
git clone https://github.com/gufranco/mos65xx-python.git
cd mos65xx-python
python3 mos65xx/doctor.py
```

このパッケージは標準ライブラリ以外を何もインポートしません。`pip install git+https://github.com/gufranco/mos65xx-python.git`でインストールすると、同じレポートを実行する`mos65xx-doctor`コマンドも入ります。

ドクターはマシンを確認し、すべての品種を生成してリセットし、どの適合性スイートが取得済みかを報告します。`-m`ではなくファイルとして実行するため、パッケージがインポートできない場合でも報告します。最後は1行で終わります。バグ報告には出力全体を貼り付けてください。

```
  26 checks, nothing to report
```

リリースは[Semantic Versioning](https://semver.org/)に従い、semantic-releaseがコミット履歴から作成します。すべてのリリースにはタグが付き、[リリースページ](https://github.com/gufranco/mos65xx-python/releases)に掲載されます。

## インターフェース

`Cpu(model, memory=None, fill=None, **options)`は電源が入りリセットされていない品種を1つ生成します。`model`は必須で、省略すると受け付けるすべての名前を添えて`UnknownModelError`を送出します。16の名前とその別名は[モデル](#models)にあります。名前の大文字小文字、`-`、`_`は無視されます。`memory`は`read8(address)`と`write8(address, value)`を持つ任意のオブジェクトです。指定しない場合は`SparseMemory`が使われ、`fill`を指定した場合は`fill`で埋めた16 MBの`Memory`が使われます。

| オプション | 品種 | 効果 |
|:--|:--|:--|
| `seed=` | すべて | 電源投入時にかき混ぜられるレジスタのシードです。デフォルトは`UNSET_SEED` |
| `decimal=` | 8ビット | 十進加算器が配線されているかどうかです。モデルが設定し、falseにするのは`2a03`だけです |
| `table=` | 8ビット | オペコード表です。モデルが設定します |

### 呼び出し

| 呼び出し | 効果 | 戻り値 |
|:--|:--|:--|
| `reset(seed=UNSET_SEED)` | RESETを駆動します。6サイクルの後、`$FFFC`のベクタを読むのに2サイクルです。W65C02Sは5と2です。`steps`をクリアし、割り込み禁止フラグをセットし、CMOS品種では十進フラグをクリアします。65816はさらに8ビットレジスタのエミュレーションモードに入り、`d`、`db`、`pb`を0にします | 品種 |
| `step()` | 1命令を実行し、その後割り込みラインをサンプリングします | 割り込みの受け付けを含むかかったサイクル数 |
| `run_for(cycles)` | 少なくとも`cycles`が経過するまで命令単位で実行します。停止した品種は`held_cycle()`の呼び出し1回につき1サイクルを使います | かかったサイクル数。`cycles`を超えることがあります |
| `run_until(check, limit=None)` | `check(part)`がfalseの間ステップを進めます。`limit`命令の後に`RunLimit`を送出します | 品種 |
| `call(address, limit=None)` | `address`にジャンプし、対応する`RTS`、65816では`RTL`が次に来るまでステップを進めます。ネストした呼び出しも数えます | 品種 |
| `held()` | 品種がジャム、停止、待機のいずれかの状態かどうか | `bool` |
| `held_cycle()` | 停止した品種の1サイクルです。ジャムしたNMOS品種は`$FFFF`を読みます。他の品種はバスアクセスなしで1サイクルを使います | なし |
| `irq()` | 割り込み禁止フラグがセットされていなければ、割り込み要求を即座に受け付けます | 受け付けた場合は`True` |
| `nmi()` | マスク不能割り込みを即座に受け付けます | 8ビット品種ではなし、65816では`True` |
| `abort()` | 65816のみです。アボートを即座に受け付けます | 受け付けた場合は`True` |
| `status()` | ステータスレジスタを1バイトで返します | `int` |
| `set_status(byte)` | 1バイトからすべてのフラグを設定します | なし |
| `set_emulation(flag)` | 65816のみです。エミュレーションモードに入るか抜けます。このモードではレジスタが8ビット、スタックがページ1に固定されます | なし |
| `read8(address)` / `write8(address, value)` | 品種のアドレスラインを通る1バスサイクルで、トレースされ数えられます | 読んだバイト、またはなし |
| `power_on(seed)` | 生成時と同じようにレジスタを再びかき混ぜます | なし |

パッケージがラインを外に出していない品種では、`irq()`と`nmi()`は`NoSuchPin`を送出します。65816と65802は3本のラインをすべて外に出しています。

### 状態

| 属性 | 意味 |
|:--|:--|
| `a`、`x`、`y`、`s`、`pc` | レジスタです。65816では`a`、`x`、`y`、`s`が16ビットを保持します |
| `db`、`pb`、`d` | 65816のみです。データバンク、プログラムバンク、ダイレクトページレジスタです |
| `n`、`v`、`z`、`c` | すべての品種で同じ意味を持つフラグで、それぞれ`bool`です |
| `i`、`d`、`b`、`decimal` | 8ビット品種です。割り込み禁止、十進フラグ、ブレークフラグ、十進加算器が配線されているかどうかです |
| `irq_disable`、`decimal`、`m8`、`x8`、`emulation` | 65816のみです。割り込み禁止、十進フラグ、8ビットアキュムレータ、8ビットインデックスレジスタ、エミュレーションモードです |
| `irq_line` | レベルとしての要求ラインです。各命令の後にサンプリングされるため、それより前に取り下げられた要求は受け付けられません |
| `nmi_line` | マスク不能ラインです。低から高への変化で1回割り込み、高のまま保っても再び割り込みません。NMOSの品種では、`BRK`の実行中、そのベクタを読む前に届いた変化は、WDCとRockwellが記載しているとおり`BRK`のベクタをNMIのベクタに置き換えます |
| `ready_line` | falseの間、読み出しはtrueに戻るまでサイクルを消費するため、ホストは`on_cycle`からこれをクリアします。CMOS品種と65816は書き込みも同じように保持し、NMOS品種は保持しません |
| `cycles` | 生成からのサイクル数です。リセットの分も加算されます |
| `steps` | 最後のリセットからの命令数です |
| `stopped`、`jammed`、`waiting` | 3つの停止状態です。`jammed`はNMOSのみ、`waiting`はCMOS品種と65816です |
| `trace` | リストを設定すると、すべてのバスサイクルが`(address, value, kind)`として追加されます。`kind`は8ビット品種では`read`または`write`、65816では8つのピン文字で、データ、プログラム、ベクタプル、書き込み、エミュレーション、`m`、`x`、メモリロックです。65816の内部サイクルは、エミュレーションモードの修正サイクルを除き値として`None`を記録し、停止中のサイクルは`(None, None, "--------")`を記録します |
| `on_cycle` | そのサイクルのバス動作の後、1サイクルにつき1回呼ばれます |
| `model` | 正規のモデル名です |
| `package_pins` | パッケージが外に出している割り込みラインとレディラインで、`("irq", "nmi", "rdy")`のような形です |
| `address_mask` | パッケージが外に出しているアドレスラインです。6507は`$1234`で`$F234`を読みます |
| `reset_cycles` | リセットにかかるサイクル数で、8または7です |
| `memory` | メモリオブジェクトです |
| `cycle_budget` | 65816のみです。設定すると、`MVN`と`MVP`はそのサイクル数に収まる分のバイトだけを移動します |

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

`$0200`の`CLI`は要求ラインが保持されたまま割り込み禁止フラグをクリアするため、同じステップで`$FFFE`を通じて割り込みを受け付けます。`CLI`に2サイクル、受け付けに7サイクルです。マスク不能ラインを上げると`$FFFA`を通じて1回割り込みます。3番目のステップは、ラインが高いままで`NOP`を実行します。

### エラー

| エラー | 送出される条件 |
|:--|:--|
| `UnknownModelError` | `Cpu()`に名前が渡されないか、どのモデルにも別名にも該当しない名前が渡された場合 |
| `NoSuchPin` | パッケージがそのラインを外に出していない8ビット品種で`irq()`または`nmi()`を呼んだ場合 |
| `RunLimit` | `run_until()`または`call()`が`limit`に達した場合 |
| `Stopped` | `STP`を実行した品種、またはジャムした品種で`step()`を呼んだ場合 |
| `Waiting` | `WAI`を実行した品種で`step()`を呼んだ場合。`Stopped`のサブクラスです。`irq()`と`nmi()`で解除されます |
| `ClockClosed` | 閉じた`Clock`で`tick()`を呼んだ場合 |
| `Truncated` | `decode()`が命令の終わりより前にバイトを使い切った場合 |
| `UnsupportedError` | オペコード表に、コアがハンドラを持たない命令またはアドレッシングモードが含まれる場合 |

### モジュールの内容

| 名前 | 内容 |
|:--|:--|
| `MODELS` | 正規名をキーとする16の`Model`レコードです |
| `Model` | `name`、`summary`、`address_bits`、`data_bits`、`decimal`、`pins`、`reset_cycles`、`aliases`、`narrows`、`revision`、`address_mask`、および`build(memory, **options)`です |
| `Clock(cpu)` | 品種を1サイクルずつ実行します。[1サイクルずつ駆動する](#driving-it-one-cycle-at-a-time)を参照してください |
| `Memory(size=0x1000000, image=None, seed=UNSET_SEED, fill=None)` | フラットなバイト配列で、`seed`からかき混ぜ、`fill`で埋め、その上に`image`を重ねます。バイト列は`data`です |
| `SparseMemory(seed=UNSET_SEED)` | 書き込まれたものだけを保存する24ビットのアドレス空間です。書き込まれたバイトは`cells`です |
| `scramble(size, seed=UNSET_SEED)` | 両方のメモリとすべての品種の初期状態となる、かき混ぜられた`bytearray`です |
| `UNSET_SEED` | デフォルトのシード`0x5A5A5A5A`です |
| `Cpu65816(memory, seed=UNSET_SEED)` | 型チェック用の65816コアクラスです |
| `OPCODES`、`MODE_SIZE`、`FLAG_DEPENDENT` | `(mnemonic, mode)`の組による65816のオペコード表、モードごとのオペランドのバイト数、幅が`m`または`x`に従う2つのモードです |
| `decode(data, offset=0, address=0, m=True, x=True)` | 65816の`Instruction`を1つ返します。`address`、`offset`、`opcode`、`mnemonic`、`mode`、`operand`、`size`、`text`を持ちます |
| `disassemble(data, offset=0, address=0, count=None, m=True, x=True, stop_at_return=False)` | `REP`と`SEP`を追跡する65816命令のリストです。最後の完全な命令で止まります |
| `operand_size(mode, m, x)`、`branch_target(address, size, operand, width)`、`render(mode, operand, address, size, width)`、`apply_flags(instruction, m, x)` | `decode`と`disassemble`を構成する各段階です |
| `FLAG_C`、`FLAG_Z`、`FLAG_I`、`FLAG_D`、`FLAG_X`、`FLAG_M`、`FLAG_V`、`FLAG_N` | 65816のステータスビットで、`0x01`から`0x80`です |
| `__version__` | インストールされているバージョンです |

8ビットのオペコード表は2つのモジュールにあります。`mos65xx.opcodes6502`には`NMOS`、`decode(data, offset, address, table=NMOS)`、`disassemble(data, offset, address, count=None, table=NMOS, stop_at_return=False)`があり、後者は`undocumented`と`unstable`のプロパティを持つ命令を返します。`mos65xx.opcodes65c02.TABLES`は`65c02`、`rockwell`、`wdc`の表を保持します。

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

### コマンドラインツール

| コマンド | 引数 | 終了コード |
|:--|:--|:--|
| `python3 mos65xx/doctor.py` | なし | すべてのチェックに合格すれば0、それ以外は1 |
| `python3 -m conformance.fetch` | `[directory] [--latest]`。デフォルトは`~/.cache/conformance-suites`。`--latest`は固定版の代わりに各上流の最新を取得します。既存のコピーは固定版へ移し、固定版で終わらないコピーは実行を止めます | 0、または上流に到達できない場合は1 |
| `python3 -m conformance.singlestep` | `<suite directory> [tests per file] [filter] [--model name]`。デフォルトのモデルは`65816` | すべてのケースが一致するかスイートがなければ0、不一致があれば1、引数が不正なら2 |
| `python3 -m conformance.cycles` | `singlestep`と同じ | `singlestep`と同じ |
| `python3 -m conformance.documents` | `[--check] [--only substring]` | すべてのダイジェストが一致すれば0、1つでも拒否されるか引数が不正なら1 |
| `python3 -m conformance.quotes` | なし | すべての引用が文書内に見つかるか文書がなければ0、それ以外は1 |
| `python3 -m conformance.speed` | `[--instructions N] [--repeats N]`。デフォルトは200,000と7 | 下限の毎秒700,000サイクルを上回れば0、下回れば1、引数が不正なら2 |
| `python3 -m conformance.netlist` | なし。`NETLIST`変数を読みます | すべてのケースが一致するかシミュレーションが設定されていなければ0、それ以外は1 |
| `python3 -m conformance.links` | なし | 0、または引用したアドレスが404か410を返した場合は1 |
| `python3 -m conformance.watch` | `[definition] [--moved]` | 0、または定義が読めないか食い違う場合は1 |
| `python3 -m conformance.package` | `<wheel>` | すべてのモジュールがwheelに含まれテストが含まれていなければ0、それ以外は1、引数がなければ2 |

## 実速度で動かす

`step()`と`run_for()`はかかったサイクル数を報告するため、ホストは品種を水晶の速度に合わせられます。Ricoh 2A03は1,789,773 Hzで動作します。

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

`NOP`で埋めたメモリは1命令あたり2サイクルで動き、35,795サイクルのスライスは奇数です。`run_for()`は命令を途中で切れないため、1サイクル超過します。その差を次のスライスに持ち越すことで、合計はクロックとの差1サイクル以内に収まります。停止した品種も与えられたサイクルをすべて消費します。ジャムしたNMOS品種は`$FFFF`を読み続け、`STP`や`WAI`の後の65816はアドレスのないサイクルを生成します。

<a id="driving-it-one-cycle-at-a-time"></a>

## 1サイクルずつ駆動する

`Clock(cpu)`は任意の2サイクルの間で品種を止めます。ボードはそこで、後の読み出しが返す値を変更します。

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

`$0010`のバイトが変わったとき、`LDA $10`はすでにオペコードとオペランドをフェッチしており、3番目のサイクルで新しい値を読みました。

| 呼び出し | 効果 |
|:--|:--|
| `tick()` | 品種を次のサイクルの終わりまで実行し、クロックのサイクル数を返します |
| `run_for(cycles)` | `cycles`回のティックです。クロックのサイクル数を返します |
| `close()` | ワーカースレッドを止め、品種の`on_cycle`を元に戻します |
| `cycles`、`closed`、`cpu` | これまでのティック数、閉じているかどうか、駆動している品種です |

`Clock`はコンテキストマネージャであり、1ティックずつ返すイテレータでもあります。停止した品種は`held_cycle()`を通じてティックを続けます。Pythonはコールスタックを中断できないため、クロックは品種をワーカースレッドで実行し、毎サイクル2つのセマフォで制御を受け渡します。スループットには`step()`を、何がどのサイクルで起きるかが問題のときは`Clock`を使ってください。

<a id="models"></a>

## モデル

モデルはアドレスライン、割り込みライン、十進加算器、命令セットを決めます。

| 生成方法 | アドレスビット | ピン | 十進 | 品種 | 別名 |
|:--|:--:|:--|:--:|:--|:--|
| `Cpu("6502")` | 16 | IRQ, NMI, RDY | あり | MOS 6502 | `mos6502`, `nmos6502`, `6510`, `8500` |
| `Cpu("6503")` | 12 | IRQ, NMI | あり | MOS 6503 | `mos6503` |
| `Cpu("6504")` | 13 | IRQ | あり | MOS 6504 | `mos6504` |
| `Cpu("6505")` | 12 | IRQ, RDY | あり | MOS 6505 | `mos6505` |
| `Cpu("6506")` | 12 | IRQ | あり | MOS 6506、RDYの代わりに2つ目のクロック出力を持つ | `mos6506` |
| `Cpu("6507")` | 13 | RDY | あり | MOS 6507 | `mos6507` |
| `Cpu("6512")` | 16 | IRQ, NMI, RDY | あり | MOS 6512、外部2相クロックで動く6502 | `mos6512` |
| `Cpu("6513")` | 12 | IRQ, NMI | あり | MOS 6513、外部クロックで動く6503 | `mos6513` |
| `Cpu("6514")` | 13 | IRQ | あり | MOS 6514、外部クロックで動く6504 | `mos6514` |
| `Cpu("6515")` | 12 | IRQ, RDY | あり | MOS 6515、外部クロックで動く6505 | `mos6515` |
| `Cpu("2a03")` | 16 | IRQ, NMI, RDY | なし | Ricoh 2A03と2A07 | `ricoh2a03`, `2a07`, `ricoh2a07`, `nes6502`, `famicom` |
| `Cpu("65c02")` | 16 | IRQ, NMI, RDY | あり | 基本のCMOS設計 | `synertek65c02`, `s65c02`, `cmos6502` |
| `Cpu("r65c02")` | 16 | IRQ, NMI, RDY | あり | Rockwell R65C02、32個のシングルビット命令を追加 | `rockwell65c02`, `rockwell` |
| `Cpu("w65c02")` | 16 | IRQ, NMI, RDY | あり | WDC W65C02S、`STP`と`WAI`を追加 | `wdc65c02`, `w65c02s` |
| `Cpu("65802")` | 16 | IRQ, NMI, RDY | あり | WDC W65C802、16本のアドレスラインを持つ65816コア | `w65c802`, `65c802` |
| `Cpu("65816")` | 24 | IRQ, NMI, RDY | あり | WDC W65C816S | `w65c816`, `w65c816s`, `65c816`, `65816s` |

11のNMOSモデルは1つのコアを共有し、3つの65C02モデルは2つ目のコアを、65816と65802は3つ目のコアを共有します。狭いパッケージは届く範囲も狭くなります。65802は`$0012`で`$7E0012`を読み、6507は`$1234`で`$F234`を読みます。2A03では十進フラグはセットできますが、何も変わりません。

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

256個のオペコードはすべての8ビット品種で動作します。MOSが文書化したのはそのうち151個です。残りの105個はスイートが記録したとおりに動作し、`JAM`も含まれます。[`conformance/instruction-set.json`](conformance/instruction-set.json)はAppendix Bに印刷されたとおりの文書化された区分を保持しています。

## 実行せずに読む

`disassemble()`は、実行する品種なしでバイト列を読みます。

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

65816では、即値オペランドの幅はそれ以前にセットされたフラグに依存します。`disassemble`は`m`と`x`がセットされた状態から始まり、すべての`REP`と`SEP`を追跡するため、`REP #$30`の後のロードは2バイトのオペランドを取ります。同じ8ビットのバイト列は、NMOS品種では文書化されていない`SAX`として、W65C02Sでは`BBS0`としてデコードされます。

## 何もきれいな状態では始まらない

レジスタとメモリは電源投入時に再現可能なかき混ぜられたパターンを保持するため、何も書き込んでいないバイトを読むプログラムはゼロでないバイトを得ます。レジスタをクリアするオプションはありません。メモリは`fill`を指定して生成した場合にのみクリアされます。

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

`SparseMemory`は書き込まれていないバイトをアドレスとシードから導出するため、12バイトに触れるテストは12バイトだけを保存します。両方のメモリとすべての品種が`seed`を受け取るため、別の実装と比べる実行は正確に繰り返せます。`Memory`は`image`を受け取ります。これは電源投入時にボードが保持している内容です。

## 正しいのか

各コアは、その品種について記録されたSingleStepTestsスイートと比較されます。65816、6502、nes6502、synertek65c02、rockwell65c02、wdc65c02の6つのスイートにわたり、オペコードごとに10,000ケースです。状態の比較では、レジスタ、フラグ、各ケースが触れたメモリのすべてのバイトを確認します。結果は**17,900,000ケース、説明のつかない失敗なし**です。サイクルの比較では、すべてのバスサイクルを順番に、アドレスごとに、読み出しと書き込みの区別まで確認し、65816では8本のピンも確認します。結果は**17,870,080ケース、説明のつかない失敗なし**です。

```bash
python3 -m conformance.fetch ~/.cache/conformance-suites
python3 -m conformance.singlestep ~/.cache/conformance-suites/6502/6502/v1 --model 6502
python3 -m conformance.cycles ~/.cache/conformance-suites/6502/6502/v1 --model 6502
```

どちらの合計も[`conformance/suites.json`](conformance/suites.json)から導出され、テストがこのページをその値に保っています。wdc65c02スイートは`WAI`と`STP`のファイルを空で配布しています。サイクルの合計からは、追加のサイクルがどのレジスタも生成しない一定のアドレスで記録されている29,920件のCMOS十進ケースを除いています。このコアがスイートではなくデータシートに従う箇所について、どちらのランナーも別扱いにした65816のケースの件数を表示します。条件によって除くのは38ケースで、エミュレーションのスタックポインタがページ1の先頭にあるときの1バイトのプルが37ケース、整列したダイレクトページの末尾から始まる`(d,x)`のポインタが1ケースです。残りは2つの読み方が食い違う部分以外をすべて比較します。エミュレーションの`BRK`と`COP`の19,924ケースではデータバンクレジスタ、スタックポインタがページ1の末尾にある`JSR (a,x)`の43ケースではスタックへの書き込み1回のアドレスです。

[`conformance/hardware.json`](conformance/hardware.json)はメーカーのページから取ったすべての事実を、出典の文とページとともに保持しており、テストがコードをそれらに合わせています。[`conformance/addressing-cycles.json`](conformance/addressing-cycles.json)と[`conformance/instruction-set.json`](conformance/instruction-set.json)は、ハードウェアマニュアルのAppendix AとプログラミングマニュアルのAppendix Bを印刷されたとおりに保持しています。[`conformance/divergences.json`](conformance/divergences.json)は2つの出典が食い違う20か所について、このパッケージがどちらに従うか、それぞれ何があれば決着するかを記録しています。`python3 -m conformance.quotes`は引用したすべての文をその文書内で見つけます。

スイートはコミットで固定されています。週次のジョブが各上流の最新でスイートを実行し、新しいスイートが合格すればプルリクエストを、失敗すればissueを開きます。[OPEN-QUESTIONS.md](OPEN-QUESTIONS.md)には、文書とスイートでは決着しない17の問いを、それを解決する実機での測定とともに挙げています。

## 開発に参加する

| 必要なもの | 場所 |
|:--|:--|
| すべてのゲートと実行順序 | [CONTRIBUTING.md](CONTRIBUTING.md) |
| コーディングエージェント向けの同じ内容 | [AGENTS.md](AGENTS.md) |
| このリポジトリがファミリの他のリポジトリと共有する基準 | [FAMILY.md](FAMILY.md) |
| バグ報告 | [GitHub Issues](https://github.com/gufranco/mos65xx-python/issues) |
| セキュリティ報告 | [SECURITY.md](SECURITY.md) |

```bash
uvx ruff@0.16.3 format --check .
uvx ruff@0.16.3 check .
uvx --python 3.12 mypy==1.14.1
python3 mos65xx/mos6502.test.py
```

各モジュールには、その名前を付けたテストファイルが隣にあり、上のようにそれぞれ単独で実行できます。カバレッジはステートメントとブランチで100%の厳格なゲートです。

## 参考文献

以下の文書はすべて発行元が著作権を持ち、どれもこのリポジトリには含まれていません。[`conformance/documents.json`](conformance/documents.json)はそれぞれの完全なSHA-256、バイト数、アドレスを保持しています。`python3 -m conformance.documents`は12点すべてをgitが無視する`docs/`にダウンロードし、ダイジェストが一致しないファイルは拒否します。`--check`はすでにあるものを検証します。

| 文書 | 日付 | ページ数 | SHA-256 |
|:--|:--|--:|:--|
| [MOS Technology, Inc., *MCS6500 Microcomputer Family Hardware Manual*](https://archive.org/download/mcs-6500-family-hardware-manual-1976-01/MCS6500_family_hardware_manual_1976-01.pdf) | 1976-01 | 182 | `81ea570c9d68deff64d67365bdf24534df93a8c62121e53036aeac6a557cea23` |
| [MOS Technology, Inc., *MCS6500 Microcomputer Family Programming Manual*](https://archive.org/download/6500-50A_MCS6500_Programming_Manual_1976_Jan/6500-50A_MCS6500_Programming_Manual_1976_Jan.pdf) | 1976-01 | 262 | `a2d54dd8b6557c7f2f275b4ddaa9180b5754274a762df122d79392f03264b483` |
| [MOS Technology, Inc., *MOS 6500 Microprocessors*](https://6502.org/documents/datasheets/mos/mos_6500_mpu_nov_1985.pdf) | 1985-11 | 12 | `ccd72376d1e5db1fb13777de538417f4799ab38e1f746452f9695465c422dcd7` |
| [MOS Technology, Inc., *MOS 6500 Microprocessors*](https://6502.org/documents/datasheets/mos/mos_6500_mpu_mar_1980.pdf) | 1980-03 | 12 | `a564c4de593ea178868a43eaf7e00fe7d3460016d2a7880d20eb756f2bf2d030` |
| [Synertek, Inc., *SY6500 Microprocessors*](https://6502.org/documents/datasheets/synertek/synertek_sy6500_microprocessors.pdf) | 日付なし | 6 | `f20b50961df60bb0e1980f271ad49b4b788c46a143127ccc58e8d3ce84d99193` |
| [Synertek, Inc., *SY6500 Hardware Manual*](https://6502.org/documents/datasheets/synertek/synertek_hardware_manual.pdf) | 日付なし | 178 | `9cd0991dcbb4a46bf63747528282ad175ed15e1957d08bd755ef14b978b67a1c` |
| [Rockwell International, *R65C00 Microprocessors: R65C02, R65C102 and R65C112*](https://6502.org/documents/datasheets/rockwell/rockwell_r65c00_microprocessors.pdf) | 1987-06 | 16 | `63deee76c8d0d4faee7bb8f9c50ff21662c73f2e82093ebacfb284f527faf134` |
| [The Western Design Center, Inc., *W65C02S 8-bit Microprocessor Data Sheet*](https://westerndesigncenter.com/wdc/documentation/w65c02s.pdf) | 2022-04-08 | 32 | `a6af3ca9da45c8a03504c94c7399cb6b08f15ce14185dd3e1e880433cdaa8cf5` |
| [The Western Design Center, Inc., *W65C816S 8/16-bit Microprocessor Data Sheet*](https://datasheets.chipdb.org/Western%20Design/w65c816s.pdf) | 2004-06-14 | 62 | `60f21a3da0331273c6b92963ba7660408ab1ba3cf9dca2e37b1e55e7950ff313` |
| [The Western Design Center, Inc., *W65C816S 8/16-bit Microprocessor Data Sheet*](https://6502.org/documents/datasheets/wdc/wdc_w65c816s_jul_1994.pdf) | 1994-07 | 72 | `823c2f286a97102fc3695596f7c03e26e2f01cff0f45023dc3bb71688e689bc7` |
| [The Western Design Center, Inc., *W65C816S Datasheet*](https://westerndesigncenter.com/wdc/documentation/w65c816s.pdf) | 2024-03-13 | 55 | `b9177e1b045d2c8a801d1b23619abb4e5b29b88868fa491df7296dbc0b13447e` |
| [The Western Design Center, Inc., David Eyes and Ron Lichty, *Programming the 65816, including the 6502, 65C02 and 65802*](https://github.com/gilligan/snesdev/blob/master/docs/programming_the_65816.pdf) | 2007 | 469 | `dbccafcc47d6e53436bdc1c0049b3c54ffacfc9034a4041a7d92b6e6c5d72bb5` |

Ricohは2A03のデータシートを公開していないため、そのもとになったコアはMOSの文書が扱っています。W65C816Sの3つの版はどれもW65C802に触れていないため、そのコアは65816の文書が扱い、パッケージは文書化されていません。

スイートは[SingleStepTests](https://github.com/SingleStepTests)のもので、[`conformance/suites.json`](conformance/suites.json)でコミットにより固定されています。発行元はどのスイートについても生成に使った実装を示していないため、メーカーの記述より下位に位置付けています。

## 引用

[CITATION.cff](CITATION.cff)は、パッケージのバージョンを記入するスクリプトによってリリースごとに更新されます。

## ライセンス

MIT。[LICENSE](LICENSE)を参照してください。
