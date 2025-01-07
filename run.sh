#!/bin/bash

export PATH="/home/tosaki/ffmpeg-psy/bin:$PATH"
export LD_LIBRARY_PATH="/home/tosaki/ffmpeg-psy/lib:$LD_LIBRARY_PATH"
export SVT_LOG=1
# nice -n 15 python video-converter.py
rm -r ~/temp_ffmpeg/*
nice -n 15 python video_converter.py /mnt/synology/inpersistent/convert/2412/input/ /mnt/synology/inpersistent/convert/2412/output/ --delete