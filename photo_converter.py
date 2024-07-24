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
parser.add_argument('--crf', type=int, default=36, help='CRF value')
parser.add_argument('--max_resolution', type=int,
                    default=3024 * 4032, help='Max resolution in pixels')
parser.add_argument('--max_workers', type=int, default=4,
                    help='Max number of workers')
parser.add_argument("--video_ffmpeg_args", type=str, help="Additional arguments to pass to ffmpeg.",
                    default="-loglevel error -stats -c:v libsvtav1 -preset 4 -crf 36 -pix_fmt yuv420p10le -c:a libopus -b:a 64k")
args = parser.parse_args()

# Set up logging
setup_logging()

image_extensions = ('.png', '.jpg', '.jpeg', '.webp',
                    '.heic', '.heif', '.gif', '.tiff', '.tif')


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

        cmd_aomav1 = cmd + [
            "-c:v", "libaom-av1",
            "-cpu-used", "1",
            "-pix_fmt", "yuv420p10le",
            "-crf", str(crf),
            "-still-picture", "1",
            str(target_path),
            "-y",
            "-hide_banner",
            "-loglevel", "error"
        ]

        # cmd_svtav1 = cmd + [
        #     "-c:v", "libsvtav1",
        #     "-preset", "4",
        #     "-crf", str(crf),
        #     "-pix_fmt", "yuv420p10le",
        #     "-still-picture", "1",
        #     str(target_path),
        #     "-y",
        #     "-hide_banner",
        #     "-loglevel", "error"
        # ]

        if not cmd_runner(cmd_aomav1):
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


def process_image(args):
    filepath, source_dir, target_dir, crf, max_resolution = args
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
            convert_img_to_avif(filepath, target_path, crf, max_resolution)

            # Copy all other exif data
            copy_metadata(filepath, target_path)

        # Remove "_original" backup file created by exiftool
        backup_file = target_path.with_name(target_path.name + '_original')
        if backup_file.exists():
            backup_file.unlink()
    except Exception:
        logging.error(f"Error processing image {
                      filepath}: {traceback.format_exc()}")

    logging.info(f"Processed {filepath} -> {target_path}")


def convert_images(source_dir, target_dir, crf, max_resolution, max_workers=1):
    source_dir = Path(source_dir)
    target_dir = Path(target_dir)

    video_ext = ".mp4"

    image_files = [f for f in source_dir.rglob(
        '*') if f.suffix.lower() in image_extensions and '@' not in str(f)]

    # remove redundant .MOV live photos
    live_photos = [f for f in source_dir.rglob('*') if f.suffix.lower() == '.mov' and f.with_suffix(
        '.HEIC') in image_files or f.with_suffix('.heic') in image_files]

    # Convert images
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(tqdm(executor.map(process_image, [(image_file, source_dir, target_dir, crf, max_resolution)
             for image_file in image_files]), total=len(image_files), ncols=80))
    # for image_file in tqdm(image_files, desc="Converting", ncols=50):
    #     process_image(
    #         (image_file, source_dir, target_dir, crf, max_resolution))

    # Convert videos
    process_directory(source_dir, target_dir,
                      delete_original=False, ffmpeg_args=args.video_ffmpeg_args, ext=video_ext)

    # remove redundant .MOV live photos in target_dir
    for live_photo in live_photos:
        target_live_photo = target_dir / live_photo.relative_to(source_dir)
        target_live_photo = target_live_photo.with_suffix(video_ext)
        if target_live_photo.exists():
            target_live_photo.unlink()


if __name__ == '__main__':
    source_dir = args.source_dir
    target_dir = args.target_dir
    crf = args.crf
    max_resolution = args.max_resolution

    convert_images(source_dir, target_dir, crf, max_resolution,
                   max_workers=args.max_workers)
