import os
import sys
import subprocess
from pathlib import Path
import argparse
from tqdm import tqdm
import json
import logging
from datetime import datetime
import shutil
import uuid
import time

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
    fields = json.loads(result)
    duration_seconds = float(fields["format"]["duration"])
    return duration_seconds


def cmd_runner(cmd):
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        result.check_returncode()
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running command {cmd}: {e.stderr}")
        return False
    except Exception as e:
        logging.error(f"Error running command {cmd}: {e}")
        return False


def copy_metadata(source_path, target_path):
    try:
        file_time = datetime.fromtimestamp(source_path.stat().st_atime)
        creation_time = datetime.fromtimestamp(source_path.stat().st_ctime)
        modification_time = datetime.fromtimestamp(source_path.stat().st_mtime)
        write_time = min(file_time, creation_time, modification_time)
        os.utime(target_path, (file_time.timestamp(), modification_time.timestamp()))
    except Exception as e:
        logging.error(f"Error copying metadata: {e}")
    try:
        exif_info = subprocess.check_output(['exiftool', '-j', source_path])
    except subprocess.CalledProcessError:
        exif_info = None

    def write_exif():
        try:
            subprocess.run(['exiftool', f'-DateTimeOriginal={write_time.strftime("%Y:%m:%d %H:%M:%S")}',
                            f'-CreateDate={write_time.strftime("%Y:%m:%d %H:%M:%S")}',
                            f'-ModifyDate={write_time.strftime("%Y:%m:%d %H:%M:%S")}',
                            '-overwrite_original', target_path], check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Error writing EXIF data: {e}")

    exif_info_json = {}
    if exif_info:
        try:
            subprocess.run(['exiftool', '-tagsFromFile', source_path,
                            '-all:all', '-overwrite_original', target_path], check=True)
            exif_info_json = json.loads(exif_info.decode())[0]
            if 'DateTimeOriginal' not in exif_info_json:
                cmd = ['exiftool', '-DateTimeOriginal=' + write_time.strftime('%Y:%m:%d %H:%M:%S'),
                       str(target_path), '-overwrite_original']
                assert cmd_runner(cmd)
        except subprocess.CalledProcessError as e:
            logging.error(f"Error copying EXIF data: {e}")
            write_exif()
    else:
        write_exif()
    if target_path.suffix.lower() in in_format and 'Creation Date' not in subprocess.run(['exiftool', '-QuickTime:CreationDate', str(source_path), '-m'], capture_output=True, text=True).stdout:
        def try_get_time(exiftime_list, exif_info_json, key):
            if key in exif_info_json:
                try:
                    if '+' in exif_info_json[key]:
                        format_str = '%Y:%m:%d %H:%M:%S%z'
                    else:
                        format_str = '%Y:%m:%d %H:%M:%S'
                    exiftime_list.append(datetime.strptime(exif_info_json[key], format_str))
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
        for i in range(len(exiftime)):
            if exiftime[i].tzinfo is None:
                exiftime[i] = exiftime[i].replace(tzinfo=datetime.now().astimezone().tzinfo)
        write_time = min(exiftime)
        cmd = ['exiftool', '-QuickTime:CreationDate=' + write_time.strftime('%Y:%m:%d %H:%M:%S%z'),
               str(target_path), '-overwrite_original']
        assert cmd_runner(cmd)
        if 'DateTimeOriginal' not in exif_info_json:
            cmd = ['exiftool', '-DateTimeOriginal=' + write_time.strftime('%Y:%m:%d %H:%M:%S'),
                   str(target_path), '-overwrite_original']
            assert cmd_runner(cmd)
    os.utime(target_path, (write_time.timestamp(), write_time.timestamp()))


def is_rotated_video_ffprobe(video_file):
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream_tags=rotate',
            '-of', 'default=nw=1:nk=1',
            str(video_file)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logging.error(f"Cannot get rotation info for video {video_file}")
            return False
        rotation = result.stdout.strip()
        if rotation == '':
            rotation = 0
        else:
            rotation = int(rotation)
        return rotation in [90, 270]
    except Exception as e:
        logging.error(f"Error checking video rotation: {e}")
        return False


def is_rotated_video_exiftool(video_file):
    import re
    try:
        cmd = [
            'exiftool',
            '-n',
            '-Rotation',
            str(video_file)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logging.error(f"Cannot get rotation info for video {video_file}")
            return False
        output = result.stdout.strip()
        rotation = 0
        if output:
            match = re.search(r'Rotation\s*:\s*(\d+)', output)
            if match:
                rotation = int(match.group(1))
        return rotation in [90, 270]
    except Exception as e:
        logging.error(f"Error checking video rotation: {e}")
        return False


def is_rotated_video(video_file):
    return is_rotated_video_ffprobe(video_file) or is_rotated_video_exiftool(video_file)


def convert_video(source_path, target_path, ffmpeg_args, max_resolution=None):
    scale_filter = ""
    size_factor = 1.0
    try:
        probe_result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
             'stream=width,height', '-of', 'csv=s=x:p=0', str(source_path)],
            capture_output=True, text=True
        )
        if probe_result.returncode != 0:
            logging.error(f"Failed to get video resolution for {source_path}")
            return False, size_factor
        width, height = map(int, probe_result.stdout.strip().split('x')[:2])
        resolution = width * height
        if max_resolution and resolution > max_resolution:
            if is_rotated_video(source_path):
                width, height = height, width
            scale_factor = (max_resolution / resolution) ** 0.5
            target_width = round(width * scale_factor)
            target_height = round(height * scale_factor)
            if target_width % 2 != 0:
                target_width += 1
            if target_height % 2 != 0:
                target_height += 1
            scale_filter = f"-vf scale={target_width}:{target_height}"
        else:
            scale_filter = ""
    except Exception as e:
        logging.error(f"Error getting video resolution: {e}")
    cmd = [
        'ffmpeg',
        '-i',
        str(source_path),
        *ffmpeg_args.split(),
        *scale_filter.split(),
        str(target_path)
    ]
    result = cmd_runner(cmd)
    if result:
        try:
            source_size = source_path.stat().st_size
            target_size = target_path.stat().st_size
            if target_size > 0:
                size_factor = source_size / target_size
            else:
                size_factor = 0
        except Exception as e:
            logging.error(f"Error calculating size factor: {e}")
            size_factor = 1.0  # Default to 1.0
        return True, size_factor
    return False, size_factor


def process_directory(input_dir, output_dir, delete_original, ffmpeg_args, ext='.mp4', max_resolution=3840*2160, all_files=None, temp_dir=None):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if temp_dir:
        temp_dir = Path(temp_dir)
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

    if all_files is None:
        all_files = [f for f in input_dir.rglob('*') if '@eaDir' not in str(f)]
    video_files = [f for f in all_files if f.suffix.lower() in in_format]
    for video_file in tqdm(video_files, desc="Converting", ncols=50):
        start_time = time.time()
        logging.info(f"Start converting {video_file}")
        relative_path = video_file.relative_to(input_dir)
        target_file = output_dir / relative_path
        target_file = target_file.with_suffix(ext)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        # If target file already exists, copy metadata and continue
        if target_file.exists():
            logging.info(f"Target file already exists: {target_file}")
            copy_metadata(video_file, target_file)
            continue

        # Prepare temporary input and output files
        if temp_dir:
            unique_id = uuid.uuid4().hex
            temp_input_file = temp_dir / (unique_id + '_input' + video_file.suffix)
            temp_output_file = temp_dir / (unique_id + '_output' + ext)
            # Copy source file to temp_dir
            try:
                shutil.copy2(video_file, temp_input_file)
                # logging.info(f"Copied {video_file} to temp dir {temp_input_file}")
            except Exception as e:
                logging.error(f"Failed to copy {video_file} to temp dir {temp_dir}: {e}")
                continue
        else:
            temp_input_file = video_file
            temp_output_file = target_file.with_name("ffmpeg_temp" + ext)
            # If temporary output file exists, remove it
            if temp_output_file.exists():
                os.remove(temp_output_file)

        source_file = temp_input_file

        try:
            source_duration = get_video_duration(str(source_file))
            convert_success, size_factor = convert_video(source_file, temp_output_file, ffmpeg_args, max_resolution)
            if convert_success:
                # Verify output duration
                target_duration = get_video_duration(str(temp_output_file))
                if (source_duration == 0 or abs(source_duration - target_duration) / source_duration > 0.05) and (source_duration - target_duration > 1):
                    logging.error(f"Duration mismatch: {source_duration} vs {target_duration}")
                    if temp_output_file.exists():
                        os.remove(temp_output_file)
                    continue
                # Move the converted file to the target location
                shutil.move(str(temp_output_file), str(target_file))
                copy_metadata(video_file, target_file)
                if delete_original:
                    os.remove(video_file)
                run_time = time.time() - start_time
                time_ratio = run_time / source_duration if source_duration > 0 else 0
                logging.info(f"Converted {video_file}")
                logging.info(f"Size factor (source/target): {size_factor:.4f}, Processing Time: {run_time:.2f}s, Time ratio: {time_ratio:.2f}x of real-time")
            else:
                # Conversion failed; remove temporary output file
                if temp_output_file.exists():
                    os.remove(temp_output_file)
                logging.error(f"Failed to convert {video_file}")
        except Exception as e:
            logging.error(f"Error processing {video_file}: {e}")
        finally:
            # Clean up temporary input file
            if temp_dir and temp_input_file.exists():
                os.remove(temp_input_file)


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
                        default="-loglevel error -stats -c:v libsvtav1 -preset 8 -crf 36 -pix_fmt yuv420p10le -svtav1-params film-grain=8 -svtav1-params adaptive-film-grain=1 -c:a libopus -b:a 64k")
    parser.add_argument("--max_resolution", type=int,
                        help="Maximum resolution (in pixels).")
    parser.add_argument("--temp_dir", type=str, help="Temporary directory for processing files.")
    args = parser.parse_args()
    process_directory(args.input_dir, args.output_dir,
                      args.delete, args.ffmpeg_args, max_resolution=args.max_resolution, temp_dir=args.temp_dir)


if __name__ == "__main__":
    setup_logging()
    logging.info("Starting video conversion...")
    main()
    logging.info("Finished video conversion.")