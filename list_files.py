import os
import json


def list_files_and_dirs(directory):
    structure = {}
    for root, dirs, files in os.walk(directory):
        relative_path = os.path.relpath(root, directory)
        structure[relative_path] = {
            "dirs": dirs,
            "files": files
        }
    return structure


def save_to_json(data, output_file):
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# 指定目标目录和输出文件路径
target_directory = "E:/2024-11-21"  # 修改为你的目标目录
output_file = "2024-11-21.json"

# 获取目录结构并保存
directory_structure = list_files_and_dirs(target_directory)
save_to_json(directory_structure, output_file)
print(f"文件和子文件夹的列表已保存到 {output_file}")
