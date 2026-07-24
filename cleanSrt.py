import os
import re
import argparse

def is_no_speech(text: str) -> bool:
    """判断字幕内容是否为 <No Speech>（忽略大小写、空格和尖括号）"""
    cleaned = text.strip().lower().replace(' ', '')
    return cleaned in ('<nospeech>', 'nospeech')

def clean_srt(file_path: str) -> int:
    """
    清理单个srt文件，输出到 原文件名_cleaned.srt
    返回删除的字幕条数
    """
    # 读取全部内容
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # 按空行分割成字幕块（兼容Windows和Unix换行）
    blocks = re.split(r'\r?\n\r?\n', content.strip())
    cleaned_blocks = []

    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue  # 不完整的块跳过

        # 第0行是序号，第1行是时间轴，第2行及以后是字幕文本
        index_line = lines[0]
        time_line = lines[1]
        text_lines = lines[2:]
        text = '\n'.join(text_lines)

        # 保留非 No Speech 的条目
        if not is_no_speech(text):
            cleaned_blocks.append((time_line, text))

    # 重新编号并写回
    out_path = os.path.splitext(file_path)[0] + '_cleaned.srt'
    with open(out_path, 'w', encoding='utf-8') as f:
        for idx, (time_line, text) in enumerate(cleaned_blocks, start=1):
            f.write(f"{idx}\n")
            f.write(f"{time_line}\n")
            f.write(f"{text}\n\n")

    removed = len(blocks) - len(cleaned_blocks)
    print(f"[{os.path.basename(file_path)}] 删除 {removed} 条，剩余 {len(cleaned_blocks)} 条 → {os.path.basename(out_path)}")
    return removed

def batch_clean_srt(folder: str = '.'):
    """批量清理指定目录下所有srt文件"""
    srt_files = [f for f in os.listdir(folder) if f.lower().endswith('.srt') and not f.endswith('_cleaned.srt')]
    if not srt_files:
        print("当前目录未找到 .srt 文件")
        return

    total_removed = 0
    for fname in srt_files:
        total_removed += clean_srt(os.path.join(folder, fname))

    print(f"\n处理完成，共处理 {len(srt_files)} 个文件，累计删除 {total_removed} 条字幕")

def main():
    parser = argparse.ArgumentParser(
        description="Remove <No Speech> subtitle blocks from SRT files."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="SRT file or folder to clean. Defaults to batch cleaning the current folder.",
    )
    args = parser.parse_args()

    path = args.path
    if os.path.isdir(path):
        batch_clean_srt(path)
    elif os.path.isfile(path):
        if not path.lower().endswith('.srt'):
            raise SystemExit(f"不是 .srt 文件: {path}")
        clean_srt(path)
    else:
        raise SystemExit(f"路径不存在: {path}")

if __name__ == '__main__':
    main()
