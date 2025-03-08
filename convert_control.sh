#!/bin/bash
# 添加日志输出
LOG="/tmp/convert_control.log"
echo "$(date): Running $0 $1" >> $LOG

case $1 in
    start)
        /usr/bin/pkill -CONT -f "ffmpeg -nostdin -i /con" && echo "Process continued" >> $LOG || echo "Failed to continue process" >> $LOG
        ;;
    stop)
        /usr/bin/pkill -STOP -f "ffmpeg -nostdin -i /con" && echo "Process stopped" >> $LOG || echo "Failed to stop process" >> $LOG
        ;;
esac