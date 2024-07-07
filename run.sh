#!/bin/bash
export SVT_LOG=1
# nice -n 15 python video-converter.py
nice -n 15 python video-converter-new.py /mnt/synology/inpersistent/convert/2406/input/ /mnt/synology/inpersistent/convert/2406/output/ --delete