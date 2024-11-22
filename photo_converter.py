import os
import tempfile
from video_converter import setup_logging, process_directory, cmd_runner, copy_metadata
import logging
import traceback
import subprocess
import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tqdm import tqdm
import argparse
from math import ceil, trunc

parser = argparse.ArgumentParser(description='Convert images to AVIF format')
parser.add_argument('source_dir', type=str, help='Source directory')
parser.add_argument('target_dir', type=str, help='Target directory')
parser.add_argument('--quality', type=int, default=50, help='quality value')
parser.add_argument('--max_resolution', type=int,
                    default=3024 * 4032, help='Max resolution in pixels')
parser.add_argument('--max_workers', type=int, default=4,
                    help='Max number of workers')
parser.add_argument("--video_ffmpeg_args", type=str, help="Additional arguments to pass to ffmpeg.",
                    default="-loglevel error -stats -c:v libsvtav1 -preset 4 -crf 36 -pix_fmt yuv420p10le -c:a libopus -b:a 64k")
args = parser.parse_args()

# Set up logging
setup_logging()

image_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.heic', '.heif', '.gif', '.tiff', '.tif', 'avif')


def convert_img_to_avif(filepath, target_path, crf, max_resolution):
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_png_created = False  # Flag to track if a temp PNG file is created

        if filepath.suffix.lower() in ['.heic', '.heif']:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_png:
                temp_png_filepath = Path(temp_png.name)

            # Convert HEIC or HEIF to PNG using ImageMagick
            magick_cmd = ['magick', str(filepath), '-compress',
                          'lossless', str(temp_png_filepath)]

            assert cmd_runner(magick_cmd)

            # # Convert HEIC or HEIF to PNG using ffmpeg
            # ffmpeg_cmd = ['ffmpeg', '-y', '-i',
            #               str(filepath), str(temp_png_filepath)]
            # assert cmd_runner(ffmpeg_cmd)

            filepath = temp_png_filepath  # Use the PNG file for the rest of the process
            temp_png_created = True  # Set flag

        cmd = ["ffmpeg", "-i", str(filepath)]
        try:
            # Check image resolution using ffprobe
            ffprobe_process = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                    'stream=width,height', '-of', 'csv=s=x:p=0', str(filepath)],
                capture_output=True, text=True)
            width, height = map(int, ffprobe_process.stdout.strip().split('x'))
            resolution = width * height

            try:
                # Get image rotation info using exiftool
                exiftool_process = subprocess.run(
                    ['exiftool', '-Orientation', '-n', str(filepath)],
                    capture_output=True, text=True)
                orientation = exiftool_process.stdout.split(':')[1].strip()

                # Adjust width and height based on rotation
                if orientation in ['6', '8']:  # 6 = 90 CW, 8 = 270 CW
                    width, height = height, width
            except Exception:
                pass

            if resolution > max_resolution:
                # If the resolution is greater than max_resolution, scale it down
                # Calculate target resolution
                target_width = round(
                    width * (max_resolution / resolution) ** 0.5)
                target_height = round(
                    height * (max_resolution / resolution) ** 0.5)
            else:
                # If the resolution is within the limit, make sure both dimensions are even
                target_width = width
                target_height = height

            # Ensure both width and height are even
            pad_filter = f"scale={
                trunc(target_width/2)*2}:{trunc(target_height/2)*2}"
        except Exception as e:
            logging.error(f"Error processing image resolution: {e}")
            pad_filter = "scale=trunc(iw/2)*2:trunc(ih/2)*2"

        cmd.extend(["-vf", pad_filter])

        # cmd_aomav1 = cmd + [
        #     "-c:v", "libaom-av1",
        #     "-cpu-used", "1",
        #     "-pix_fmt", "yuv420p10le",
        #     "-crf", str(crf),
        #     "-still-picture", "1",
        #     str(target_path),
        #     "-y",
        #     "-hide_banner",
        #     "-loglevel", "error"
        # ]

        cmd_svtav1 = cmd + [
            "-c:v", "libsvtav1",
            "-preset", "4",
            "-crf", str(crf),
            "-pix_fmt", "yuv420p10le",
            "-still-picture", "1",
            str(target_path),
            "-y",
            "-hide_banner",
            "-loglevel", "error"
        ]

        if not cmd_runner(cmd_svtav1):
            # if True:
            # use webp if av1 fails
            logging.warning(
                f"av1 failed for {filepath}, using webp instead.")
            target_path = target_path.with_suffix('.webp')
            cmd_webp = cmd + [
                "-c:v", "libwebp",
                "-lossless", "0",
                "-compression_level", "6",
                "-quality", "80",
                "-preset", "picture",
                str(target_path),
                "-y",
                "-hide_banner",
                "-loglevel", "error"
            ]
            assert cmd_runner(cmd_webp)

            if temp_png_created:
                filepath.unlink()

        return True
    except Exception:
        logging.error(f"Error processing image {
                      filepath}: {traceback.format_exc()}")
        return False

def get_img_wh_magick(filepath):
    identify_process = subprocess.run(
        ['magick', 'identify', '-format', '%w %h', str(filepath)],
        capture_output=True, text=True
    )
    if identify_process.returncode != 0:
        logging.error(f"无法获取图像尺寸：{filepath}, {identify_process.stderr}")
        return
    width_str, height_str = identify_process.stdout.strip().split()
    width, height = int(width_str), int(height_str)
    return width, height

def get_img_wh_ffprobe(filepath):
    ffprobe_process = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                                      'stream=width,height', '-of', 'csv=s=x:p=0', str(filepath)], capture_output=True, text=True)
    width, height = map(int, ffprobe_process.stdout.strip().split('x'))
    return width, height

def convert_avif_magick(filepath, target_path, quality, max_resolution):
    # # 获取相对路径并生成目标路径
    # relative_path = filepath.relative_to(source_dir)
    # target_path = target_dir / relative_path
    # target_path = target_path.with_suffix('.avif')
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        width, height = get_img_wh_magick(filepath)
    except Exception as e:
        width, height = get_img_wh_ffprobe(filepath)

    resolution = width * height
    target_width = width
    target_height = height

    if resolution > max_resolution:
        scale_factor = (max_resolution / resolution) ** 0.5
        target_width = round(width * scale_factor)
        target_height = round(height * scale_factor)

    # # 确保宽高为偶数
    # if target_width % 2 != 0:
    #     target_width += 1
    # if target_height % 2 != 0:
    #     target_height += 1

    # 构建 ImageMagick 转换命令
    cmd = [
        'magick', str(filepath),
        '-resize', f'{target_width}x{target_height}',
        '-quality', str(quality),
        '-depth', '10',
        '-define', 'heic:depth=10',
        '-define', 'heic:speed=4',
        str(target_path)
    ]

    # 执行命令
    result = cmd_runner(cmd)
    if not result:
        logging.error(f"处理图像时出错：{filepath}")



def process_image(args):
    filepath, source_dir, target_dir, quality, max_resolution = args
    relative_path = filepath.relative_to(source_dir)
    target_path = target_dir / relative_path
    target_path = target_path.with_suffix('.avif')

    try:
        def detect_exists(filepath):
            if filepath.with_suffix('.avif').exists() and filepath.with_suffix('.avif').stat().st_size > 0:
                return True
            if filepath.with_suffix('.webp').exists() and filepath.with_suffix('.webp').stat().st_size > 0:
                return True
            return False

        if not detect_exists(target_path):
            # convert_img_to_avif(filepath, target_path, quality, max_resolution)

            # # Copy all other exif data
            # copy_metadata(filepath, target_path)

            convert_avif_magick(filepath, target_path, quality, max_resolution)

        # check if exif data is copied
        if target_path.exists() and target_path.stat().st_size > 0:
            exiftool_process = subprocess.run(
                ['exiftool', '-DateTimeOriginal', '-n', str(target_path)],
                capture_output=True, text=True)
            if not exiftool_process.stdout:
                copy_metadata(filepath, target_path)
            else:
                # copy file time
                mtime = filepath.stat().st_mtime
                atime = filepath.stat().st_atime
                target_path.touch()
                os.utime(target_path, (atime, mtime))

        # Remove "_original" backup file created by exiftool
        backup_file = target_path.with_name(target_path.name + '_original')
        if backup_file.exists():
            backup_file.unlink()
    except Exception:
        logging.error(f"Error processing image {
                      filepath}: {traceback.format_exc()}")

    # logging.info(f"Processed {filepath} -> {target_path}")
    # only log this to file


def convert_images(source_dir, target_dir, quality, max_resolution, max_workers=1):
    source_dir = Path(source_dir)
    target_dir = Path(target_dir)

    video_ext = ".mp4"

    all_files = [f for f in source_dir.rglob('*') if '@eaDir' not in str(f)]

    image_files = [f for f in all_files if f.suffix.lower() in image_extensions]

    # # remove redundant .MOV live photos
    # live_photos = [f for f in all_files if f.suffix.lower() == '.mov' and f.with_suffix(
    #     '.HEIC') in image_files or f.with_suffix('.heic') in image_files]
    # image_files = [f for f in image_files if f not in live_photos]

    # # Convert images
    # with ThreadPoolExecutor(max_workers=max_workers) as executor:
    #     list(tqdm(executor.map(process_image, [(image_file, source_dir, target_dir, quality, max_resolution)
    #          for image_file in image_files]), total=len(image_files), dynamic_ncols=True, smoothing=0.01))

    # Convert videos
    process_directory(source_dir, target_dir,
                      delete_original=False, ffmpeg_args=args.video_ffmpeg_args, ext=video_ext, max_resolution=1920*1080, all_files=all_files)


if __name__ == '__main__':
    source_dir = args.source_dir
    target_dir = args.target_dir
    quality = args.quality
    max_resolution = args.max_resolution

    convert_images(source_dir, target_dir, quality, max_resolution,
                   max_workers=args.max_workers)
