from pathlib import Path
from video_converter import copy_metadata

copy_metadata(Path("D:\Temp\photos_conv\input_test\IMG_3475.MOV"),
              Path("test2.mp4"))
