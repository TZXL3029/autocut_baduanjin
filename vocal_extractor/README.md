把视频放到 `videos` 文件夹下，然后运行：

```bash
python vocal_extractor.py
```

如果 Windows 上 `python` 命令不可用，可以运行：

```bash
py vocal_extractor.py
```

提取结果会保存到 `output` 文件夹。

再次运行时，程序会直接检查 `output` 文件夹；如果已经存在非空的 `<视频名>_vocals.wav`，就会跳过对应视频。
