# AutoCut: 通过字幕来剪切视频

AutoCut 对你的视频自动生成字幕。然后你选择需要保留的句子，AutoCut 将对你视频中对应的片段裁切并保存。你无需使用视频编辑软件，只需要编辑文本文件即可完成剪切。

**2024.10.05更新**：支持 `large-v3-turbo` [模型](https://github.com/openai/whisper/discussions/2363)，提供更快的转录速度。

```shell
autocut -t xxx --whisper-model large-v3-turbo
````

**2024.03.10更新**：支持 pip 安装和提供 import 转录相关的功能

```shell
# Install
pip install autocut-sub
```

```python
from autocut import Transcribe, load_audio
```


**2023.10.14更新**：支持 faster-whisper 和指定依赖（但由于 Action 限制暂时移除了 faster-whisper 的测试运行）

```shell
# for whisper only
python -m pip install -e .

# for whisper and faster-whisper
python -m pip install -e ".[faster]"

# for whisper and OpenAI API
python -m pip install -e ".[openai]"

# for all optional dependencies
python -m pip install -e ".[all]"
```

```shell
# using faster-whisper
autocut -t xxx --whisper-mode=faster
```

```shell
# using openai api
export OPENAI_API_KEY=sk-xxx
autocut -t xxx --whisper-mode=openai --openai-rpm=3
```

**2023.8.13更新**：支持调用 Openai Whisper API
```shell
export OPENAI_API_KEY=sk-xxx
autocut -t xxx --whisper-mode=openai --openai-rpm=3
```

## 使用例子

假如你录制的视频放在 `2022-11-04/` 这个文件夹里。那么运行

```bash
autocut -d 2022-11-04
```

> 提示：如果你使用 OBS 录屏，可以在 `设置->高级->录像->文件名格式` 中将空格改成 `/`，即 `%CCYY-%MM-%DD/%hh-%mm-%ss`。那么视频文件将放在日期命名的文件夹里。

AutoCut 将持续对这个文件夹里视频进行字幕抽取和剪切。例如，你刚完成一个视频录制，保存在 `11-28-18.mp4`。AutoCut 将生成 `11-28-18.md`。你在里面选择需要保留的句子后，AutoCut 将剪切出 `11-28-18_cut.mp4`，并生成 `11-28-18_cut.md` 来预览结果。

你可以使用任何的 Markdown 编辑器。例如我常用 VS Code 和 Typora。下图是通过 Typora 来对 `11-28-18.md` 编辑。

![](imgs/typora.jpg)

全部完成后在 `autocut.md` 里选择需要拼接的视频后，AutoCut 将输出 `autocut_merged.mp4` 和对应的字幕文件。

## 安装

首先安装 Python 包。项目没有单独的 `requirements.txt`，运行下面的命令会根据 `setup.py` 自动安装运行所需依赖。

```
python -m pip install git+https://github.com/mli/autocut.git
```

## 本地安装测试


```
git clone https://github.com/mli/autocut
cd autocut
python -m pip install -e .
```

如果需要额外安装 faster-whisper 或 OpenAI API 支持，可以使用：

```
python -m pip install -e ".[faster]"
python -m pip install -e ".[openai]"
python -m pip install -e ".[all]"
```


> 上面将安装 [pytorch](https://pytorch.org/)。如果你需要 GPU 运行，且默认安装的版本不匹配的话，你可以先安装 Pytorch。如果安装 Whipser 出现问题，请参考[官方文档](https://github.com/openai/whisper#setup)。

另外需要安装 [ffmpeg](https://ffmpeg.org/)

```
# on Ubuntu or Debian
sudo apt update && sudo apt install ffmpeg

# on Arch Linux
sudo pacman -S ffmpeg

# on MacOS using Homebrew (https://brew.sh/)
brew install ffmpeg

# on Windows using Scoop (https://scoop.sh/)
scoop install ffmpeg
```


## 更多使用选项

### 转录某个视频生成 `.srt` 和 `.md` 结果。

```bash
autocut -t 22-52-00.mp4
```

也可以传入文件夹，批量转写该目录当前层的所有视频和音频文件（不递归子目录），输出到各媒体文件所在目录：

```bash
autocut -t ./videos
```

也可以用 `-o` 指定 `.srt` 和 `.md` 的输出目录：

```bash
autocut -t 22-52-00.mp4 -o ./output
```

`-t` 会根据输入文件名或路径自动选择部分转录参数组。目前内置了 `default`、`baduanjin` 和 `taiji` 三组，用来调整 VAD 语音片段切分参数。没有匹配到特定关键词时使用默认参数。

| 参数组 | 自动匹配关键词 | `remove_short_segments` | `expand_segments` | `merge_adjacent_segments` |
|---|---|---:|---:|---:|
| `default` | 未命中特定关键词 | `1.0` | `(0.2, 0.0)` | `0.5` |
| `baduanjin` | `八段锦`、`八段錦`、`baduanjin`、`ba duan jin`、`bdj` | `0.3` | `(0.2, 0.1)` | `0.7` |
| `taiji` | `太极拳`、`太極拳`、`太极`、`太極`、`taiji`、`taijiquan` | `0.2` | `(0.2, 0.1)` | `0.5` |

例如输入路径中包含 `八段锦` 时会自动使用八段锦参数：

```bash
autocut -t ./videos/八段锦
```

也可以通过命令行显式指定参数组。显式参数优先级高于文件名或路径自动匹配：

```bash
autocut -t ./videos/class01.mp4 --baduanjin
autocut -t ./videos/class02.mp4 --taiji
autocut -t ./videos/class02.mp4 --taiji24
```

`--baduanjin` 和 `--taiji` / `--taiji24` 不能同时使用。后续如果需要支持其他输入类型，可以在 `autocut/transcribe.py` 中追加新的 `TranscribeProfile`，或通过 `register_transcribe_profile(...)` 注册新的参数组。

1. 如果对转录质量不满意，可以使用更大的模型，例如

    ```bash
    autocut -t 22-52-00.mp4 --whisper-model large
    ```

    默认是 `small`。更好的模型是 `medium` 和 `large`，但推荐使用 GPU 获得更好的速度。也可以使用更快的 `tiny` 和 `base`，但转录质量会下降。


### 清理 `<No Speech>` 字幕块

如果转录结果里包含 `<No Speech>` 或 `No Speech` 字幕块，可以用 `cleanSrt.py` 重新编号并生成清理后的 `.srt` 文件。

清理单个字幕文件：

```bash
python cleanSrt.py 22-52-00.srt
```

默认输出到原字幕同目录，文件名追加 `_cleaned`：

```text
22-52-00_cleaned.srt
```

也可以传入目录，批量清理该目录当前层的 `.srt` 文件，不递归子目录，并跳过已经以 `_cleaned.srt` 结尾的文件：

```bash
python cleanSrt.py ./videos
```

`cleanSrt.py` 支持清理非当前目录下的文件或目录，但当前不支持指定单独的输出目录；清理后的文件始终写在输入 `.srt` 所在目录。


### 剪切某个视频

```bash
autocut -c 22-52-00.mp4 22-52-00.srt 22-52-00.md
```

1. 默认视频比特率是 `--bitrate 10m`，你可以根据需要调大调小。
2. 如果不习惯 Markdown 格式文件，你也可以直接在 `srt` 文件里删除不要的句子，在剪切时不传入 `md` 文件名即可。就是 `autocut -c 22-52-00.mp4 22-52-00.srt`
3. 如果字幕文件和视频同名，或者是常见的人声字幕命名（例如 `test3_vocals_cleaned.srt`、`test3_vocals.srt`），可以只传视频文件，AutoCut 会在视频所在目录和当前目录中自动匹配字幕文件：

   ```bash
   autocut -c vocal_extractor/videos/test3.mp4 -o test/test3_name --cut-by-start --force
   ```

   也可以传入视频目录，批量切割该目录当前层的所有视频和音频文件（不递归子目录）。指定 `-o` 时，每个视频会输出到独立子目录，例如 `test/test3_name`：

   ```bash
   autocut -c vocal_extractor/videos -o test --cut-by-start --force
   ```

4. 如果仅有 `srt` 文件，编辑不方便可以使用如下命令生成 `md` 文件，然后编辑 `md` 文件即可，但此时会完全对照 `srt` 生成，不会出现 `no speech` 等提示文本。

   ```bash
   autocut -m test.srt test.mp4
   autocut -m test.mp4 test.srt # 支持视频和字幕乱序传入
   autocut -m test.srt # 也可以只传入字幕文件
   ```

### 八段锦片段打标

如果已经使用 `[原视频名]_字幕序号_[前5个字].mp4` 命名规则切好了八段锦视频片段，可以先生成一个可人工复核的 CSV，再按标签复制到分类文件夹：

```bash
python -m autocut.baduanjin_label ./test/test6_name
```

如果是在源码目录中临时使用，且当前 Python 环境还没有安装完整的 AutoCut 视频依赖，也可以直接运行脚本文件：

```bash
python autocut/baduanjin_label.py ./test/test6_name
```

默认输出：

```text
./test/test6_name_labels.csv
./test/test6_name_labeled/
```

CSV 字段包含 `filename`、`source_video`、`segment_index`、`text_hint`、`big_label`、`action_label`、`confidence`、`review` 和 `notes`。工具会结合文件名文字线索和片段顺序做弱自动标注，不能确定的片段会标记 `review=yes`，便于后续人工修正。

打标规则使用五层逻辑：标准强锚点、核心中等锚点、常见错词、动作过程弱线索和通用呼吸词黑名单。强/中/错词规则还会尝试基于 `jieba` 分词和 `pypinyin` 的无声调拼音匹配，以提高 `拖天/托天`、`开工/开弓` 这类同音错词的召回率；如果运行环境缺少这些库，会降级使用内置的常用字拼音表。每个动作边界前后附近的片段会自动标记为需要复核，避免跨动作片段直接进入训练集。片段文件名中的原视频名如果包含空格，后续新切片会折叠为下划线，已有片段在 CSV 和 JSON manifest 的 `source_video` 字段中也会统一规整。

人工修改 CSV 后，再次运行同一命令会优先读取已有 CSV 并继续复制分类文件夹，不会覆盖 CSV。若希望按修改后的 CSV 重建分类目录并清掉旧位置的复制件，使用：

```bash
python -m autocut.baduanjin_label ./test/test6_name --clean-output
```

需要重新自动生成标签时使用：

```bash
python -m autocut.baduanjin_label ./test/test6_name --force
```

默认是复制视频，不会移动原始片段；如只想生成 CSV 不复制文件夹：

```bash
python -m autocut.baduanjin_label ./test/test6_name --no-copy
```

### 24式太极拳片段打标

24式简化太极拳也支持同样的片段命名规则和 CSV 复核流程，标签粒度是 24 个正式动作：

```bash
python -m autocut.taiji24_label ./test/taiji24_name
```

默认输出：

```text
./test/taiji24_name_labels.csv
./test/taiji24_name_labeled/
```

CSV 字段和八段锦一致。`起势`、`收势` 会归入 `action`，开头寒暄/课程介绍归入 `irrelevant/opening`，完整收势后的感谢、关注、下次见等归入 `irrelevant/closing`。重复动作（例如两次 `单鞭`）会结合文本线索和动作顺序推断，边界附近或置信度不足的片段仍会标记 `review=yes` 方便人工复核。

常用参数也和八段锦一致：

```bash
python -m autocut.taiji24_label ./test/taiji24_name --clean-output
python -m autocut.taiji24_label ./test/taiji24_name --force
python -m autocut.taiji24_label ./test/taiji24_name --no-copy
```


### 一些小提示


1. 讲得流利的视频的转录质量会高一些，这因为是 Whisper 训练数据分布的缘故。对一个视频，你可以先粗选一下句子，然后在剪出来的视频上再剪一次。
2. 最终视频生成的字幕通常还需要做一些小编辑。但 `srt` 里面空行太多。你可以使用 `autocut -s 22-52-00.srt` 来生成一个紧凑些的版本 `22-52-00_compact.srt` 方便编辑（这个格式不合法，但编辑器，例如 VS Code，还是会进行语法高亮）。编辑完成后，`autocut -s 22-52-00_compact.srt` 转回正常格式。
3. 用 Typora 和 VS Code 编辑 Markdown 都很方便。他们都有对应的快捷键 mark 一行或者多行。但 VS Code 视频预览似乎有点问题。
4. 视频是通过 ffmpeg 导出。在 Apple M1 芯片上它用不了 GPU，导致导出速度不如专业视频软件。

### 常见问题

1. **输出的是乱码？**

   AutoCut 默认输出编码是 `utf-8`. 确保你的编辑器也使用了 `utf-8` 解码。你可以通过 `--encoding` 指定其他编码格式。但是需要注意生成字幕文件和使用字幕文件剪辑时的编码格式需要一致。例如使用 `gbk`。

    ```bash
    autocut -t test.mp4 --encoding=gbk
    autocut -c test.mp4 test.srt test.md --encoding=gbk
    ```

    如果使用了其他编码格式（如 `gbk` 等）生成 `md` 文件并用 Typora 打开后，该文件可能会被 Typora 自动转码为其他编码格式，此时再通过生成时指定的编码格式进行剪辑时可能会出现编码不支持等报错。因此可以在使用 Typora 编辑后再通过 VSCode 等修改到你需要的编码格式进行保存后再使用剪辑功能。

2. **如何使用 GPU 来转录？**

   当你有 Nvidia GPU，而且安装了对应版本的 PyTorch 的时候，转录是在 GPU 上进行。你可以通过命令来查看当前是不是支持 GPU。

   ```bash
   python -c "import torch; print(torch.cuda.is_available())"
   ```

   否则你可以在安装 AutoCut 前手动安装对应的 GPU 版本 PyTorch。

3. **使用 GPU 时报错显存不够。**

   whisper 的大模型需要一定的 GPU 显存。如果你的显存不够，你可以用小一点的模型，例如 `small`。如果你仍然想用大模型，可以通过 `--device` 来强制使用 CPU。例如

   ```bash
   autocut -t 11-28-18.mp4 --whisper-model large --device cpu
   ```

4. **能不能使用 `pip` 安装?**

    whisper已经发布到PyPI了，可以直接用`pip install openai-whisper`安装。
   
   [https://github.com/openai/whisper#setup](https://github.com/openai/whisper#setup)

   [https://pypi.org/project/openai-whisper/](https://pypi.org/project/openai-whisper/)

## 如何参与贡献

[这里有一些想做的 feature](https://github.com/mli/autocut/issues/22)，欢迎贡献。

### 代码结构
```text
autocut
│  .gitignore
│  LICENSE
│  README.md # 一般新增或修改需要让使用者知道就需要对应更新 README.md 内容
│  setup.py
│
└─autocut # 核心代码位于 autocut 文件夹中，新增功能的实现也一般在这里面进行修改或新增
   │  cut.py
   │  daemon.py
   │  main.py
   │  transcribe.py
   │  utils.py
   └─ __init__.py

```

### 安装依赖
开始安装这个项目的需要的依赖之前，建议先了解一下 Anaconda 或者 venv 的虚拟环境使用，推荐**使用虚拟环境来搭建该项目的开发环境**。
具体安装方式为在你搭建的虚拟环境之中按照[本地安装测试](./README.md#本地安装测试)进行安装。这个项目通过 `setup.py` 声明依赖，不需要 `pip install -r requirements.txt`。

> 为什么推荐使用虚拟环境开发？
>
> 一方面是保证各种不同的开发环境之间互相不污染。
>
> 更重要的是在于这个项目实际上是一个 Python Package，所以在你安装之后 AutoCut 的代码实际也会变成你的环境依赖。
> **因此在你更新代码之后，你需要让将新代码重新安装到环境中，然后才能调用到新的代码。**

### 开发

1. 代码风格目前遵循 PEP-8，可以使用相关的自动格式化软件完成。
2. `utils.py` 主要是全局共用的一些工具方法。
3. `transcribe.py` 是调用模型生成`srt`和`md`的部分。
4. `cut.py` 提供根据标记后`md`或`srt`进行视频剪切合并的功能。
5. `daemon.py` 提供的是监听文件夹生成字幕和剪切视频的功能。
6. `main.py` 声明命令行参数，根据输入参数调用对应功能。

开发过程中请尽量保证修改在正确的地方，以及合理地复用代码，
同时工具函数请尽可能放在`utils.py`中。
代码格式目前是遵循 PEP-8，变量命名尽量语义化即可。

在开发完成之后，最重要的一点是需要进行**测试**，请保证提交之前对所有**与你修改直接相关的部分**以及**你修改会影响到的部分**都进行了测试，并保证功能的正常。
目前使用 `GitHub Actions` CI, Lint 使用 black 提交前请运行 `black`。

### 提交

1. commit 信息用英文描述清楚你做了哪些修改即可，小写字母开头。
2. 最好可以保证一次的 commit 涉及的修改比较小，可以简短地描述清楚，这样也方便之后有修改时的查找。
3. PR 的时候 title 简述有哪些修改， contents 可以具体写下修改内容。
4. run test `python -m pip install pytest` then `python -m pytest test`
5. run lint `python -m pip install black` then `python -m black .`
