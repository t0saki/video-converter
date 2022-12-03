# -*- coding: UTF-8 -*-
# reference: https://www.stubbornhuang.com/1192/
# version 1.4
import configparser
import os
import shutil
import subprocess
import datetime
from enum import Enum
from tqdm import tqdm

# 对视频操作的枚举

in_format = ['.mp4', '.avi', '.mkv', '.flv', '.rmvb', '.wmv',
             '.mov', '.mpg', '.mpeg', '.m4v', '.3gp', '.f4v', '.webm', '.ts']
speed_present = "medium"

data_time = datetime.datetime.now().strftime('%m-%d-%H:%M:%S')
logs_name = data_time + "-logs.txt"


def get_video_duration(filename):
    import subprocess
    import json

    result = subprocess.check_output(
        ["ffprobe", "-v", "quiet", "-show_format", "-print_format", "json", filename])
    fields = json.loads(result)  # ['streams'][0]

    duration_seconds = float(fields["format"]["duration"])
    # fps = eval(fields['r_frame_rate'])
    return duration_seconds  # , fps


class FFmpegOperatorEnum(Enum):
    Modify_Video_Resolution = 0
    Modify_Video_BitRate = 1
    Modify_Video_FrameRate = 2


class FFmpegBatchConversionVideo:
    m_TotalConversionFiles = 0
    m_TotalFiles = 0
    m_SupportVideoFormat = in_format
    m_FFmpegOperatorEnum = None

    m_Video_Resolution = ''
    m_Video_CRF = ''
    m_Video_FrameRate = ''

    def __init__(self, videoformat=in_format, ffmpegOperatorEnum=FFmpegOperatorEnum.Modify_Video_BitRate):
        self.m_SupportVideoFormat = videoformat
        self.m_FFmpegOperatorEnum = ffmpegOperatorEnum
        pass

    def ConvertBatchVideos(self, inputPath, outputPath):

        try:

            if not os.path.isdir(outputPath):
                os.mkdir(outputPath)

            # count total files
            for root, dirs, files in os.walk(inputPath):
                for file in files:
                    if os.path.splitext(file)[1] in self.m_SupportVideoFormat:
                        self.m_TotalFiles += 1

            # for files in os.listdir(inputPath):
            for files in tqdm(os.listdir(inputPath)):  # 增加tqdm进度条
                input_name = os.path.join(inputPath, files)
                # change extension to .mkv
                final_name = os.path.join(
                    outputPath, os.path.splitext(files)[0] + '.mkv')
                output_name = os.path.join(outputPath, files)
                temp_name = os.path.join(outputPath, 'temp_of_ffmpeg.mkv')
                # remove previous temp file
                if os.path.exists(temp_name):
                    os.remove(temp_name)

                # detect exists
                if os.path.exists(final_name):
                    continue

                # 如果输入路径为文件
                if os.path.isfile(input_name):
                    dirPath = (os.path.abspath(os.path.dirname(output_name)))
                    input_duration = get_video_duration(input_name)
                    # 如果不存在输出文件夹则创建该文件夹
                    if not os.path.isdir(dirPath):
                        os.mkdir(dirPath)
                    # 判断输入视频的后缀名是否在支持的列表之中
                    # if os.path.split(input_name)[-1].lower() in self.m_SupportVideoFormat:
                    if '.'+input_name.split('.')[-1].lower() in self.m_SupportVideoFormat:
                        # 修改视频分辨率
                        if self.m_FFmpegOperatorEnum == FFmpegOperatorEnum.Modify_Video_Resolution:
                            self.ModifyVideoResolution(input_name, output_name)
                        # 修改视频码率
                        elif self.m_FFmpegOperatorEnum == FFmpegOperatorEnum.Modify_Video_BitRate:
                            self.ModifyVideoBitRate(input_name, temp_name)
                            temp_duration = get_video_duration(temp_name)
                            if abs(input_duration-temp_duration) < 8:
                                # move temp and remove input
                                shutil.move(temp_name, final_name)
                                os.remove(input_name)
                                # log to file
                                with open(logs_name, 'a') as f:
                                    f.write(
                                        'finished: ' + input_name + ' with ' + str(input_duration) + 's' + '\n')
                            else:
                                os.remove(temp_name)
                                # log
                                with open(logs_name, 'a') as f:
                                    f.write('failed: ' + input_name + '\n')

                        # 修改视频帧率
                        elif self.m_FFmpegOperatorEnum == FFmpegOperatorEnum.Modify_Video_FrameRate:
                            self.ModifyVideoFrameRate(input_name, output_name)
                        else:
                            pass

                # 如果输入路径为文件夹
                else:
                    # 如果输出文件夹不存在则创建文件夹
                    if not os.path.isdir(output_name):
                        os.mkdir(output_name)
                    # 递归
                    self.ConvertBatchVideos(input_name, output_name)

        except Exception as e:
            # print to logs
            with open(logs_name, 'a') as f:
                f.write(str(e) + ' logging at ' + data_time+'\n')

    def ModifyVideoResolution(self, videoin, videoout):
        t_ffmpegcmdline = 'ffmpeg -i "{}"  -vf scale={} -threads 4 "{}" -hide_banner'.format(
            videoin, self.m_Video_Resolution, videoout)
        returncode = subprocess.call(t_ffmpegcmdline)
        self.m_TotalConversionFiles += 1

    def ModifyVideoBitRate(self, videoin, videoout):
        # t_ffmpegcmdline = 'ffmpeg -i "{}"  -b:v {} -threads 4 "{}" -hide_banner'.format(
        #     videoin, self.m_Video_BitRate, videoout)
        t_ffmpegcmdline = 'ffmpeg -loglevel error -stats -i "{}" -c:v libx265 -x265-params log-level=error -preset {}  -crf {} -pix_fmt yuv420p10le -c:a libopus -b:a 64k "{}"'.format(
            videoin, speed_present, self.m_Video_CRF, videoout)
        # change shell title with filename
        os.system('xtitle ' + str(self.m_TotalConversionFiles) +
                  '/' + str(self.m_TotalFiles) + ' ' + videoin)
        # returncode = subprocess.call(t_ffmpegcmdline)
        returncode = subprocess.call(t_ffmpegcmdline, shell=True)
        self.m_TotalConversionFiles += 1

    def ModifyVideoFrameRate(self, videoin, videoout):
        t_ffmpegcmdline = 'ffmpeg -r {} -i "{}"  -threads 4 "{}" -hide_banner'.format(
            self.m_Video_FrameRate, videoin, videoout)
        returncode = subprocess.call(t_ffmpegcmdline)
        self.m_TotalConversionFiles += 1


if __name__ == '__main__':
    cp = configparser.RawConfigParser()
    configPath = os.path.join(os.path.dirname(
        __file__), r'video-converter.ini')
    cp.read(configPath, encoding='utf-8')
    inputDir = cp.get('Path', 'inputDir')
    outputDir = cp.get('Path', 'outputDir')

    # 记录转换总时间
    opeartion_start_time = datetime.datetime.now()

    # 批量修改视频帧率
    # ffmpegBatchConversionVideo = FFmpegBatchConversionVideo(['mp4','avi'],ffmpegOperatorEnum=FFmpegOperatorEnum.Modify_Video_FrameRate)
    # ffmpegBatchConversionVideo.m_Video_FrameRate = '60'
    # ffmpegBatchConversionVideo.ConvertBatchVideos(inputDir,outputDir)

    # 批量修改视频码率
    ffmpegBatchConversionVideo = FFmpegBatchConversionVideo(
        in_format, ffmpegOperatorEnum=FFmpegOperatorEnum.Modify_Video_BitRate)
    ffmpegBatchConversionVideo.m_Video_CRF = '25'
    ffmpegBatchConversionVideo.ConvertBatchVideos(inputDir, outputDir)

    # 批量修改视频分辨率
    # ffmpegBatchConversionVideo = FFmpegBatchConversionVideo(
    #     ['mp4', 'avi'], ffmpegOperatorEnum=FFmpegOperatorEnum.Modify_Video_Resolution)
    # ffmpegBatchConversionVideo.m_Video_Resolution = '64:64'
    # ffmpegBatchConversionVideo.ConvertBatchVideos(inputDir, outputDir)

    opeartion_end_time = datetime.datetime.now()
    opeartion_duration = opeartion_end_time - opeartion_start_time

    print('Conversion finished, total time: ' + str(opeartion_duration)) + 's\n' + 'Total files: ' + \
        str(ffmpegBatchConversionVideo.m_TotalFiles) + '\n' + 'Total conversion files: ' + \
        str(ffmpegBatchConversionVideo.m_TotalConversionFiles)
