#!/bin/bash
export SVT_LOG=1
# nice -n 15 python video-converter.py
rm -r ~/temp_ffmpeg/*
nice -n 15 python video_converter.py /mnt/synology/inpersistent/convert/2406/input/ /mnt/synology/inpersistent/convert/2406/output/ --delete