import os
from getfiles import get_all_files
def get_rename_names_preview(paths_list, new_base_name):
    if not paths_list:
        return []
    files = get_all_files(paths_list)
    preview_list = []
    for index, old_path in enumerate(files, start=1):
        folder_path, file_name = os.path.split(old_path)
        ext = os.path.splitext(file_name)[1]
        new_name = f"{new_base_name}_{index}{ext}"
        new_path = os.path.join(folder_path, new_name)
        preview_list.append((old_path, new_path, file_name, new_name))
    return preview_list
def execute_rename(rename_list):
    success_count = 0
    for old_path, new_path, _, _ in rename_list:
        try:
            os.rename(old_path, new_path)
            success_count += 1
        except OSError:
            pass
    return success_count