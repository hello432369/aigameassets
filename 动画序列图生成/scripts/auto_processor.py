#!/usr/bin/env python3
"""
Sprite Forge - 全自动精灵图处理器
支持动画(4x4)和静态(切割)两种模式
"""
import os, sys, time, json, shutil, argparse, math, threading
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import numpy as np
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

sys.path.insert(0, str(Path(__file__).parent))
from generate2dsprite import remove_bg_magenta, split_grid, compose_sheet, save_transparent_gif
from PIL import Image

WATCH_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
PROCESS_CONFIG = {"threshold":100,"edge_threshold":150,"fit_scale":0.85,"trim_border":4,"edge_clean_depth":3,"align":"bottom","shared_scale":True,"component_mode":"largest","component_padding":0,"min_component_area":1,"edge_touch_margin":0,"duration":200}


def detect_grid_size(image: Image.Image):
    """通过内容投影检测网格大小，无需品红分隔线"""
    rgb = np.array(image.convert("RGB")).astype(np.float64)
    r, g, b = rgb[:,:,0], rgb[:,:,1], rgb[:,:,2]
    # 非品红像素 = 内容像素（到 #FF00FF 的欧氏距离 >= 100）
    dist = np.sqrt((r - 255) ** 2 + g ** 2 + (b - 255) ** 2)
    content = dist >= 100

    h, w = content.shape
    row_proj = content.sum(axis=1)
    col_proj = content.sum(axis=0)

    def count_gaps(proj, total_len):
        max_val = proj.max()
        if max_val < 1:
            return 0
        threshold = max(max_val * 0.05, 5.0)
        min_gap = max(5, total_len // 80)
        gaps = 0
        in_gap = False
        cur = 0
        for v in proj:
            if v <= threshold:
                cur += 1
                if not in_gap:
                    in_gap = True
            else:
                if in_gap and cur >= min_gap:
                    gaps += 1
                in_gap = False
                cur = 0
        if in_gap and cur >= min_gap:
            gaps += 1
        return gaps

    row_gaps = count_gaps(row_proj, h)
    col_gaps = count_gaps(col_proj, w)

    rows = max(1, row_gaps - 1)
    cols = max(1, col_gaps - 1)

    # 单行单列 fallback：大图默认 4x4
    if rows == 1 and cols == 1 and (h > 800 or w > 800):
        rows, cols = 4, 4

    print(f"   🔍 检测到网格: {rows}x{cols}（{row_gaps} 行间隙, {col_gaps} 列间隙）")
    return (rows, cols)


def process_image(image_path: Path, output_dir: Path, config: dict, mode: str = "auto"):
    print(f"🎨 处理: {image_path.name}")
    timestamp = datetime.now().strftime("%m%d_%H%M%S")
    folder_name = f"{image_path.stem}_{timestamp}"
    out = output_dir / folder_name
    out.mkdir(parents=True, exist_ok=True)
    print(f"   📁 输出到: {out.name}")

    raw = Image.open(image_path).convert("RGBA")
    raw.save(out / "raw.png")

    if mode == "anim":
        rows, cols = 4, 4
        print(f"   🔍 input-1 强制 4x4 动画模式")
    else:
        rows, cols = detect_grid_size(raw)
        print(f"   🔍 检测到网格: {rows}x{cols}")

    cleaned = remove_bg_magenta(raw.copy(), config["threshold"], config["edge_threshold"])
    cleaned.save(out / "clean.png")

    if rows == 4 and cols == 4:
        cell_size = 96
        frames, frame_info = split_grid(raw, rows, cols, cell_size,
            config["threshold"], config["edge_threshold"],
            fit_scale=config["fit_scale"], trim_border_px=config["trim_border"],
            edge_clean_depth=config["edge_clean_depth"], align=config["align"],
            shared_scale=config["shared_scale"], component_mode=config["component_mode"],
            component_padding=config["component_padding"], min_component_area=config["min_component_area"],
            edge_touch_margin=config["edge_touch_margin"])

        total_frames = rows * cols
        frames_dir = out / "frames"; frames_dir.mkdir(exist_ok=True)

        directions = ["down","left","right","up"]
        labels = [f"{d}-{i}" for d in directions for i in range(1,5)]
        for label, frame in zip(labels, frames):
            frame.save(frames_dir / f"{label}.png")

        sheet = compose_sheet(frames, rows, cols, cell_size)
        sheet.save(out / "sheet.png")

        strips_dir = out / "strips"; strips_dir.mkdir(exist_ok=True)
        gifs_dir = out / "gifs"; gifs_dir.mkdir(exist_ok=True)
        for row_idx, direction in enumerate(directions):
            row_frames = frames[row_idx * cols : (row_idx + 1) * cols]
            compose_sheet(row_frames, 1, cols, cell_size).save(strips_dir / f"{direction}-strip.png")
            save_transparent_gif(row_frames, gifs_dir / f"{direction}.gif", config["duration"])
        print(f"   ✅ 4x4 动画: sheet + 4方向GIF + 条带")
    else:
        total_frames = 0
        print(f"   ✅ 静态: 原图 + 抠图完成")

    meta = {"source_file":image_path.name,"processed_at":datetime.now().isoformat(),"grid":f"{rows}x{cols}","cell_size":cell_size if rows == 4 and cols == 4 else None,"total_frames":total_frames,"config":config}
    (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"   ✨ 完成: {out.name}")
    return out


def process_image_with_grid(image_path: Path, output_dir: Path, config: dict, rows: int, cols: int):
    """用指定的行列数处理图片（手动网格覆盖用）"""
    print(f"🎨 手动网格处理: {image_path.name} ({rows}x{cols})")
    timestamp = datetime.now().strftime("%m%d_%H%M%S")
    folder_name = f"{image_path.stem}_{timestamp}"
    out = output_dir / folder_name
    out.mkdir(parents=True, exist_ok=True)
    print(f"   📁 输出到: {out.name}")

    raw = Image.open(image_path).convert("RGBA")
    raw.save(out / "raw.png")
    cleaned = remove_bg_magenta(raw.copy(), config["threshold"], config["edge_threshold"])
    cleaned.save(out / "clean.png")

    cell_size = 96
    frames, frame_info = split_grid(raw, rows, cols, cell_size,
        config["threshold"], config["edge_threshold"],
        fit_scale=config["fit_scale"], trim_border_px=config["trim_border"],
        edge_clean_depth=config["edge_clean_depth"], align=config["align"],
        shared_scale=config["shared_scale"], component_mode=config["component_mode"],
        component_padding=config["component_padding"], min_component_area=config["min_component_area"],
        edge_touch_margin=config["edge_touch_margin"])

    total_frames = rows * cols
    frames_dir = out / "frames"; frames_dir.mkdir(exist_ok=True)

    if rows == 4 and cols == 4:
        directions = ["down","left","right","up"]
        labels = [f"{d}-{i}" for d in directions for i in range(1,5)]
        for label, frame in zip(labels, frames):
            frame.save(frames_dir / f"{label}.png")
        sheet = compose_sheet(frames, rows, cols, cell_size)
        sheet.save(out / "sheet.png")
        strips_dir = out / "strips"; strips_dir.mkdir(exist_ok=True)
        gifs_dir = out / "gifs"; gifs_dir.mkdir(exist_ok=True)
        for row_idx, direction in enumerate(directions):
            row_frames = frames[row_idx * cols : (row_idx + 1) * cols]
            compose_sheet(row_frames, 1, cols, cell_size).save(strips_dir / f"{direction}-strip.png")
            save_transparent_gif(row_frames, gifs_dir / f"{direction}.gif", config["duration"])
        print(f"   ✅ {rows}x{cols} 动画: sheet + 4方向GIF + 条带")
    else:
        for i, frame in enumerate(frames):
            frame.save(frames_dir / f"frame-{i+1}.png")
        sheet = compose_sheet(frames, rows, cols, cell_size)
        sheet.save(out / "sheet.png")
        print(f"   ✅ {rows}x{cols} 切割: {total_frames} 帧 + 图集")

    meta = {"source_file":image_path.name,"processed_at":datetime.now().isoformat(),"grid":f"{rows}x{cols}","cell_size":cell_size,"total_frames":total_frames,"mode":"manual","config":config}
    (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"   ✨ 完成: {out.name}")
    return out


def scan_output(output_dir: Path, mode: str):
    heroes = []
    if not output_dir.exists():
        return heroes
    for entry in sorted(output_dir.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        source = name
        total_frames = 0
        mp = entry / "meta.json"
        if mp.exists():
            try:
                meta = json.loads(mp.read_text(encoding="utf-8"))
                source = meta.get("source_file", name)
                total_frames = meta.get("total_frames", 0)
            except Exception:
                pass
        heroes.append({
            "name": name, "sourceFile": source, "dir": str(entry.relative_to(entry.parent.parent)),
            "type": mode, "totalFrames": total_frames,
            "hasRaw": (entry / "raw.png").exists(),
            "hasClean": (entry / "clean.png").exists(),
            "hasFrames": (entry / "frames").exists(),
            "hasGifs": (entry / "gifs").exists(),
            "hasStrips": (entry / "strips").exists(),
            "hasSheet": (entry / "sheet.png").exists(),
            "mtime": int(entry.stat().st_mtime * 1000),
        })
    heroes.sort(key=lambda h: h["mtime"], reverse=True)
    return heroes


def write_data_js():
    data = {
        "anim": scan_output(Path("output-1"), "anim"),
        "static": scan_output(Path("output-0"), "static"),
    }
    Path("data.js").write_text(
        f"window.heroesData = {json.dumps(data, indent=2, ensure_ascii=False)};", encoding="utf-8")


def process_existing(input_dir: Path, output_dir: Path, processed_dir: Path, config: dict, mode: str = "auto"):
    if not input_dir.exists():
        return
    files = [f for f in input_dir.iterdir() if f.is_file() and f.suffix.lower() in WATCH_EXTENSIONS and ".processed" not in str(f)]
    if not files:
        print(f"📂 {input_dir.name}/ 中没有待处理的图片")
        return
    print(f"\n🔍 发现 {len(files)} 个文件")
    for fp in files:
        try:
            process_image(fp, output_dir, config, mode)
            processed_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.move(str(fp), str(processed_dir / f"{fp.stem}_{ts}{fp.suffix}"))
        except Exception as e:
            print(f"   ❌ 失败: {e}")
            import traceback; traceback.print_exc()
    write_data_js()


def start_http_server():
    """启动 HTTP 服务器，接收前端发来的网格覆盖数据"""
    HOST, PORT = 'localhost', 8765

    class GridHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path == '/save-grid':
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length)
                try:
                    Path('grid-override.json').write_bytes(body)
                    self.send_response(200)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(b'ok')
                    print(f"   🌐 收到网格覆盖请求")
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(str(e).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()

        def log_message(self, format, *args):
            pass

    server = HTTPServer((HOST, PORT), GridHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"   🌐 网格编辑接口: http://{HOST}:{PORT}/save-grid")


def check_grid_override():
    """检查 grid-override.json，有新的覆盖请求就处理"""
    path = Path("grid-override.json")
    if not path.exists():
        return
    try:
        override = json.loads(path.read_text(encoding="utf-8"))
        raw_path = Path(override["source"])
        rows = int(override["rows"])
        cols = int(override["cols"])
        output_dir = Path(override["output_dir"])

        if not raw_path.exists():
            print(f"   ❌ 网格覆盖: 源文件不存在 {raw_path}")
            path.unlink()
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        process_image_with_grid(raw_path, output_dir, PROCESS_CONFIG, rows, cols)

        # 移动到 .processed
        inp_dir = raw_path.parent
        proc_dir = inp_dir / ".processed"
        proc_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.move(str(raw_path), str(proc_dir / f"{raw_path.stem}_{ts}{raw_path.suffix}"))

        write_data_js()
        path.unlink()
        print(f"   ✅ 网格覆盖处理完成")
    except Exception as e:
        print(f"   ❌ 网格覆盖处理失败: {e}")
        import traceback; traceback.print_exc()
        path.unlink()


def start_watching():
    dirs = [
        (Path("input-1"), Path("output-1"), Path("input-1/.processed")),
        (Path("input-0"), Path("output-0"), Path("input-0/.processed")),
    ]
    observers = []

    start_http_server()

    for inp, out, proc in dirs:
        inp.mkdir(parents=True, exist_ok=True)
        out.mkdir(parents=True, exist_ok=True)
        p_mode = "anim" if inp.name == "input-1" else "static"
        process_existing(inp, out, proc, PROCESS_CONFIG, p_mode)
        write_data_js()

        class Handler(FileSystemEventHandler):
            def __init__(self, out_dir, proc_dir, mode):
                self.processing = set()
                self.out_dir = out_dir
                self.proc_dir = proc_dir
                self.mode = mode
            def on_created(self, e):
                if e.is_directory: return
                fp = Path(e.src_path)
                if fp.suffix.lower() not in WATCH_EXTENSIONS or ".processed" in str(fp) or fp in self.processing:
                    return
                self.processing.add(fp)
                try:
                    time.sleep(0.5)
                    process_image(fp, self.out_dir, PROCESS_CONFIG, self.mode)
                    self.proc_dir.mkdir(parents=True, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    shutil.move(str(fp), str(self.proc_dir / f"{fp.stem}_{ts}{fp.suffix}"))
                except Exception as e:
                    print(f"   ❌ 失败: {e}")
                    import traceback; traceback.print_exc()
                finally:
                    self.processing.discard(fp)

        h = Handler(out, proc, p_mode)
        o = Observer()
        o.schedule(h, str(inp), recursive=False)
        o.start()
        observers.append(o)

    class OutputHandler(FileSystemEventHandler):
        def on_any_event(self, e):
            write_data_js()
    for out_dir in [Path("output-1"), Path("output-0")]:
        o = Observer()
        o.schedule(OutputHandler(), str(out_dir), recursive=True)
        o.start()
        observers.append(o)

    print(f"\n{'='*40}\n🚀 Sprite Forge 已启动\n📥 input-1 ➡ output-1 (动画) | input-0 ➡ output-0 (静态)\n{'='*40}")
    try:
        while True:
            time.sleep(1)
            check_grid_override()
    except KeyboardInterrupt:
        for o in observers: o.stop()
        for o in observers: o.join()
        print("\n👋 已停止")


def main():
    parser = argparse.ArgumentParser(description="Sprite Forge")
    parser.add_argument("--once", action="store_true", help="只处理现有文件")
    args = parser.parse_args()

    for inp, out, proc in [
        (Path("input-1"), Path("output-1"), Path("input-1/.processed")),
        (Path("input-0"), Path("output-0"), Path("input-0/.processed")),
    ]:
        inp.mkdir(parents=True, exist_ok=True)
        out.mkdir(parents=True, exist_ok=True)
        p_mode = "anim" if inp.name == "input-1" else "static"
        process_existing(inp, out, proc, PROCESS_CONFIG, p_mode)

    write_data_js()

    if not args.once:
        start_watching()


if __name__ == "__main__":
    main()
