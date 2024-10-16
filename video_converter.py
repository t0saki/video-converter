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


def cmd_runner(cmd):
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        result.check_returncode()  # 检查命令是否执行成功
        return result
    except subprocess.CalledProcessError:
        logging.error(f"Error running command {cmd}: {result.stderr}")
        return False
    except Exception as e:
        logging.error(f"Error running command {cmd}: {e}")
        return False


def copy_metadata(source_path, target_path):
    try:
        # Copy all metadata from source to target
        # Copy file time, creation time, modification time, and all exif data
        file_time = datetime.fromtimestamp(source_path.stat().st_atime)
        creation_time = datetime.fromtimestamp(source_path.stat().st_ctime)
        modification_time = datetime.fromtimestamp(source_path.stat().st_mtime)

        write_time = min(file_time, creation_time, modification_time)

        os.utime(target_path, (file_time.timestamp(),
                 modification_time.timestamp()))

    except Exception as e:
        logging.error(f"Error copying metadata: {e}")
    # 检查原图片是否有exif信息
    try:
        exif_info = subprocess.check_output(
            ['exiftool', '-j', source_path])
    except subprocess.CalledProcessError:
        exif_info = None

    # try:
    #     # "Recorded_Date": "2023-09-26T03:38:24+0800",
    #     # "Encoded_Date": "UTC 2022-12-09 12:07:17",
    #     # "Tagged_Date": "UTC 2022-12-09 12:07:17",
    #     if 'Recorded_Date' in exif_info.decode():
    #         recorded_date = json.loads(exif_info.decode())[0]['Recorded_Date']
    #         write_time = datetime.strptime(
    #             recorded_date, '%Y-%m-%dT%H:%M:%S%z')

    def write_exif():
        # 将文件时间写入目标图片的exif信息
        try:
            subprocess.run(['exiftool', f'-DateTimeOriginal={write_time.strftime('%Y:%m:%d %H:%M:%S')}', f'-CreateDate={write_time.strftime(
                '%Y:%m:%d %H:%M:%S')}', f'-ModifyDate={write_time.strftime('%Y:%m:%d %H:%M:%S')}', '-overwrite_original', target_path], check=True)
        except subprocess.CalledProcessError as e:
            # print(f"Error writing EXIF data: {e}")
            logging.error(f"Error writing EXIF data: {e}")

    if exif_info:
        # 复制所有的exif信息到目标图片
        try:
            subprocess.run(['exiftool', '-tagsFromFile', source_path,
                           '-all:all', '-overwrite_original', target_path], check=True)
            # if no DateTimeOriginal:
            # if 'DateTimeOriginal' not in subprocess.run(['exiftool', '-DateTimeOriginal', str(target_path), '-m'], capture_output=True, text=True).stdout
            exif_info_json = json.loads(exif_info.decode())[0]
            if 'DateTimeOriginal' not in exif_info_json:
                cmd = ['exiftool', '-DateTimeOriginal=' + write_time.strftime(
                    '%Y:%m:%d %H:%M:%S'), str(target_path), '-overwrite_original']
                assert cmd_runner(cmd)
        except subprocess.CalledProcessError as e:
            logging.error(f"Error copying EXIF data: {e}")
            write_exif()
    else:
        write_exif()

    # if is video and no QuickTime:CreationDate:
    if target_path.suffix.lower() in in_format and 'Creation Date' not in subprocess.run(['exiftool', '-QuickTime:CreationDate', str(source_path), '-m'], capture_output=True, text=True).stdout:
        def try_get_time(exiftime_list, exif_info_json, key):
            if key in exif_info_json:
                try:
                    if '+' in exif_info_json[key]:
                        format = '%Y:%m:%d %H:%M:%S%z'
                    else:
                        format = '%Y:%m:%d %H:%M:%S'
                    exiftime_list.append(datetime.strptime(
                        exif_info_json[key], format))
                except ValueError:
                    pass
            return exiftime_list
        exiftime = [write_time]
        exiftime = try_get_time(exiftime, exif_info_json, 'FileModifyDate')
        exiftime = try_get_time(exiftime, exif_info_json, 'FileAccessDate')
        exiftime = try_get_time(exiftime, exif_info_json, 'FileCreateDate')
        exiftime = try_get_time(exiftime, exif_info_json, 'CreateDate')
        exiftime = try_get_time(exiftime, exif_info_json, 'ModifyDate')
        exiftime = try_get_time(exiftime, exif_info_json, 'DateTimeOriginal')
        exiftime = try_get_time(exiftime, exif_info_json, 'CreationDate')

        # add default time zone local
        for i in range(len(exiftime)):
            if exiftime[i].tzinfo is None:
                exiftime[i] = exiftime[i].replace(
                    tzinfo=datetime.now().astimezone().tzinfo)
        write_time = min(exiftime)

        cmd = ['exiftool', '-QuickTime:CreationDate=' + write_time.strftime('%Y:%m:%d %H:%M:%S-%z'), str(
            target_path), '-overwrite_original']
        assert cmd_runner(cmd)

        if 'DateTimeOriginal' not in exif_info_json:
            cmd = ['exiftool', '-DateTimeOriginal=' + write_time.strftime(
                '%Y:%m:%d %H:%M:%S'), str(target_path), '-overwrite_original']
            assert cmd_runner(cmd)

    os.utime(target_path, (write_time.timestamp(),
                           write_time.timestamp()))


def convert_video(source_path, target_path, ffmpeg_args):
    cmd = [
        'ffmpeg', '-i', str(source_path),
        *ffmpeg_args.split(),
        str(target_path)
    ]
    result = cmd_runner(cmd)
    # result = True
    if result:
        source_duration = get_video_duration(str(source_path))
        target_duration = get_video_duration(str(target_path))
        if abs(source_duration - target_duration) / source_duration > 0.05:
            logging.error(f"Duration mismatch: {
                          source_duration} vs {target_duration}")
            return False
        return True


def process_directory(input_dir, output_dir, delete_original, ffmpeg_args, ext='.mp4'):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    video_files = [f for f in input_dir.rglob(
        '*') if f.suffix.lower() in in_format and '@' not in str(f)]

    # exempt live photos
    live_photos = [f for f in video_files if f.with_suffix(
        '.HEIC').exists() or f.with_suffix('.heic').exists()]
    video_files = [f for f in video_files if f not in live_photos]

    parent_tmp_dir = f"/home/tosaki/temp_ffmpeg/"
    os.makedirs(parent_tmp_dir, exist_ok=True)

    for video_file in tqdm(video_files, desc="Converting", ncols=50):
        logging.info(f"Start converting {video_file}")

        relative_path = video_file.relative_to(input_dir)
        target_file = output_dir / relative_path
        target_file = target_file.with_suffix(ext)
        target_file.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=parent_tmp_dir) as temp_dir:
            # detect if target file already exists
            if target_file.exists():
                logging.info(f"Target file already exists: {target_file}")
                copy_metadata(video_file, target_file)
                continue

            temp_source = Path(temp_dir) / video_file.name
            temp_target = Path(temp_dir) / f"ffmpeg_temp{ext}"

            shutil.copy(video_file, temp_source)
            convert_success = convert_video(
                temp_source, temp_target, ffmpeg_args)

            if convert_success:
                shutil.move(temp_target, target_file)
                copy_metadata(video_file, target_file)
                if delete_original:
                    os.remove(video_file)
                logging.info(f"Converted {video_file}")

            else:
                logging.error(f"Failed to convert {video_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Batch convert videos with ffmpeg.")
    parser.add_argument("input_dir", type=str,
                        help="Input directory containing video files.")
    parser.add_argument("output_dir", type=str,
                        help="Output directory for converted videos.")
    parser.add_argument("--delete", action='store_true',
                        help="Delete original files after conversion.")
    parser.add_argument("--ffmpeg_args", type=str, help="Additional arguments to pass to ffmpeg.",
                        default="-loglevel error -stats -c:v libsvtav1 -preset 4 -crf 28 -pix_fmt yuv420p10le -c:a libopus -b:a 64k")

    args = parser.parse_args()

    process_directory(args.input_dir, args.output_dir,
                      args.delete, args.ffmpeg_args)


if __name__ == "__main__":
    setup_logging()
    logging.info("Starting video conversion...")
    main()
    logging.info("Finished video conversion.")
