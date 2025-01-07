#!/usr/bin/env python3

import os
import sys
import shutil
import subprocess

audio_extensions = {'.mp3', '.wav', '.flac', '.aac',
                    '.ogg', '.m4a', '.wma', '.aiff', '.alac'}
def is_audio_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in audio_extensions


def replace_suffix_with_opus(filename):
    # replace audio ext in last 8 characters with .opus
    if len(filename) == 0:
        part1, part2 = '', filename
    else:
        part1, part2 = filename[:-8], filename[-8:]
    for ext in audio_extensions:
        if ext in part2:
            return part1 + part2.replace(ext, '.opus')
        
    return filename


def main(input_dir, output_dir):
    if not os.path.exists(input_dir):
        print(f"Input directory '{input_dir}' does not exist.")
        sys.exit(1)

    for root, dirs, files in os.walk(input_dir):
        for file in files:
            input_file_path = os.path.join(root, file)
            # Compute relative path from input_dir to current file
            rel_path = os.path.relpath(input_file_path, input_dir)
            output_file_path = os.path.join(output_dir, rel_path)

            # Ensure the output directory exists
            os.makedirs(os.path.dirname(output_file_path), exist_ok=True)

            if is_audio_file(file):
                # Change output file extension to .opus
                base, _ = os.path.splitext(output_file_path)
                output_file_path = base + '.opus'

                # Build ffmpeg command
                cmd = [
                    'ffmpeg',
                    '-y',  # Overwrite output files without asking
                    '-i', input_file_path,
                    '-c:a', 'libopus',
                    '-b:a', '96k',  # Set bitrate to 96kbps
                    output_file_path
                ]

                print(f"Converting audio file: '{
                      input_file_path}' to '{output_file_path}'")
                try:
                    subprocess.run(cmd, check=True)
                except subprocess.CalledProcessError as e:
                    print(f"Error converting '{input_file_path}': {e}")
            else:
                # Copy non-audio file with adjusted suffix
                adjusted_output_file_path = replace_suffix_with_opus(
                    output_file_path)
                print(
                    f"Copying non-audio file: '{input_file_path}' to '{adjusted_output_file_path}'")
                try:
                    shutil.copy2(input_file_path, adjusted_output_file_path)
                except Exception as e:
                    print(f"Error copying '{input_file_path}': {e}")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python convert_audio.py <input_directory> <output_directory>")
        sys.exit(1)

    input_directory = sys.argv[1]
    output_directory = sys.argv[2]

    main(input_directory, output_directory)
