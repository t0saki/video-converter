import os
import sys
import subprocess
from pathlib import Path
import argparse
from tqdm import tqdm
import json
import logging
import tempfile
from datetime import datetime
import shutil
import uuid

in_format = ('.mp4', '.avi', '.mkv', '.flv', '.rmvb', '.wmv',
             '.mov', '.mpg', '.mpeg', '.m4v', '.3gp', '.f4v', '.webm', '.ts')


def setup_logging():
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    log_filename = datetime.now().strftime('%Y-%m-%d_%H-%M-%S.log')
    log_filepath = log_dir / log_filename

    logging.basicConfig(
        filename=log_filepath,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)


def get_video_duration(filename):
    result = subprocess.check_output(
        ["ffprobe", "-v", "quiet", "-show_format", "-print_format", "json", filename])
    fields = json.loads(result)  # ['streams'][0]

    duration_seconds = float(fields["format"]["duration"])
    # fps = eval(fields['r_frame_rate'])
    return duration_seconds  # , fps

def convert_video(source_path, target_path, ffmpeg_args):
    cmd = [
        'ffmpeg', '-i', str(source_path),
        *ffmpeg_args.split(),
        str(target_path)
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        result.check_returncode()  # 检查命令是否执行成功

        source_duration = get_video_duration(str(source_path))
        target_duration = get_video_duration(str(target_path))
        if abs(source_duration - target_duration) > 8:
            raise ValueError("Duration mismatch")

        return True
    except subprocess.CalledProcessError:
        logging.error(f"Error converting {source_path}: {result.stderr}")
        return False
    except Exception as e:
        logging.error(f"Error converting {source_path}: {e}")
        return False

def process_directory(input_dir, output_dir, delete_original, ffmpeg_args):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    video_files = [f for f in input_dir.rglob('*') if f.suffix.lower() in in_format and '@' not in str(f)]

    parent_tmp_dir = f"/home/tosaki/temp_ffmpeg/"
    os.makedirs(parent_tmp_dir, exist_ok=True)

    for video_file in tqdm(video_files, desc="Converting", ncols=50):
        relative_path = video_file.relative_to(input_dir)
        target_file = output_dir / relative_path
        target_file = target_file.with_suffix('.mkv')
        target_file.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=parent_tmp_dir) as temp_dir:
            temp_source = Path(temp_dir) / video_file.name
            temp_target = Path(temp_dir) / "ffmpeg_temp.mkv"

            shutil.copy(video_file, temp_source)
            convert_success = convert_video(temp_source, temp_target, ffmpeg_args)
            
            if convert_success:
                shutil.move(temp_target, target_file)
                if delete_original:
                    os.remove(video_file)
                logging.info(f"Converted {video_file}")
            else:
                logging.error(f"Failed to convert {video_file}")

            


def main():
    parser = argparse.ArgumentParser(description="Batch convert videos with ffmpeg.")
    parser.add_argument("input_dir", type=str, help="Input directory containing video files.")
    parser.add_argument("output_dir", type=str, help="Output directory for converted videos.")
    parser.add_argument("--delete", action='store_true', help="Delete original files after conversion.")
    parser.add_argument("--ffmpeg_args", type=str, help="Additional arguments to pass to ffmpeg.", default="-loglevel error -stats -c:v libsvtav1 -preset 4 -crf 25 -pix_fmt yuv420p10le -c:a libopus -b:a 64k")
    
    args = parser.parse_args()

    process_directory(args.input_dir, args.output_dir, args.delete, args.ffmpeg_args)

if __name__ == "__main__":
    setup_logging()
    logging.info("Starting video conversion...")
    main()
    logging.info("Finished video conversion.")